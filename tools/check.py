"""Objective defect gate: count what can be measured before any taste review. Report only, it never fixes anything.

  python tools/check.py decup  <episode> [xml] [--seq 01_DECUPADO] [--no-trans] [--force]
  python tools/check.py render <file.mov|mp4> [--episode dir]
  python tools/check.py frames <folder of frames | video> [--episode dir] [--every 1.0] [--no-palette]
  common: [--client slug | --client-json file] [--out dir]

Each prints one summary line + the worst defects (cheap to read) and writes `check_<stage>.json` plus its caches
and logs into `--out` (default `<episode>/work/check/`; without an episode `<input>.check/` beside the input).
Use `--out` on anything delivered or in a client folder you must not touch: the input is only read.
Exit code 1 = defects found, 0 = clean, 2 = usage / nothing to measure.
Only "0 defects" goes to the taste review (CLAUDE.md "Loop before you show me anything", step 0).

decup   timeline of the decupagem XML (gaps, overlaps, flash clips, duplicate ids, frames with no video, doubled
        audio, sequence size / fps and screen video state vs client.json), cut points where the voice still
        sounds (the `settle` measure), and a re-transcription of the kept audio of the sequence: the same phrase
        twice in a row (merged or surviving takes) and words cut across a join. A loud cut counts only when the
        re-transcription also hears a missing or low-confidence word there (`--no-trans` = level test alone).
render  ffprobe (codec, profile, size, fps vs the expected delivery), blackdetect, freezedetect, flash frames,
        loudness (ebur128 integrated LUFS vs target, true peak) and clipped samples.
frames  motion frames: text (glyphs drawn in a client colour) outside the title safe area, WCAG contrast of that
        text vs what is around it, and flat areas in colours that are not in client.json (nor a mix of two of
        them, nor a tint / shade). Pixel sampling only, no AI: glyphs under 1.2 % of the frame height (about
        13 px at 1080) and text in a colour outside the palette are not measured.

Thresholds: client.json "qa" (template has the neutral defaults); see QA below.
"""
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import studio  # noqa: E402

QA = {                                   # defaults; client.json "qa" overrides key by key
    "min_clip_frames": 4,                # an enabled clip shorter than this is a flash
    "lufs": -14.0, "lufs_tol": 1.0,      # integrated loudness target and tolerance (LU)
    "true_peak_db": -1.0,                # true peak ceiling (dBTP)
    "freeze_s": 3.0,                     # a frozen picture this long is a defect
    "black_s": 0.08,                     # black this long (outside a fade-out at the very end) is a defect
    "black_end_ok_s": 2.0,               # a black tail up to this long is a fade-out
    "delivery": {},                      # {"codec": "prores", "profile": "HQ", "size": [w, h], "fps": 29.97, "pix_fmt": ...}
    "safe_title": 0.90,                  # text stays inside this centred fraction of the frame
    "contrast_min": 4.5,                 # WCAG ratio for small text
    "contrast_large": 3.0,               # WCAG ratio for large text (glyph >= large_text_h of the frame height)
    "large_text_h": 0.025,
    "offpalette_min_area": 0.003,        # a flat area off the palette must cover this fraction of the frame to count
    "repeat_min_words": 3,               # the same n words twice in a row
    "word_cut_p": 0.7,                   # a word heard across a join / loud cut below this confidence = chopped
}
SHOW = 14                                # defect lines printed


def qa_cfg(cj):
    q = dict(QA)
    q.update({k: v for k, v in (cj.get("qa") or {}).items() if not k.startswith("_")})
    return q


def arg(args, flag, default=None):
    return args[args.index(flag) + 1] if flag in args else default


def tc(t):
    t = max(0.0, float(t))
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def find_episode(p):
    for d in [Path(p).resolve()] + list(Path(p).resolve().parents):
        if (d / "episode.json").exists() or (d / "manifest.json").exists():
            return d
    return None


def client_for(args, ep):
    """(slug, client.json merged over the template). cj["_own_colors"] = the colours the client's own file defines:
    the template's placeholder colours must never widen a client's palette."""
    if "--client-json" in args:                          # a test palette / thresholds without registering a client
        own = json.loads(Path(arg(args, "--client-json")).read_text(encoding="utf-8"))
        slug, cj = Path(arg(args, "--client-json")).name, studio._merge(studio.client_json("_none"), own)
    else:
        slug = arg(args, "--client") or (studio.client_of(ep) if ep else None)
        known = bool(slug) and studio.known_client(slug)
        cj = studio.client_json(slug if known else "_none")
        p = studio.client_dir(slug) / "client.json" if known else None
        own = json.loads(p.read_text(encoding="utf-8")) if p and p.exists() else cj   # no client: template defaults
    cj["_own_colors"] = own.get("colors") or {}
    return slug, cj


def workdir(args, ep, target):
    """Where reports, caches and logs go: --out, else <episode>/work/check, else <input>.check/ beside the input."""
    if "--out" in args:
        d = Path(arg(args, "--out")).resolve()
    elif ep:
        d = Path(ep) / "work" / "check"
    else:
        d = Path(target).with_name(Path(target).name + ".check")
    d.mkdir(parents=True, exist_ok=True)
    return d


def report(stage, target, wd, defects, info, extra=None):
    counts = {}
    for d in defects:
        counts[d["kind"]] = counts.get(d["kind"], 0) + 1
    out = {"stage": stage, "target": str(target), "defects_total": len(defects), "counts": counts, "info": info,
           "defects": defects}
    if extra:
        out.update(extra)
    p = Path(wd) / f"check_{stage}.json"
    p.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    head = ", ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1])) or "clean"
    print(f"check {stage}: {len(defects)} defects ({head})")
    for k, v in info.items():
        if not isinstance(v, (list, dict)):
            print(f"  {k}: {v}")
    for d in defects[:SHOW]:
        print(f"  [{d['kind']}] {d.get('at', '')} {d['msg']}")
    if len(defects) > SHOW:
        print(f"  ... {len(defects) - SHOW} more in the json")
    print(f"-> {p}")
    return 1 if defects else 0


