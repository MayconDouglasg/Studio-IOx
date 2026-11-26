"""Learn from the editor's final Premiere XML: compare it with our decupagem and measure the style.
  python tools/edit_study.py <episode_dir> "<final.xml>" [sequence_name] [--edl edl_x.json] [--out folder]
Writes <episode>/study/{study.json, study.md, final_words.json, final_transcript.md}.
"""
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from decup import load, wav_path, read_wav  # noqa: E402
from decup_stage2 import speech_mask, HOP  # noqa: E402

_a = sys.argv[1:]
_opt = lambda k: _a[_a.index(k) + 1] if k in _a else None  # noqa: E731
_pos = [x for i, x in enumerate(_a) if not x.startswith("--") and (i == 0 or not _a[i - 1].startswith("--"))]
ep, xmlp = Path(_pos[0]), Path(_pos[1])
SEQ = _pos[2] if len(_pos) > 2 else "01_DECUPADO"
m = load(ep)
edl = json.loads(((ep / _opt("--edl")) if _opt("--edl") else ep / "edl.json").read_text(encoding="utf-8"))   # --edl: measure another cut
out = Path(_opt("--out")) if _opt("--out") else ep / "study"                                            # --out: keep study/ untouched
out.mkdir(exist_ok=True)

root = ET.parse(xmlp).getroot()
seq = next(s for s in root.iter("sequence") if s.findtext("name") == SEQ)
TB = int(seq.findtext("rate/timebase"))
FPS = TB * (1000 / 1001 if seq.findtext("rate/ntsc") == "TRUE" else 1)
SEQ_DUR = int(seq.findtext("duration")) / FPS


def rate_of(c):
    r = c.find("rate")
    tb = int(r.findtext("timebase"))
    return tb * (1000 / 1001 if r.findtext("ntsc") == "TRUE" else 1)


# file ids -> names (Premiere writes the full <file> once, then references by id)
fname = {}
for f in root.iter("file"):
    if f.get("id") and f.findtext("name"):
        fname[f.get("id")] = f.findtext("name")


def clips(kind, ti):
    tr = seq.find(f"media/{kind}").findall("track")[ti]
    res = []
    for c in tr.findall("clipitem"):
        name = c.findtext("name")
        s, e = int(c.findtext("start")), int(c.findtext("end"))
        if s < 0 or e < 0:                  # Premiere writes -1 next to transitions; position comes from in/out
            continue
        cin = int(c.findtext("in"))
        cr = rate_of(c)
        eff = [x.findtext("name") for x in c.iter("effect")]
        res.append({"name": name, "s": s / FPS, "e": e / FPS, "src": cin / cr, "on": c.findtext("enabled") != "FALSE",
                    "fx": [x for x in eff if x], "track": ti + 1})
    return res


ntv = len(seq.find("media/video").findall("track"))
V = {i + 1: clips("video", i) for i in range(ntv)}
A1 = clips("audio", 0)


import fnmatch  # noqa: E402
import studio  # noqa: E402
_DEC = studio.client_json(studio.client_of(ep)).get("decup", {})
_ROLES = {**_DEC.get("study_roles", {}), **_DEC.get("roles", {})}   # file-name patterns from the client's client.json


def role(name):
    n = (name or "").lower()
    for r, pats in _ROLES.items():
        if any(fnmatch.fnmatch(n, q.lower()) for q in pats):
            return r
    if n in ("camera ecra", "cam com ecra") or "ecra" in n or "ecrã" in n:
        return "tela"
    if "adjustment" in n:
        return "ajuste"
    if n == "graphic":
        return "grafico"
    return "outro"


# ---------------------------------------------------------------- what is on screen, frame by frame (top-most opaque)
step = 1 / FPS
T = np.arange(0, SEQ_DUR, step)
vis = np.array(["-"] * len(T), dtype=object)
overlays = []
for ti in sorted(V):                        # higher track wins
    for c in V[ti]:
        r = role(c["name"])
        if not c["on"]:
            continue
        if r in ("ajuste", "grafico"):
            overlays.append({**c, "role": r})
            continue
        vis[(T >= c["s"]) & (T < c["e"])] = r