# ====================================================================== decup
def parse_xmeml(path):
    """Sequences of an FCP7 xmeml: {name: {w, h, timebase, ntsc, video: [[clip]], audio: [[clip]]}} + clip ids."""
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    files = {}
    for f in root.iter("file"):
        if f.get("id") and f.find("name") is not None:
            files[f.get("id")] = {"name": f.findtext("name"), "path": f.findtext("pathurl") or ""}
    seqs = {}
    for s in root.iter("sequence"):
        name = s.findtext("name") or s.get("id")
        sc = s.find("media/video/format/samplecharacteristics")
        q = {"w": int(sc.findtext("width") or 0) if sc is not None else 0,
             "h": int(sc.findtext("height") or 0) if sc is not None else 0,
             "timebase": int(s.findtext("rate/timebase") or 30), "ntsc": (s.findtext("rate/ntsc") or "").upper() == "TRUE",
             "video": [], "audio": [], "ids": [c.get("id") for c in s.iter("clipitem") if c.get("id")]}
        for kind in ("video", "audio"):
            for tr in s.findall(f"media/{kind}/track"):
                clips = []
                for c in tr.findall("clipitem"):
                    fe = c.find("file")
                    fd = files.get(fe.get("id"), {}) if fe is not None else {}
                    clips.append({"id": c.get("id"), "name": c.findtext("name") or fd.get("name", ""), "path": fd.get("path", ""),
                                  "start": int(c.findtext("start")), "end": int(c.findtext("end")),
                                  "in": int(c.findtext("in") or 0), "out": int(c.findtext("out") or 0),
                                  "enabled": (c.findtext("enabled") or "TRUE").upper() == "TRUE"})
                q[kind].append(clips)
        seqs[name] = q
    return seqs


def _union(iv):
    out = []
    for a, b in sorted(iv):
        if out and a <= out[-1][1]:
            out[-1][1] = max(out[-1][1], b)
        else:
            out.append([a, b])
    return out


def timeline_checks(seq, cj, q, fps):
    import decup
    D = []
    roles = (cj.get("decup") or {}).get("roles")
    # duplicate ids inside the sequence (the same ids in the other sequences of the file are normal)
    seen, dup = set(), set()
    for i in seq["ids"]:
        (dup if i in seen else seen).add(i)
    for i in sorted(dup):
        D.append({"kind": "duplicate_id", "msg": f"clipitem id {i} used more than once"})
    # overlaps on every track, flash clips on enabled clips
    for kind in ("video", "audio"):
        for ti, tr in enumerate(seq[kind]):
            cs = sorted(tr, key=lambda c: c["start"])
            for a, b in zip(cs, cs[1:]):
                if b["start"] < a["end"]:
                    D.append({"kind": "overlap", "at": tc(b["start"] / fps), "msg": f"{kind[0].upper()}{ti + 1}: {a['id']} / {b['id']} overlap {a['end'] - b['start']} frames"})
            for c in cs:
                if c["enabled"] and c["end"] - c["start"] < q["min_clip_frames"]:
                    D.append({"kind": "flash_clip", "at": tc(c["start"] / fps), "msg": f"{kind[0].upper()}{ti + 1}: {c['id']} lasts {c['end'] - c['start']} frames"})
    seq_end = max([c["end"] for tr in seq["video"] + seq["audio"] for c in tr] or [0])
    # gaps on the first audio track (the voice): silence holes
    a1 = sorted(seq["audio"][0], key=lambda c: c["start"]) if seq["audio"] else []
    prev = 0
    for c in a1:
        if c["start"] > prev:
            D.append({"kind": "gap", "at": tc(prev / fps), "msg": f"A1: {c['start'] - prev} frames with no voice clip"})
        prev = max(prev, c["end"])
    # frames with no enabled video (a disabled piece with no camera under it = black)
    cov = _union([[c["start"], c["end"]] for tr in seq["video"] for c in tr if c["enabled"]])
    prev = 0
    for a, b in cov + [[seq_end, seq_end]]:
        if a > prev:
            D.append({"kind": "no_video", "at": tc(prev / fps), "msg": f"{a - prev} frames with no enabled video"})
        prev = max(prev, b)
    # doubled audio: two enabled audio tracks at the same time
    per = [_union([[c["start"], c["end"]] for c in tr if c["enabled"]]) for tr in seq["audio"]]
    for i in range(len(per)):
        for j in range(i + 1, len(per)):
            for a, b in per[i]:
                for x, y in per[j]:
                    if x < b and a < y:
                        D.append({"kind": "audio_doubled", "at": tc(max(a, x) / fps), "msg": f"A{i + 1} and A{j + 1} both on for {min(b, y) - max(a, x)} frames"})
    # screen recording state
    want = bool((cj.get("decup") or {}).get("screen_video_enabled", False))
    bad_v = [c for tr in seq["video"] for c in tr if decup.role_of(c["name"], roles) == "tela" and c["enabled"] != want]
    bad_a = [c for tr in seq["audio"] for c in tr if decup.role_of(c["name"], roles) == "tela" and c["enabled"]]
    if bad_v:
        D.append({"kind": "screen_state", "at": tc(bad_v[0]["start"] / fps), "msg": f"{len(bad_v)} screen video clips {'off' if want else 'on'} (client.json screen_video_enabled = {want})"})
    if bad_a:
        D.append({"kind": "screen_state", "at": tc(bad_a[0]["start"] / fps), "msg": f"{len(bad_a)} screen audio clips on (screen audio always stays off)"})
    # sequence format
    size = (cj.get("decup") or {}).get("sequence_size") or cj.get("frame") or [1920, 1080]
    if [seq["w"], seq["h"]] != list(size):
        D.append({"kind": "format", "msg": f"sequence {seq['w']}x{seq['h']}, client.json wants {size[0]}x{size[1]}"})
    want_fps = float(cj.get("fps") or 29.97)
    if abs(round(fps, 2) - want_fps) > 0.02:
        D.append({"kind": "format", "msg": f"sequence {fps:.3f} fps, client.json fps {want_fps}"})
    return D, a1, seq_end