segs = []
for i, r in enumerate(vis):
    if segs and segs[-1][0] == r:
        segs[-1][2] = T[i] + step
    else:
        segs.append([r, T[i], T[i] + step])
segs = [{"role": r, "s": round(a, 3), "e": round(b, 3), "d": round(b - a, 3)} for r, a, b in segs]
share = {}
for sg in segs:
    share[sg["role"]] = share.get(sg["role"], 0) + sg["d"]

# ---------------------------------------------------------------- speech mapping: final timeline <-> DJI source
sess_by_master = {s["master"]: s for s in m["sessions"]}
words_by_s = {s["id"]: json.loads((ep / "work" / "transcript" / f"s{s['id']}.json").read_text(encoding="utf-8"))["words"] for s in m["sessions"]}
final_ranges = []                           # (session, src_s, src_e, seq_s)
for c in V[1]:                              # V1 (DJI) carries explicit positions and the same cuts as A1
    if c["name"] in sess_by_master:
        sid = sess_by_master[c["name"]]["id"]
        final_ranges.append((sid, c["src"], c["src"] + (c["e"] - c["s"]), c["s"]))

final_words = []
for sid, a, b, ss in final_ranges:
    for w in words_by_s[sid]:
        mid = (w["s"] + w["e"]) / 2
        if a <= mid < b:
            final_words.append({"t": round(ss + (w["s"] - a), 3), "te": round(ss + (w["e"] - a), 3), "w": w["w"], "sess": sid, "src": w["s"]})
final_words.sort(key=lambda x: x["t"])


def in_ranges(sid, t, R):
    return any(r[0] == sid and r[1] <= t < r[2] for r in R)


mine = [(e["session"], k["s"], k["e"]) for e in edl for k in e["keep"]]
removed, restored = [], []
for sid, W in words_by_s.items():
    for w in W:
        mid = (w["s"] + w["e"]) / 2
        a, b = in_ranges(sid, mid, mine), in_ranges(sid, mid, final_ranges)
        if a and not b:
            removed.append((sid, w))
        if b and not a:
            restored.append((sid, w))


def group(ws, gap=1.2):
    out_ = []
    for sid, w in ws:
        if out_ and out_[-1]["sess"] == sid and w["s"] - out_[-1]["e"] < gap:
            out_[-1]["e"] = w["e"]
            out_[-1]["text"] += " " + w["w"]
            out_[-1]["n"] += 1
        else:
            out_.append({"sess": sid, "s": w["s"], "e": w["e"], "text": w["w"], "n": 1})
    return out_


rem_g, res_g = group(removed), group(restored)

# ---------------------------------------------------------------- cut padding + breaths in the editor's cut
pad_lead, pad_tail, inner_max, breath_in = [], [], [], 0
masks = {}
for sid, a, b, _ in final_ranges:
    if sid not in masks:
        s = m["sessions"][sid - 1]
        masks[sid] = speech_mask(read_wav(wav_path(ep, s["master"])), words_by_s[sid])
    sp, br, _ = masks[sid]
    seg = sp[int(a / HOP): int(b / HOP) + 1]
    if seg.any() and b - a > .3:
        on = np.where(seg)[0]
        pad_lead.append(on[0] * HOP)
        pad_tail.append((len(seg) - 1 - on[-1]) * HOP)
        g = np.diff(on) - 1
        inner_max.append((g.max() if len(g) else 0) * HOP)
    bseg = br[int(a / HOP): int(b / HOP) + 1] & ~sp[int(a / HOP): int(b / HOP) + 1]
    breath_in += int(np.sum(np.diff(np.concatenate([[0], bseg.astype(int), [0]])) == 1))

# ---------------------------------------------------------------- camera switching
word_starts = np.array([w["t"] for w in final_words])
sent_starts = np.array([w["t"] for i, w in enumerate(final_words)
                        if i == 0 or re.search(r"[.!?…,]$", final_words[i - 1]["w"]) or w["t"] - final_words[i - 1]["te"] > .4])


def near(arr, t):
    return float(np.min(np.abs(arr - t))) if len(arr) else 99