def cut_voice_checks(ep, a1, cj, fps, wd):
    """Every in / out of the voice track must land where the voice has decayed (decup_stage2.settle level)."""
    import decup
    import decup_stage2 as d2
    settle = (cj.get("decup") or {}).get("settle", d2.SETTLE)
    if settle is None:
        return [], {"cut_points": "settle off in client.json"}
    m = decup.load(ep) if (ep / "manifest.json").exists() else {"sessions": []}
    sess_of = {s["master"]: s["id"] for s in m.get("sessions", [])}
    stats, D, n, margins, soft, dips = {}, [], 0, [], 0, 0

    def st(name, path):
        if name in stats:
            return stats[name]
        w = decup.wav_path(ep, name)
        if not w.exists():
            src = _url_path(path)
            if not src or not Path(src).exists():
                stats[name] = None
                return None
            w = wd / (Path(name).stem + ".wav")
            if not w.exists():
                decup.run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vn", "-ac", "1", "-ar", str(decup.SR), "-c:a", "pcm_s16le", str(w)])
        db = d2.level_db(decup.read_wav(w))
        floor = float(np.percentile(db, 10))
        words = []
        tp = ep / "work" / "transcript" / f"s{sess_of.get(name)}.json"
        if name in sess_of and tp.exists():
            words = json.loads(tp.read_text(encoding="utf-8"))["words"]
        inword = np.zeros(len(db), bool)
        for w_ in words:
            inword[int(w_["s"] / d2.HOP): int(w_["e"] / d2.HOP) + 1] = True
        speech = float(np.percentile(db[inword], 75)) if inword.any() else float(np.percentile(db[db > floor + 15], 75)) if (db > floor + 15).any() else floor + 30
        stats[name] = (db, floor + settle * (speech - floor), speech, floor + 0.38 * (speech - floor))   # 0.38 = speech_mask's speech threshold
        return stats[name]

    cs = [c for c in sorted(a1, key=lambda c: c["start"]) if c["enabled"]]
    for i, c in enumerate(cs):
        s = st(c["name"], c["path"])
        if s is None:
            continue
        db, lvl, speech, loud = s
        t_in, t_out = c["in"] / fps, c["out"] / fps
        prev, nxt = (cs[i - 1] if i else None), (cs[i + 1] if i + 1 < len(cs) else None)
        joined_in = prev is not None and prev["name"] == c["name"] and abs(prev["out"] - c["in"]) <= 1 and prev["end"] == c["start"]
        joined_out = nxt is not None and nxt["name"] == c["name"] and abs(c["out"] - nxt["in"]) <= 1 and c["end"] == nxt["start"]
        for t, edge, joined in ((t_in, "in", joined_in), (t_out, "out", joined_out)):
            if joined:
                continue
            k = int(round(t / d2.HOP))
            seg = db[k: k + 2] if edge == "in" else db[max(0, k - 2): k]
            if not len(seg):
                continue
            n += 1
            v = float(seg.max())
            margins.append(speech - v)
            soft += v > lvl
            if v > max(loud, speech - 20):                     # speech_mask's speech level and within 20 dB of the voice
                win = db[max(0, k - 8): k + 8]
                if v <= win.min() + 4 and v <= speech - 10:   # quietest point between two words of one breath: a tight
                    dips += 1                                  # join (polish / trim), not a chopped word
                    continue
                at = (c["start"] if edge == "in" else c["end"]) / fps
                D.append({"kind": "cut_in_voice", "at": tc(at), "t": round(at, 3), "msg": f"{edge} of {c['id']} only {speech - v:.0f} dB under the speech, not at a dip (settle wants {speech - lvl:.0f}+): a word is chopped"})
    info = {"cut_points": n, "cut_depth_median_db": round(float(np.median(margins)), 1) if margins else None,
            "cuts_above_settle_level": soft, "tight_joins_between_words": dips}
    return D, info


def _url_path(u):
    from urllib.parse import unquote
    if not u:
        return ""
    u = unquote(u)
    u = re.sub(r"^file://localhost/", "", u)
    u = re.sub(r"^file:///?", "", u)
    return u


def retranscribe(ep, a1, cj, fps, wd, force=False):
    """Kept voice of the sequence (A1, enabled clips, in timeline order) -> words in sequence time.
    Transcribed in windows of ~25 s split at joins (+2 s context each side), like the chunked trans: Whisper on
    one long file merges repeated phrases, which is exactly what this check must see."""
    import decup
    import decup_stage2 as d2
    cs = [c for c in sorted(a1, key=lambda c: c["start"]) if c["enabled"]]
    key = hashlib.sha1(json.dumps(["v2"] + [[c["name"], c["start"], c["end"], c["in"]] for c in cs]).encode()).hexdigest()[:16]
    cache = wd / "decup_words.json"
    if cache.exists() and not force:
        d = json.loads(cache.read_text(encoding="utf-8"))
        if d.get("key") == key:
            return d["words"], d["joins"]
    SR = decup.SR
    total = int(round(max(c["end"] for c in cs) / fps * SR)) + SR
    y = np.zeros(total, np.float32)
    wav = {}
    for c in cs:
        if c["name"] not in wav:
            w = decup.wav_path(ep, c["name"])
            if not w.exists():
                w = wd / (Path(c["name"]).stem + ".wav")
                if not w.exists():
                    decup.run(["ffmpeg", "-v", "error", "-y", "-i", _url_path(c["path"]), "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(w)])
            wav[c["name"]] = decup.read_wav(w)
        x = wav[c["name"]]
        a, n = int(round(c["in"] / fps * SR)), int(round((c["end"] - c["start"]) / fps * SR))
        p = int(round(c["start"] / fps * SR))
        seg = x[a: a + n]
        y[p: p + len(seg)] = seg
    joins = []
    for a, b in zip(cs, cs[1:]):
        if not (a["name"] == b["name"] and abs(a["out"] - b["in"]) <= 1 and a["end"] == b["start"]):
            joins.append(b["start"] / fps)
    dur = len(y) / SR
    bounds, last = [0.0], 0.0
    for j in joins:
        if j - last >= 25:
            bounds.append(j)
            last = j
    bounds.append(dur)
    d2._cuda_dlls()
    from faster_whisper import WhisperModel
    model = WhisperModel("large-v3", device="cuda", compute_type="float16")
    epj = studio.episode_json(ep)
    prompt = cj.get("transcribe_prompt", "") + (" " + ", ".join(epj.get("vocab", [])) + "." if epj.get("vocab") else "")
    lang = (cj.get("language") or "pt").split("-")[0]
    db = d2.level_db(y)
    voiced = db > float(np.percentile(db, 10)) + 12          # same voice mask as decup trans (chunks)
    words = []
    print(f"re-transcribing the kept audio ({dur / 60:.1f} min, {len(bounds) - 1} windows)", flush=True)
    for b0, b1 in zip(bounds, bounds[1:]):
        a0, a1_ = max(0.0, b0 - 2), min(dur, b1 + 2)
        res, _ = model.transcribe(y[int(a0 * SR): int(a1_ * SR)], language=lang, word_timestamps=True, vad_filter=False,
                                  condition_on_previous_text=False, initial_prompt=prompt, beam_size=5)
        ws = [{"s": round(a0 + w.start, 3), "e": round(a0 + w.end, 3), "w": w.word.strip(), "p": round(w.probability, 3)}
              for sg in res for w in sg.words]
        ws, _ = d2.align_words(ws, voiced, a0, a1_)             # Whisper puts words ~0.2 s early
        words += [w for w in ws if b0 <= (w["s"] + w["e"]) / 2 < b1]
    words.sort(key=lambda w: w["s"])
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"key": key, "joins": joins, "words": words}, ensure_ascii=False, indent=0), encoding="utf-8")
    return words, joins


STOP = {"a", "o", "as", "os", "e", "de", "do", "da", "dos", "das", "que", "em", "no", "na", "nos", "nas", "um", "uma",
        "eu", "tu", "ele", "se", "me", "te", "lhe", "por", "para", "pra", "com", "isto", "isso", "aqui", "ai", "e",
        "the", "to", "and", "of", "is", "it", "this", "that", "i", "you", "ok", "entao", "pronto", "tipo"}


def text_checks(words, joins, q):
    import decup_stage2 as d2
    D = []
    toks = []
    for i, w in enumerate(words):
        t = " ".join(d2.norm(w["w"]))
        if t:
            toks.append((t, i))
    T = [t for t, _ in toks]
    nmin, covered = int(q["repeat_min_words"]), -1
    for i in range(len(T)):
        if i <= covered:
            continue
        hit = None
        for n in range(10, nmin - 1, -1):
            a = T[i: i + n]
            if len(a) < n or sum(t not in STOP and t not in d2.REPEAT_OK for t in a) < 2:
                continue
            for j in range(i + n, min(len(T) - n + 1, i + n + 12)):
                if T[j: j + n] == a and words[toks[j][1]]["s"] - words[toks[i + n - 1][1]]["e"] <= 8:
                    hit = (n, j)
                    break
            if hit:
                break
        if hit:
            n, j = hit
            w0, w1 = words[toks[i][1]], words[toks[j][1]]
            D.append({"kind": "repeat", "at": tc(w0["s"]), "msg": f"\"{' '.join(T[i:i + n])}\" again at {tc(w1['s'])} (two takes survived or merged)"})
            covered = j + n - 1
    # a later phrase that restarts / redoes the one just before it
    ph = d2.phrases(words, gap=0.35)
    for a, b in zip(ph, ph[1:]):
        if len(a["toks"]) >= 4 and len(b["toks"]) >= 4 and d2.similar(a["toks"], b["toks"]) >= 0.75:
            if any(d["kind"] == "repeat" and abs(_sec(d["at"]) - a["s"]) < 3 for d in D):
                continue
            D.append({"kind": "retake", "at": tc(a["s"]), "msg": f"\"{a['text'][:60]}\" then \"{b['text'][:60]}\""})
    # words cut across a join: Whisper's word times are +/- 0.1-0.2 s, so a word it heard with high confidence across
    # a tight join is whole; only a low-confidence one is a chopped or glued word
    whole = 0
    for J in joins:
        for w in words:
            if w["s"] > J + 1:
                break
            if w["s"] < J - 0.1 and w["e"] > J + 0.1:
                if w["p"] >= q["word_cut_p"]:
                    whole += 1
                    continue
                D.append({"kind": "word_cut", "at": tc(J), "msg": f"\"{w['w']}\" spans the join (p {w['p']:.2f}): a word cut in half or two glued"})
    return D, whole