lat = [sg for sg in segs if sg["role"] == "lateral"]
fro = [sg for sg in segs if sg["role"] == "frontal"]
gaps_between_lat = [lat[i + 1]["s"] - lat[i]["e"] for i in range(len(lat) - 1)]
cuts_to_lat = [{"t": sg["s"], "to_word_start": round(near(word_starts, sg["s"]), 3), "to_sentence_start": round(near(sent_starts, sg["s"]), 3)} for sg in lat]
tela = [sg for sg in segs if sg["role"] == "tela"]
lat_inside_tela = sum(1 for L in lat for t in tela if L["s"] < t["e"] and L["e"] > t["s"])

stats = {
    "sequence_min": round(SEQ_DUR / 60, 2), "my_cut_min": round(sum(k["e"] - k["s"] for e in edl for k in e["keep"]) / 60, 2),
    "screen_share_s": {k: round(v, 1) for k, v in sorted(share.items(), key=lambda x: -x[1])},
    "lateral": {"count": len(lat), "dur_median": round(float(np.median([x["d"] for x in lat])), 2) if lat else 0,
                "dur_p10_p90": [round(float(np.percentile([x["d"] for x in lat], q)), 2) for q in (10, 90)] if lat else [],
                "gap_between_median": round(float(np.median(gaps_between_lat)), 1) if gaps_between_lat else 0,
                "gap_p10_p90": [round(float(np.percentile(gaps_between_lat, q)), 1) for q in (10, 90)] if gaps_between_lat else [],
                "cut_to_word_start_median_s": round(float(np.median([c["to_word_start"] for c in cuts_to_lat])), 3) if lat else 0,
                "on_sentence_start_pct": round(100 * np.mean([c["to_sentence_start"] < .35 for c in cuts_to_lat]), 1) if lat else 0,
                "inside_screen_parts": lat_inside_tela},
    "frontal_segment_median_s": round(float(np.median([x["d"] for x in fro])), 1) if fro else 0,
    "tela": {"count": len(tela), "total_s": round(sum(x["d"] for x in tela), 1)},
    "speech_removed_by_editor": {"groups": len(rem_g), "words": len(removed)},
    "speech_restored_by_editor": {"groups": len(res_g), "words": len(restored)},
    "editor_cut_padding_ms": {"lead_median": round(1000 * float(np.median(pad_lead))), "tail_median": round(1000 * float(np.median(pad_tail))),
                              "lead_p10_p90": [round(1000 * float(np.percentile(pad_lead, q))) for q in (10, 90)],
                              "tail_p10_p90": [round(1000 * float(np.percentile(pad_tail, q))) for q in (10, 90)],
                              "longest_inner_pause_median_ms": round(1000 * float(np.median(inner_max)))},
    "breath_islands_left_in_cut": breath_in,
    "audio_transitions_A1": len(seq.find("media/audio").findall("track")[0].findall("transitionitem")),
    "overlays": [{"role": o["role"], "track": o["track"], "s": round(o["s"], 2), "e": round(o["e"], 2), "fx": o["fx"][:6]} for o in overlays],
}
(out / "study.json").write_text(json.dumps({"stats": stats, "segments": segs, "removed": rem_g, "restored": res_g}, indent=1, ensure_ascii=False), encoding="utf-8")
(out / "final_words.json").write_text(json.dumps(final_words, ensure_ascii=False), encoding="utf-8")

# final transcript with timecodes (one line per sentence)
lines, cur = [], []
for i, w in enumerate(final_words):
    cur.append(w)
    end = re.search(r"[.!?…]$", w["w"]) or i + 1 == len(final_words) or final_words[i + 1]["t"] - w["te"] > .9
    if end:
        t = cur[0]["t"]
        lines.append(f"[{int(t // 60):02d}:{t % 60:05.2f}] " + " ".join(x["w"] for x in cur))
        cur = []
(out / "final_transcript.md").write_text("\n".join(lines), encoding="utf-8")
print(json.dumps({k: v for k, v in stats.items() if k != "overlays"}, indent=1, ensure_ascii=False))
print("overlays:", len(overlays), "| transcript lines:", len(lines))