def confirm_cuts(D, words, q):
    """A cut that the level test calls loud is a defect only when the re-transcription also hears trouble there:
    the word at that edge is missing or low-confidence. A tight join in connected speech (no dip between two
    words) is loud but heard clean. Returns (kept defects, demoted count)."""
    keep, demoted = [], 0
    for d in D:
        if d["kind"] != "cut_in_voice":
            keep.append(d)
            continue
        t = d["t"]
        near = [w for w in words if w["s"] - 0.3 <= t <= w["e"] + 0.3]
        if near and min(w["p"] for w in near) >= q["word_cut_p"]:
            demoted += 1
            continue
        d["msg"] += " (re-transcription: " + (", ".join(f"\"{w['w']}\" p {w['p']:.2f}" for w in near) or "no word heard") + ")"
        keep.append(d)
    return keep, demoted


def _sec(s):
    m, x = s.split(":")
    return int(m) * 60 + float(x)


def cmd_decup(args):
    ep = Path(args[0]).resolve()
    xmlp = Path(args[1]) if len(args) > 1 and not args[1].startswith("--") else None
    if xmlp is None:
        m = json.loads((ep / "manifest.json").read_text(encoding="utf-8")) if (ep / "manifest.json").exists() else {}
        cand = ep / "premiere" / f"{m.get('episode', ep.name)}_decupagem.xml"
        xmlp = cand if cand.exists() else max((ep / "premiere").glob("*decupagem*.xml"), key=lambda p: p.stat().st_mtime)
    slug, cj = client_for(args, ep)
    q = qa_cfg(cj)
    seqs = parse_xmeml(xmlp)
    name = arg(args, "--seq", "01_DECUPADO")
    if name not in seqs:
        name = next(iter(seqs))
    seq = seqs[name]
    fps = seq["timebase"] * (1000 / 1001 if seq["ntsc"] else 1)
    D, a1, seq_end = timeline_checks(seq, cj, q, fps)
    info = {"xml": xmlp.name, "sequence": name, "client": slug, "length": tc(seq_end / fps),
            "clips_voice": sum(c["enabled"] for c in a1)}
    wd = workdir(args, ep, xmlp)
    d2, i2 = cut_voice_checks(ep, a1, cj, fps, wd)
    info.update(i2)
    if "--no-trans" not in args and a1:
        words, joins = retranscribe(ep, a1, cj, fps, wd, force="--force" in args)
        d2, info["loud_cuts_heard_clean"] = confirm_cuts(d2, words, q)
        d3, info["joins_inside_a_word_heard_whole"] = text_checks(words, joins, q)
        D += d3
        info["words_heard"] = len(words)
        info["joins"] = len(joins)
    else:
        info["cut_points_note"] = "level test only (--no-trans): a tight join in connected speech also reads as loud"
    D += d2
    D.sort(key=lambda d: _sec(d["at"]) if d.get("at") else -1)
    return report("decup", xmlp, wd, D, info)


# ====================================================================== render
def ffprobe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(p)],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return json.loads(r.stdout or "{}")


def _rate(s):
    a, b = (s or "0/1").split("/")
    return float(a) / float(b or 1) if float(b or 1) else 0.0


def cmd_render(args):
    f = Path(args[0]).resolve()
    ep = Path(arg(args, "--episode")).resolve() if "--episode" in args else find_episode(f)
    slug, cj = client_for(args, ep)
    q = qa_cfg(cj)
    wd = workdir(args, ep, f)
    pr = ffprobe(f)
    vs = next((s for s in pr.get("streams", []) if s["codec_type"] == "video"), None)
    as_ = next((s for s in pr.get("streams", []) if s["codec_type"] == "audio"), None)
    dur = float(pr.get("format", {}).get("duration", 0))
    D = []
    if vs is None:
        return report("render", f, wd, [{"kind": "format", "msg": "no video stream"}], {"client": slug, "file": f.name})
    fps = _rate(vs.get("r_frame_rate"))
    deliv = dict(q.get("delivery") or {})
    size = deliv.get("size") or cj.get("frame")          # the Premiere sequence size is not the delivery size
    want_fps = deliv.get("fps") or cj.get("fps")
    info = {"client": slug, "file": f.name, "length": tc(dur),
            "video": f"{vs.get('codec_name')} {vs.get('profile', '')} {vs['width']}x{vs['height']} {fps:.3f} fps {vs.get('pix_fmt')}",
            "audio": f"{as_.get('codec_name')} {as_.get('sample_rate')} Hz {as_.get('channels')} ch" if as_ else "none"}
    if size and [vs["width"], vs["height"]] != list(size):
        D.append({"kind": "format", "msg": f"{vs['width']}x{vs['height']}, expected {size[0]}x{size[1]}"})
    if want_fps and abs(fps - float(want_fps)) > 0.02:
        D.append({"kind": "format", "msg": f"{fps:.3f} fps, expected {want_fps}"})
    for k, have in (("codec", vs.get("codec_name", "")), ("profile", vs.get("profile", "")), ("pix_fmt", vs.get("pix_fmt", ""))):
        if deliv.get(k) and str(deliv[k]).lower() not in str(have).lower():
            D.append({"kind": "format", "msg": f"{k} {have}, expected {deliv[k]}"})
    if as_ is None:
        D.append({"kind": "format", "msg": "no audio stream"})
    # --- video pass: black / freeze on a small copy, flash frames on 64x36 grey
    log = wd / "render_ffmpeg.txt"
    fc = (f"[0:v]scale=320:-2,split=2[x][y];[x]blackdetect=d={q['black_s']}:pix_th=0.10,"
          f"freezedetect=n=-50dB:d={q['freeze_s']},nullsink;[y]scale=64:36,format=gray[g]")
    print(f"decoding video ({tc(dur)})...", flush=True)
    with open(log, "w", encoding="utf-8", errors="replace") as lf:
        pv = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostats", "-i", str(f), "-filter_complex", fc, "-map", "[g]",
                               "-an", "-f", "rawvideo", "pipe:1"], stdout=subprocess.PIPE, stderr=lf)
        g = np.frombuffer(pv.stdout.read(), np.uint8)
        pv.wait()
    g = g[: len(g) // 2304 * 2304].reshape(-1, 36, 64).astype(np.float32)
    txt = log.read_text(encoding="utf-8", errors="replace")
    blacks = [(float(a), float(b)) for a, b in re.findall(r"black_start:([\d.]+) black_end:([\d.]+)", txt)]
    fz_s = [float(x) for x in re.findall(r"freeze_start: ([\d.]+)", txt)]
    fz_e = [float(x) for x in re.findall(r"freeze_end: ([\d.]+)", txt)]
    mean = g.mean(axis=(1, 2)) if len(g) else np.zeros(0)
    fades = 0
    for a, b in blacks:
        if b >= dur - 0.1 and b - a <= q["black_end_ok_s"]:
            continue
        i = int(round(a * fps))
        if a >= 0.05 and i >= 8 and mean[i - 8] > 1.5 * mean[i - 2] + 4 and mean[i - 8] > mean[i - 5] > mean[i - 2]:
            fades += 1                                         # a dip to black that fades out first: an edit choice
            continue
        D.append({"kind": "black", "at": tc(a), "msg": f"black for {b - a:.2f} s" + (" at frame 0 (never open on an empty frame)" if a < 0.05 else " after a hard cut")})
    info["fades_to_black"] = fades
    # freezedetect averages the frame, so a talking bubble over a still screen reads as frozen: a stuck picture
    # also leaves every pixel of the 64x36 copy unchanged (max diff < 3 levels on 95 % of the frames)
    still = 0
    for i, a in enumerate(fz_s):
        b = fz_e[i] if i < len(fz_e) else dur
        seg = g[int(a * fps): int(b * fps) + 1]
        if len(seg) > 2 and np.mean(np.abs(np.diff(seg, axis=0)).max(axis=(1, 2)) < 3) < 0.95:
            still += 1
            continue
        D.append({"kind": "freeze", "at": tc(a), "msg": f"frozen picture for {b - a:.1f} s"})
    flashes = 0
    if len(g) > 3:
        d1 = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2))              # d1[i] = |g[i+1] - g[i]|
        for i in range(1, len(g) - 2):
            for L in (1, 2):                                            # 1- or 2-frame flash: i..i+L-1 differ from both sides
                if i + L >= len(g):
                    continue
                around = np.abs(g[i + L] - g[i - 1]).mean()
                if d1[i - 1] > 25 and d1[i + L - 1] > 25 and around < 8:
                    flashes += 1
                    D.append({"kind": "flash_frame", "at": tc(i / fps), "msg": f"{L} frame(s) unlike both neighbours (diff {d1[i - 1]:.0f})"})
                    break
    info["black_segments"] = len(blacks)
    info["still_stretches_with_motion"] = still                 # mostly static (a screen) but something moves: content
    # --- audio pass: loudness + clipped samples
    if as_:
        print("measuring loudness...", flush=True)
        pa = subprocess.Popen(["ffmpeg", "-hide_banner", "-nostats", "-i", str(f), "-vn", "-af", "ebur128=peak=true:framelog=quiet",
                               "-f", "f32le", "-ac", str(as_.get("channels", 2)), "pipe:1"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        import threading
        err = []
        th = threading.Thread(target=lambda: err.append(pa.stderr.read().decode("utf-8", "replace")))
        th.start()
        clip_runs, rest = 0, b""
        while True:
            b = pa.stdout.read(1 << 22)
            if not b:
                break
            b = rest + b
            k = len(b) // 4 * 4
            rest = b[k:]
            hot = (np.abs(np.frombuffer(b[:k], np.float32)) >= 0.999).astype(np.int8)   # interleaved channels: a run
            dd = np.diff(np.concatenate([[0], hot, [0]]))                               # of 3+ hot values = clipped
            st_, en_ = np.where(dd == 1)[0], np.where(dd == -1)[0]
            clip_runs += int(np.sum((en_ - st_) >= 3))
        pa.wait()
        th.join()
        e = err[0] if err else ""
        mI = re.findall(r"I:\s+(-?[\d.]+) LUFS", e)
        mTP = re.findall(r"True peak:\s+Peak:\s+(-?[\d.inf]+) dBFS", e)
        I = float(mI[-1]) if mI else None
        TP = float(mTP[-1]) if mTP and mTP[-1] not in ("-inf", "inf") else None
        info["loudness"] = f"{I} LUFS, true peak {TP} dBTP (target {q['lufs']} LUFS, ceiling {q['true_peak_db']} dBTP)"
        if I is not None and abs(I - q["lufs"]) > q["lufs_tol"]:
            D.append({"kind": "loudness", "msg": f"integrated {I:.1f} LUFS, target {q['lufs']} +/- {q['lufs_tol']}"})
        if TP is not None and TP > q["true_peak_db"]:
            D.append({"kind": "true_peak", "msg": f"true peak {TP:.1f} dBTP > {q['true_peak_db']}"})
        if clip_runs:
            D.append({"kind": "clipping", "msg": f"{clip_runs} runs of 3+ samples at full scale"})
    D.sort(key=lambda d: _sec(d["at"]) if d.get("at") else -1)
    return report("render", f, wd, D, info)


# ====================================================================== frames
def palette(cj, ep):
    """client.json colours (+ the episode's partner colours, e.g. a sponsor's brand) as an N x 3 array."""
    hexes = {}

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if not str(k).startswith("_"):
                    walk(v, f"{path}.{k}" if path else str(k))
        elif isinstance(o, str) and re.fullmatch(r"#[0-9a-fA-F]{6}", o.strip()):
            hexes[path] = o.strip()
    walk(cj.get("_own_colors", cj.get("colors")) or {})
    if ep:
        walk({"episode": studio.episode_json(ep)})
    names = list(hexes)
    return names, np.array([[int(h[i:i + 2], 16) for i in (1, 3, 5)] for h in hexes.values()], np.float32)


def _lum(rgb):
    c = np.asarray(rgb, np.float64) / 255
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def wcag(a, b):
    la, lb = _lum(a), _lum(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


def _lossy(vs):
    """Chroma-subsampled video (4:2:0 / 4:2:2 H.264, HEVC...) smears thin coloured strokes off the exact token."""
    return bool(re.match(r"(yuvj?4(20|22|11)|nv12|nv21)", vs.get("pix_fmt", "")))


def read_frames(src, every):
    """(label, HxWx4 uint8, lossy) for every image in a folder or one frame per `every` s of a video; at most 1920 wide."""
    src = Path(src)
    exts = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp"}
    if src.is_dir():
        for p in sorted(x for x in src.iterdir() if x.suffix.lower() in exts):
            yield p.name, _decode(p, None), False
        return
    pr = ffprobe(src)
    vs = next(s for s in pr["streams"] if s["codec_type"] == "video")
    w, h = vs["width"], vs["height"]
    if w > 1920:
        w, h = 1920, int(round(h * 1920 / w / 2) * 2)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(src), "-vf", f"fps=1/{every},scale={w}:{h}", "-pix_fmt", "rgba",
                        "-f", "rawvideo", "pipe:1"], capture_output=True)
    a = np.frombuffer(r.stdout, np.uint8)
    for i in range(len(a) // (w * h * 4)):
        yield f"{tc(i * every)}", a[i * w * h * 4:(i + 1) * w * h * 4].reshape(h, w, 4), _lossy(vs)


def _decode(p, _):
    pr = ffprobe(p)
    vs = next(s for s in pr["streams"] if s["codec_type"] == "video")
    w, h = vs["width"], vs["height"]
    if w > 1920:
        w, h = 1920, int(round(h * 1920 / w / 2) * 2)
    r = subprocess.run(["ffmpeg", "-v", "error", "-i", str(p), "-vf", f"scale={w}:{h}", "-frames:v", "1", "-pix_fmt", "rgba",
                       "-f", "rawvideo", "pipe:1"], capture_output=True)
    return np.frombuffer(r.stdout, np.uint8)[: w * h * 4].reshape(h, w, 4)


def _seg_dist(X, P):
    """Distance of every colour in X (n x 3) to the closest token, mix of two tokens, or tint / shade of a token."""
    ends = list(P) + [np.array([255, 255, 255], np.float32), np.array([0, 0, 0], np.float32)]
    best = np.full(len(X), 1e9, np.float32)
    for i in range(len(P)):
        for j in range(i + 1, len(ends)):
            a, b = P[i], ends[j]
            ab = b - a
            t = np.clip(((X - a) @ ab) / max(float(ab @ ab), 1e-6), 0, 1)
            d = np.linalg.norm(X - (a + t[:, None] * ab), axis=1)
            best = np.minimum(best, d)
    return best


def frame_checks(img, P, names, q, check_palette=True, lossy=False):
    from scipy import ndimage as ndi
    H, W = img.shape[:2]
    rgb, alpha = img[..., :3].astype(np.float32), img[..., 3] > 127
    found, D = [], []
    mx, my = W * (1 - q["safe_title"]) / 2, H * (1 - q["safe_title"]) / 2
    for ti, tok in enumerate(P):
        dist = np.abs(rgb - tok).max(axis=2)
        near = (dist <= 24) & alpha
        if near.sum() < 30:
            continue
        exact = dist <= (8 if lossy else 3)                    # rendered text is exactly the token; footage is noisy
        lab, n = ndi.label(near, structure=np.ones((3, 3)))
        if not n:
            continue
        objs = ndi.find_objects(lab)
        area = np.bincount(lab.ravel(), minlength=n + 1)
        ex = np.bincount(lab.ravel(), weights=exact.ravel(), minlength=n + 1)
        for k, sl in enumerate(objs, 1):
            bh, bw = sl[0].stop - sl[0].start, sl[1].stop - sl[1].start
            fill = area[k] / (bh * bw)
            if not (H * 0.012 <= bh <= H * 0.2 and bw <= W * 0.35 and 0.12 <= fill <= 0.8 and area[k] >= 25 and ex[k] / area[k] >= 0.5):
                continue
            pad = max(4, bh // 3)
            y0, y1 = max(0, sl[0].start - pad), min(H, sl[0].stop + pad)
            x0, x1 = max(0, sl[1].start - pad), min(W, sl[1].stop + pad)
            comp = lab[y0:y1, x0:x1] == k
            ring = ndi.binary_dilation(comp, iterations=pad) & ~ndi.binary_dilation(comp, iterations=2)
            ring &= ~near[y0:y1, x0:x1] & alpha[y0:y1, x0:x1]
            if ring.sum() < 20:
                continue                                       # glyph inside a same-colour area or over alpha: not text
            bg = np.median(rgb[y0:y1, x0:x1][ring], axis=0)
            ratio = wcag(tok, bg)
            if ratio < 1.6:
                continue                                       # no edge against its surroundings: footage, not text
            found.append({"tok": names[ti], "box": [int(sl[1].start), int(sl[0].start), int(bw), int(bh)], "ratio": round(float(ratio), 2),
                          "bg": "#%02X%02X%02X" % tuple(int(v) for v in bg)})
    # text comes in lines: keep a glyph only when another glyph of the same colour, of similar height, sits beside it
    # on the same line (a lone blob of a client colour in footage is not text)
    def _mate(a, b):
        (x1, y1, w1, h1), (x2, y2, w2, h2) = a["box"], b["box"]
        hm = max(h1, h2)
        gap = max(x2 - (x1 + w1), x1 - (x2 + w2))
        return a["tok"] == b["tok"] and abs(h1 - h2) <= 0.45 * hm and abs((y1 + h1 / 2) - (y2 + h2 / 2)) <= 0.5 * hm and gap <= 1.5 * hm
    found = [a for i, a in enumerate(found) if any(_mate(a, b) for j, b in enumerate(found) if j != i)]
    for g in found:
        x, y, w, h = g["box"]
        if x < mx or y < my or x + w > W - mx or y + h > H - my:
            D.append({"kind": "outside_safe", "msg": f"{g['tok']} glyph at {x},{y} {w}x{h} outside the title safe area ({q['safe_title']:.0%})"})
        need = q["contrast_large"] if h >= q["large_text_h"] * H else q["contrast_min"]
        if g["ratio"] < need:
            D.append({"kind": "contrast", "msg": f"{g['tok']} on {g['bg']} = {g['ratio']}:1 (needs {need}) at {x},{y} {w}x{h}"})
    if check_palette:
        f = rgb
        m1 = ndi.uniform_filter(f, size=(7, 7, 1))
        m2 = ndi.uniform_filter(f * f, size=(7, 7, 1))
        flat = (np.sqrt(np.maximum(m2 - m1 * m1, 0)).max(axis=2) < 0.75) & alpha   # a drawn fill is exactly uniform
        if flat.any():
            ys, xs = np.nonzero(flat)
            cols = rgb[ys, xs]
            q8 = (cols // 4).astype(np.int32)
            keys = q8[:, 0] * 4096 + q8[:, 1] * 64 + q8[:, 2]
            uk, inv = np.unique(keys, return_inverse=True)
            centers = np.stack([(uk // 4096) * 4 + 2, (uk // 64 % 64) * 4 + 2, (uk % 64) * 4 + 2], 1).astype(np.float32)
            off_k = _seg_dist(centers, P) > 18
            off = np.zeros((H, W), bool)
            off[ys, xs] = off_k[inv]
            lab, n = ndi.label(off, structure=np.ones((3, 3)))
            if n:
                area = np.bincount(lab.ravel())[1:]
                objs = ndi.find_objects(lab)
                for k in np.where(area >= q["offpalette_min_area"] * H * W)[0] + 1:
                    px = rgb[lab == k]
                    if (np.percentile(px, 95, axis=0) - np.percentile(px, 5, axis=0)).max() > 4:
                        continue                               # a smooth gradient (a wall, a sky in footage), not a drawn fill
                    c = np.median(px, axis=0)
                    yy, xx = objs[k - 1]
                    D.append({"kind": "off_palette", "msg": f"flat #{int(c[0]):02X}{int(c[1]):02X}{int(c[2]):02X} over {area[k - 1] / (H * W):.1%} of the frame at {xx.start},{yy.start}: not a client.json colour nor a mix of two"})
    return D, found


def cmd_frames(args):
    src = Path(args[0]).resolve()
    ep = Path(arg(args, "--episode")).resolve() if "--episode" in args else find_episode(src)
    slug, cj = client_for(args, ep)
    q = qa_cfg(cj)
    names, P = palette(cj, ep)
    if not len(P):
        print("client.json has no colours: nothing to measure against")
        return 2
    D, n, glyphs, worst = [], 0, 0, None
    for label, img, lossy in read_frames(src, float(arg(args, "--every", 1.0))):
        n += 1
        d, found = frame_checks(img, P, names, q, check_palette="--no-palette" not in args, lossy=lossy)
        glyphs += len(found)
        for x in d:
            x["at"] = label
        D += d
        for g in found:
            if worst is None or g["ratio"] < worst[0]:
                worst = (g["ratio"], label, g["tok"], g["bg"])
    info = {"client": slug, "frames": n, "palette": len(P), "glyphs_measured": glyphs,
            "lowest_contrast": f"{worst[0]}:1 ({worst[2]} on {worst[3]}, {worst[1]})" if worst else None}
    # one line per frame and kind is enough for Claude to know where to zoom
    grouped = {}
    for d in D:
        grouped.setdefault((d["at"], d["kind"]), []).append(d)
    D2 = [dict(v[0], msg=v[0]["msg"] + (f" (+{len(v) - 1} more)" if len(v) > 1 else "")) for v in grouped.values()]
    return report("frames", src, workdir(args, ep, src), D2, info, {"all": D})


def main(a):
    if not a or a[0] not in ("decup", "render", "frames") or len(a) < 2:
        print(__doc__)
        return 2
    return {"decup": cmd_decup, "render": cmd_render, "frames": cmd_frames}[a[0]](a[1:])


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
