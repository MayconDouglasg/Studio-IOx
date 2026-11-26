"""Imagens de apoio (b-roll): find supporting footage/photos for the moments of an edited video, download the
chosen ones into a folder with credits, and write one marker per moment into a NEW copy of the Premiere XML.
The editor places the clips. All heavy work is local; Claude reads only the transcript, the script and numbers.

  python tools/apoio.py fontes [<episode>]                      which sources are configured on this PC (no network)
  python tools/apoio.py chaves [<episode>]                      create the API keys file if missing, show where it is
  python tools/apoio.py palavras <episode> --xml "<final.xml>" [--seq <name>] [--video <ref.mp4>] [--name <video>]
        transcribe the final cut on the final timeline (audio rebuilt from the XML, or the reference mp4)
        -> APOIO/<video>/_work/{words.json, transcript.md, roteiro.txt, source.json}
  python tools/apoio.py checar <episode> [--name <video>]       resolve APOIO/<video>/momentos.json (written by Claude)
  python tools/apoio.py buscar <episode> [--name <video>] [--sources local,magnific,pexels,pixabay] [--per 4]
                               [--local-dir <folder>] [--clip] [--dry] [--ids 3,4]   (--ids: only these, keep the rest)
        search every moment, source by source in the client's order -> _work/candidates.json + _work/folha_*.jpg
  python tools/apoio.py baixar <episode> [--name <video>]       download the picks -> clips, CREDITOS.md, manifest.json
  python tools/apoio.py marcas <episode> [--name <video>] [--xml-out <file.xml>]
        new XML copy with one marker per moment (never overwrites: adds _v2, _v3 ...)
Every command takes --out <folder> instead of <episode>/APOIO/<video> (tests: nothing is written in the episode).

Keys (never in git), first found wins: environment MAGNIFIC_API_KEY / PEXELS_API_KEY / PIXABAY_API_KEY,
  then the user's keys file ~/.motion-studio/chaves.json (`python tools/apoio.py chaves` creates it),
  then studio.config.json "keys": {"magnific": "...", "pexels": "...", "pixabay": "...", "magnific_daily": 100}
Client settings: client.json "apoio" (see clients/_template/client.json); STYLE.md may say more.
"""
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio  # noqa: E402

SR = 16000
UA = {"User-Agent": "motion-studio/1.0"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".mxf", ".avi", ".mkv", ".webm"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
CAMERA_TOKENS = {"img", "dji", "dsc", "mvi", "gopr", "gp", "pxl", "vid", "mov", "clip", "final", "copy", "copia"}
ALL_SOURCES = ["local", "magnific", "pexels", "pixabay", "ia"]
DEFAULTS = {"sources": ALL_SOURCES, "local_dirs": ["APOIO", "acervo", "broll"], "prefer": "video",
            "min_gap_s": 4, "max_per_min": 6, "clip_s": [2, 5], "lang": "pt",
            "regiao": {"en": "", "pt": ""}, "regional_padrao": False}
LICENSE = {
    "local": ("material do cliente", ""),
    "pexels": ("Pexels License (uso livre, atribuição apreciada)", "https://www.pexels.com/license/"),
    "pixabay": ("Pixabay Content License", "https://pixabay.com/service/license-summary/"),
    "magnific": ("Licença Magnific (stock via API)", "https://www.magnific.com/legal/terms-of-use#api-services"),
    "arquivo": ("arquivo indicado (ver nota)", ""),
}


# ------------------------------------------------------------------ settings
KEYS_FILE = Path.home() / ".motion-studio" / "chaves.json"   # per user, outside every repo and worktree


def keys():
    c = studio.config().get("keys", {}) or {}
    f = json.loads(KEYS_FILE.read_text(encoding="utf-8-sig")) if KEYS_FILE.exists() else {}
    get = lambda n: (os.environ.get(f"{n.upper()}_API_KEY") or (f.get(n) or "").strip()  # noqa: E731
                     or (c.get(n) or "").strip() or None)
    return {"magnific": get("magnific"), "pexels": get("pexels"), "pixabay": get("pixabay"),
            "magnific_daily": int(f.get("magnific_daily") or c.get("magnific_daily") or 100)}


def cmd_chaves(ep, a):
    """Create the keys file (empty) if missing and print where it is."""
    if not KEYS_FILE.exists():
        wj(KEYS_FILE, {"_leia": "Cole cada chave entre as aspas e salve. Este arquivo fica só neste PC, fora do git.",
                       "magnific": "", "pexels": "", "pixabay": "", "magnific_daily": 100})
        print("criado:", KEYS_FILE)
    else:
        print("já existe:", KEYS_FILE)
    cmd_fontes(ep, a)


def sources_status():
    """[(source, configured, note)] for doctor and `fontes` (no network)."""
    k = keys()
    try:
        import open_clip  # noqa: F401
        import torch
        clip = "CLIP na GPU disponível (--clip)" if torch.cuda.is_available() else "CLIP só na CPU (--clip fica lento)"
    except Exception:  # noqa: BLE001
        clip = "sem open_clip: só pelo nome do arquivo"
    return [("local", True, f"pasta de material do cliente; {clip}"),
            ("magnific", bool(k["magnific"]), f"MAGNIFIC_API_KEY; limite {k['magnific_daily']} downloads/dia, hoje {ledger_today()}"),
            ("pexels", bool(k["pexels"]), "PEXELS_API_KEY"),
            ("pixabay", bool(k["pixabay"]), "PIXABAY_API_KEY"),
            ("ia", True, "geração pela skill media-use (Claude roda; a ferramenta só lista os prompts)")]


def settings(ep):
    s = dict(DEFAULTS)
    s.update(studio.client_json(studio.client_of(ep)).get("apoio", {}) or {})
    s.update(studio.episode_json(ep).get("apoio", {}) or {})
    return s


def frame_of(ep):
    epj = studio.episode_json(ep)
    w, h = epj.get("frame") or studio.client_json(studio.client_of(ep)).get("frame", [1920, 1080])
    return int(w), int(h)


def target_orient(ep):
    w, h = frame_of(ep)
    return "vertical" if h > w else "horizontal" if w > h else "square"


def orient_of(w, h):
    if not w or not h:
        return "?"
    r = w / h
    return "vertical" if r < .9 else "horizontal" if r > 1.1 else "square"


LEDGER = studio.ROOT / "apoio_downloads.json"   # per PC, not in git: Magnific downloads per day


def ledger_today():
    if not LEDGER.exists():
        return 0
    return json.loads(LEDGER.read_text(encoding="utf-8")).get(dt.date.today().isoformat(), 0)


def ledger_add():
    d = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {}
    t = dt.date.today().isoformat()
    d[t] = d.get(t, 0) + 1
    LEDGER.write_text(json.dumps(d, indent=1), encoding="utf-8")


# ------------------------------------------------------------------ paths
def outdir(ep, a):
    if opt(a, "--out"):
        return Path(opt(a, "--out"))
    name = opt(a, "--name")
    if not name:
        base = Path(ep) / "APOIO"
        done = sorted(p.parent.parent.name for p in base.glob("*/_work/source.json")) if base.exists() else []
        if len(done) == 1:
            name = done[0]
        elif done:
            sys.exit(f"several videos in {base}: pass --name ({', '.join(done)})")
        else:
            sys.exit("pass --name <video> (or --xml on `palavras`, the name comes from the XML file)")
    return Path(ep) / "APOIO" / name


def opt(a, k):
    return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else None


def rj(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


def wj(p, o):
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    Path(p).write_text(json.dumps(o, indent=1, ensure_ascii=False), encoding="utf-8")


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9%]+", " ", t).split()


def slug(t, n=32):
    return "_".join(norm(t))[:n].strip("_") or "x"


def tc(t):
    return f"{int(t // 60):02d}:{t % 60:05.2f}"


# ------------------------------------------------------------------ XML (FCP7 xmeml exported by Premiere)
def rate(el):
    tb = int(el.findtext("rate/timebase") or el.findtext("timebase") or 30)
    return tb * (1000 / 1001 if (el.findtext("rate/ntsc") or "").upper() == "TRUE" else 1)


def pick_seq(root, name=None):
    seqs = list(root.iter("sequence"))
    seqs = [s for s in seqs if s.find("media") is not None]
    if name:
        s = next((s for s in seqs if s.findtext("name") == name), None)
        if s is None:
            sys.exit(f"sequence '{name}' not in XML: {[s.findtext('name') for s in seqs]}")
        return s
    # Premiere puts the exported (top) sequence first; nested sequences come after
    return seqs[0]


def audio_pieces(root, seq):
    """[(src_path, src_s, dur_s, seq_s)] for the speech track (the audio track with the most clip time)."""
    files = {}
    for f in root.iter("file"):
        if f.get("id") and f.findtext("pathurl"):
            p = unquote(f.findtext("pathurl")).replace("file://localhost/", "").replace("file:///", "").replace("file://", "")
            files[f.get("id")] = p
    fps = rate(seq)
    best, bestlen = [], -1
    for tr in seq.find("media/audio").findall("track"):
        if (tr.findtext("enabled") or "TRUE").upper() == "FALSE":
            continue
        pcs, tot, last_tr = [], 0.0, None
        for c in tr:
            if c.tag == "transitionitem":       # Premiere writes start/end -1 on clips that touch a transition
                last_tr = c
                continue
            if c.tag != "clipitem" or (c.findtext("enabled") or "TRUE").upper() == "FALSE":
                continue
            f = c.find("file")
            if f is None or f.get("id") not in files:
                continue
            cr = rate(c) if c.find("rate") is not None else fps
            s, e = int(c.findtext("start")), int(c.findtext("end"))
            if s < 0:                           # the clip starts where the previous transition starts
                if last_tr is None:
                    continue
                s = int(last_tr.findtext("start"))
            src_len = (int(c.findtext("out")) - int(c.findtext("in"))) / cr
            if e < 0:
                e = s + round(src_len * fps)
            last_tr = None
            pcs.append((files[f.get("id")], int(c.findtext("in")) / cr, (e - s) / fps, s / fps))
            tot += (e - s) / fps
        if tot > bestlen:
            best, bestlen = pcs, tot
    return best


def source_wav(ep, path, cache):
    """16 kHz mono of a source file: reuse the decupagem's work/audio/<stem>.wav when it exists."""
    stem = Path(path).stem
    for w in Path(ep).glob(f"**/work/audio/{stem}.wav"):
        return w
    w = cache / f"{stem}.wav"
    if not w.exists():
        print("  audio:", Path(path).name, flush=True)
        cache.mkdir(parents=True, exist_ok=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(w)], check=True)
    return w


def read_wav(p):
    import soundfile as sf
    x, sr = sf.read(str(p), dtype="float32")
    if x.ndim > 1:
        x = x.mean(1)
    assert sr == SR, f"{p}: {sr} Hz"
    return x


# ------------------------------------------------------------------ 1. palavras
def cmd_palavras(ep, a):
    import numpy as np
    xmlp = Path(opt(a, "--xml")) if opt(a, "--xml") else None
    if not xmlp and not opt(a, "--video"):
        sys.exit("pass --xml <final.xml> (and optionally --video <reference.mp4>)")
    if not opt(a, "--name") and not opt(a, "--out"):
        a = a + ["--name", (xmlp or Path(opt(a, "--video"))).stem]
    out = outdir(ep, a)
    work = out / "_work"
    work.mkdir(parents=True, exist_ok=True)
    src = {"xml": str(xmlp) if xmlp else None, "video": opt(a, "--video"), "frame": frame_of(ep), "orient": target_orient(ep)}
    if xmlp:
        root = ET.parse(xmlp).getroot()
        seq = pick_seq(root, opt(a, "--seq"))
        src.update(seq=seq.findtext("name"), fps=rate(seq), dur=int(seq.findtext("duration")) / rate(seq))
        w = seq.findtext("media/video/format/samplecharacteristics/width")
        h = seq.findtext("media/video/format/samplecharacteristics/height")
        if w and h:
            src["frame"], src["orient"] = [int(w), int(h)], orient_of(int(w), int(h))
    if opt(a, "--video"):
        audio = work / "final.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", opt(a, "--video"), "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(audio)], check=True)
        x = read_wav(audio)
    else:
        pcs = audio_pieces(root, seq)
        if not pcs:
            sys.exit("no audio clips with files on the XML (nested sequence?): pass --video <reference.mp4>")
        x = np.zeros(int(src["dur"] * SR) + SR, dtype="float32")
        cache = work / "audio"
        for path, s0, d, t0 in pcs:
            y = read_wav(source_wav(ep, path, cache))[int(s0 * SR): int((s0 + d) * SR)]
            i = int(t0 * SR)
            x[i: i + len(y)] += y[: len(x) - i]
        src["pieces"] = len(pcs)
    words = transcribe(ep, x, a)
    wj(work / "words.json", words)
    wj(work / "source.json", src)
    (work / "transcript.md").write_text(transcript(words), encoding="utf-8")
    rot = roteiro(ep)
    (work / "roteiro.txt").write_text(rot, encoding="utf-8")
    print(json.dumps({"out": str(out), "words": len(words), "dur_s": round(src.get("dur") or len(x) / SR, 1),
                      "orient": src["orient"], "roteiro_chars": len(rot)}, ensure_ascii=False))


def transcribe(ep, x, a):
    from decup_stage2 import whisper_model
    cj, epj = studio.client_json(studio.client_of(ep)), studio.episode_json(ep)
    prompt = cj.get("transcribe_prompt", "") + (" " + ", ".join(epj.get("vocab", [])) + "." if epj.get("vocab") else "")
    model = whisper_model(opt(a, "--model") or "large-v3")
    segs, _ = model.transcribe(x, language=(cj.get("language") or "pt").split("-")[0], word_timestamps=True,
                               vad_filter=True, vad_parameters={"min_silence_duration_ms": 400},
                               condition_on_previous_text=False, initial_prompt=prompt, beam_size=5)
    return [{"t": round(w.start, 3), "te": round(w.end, 3), "w": w.word.strip(), "p": round(w.probability, 3)}
            for sg in segs for w in sg.words]


def transcript(words):
    lines, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        if re.search(r"[.!?…]$", w["w"]) or i + 1 == len(words) or words[i + 1]["t"] - w["te"] > .9:
            lines.append(f"[{tc(cur[0]['t'])}] " + " ".join(x["w"] for x in cur))
            cur = []
    return "\n".join(lines) + "\n"


def roteiro(ep):
    """Text of the script/briefing: episode.json "briefings", else MATERIAL/*.{pdf,txt,md}."""
    ep = Path(ep)
    fs = [studio.resolve(b, ep) for b in studio.episode_json(ep).get("briefings", [])]
    if not fs and (ep / "MATERIAL").exists():
        fs = sorted(p for p in (ep / "MATERIAL").iterdir() if p.suffix.lower() in (".pdf", ".txt", ".md"))
    parts = []
    for f in fs:
        if not Path(f).exists():
            continue
        t = pdf_text(f) if Path(f).suffix.lower() == ".pdf" else Path(f).read_text(encoding="utf-8", errors="replace")
        parts.append(f"===== {Path(f).name}\n{re.sub(chr(10) + '{3,}', chr(10) * 2, t).strip()}\n")
    return "\n".join(parts) or "(sem roteiro: nenhum briefing em episode.json nem PDF/TXT em MATERIAL)\n"


def pdf_text(f):
    try:
        import pypdf
        return "\n".join(p.extract_text() or "" for p in pypdf.PdfReader(str(f)).pages)
    except ImportError:
        pass
    if shutil.which("pdftotext"):
        r = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", str(f), "-"], capture_output=True)
        return r.stdout.decode("utf-8", errors="replace")
    return f"(não consegui ler {Path(f).name}: python -m pip install --user pypdf)"


# ------------------------------------------------------------------ 2. checar (momentos.json -> exact times)
def find_anchor(words, anchor, near):
    toks = [(tk, i) for i, w in enumerate(words) for tk in norm(w["w"])]
    a = norm(anchor)
    hits = [toks[k][1] for k in range(len(toks) - len(a) + 1) if [t for t, _ in toks[k:k + len(a)]] == a] if a else []
    if not hits:
        return None
    return min(hits, key=lambda i: abs(words[i]["t"] - (near if near is not None else words[i]["t"])))


def resolve_moments(ep, out):
    words = rj(out / "_work" / "words.json")
    spec = rj(out / "momentos.json")
    st = settings(ep)
    lo, hi = st["clip_s"]
    res, warn = [], []
    for n, m in enumerate(spec["moments"], 1):
        m.setdefault("id", n)
        i = find_anchor(words, m["anchor"], m.get("near"))
        if i is None:
            warn.append(f"MISS {m['id']}: '{m['anchor']}' não foi dito assim (perto de {m.get('near')})")
            continue
        m["t"] = words[i]["t"]
        m["dur"] = float(m.get("dur") or lo + (hi - lo) / 2)
        m["kind"] = m.get("kind") or ("photo" if st["prefer"] == "photo" else "video")
        reg = st.get("regiao") or {}
        if m.get("regional", st.get("regional_padrao")) and reg.get("en"):   # places, money, government...: client's country
            has = lambda q: any(w and w.lower()[:5] in q.lower() for w in (reg["en"], reg.get("pt", "")))  # noqa: E731
            if not has(q_en(m)):
                m["q"] = f"{q_en(m)} {reg['en']}"
            if reg.get("pt") and not has(q_pt(m)):
                m["q_pt"] = f"{q_pt(m)} {reg['pt']}"
        res.append(m)
    res.sort(key=lambda m: m["t"])
    for p, q in zip(res, res[1:]):
        if q["t"] - p["t"] < st["min_gap_s"]:
            warn.append(f"PERTO {p['id']}->{q['id']}: {q['t'] - p['t']:.1f}s (min_gap_s {st['min_gap_s']})")
        if p["t"] + p["dur"] > q["t"]:
            p["dur"] = round(q["t"] - p["t"], 2)
    total = words[-1]["te"] if words else 1
    if len(res) > st["max_per_min"] * max(total / 60, 1):
        warn.append(f"DENSO: {len(res)} momentos em {total:.0f}s (max_per_min {st['max_per_min']})")
    return res, warn


def cmd_checar(ep, a):
    out = outdir(ep, a)
    res, warn = resolve_moments(ep, out)
    for m in res:
        print(f"{m['id']:>3} {tc(m['t'])} +{m['dur']:.1f}s {m['kind']:5s} {m['anchor']!r:28s} {m.get('desc', '')}")
    for w in warn:
        print(w)
    print(f"{len(res)} momentos ok, {len(warn)} avisos")


# ------------------------------------------------------------------ 3. buscar
def http_json(url, params=None, headers=None):
    import requests
    r = requests.get(url, params=params, headers={**UA, **(headers or {})}, timeout=30)
    if r.status_code >= 400:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    return r.json()


def q_en(m):
    return m.get("q") or m.get("q_en") or m.get("desc") or m["anchor"]


def q_pt(m):
    return m.get("q_pt") or m.get("desc") or m["anchor"]


def hms(d):
    if isinstance(d, (int, float)):
        return float(d)
    try:
        p = [float(x) for x in str(d).split(":")]
        return p[0] * 3600 + p[1] * 60 + p[2] if len(p) == 3 else p[0] * 60 + p[1] if len(p) == 2 else p[0]
    except ValueError:
        return 0.0


def s_pexels(m, orient, per, key):
    po = {"vertical": "portrait", "horizontal": "landscape", "square": "square"}[orient]
    h = {"Authorization": key}
    if m["kind"] == "photo":
        r = http_json("https://api.pexels.com/v1/search", {"query": q_en(m), "orientation": po, "per_page": per}, h)
        return [{"src": "pexels", "id": str(p["id"]), "kind": "photo", "w": p["width"], "h": p["height"], "page": p["url"],
                 "author": p.get("photographer"), "author_url": p.get("photographer_url"), "thumb": p["src"]["medium"],
                 "file": p["src"]["original"], "title": p.get("alt") or ""} for p in r.get("photos", [])]
    r = http_json("https://api.pexels.com/videos/search", {"query": q_en(m), "orientation": po, "per_page": per}, h)
    out = []
    for v in r.get("videos", []):
        fs = [f for f in v.get("video_files", []) if f.get("link") and f.get("width")]
        good = sorted(fs, key=lambda f: (abs(min(f["width"], f["height"]) - 1080), -f["width"]))
        if not good:
            continue
        out.append({"src": "pexels", "id": str(v["id"]), "kind": "video", "w": v["width"], "h": v["height"], "dur": v.get("duration"),
                    "page": v["url"], "author": (v.get("user") or {}).get("name"), "author_url": (v.get("user") or {}).get("url"),
                    "thumb": v.get("image"), "file": good[0]["link"], "title": ""})
    return out


def s_pixabay(m, orient, per, key, lang):
    if m["kind"] == "photo":
        po = {"vertical": "vertical", "horizontal": "horizontal"}.get(orient, "all")
        r = http_json("https://pixabay.com/api/", {"key": key, "q": q_pt(m)[:100], "lang": lang, "image_type": "photo",
                                                    "orientation": po, "per_page": max(per, 3), "safesearch": "true"})
        return [{"src": "pixabay", "id": str(p["id"]), "kind": "photo", "w": p["imageWidth"], "h": p["imageHeight"],
                 "page": p["pageURL"], "author": p.get("user"), "thumb": p.get("webformatURL"), "file": p.get("largeImageURL"),
                 "title": p.get("tags", "")} for p in r.get("hits", [])][:per]
    out = []
    for q, lg in ((q_pt(m), lang), (q_en(m), "en")):
        r = http_json("https://pixabay.com/api/videos/", {"key": key, "q": q[:100], "lang": lg, "per_page": 20, "safesearch": "true"})
        for v in r.get("hits", []):
            vs = v.get("videos", {})
            f = vs.get("large") if (vs.get("large") or {}).get("url") else vs.get("medium") or {}
            if not f.get("url"):
                continue
            out.append({"src": "pixabay", "id": str(v["id"]), "kind": "video", "w": f.get("width"), "h": f.get("height"),
                        "dur": v.get("duration"), "page": v["pageURL"], "author": v.get("user"), "thumb": f.get("thumbnail"),
                        "file": f["url"], "title": v.get("tags", "")})
        if out:
            break
    out.sort(key=lambda c: orient_of(c["w"], c["h"]) != orient)          # no orientation filter on the API: right ones first
    return out[:per]


MAG = "https://api.magnific.com"


def s_magnific(m, orient, per, key):
    h = {"x-magnific-api-key": key, "Accept-Language": "pt-BR"}
    if m["kind"] == "photo":
        po = {"vertical": "portrait", "horizontal": "landscape", "square": "square"}[orient]
        p = {"term": q_en(m), "limit": per, f"filters[orientation][{po}]": 1, "filters[content_type][photo]": 1}
        try:
            r = http_json(f"{MAG}/v1/resources", p, h)
        except RuntimeError as e:
            if "400" not in str(e):
                raise
            r = http_json(f"{MAG}/v1/resources", {"term": q_en(m), "limit": per}, h)
        out = []
        for it in r.get("data", [])[:per]:
            sz = ((it.get("image") or {}).get("source") or {}).get("size") or "0x0"
            w, hh = (int(x) for x in (sz.split("x") + ["0"])[:2]) if "x" in sz else (0, 0)
            lic = ",".join(x.get("type", "") for x in it.get("licenses", []))
            out.append({"src": "magnific", "id": str(it["id"]), "kind": "photo", "w": w, "h": hh, "page": it.get("url"),
                        "author": (it.get("author") or {}).get("name"), "thumb": ((it.get("image") or {}).get("source") or {}).get("url"),
                        "file": None, "title": it.get("title", ""), "premium": "premium" in lic, "license_note": lic})
        return out
    try:
        # tested live 2026-11: filters[orientation] is accepted but ignored; filters[aspect_ratio][] works
        ars = {"vertical": ["9:16", "135:256"], "horizontal": ["16:9", "256:135"], "square": ["1:1"]}[orient]
        r = http_json(f"{MAG}/v1/videos", {"term": q_en(m), "filters[aspect_ratio][]": ars}, h)
    except RuntimeError as e:
        if "400" not in str(e):
            raise
        r = http_json(f"{MAG}/v1/videos", {"term": q_en(m)}, h)
    out = []
    for it in r.get("data", []):
        ar = it.get("aspect-ratio") or it.get("aspect_ratio") or ""
        w, hh = (int(x) for x in ar.split(":")) if re.fullmatch(r"\d+:\d+", ar) else (0, 0)
        th = (it.get("thumbnails") or [{}])[0].get("url")
        out.append({"src": "magnific", "id": str(it["id"]), "kind": "video", "w": w, "h": hh, "dur": hms(it.get("duration")),
                    "page": it.get("url"), "author": (it.get("author") or {}).get("name"), "thumb": th, "file": None,
                    "title": it.get("name", ""), "premium": bool(it.get("premium"))})
    out.sort(key=lambda c: orient_of(c["w"], c["h"]) != orient)
    return out[:per]


# ---- client folder: file names (+ optional CLIP on the GPU), index cached in the client's _digest/
def local_dirs(ep, st, a):
    cd = studio.client_dir(studio.client_of(ep))
    ds = [Path(opt(a, "--local-dir"))] if opt(a, "--local-dir") else []
    ds += [d if Path(d).is_absolute() else cd / d for d in st["local_dirs"]]
    return [Path(d) for d in ds if Path(d).exists()]


def local_index(dirs):
    idx = []
    for d in dirs:
        for p in d.rglob("*"):
            ext = p.suffix.lower()
            if ext in VIDEO_EXT | PHOTO_EXT and "_work" not in p.parts:
                toks = {t for t in norm(" ".join(p.relative_to(d).with_suffix("").parts))
                        if len(t) > 2 and not t.isdigit() and t not in CAMERA_TOKENS and not re.fullmatch(r"[a-z]{1,4}\d+", t)}
                idx.append({"path": str(p), "kind": "video" if ext in VIDEO_EXT else "photo", "toks": sorted(toks)})
    return idx


def stems(ts):
    return {t[:5] for t in ts}            # cheap stemming: "energia"/"energético" -> "energ"


def thumb_local(path, kind, dst):
    if dst.exists():
        return dst
    dst.parent.mkdir(parents=True, exist_ok=True)
    if kind == "photo":
        from PIL import Image
        im = Image.open(path)
        im.thumbnail((320, 320))
        im.convert("RGB").save(dst, quality=80)
    else:
        for ss in ("1", "0"):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", ss, "-i", path, "-frames:v", "1", "-vf", "scale=320:-2", str(dst)])
            if dst.exists():
                break
    return dst


class Clip:
    """open_clip ViT-B-32 on the GPU; image embeddings cached by path+mtime in the client's _digest/apoio_clip.npz."""

    def __init__(self, cache):
        import open_clip
        import torch
        self.torch = torch
        self.dev = "cuda" if torch.cuda.is_available() else "cpu"
        self.model, _, self.pre = open_clip.create_model_and_transforms("ViT-B-32", pretrained="laion2b_s34b_b79k", device=self.dev)
        self.tok = open_clip.get_tokenizer("ViT-B-32")
        self.cache = cache
        self.emb = {}
        if cache.exists():
            import numpy as np
            z = np.load(cache, allow_pickle=True)
            self.emb = dict(z["emb"].item())

    def image(self, key, thumb):
        if key not in self.emb:
            from PIL import Image
            with self.torch.no_grad():
                x = self.pre(Image.open(thumb).convert("RGB")).unsqueeze(0).to(self.dev)
                e = self.model.encode_image(x)
                self.emb[key] = (e / e.norm(dim=-1, keepdim=True)).cpu().numpy()[0]
        return self.emb[key]

    def text(self, q):
        with self.torch.no_grad():
            e = self.model.encode_text(self.tok([q]).to(self.dev))
            return (e / e.norm(dim=-1, keepdim=True)).cpu().numpy()[0]

    def save(self):
        import numpy as np
        self.cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez(self.cache, emb=self.emb)


def s_local(m, orient, per, idx, work, clip):
    want = stems(t for t in norm(" ".join([*m.get("local", []), q_pt(m), m["anchor"]])) if len(t) > 2)
    tq = clip.text(q_en(m)) if clip else None
    out = []
    for it in idx:
        name_score = len(want & stems(it["toks"])) / max(len(want), 1)
        th = work / "thumbs" / f"local_{hashlib.md5(it['path'].encode()).hexdigest()[:10]}_{slug(Path(it['path']).stem, 24)}.jpg"
        sim = None
        if clip:
            thumb_local(it["path"], it["kind"], th)
            if th.exists():
                sim = float(clip.image(f"{it['path']}|{os.path.getmtime(it['path'])}", th) @ tq)
        score = name_score + (max(0.0, sim - 0.2) * 4 if sim is not None else 0)
        if score <= 0:
            continue
        out.append({"src": "local", "id": it["path"], "kind": it["kind"], "page": "", "author": "cliente", "file": it["path"],
                    "title": Path(it["path"]).name, "score": round(score, 3), "clip_sim": sim and round(sim, 3), "thumb_local": str(th)})
    out.sort(key=lambda c: -c["score"])
    out = out[:per * 2]
    for c in out:
        thumb_local(c["file"], c["kind"], Path(c["thumb_local"]))
        c["w"], c["h"] = media_size(c["file"])
        c["score"] += .15 * (orient_of(c["w"], c["h"]) == orient) + .1 * (c["kind"] == m["kind"])   # same relevance: right shape first
    out.sort(key=lambda c: -c["score"])
    return out[:per]


def media_size(p):
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:stream_side_data=rotation",
                            "-of", "json", p], capture_output=True, text=True, timeout=30)
        s = json.loads(r.stdout)["streams"][0]
        w, h = s["width"], s["height"]
        rot = next((abs(int(x.get("rotation", 0))) for x in s.get("side_data_list", []) if "rotation" in x), 0)
        return (h, w) if rot in (90, 270) else (w, h)
    except Exception:  # noqa: BLE001
        return 0, 0


def cmd_buscar(ep, a):
    out = outdir(ep, a)
    work = out / "_work"
    st = settings(ep)
    orient = rj(work / "source.json").get("orient") or target_orient(ep)
    per = int(opt(a, "--per") or 4)
    order = (opt(a, "--sources") or ",".join(st["sources"])).split(",")
    k = keys()
    moments, warn = resolve_moments(ep, out)
    for w in warn:
        print(w)
    avail = {"local": True, "magnific": bool(k["magnific"]), "pexels": bool(k["pexels"]), "pixabay": bool(k["pixabay"]), "ia": True}
    use = [s for s in order if s in avail]
    skipped = [s for s in use if not avail[s]]
    use = [s for s in use if avail[s]]
    print(f"formato {orient} | fontes: {' > '.join(use)}" + (f" | sem chave (pulado): {', '.join(skipped)}" if skipped else ""))
    if "--dry" in a:
        for m in moments:
            print(f"{m['id']:>3} {tc(m['t'])} {m['kind']:5s} en={q_en(m)!r} pt={q_pt(m)!r} local={m.get('local', [])}")
        return
    idx, clip = [], None
    if "local" in use:
        dirs = local_dirs(ep, st, a)
        idx = local_index(dirs)
        print(f"local: {len(idx)} arquivos em {[str(d) for d in dirs] or 'nenhuma pasta (client.json apoio.local_dirs)'}")
        if idx and "--clip" in a:
            cache = work if opt(a, "--out") else studio.client_dir(studio.client_of(ep)) / "_digest"   # tests stay in --out
            clip = Clip(cache / "apoio_clip.npz")
    # --ids 3,4,5: search only these moments and keep the others' candidates (no new API calls, picks stay valid)
    only = {x.strip() for x in opt(a, "--ids").split(",")} if opt(a, "--ids") else None
    cands = rj(work / "candidates.json") if only and (work / "candidates.json").exists() else {}
    if only:
        moments = [m for m in moments if str(m["id"]) in only]
    for m in moments:
        got = []
        for s in use:
            if s == "ia" or len(got) >= per:
                continue
            try:
                if s == "local":
                    r = s_local(m, orient, per, idx, work, clip) if idx else []
                elif s == "pexels":
                    r = s_pexels(m, orient, per, k["pexels"])
                elif s == "pixabay":
                    r = s_pixabay(m, orient, per, k["pixabay"], st["lang"])
                else:
                    r = s_magnific(m, orient, per, k["magnific"])
            except Exception as e:  # noqa: BLE001
                print(f"  {m['id']} {s}: {e}")
                r = []
            got += r[: per - len(got)]
        for n, c in enumerate(got, 1):
            c["n"] = n
            c["orient"] = orient_of(c.get("w"), c.get("h"))
            c["crop"] = None if c["orient"] in (orient, "?") else f"{c['orient']} -> recortar para {orient}"
        cands[str(m["id"])] = got
        print(f"{m['id']:>3} {tc(m['t'])} {m['anchor'][:26]:26s} " + (" ".join(f"{c['n']}:{c['src']}{'*' if c['crop'] else ''}" for c in got) or "nada"))
        for c in got:                    # titles catch what a thumbnail hides (foreign money, flags, brands)
            print(f"      {c['n']} {(c.get('title') or Path(str(c['id'])).name)[:70]}")
    if clip:
        clip.save()
    wj(work / "candidates.json", cands)
    sheets = contact_sheet(out, moments, cands)
    print("folha:", *sheets)
    print("escolha padrão = candidato 1 (* = orientação errada). Mude em momentos.json: \"pick\": 3 | \"ia\" | \"arquivo:<caminho>\" | \"nada\"")


def contact_sheet(out, moments, cands, cell=150, rows_per=10):
    import requests
    from PIL import Image, ImageDraw, ImageFont
    work = out / "_work"
    try:
        font = ImageFont.truetype("arial.ttf", 13)
    except OSError:
        font = ImageFont.load_default()
    pages, files = [moments[i:i + rows_per] for i in range(0, len(moments), rows_per)], []
    ncol = max([len(cands.get(str(m["id"]), [])) for m in moments] + [1])
    lab = 210
    for pi, page in enumerate(pages, 1):
        im = Image.new("RGB", (lab + ncol * (cell + 6), len(page) * (cell + 22) + 6), (24, 24, 24))
        d = ImageDraw.Draw(im)
        for r, m in enumerate(page):
            y = 6 + r * (cell + 22)
            d.text((6, y), f"{m['id']}  {tc(m['t'])}", fill=(255, 255, 255), font=font)
            txt = m.get("desc") or m["anchor"]
            for j in range(0, min(len(txt), 120), 26):
                d.text((6, y + 18 + j // 26 * 15), txt[j:j + 26], fill=(190, 190, 190), font=font)
            for c in cands.get(str(m["id"]), []):
                x = lab + (c["n"] - 1) * (cell + 6)
                th = Path(c.get("thumb_local") or work / "thumbs" / f"{c['src']}_{slug(c['id'], 40)}.jpg")
                if not th.exists() and c.get("thumb"):
                    try:
                        th.parent.mkdir(parents=True, exist_ok=True)
                        th.write_bytes(requests.get(c["thumb"], headers=UA, timeout=30).content)
                    except Exception:  # noqa: BLE001
                        pass
                try:
                    t = Image.open(th).convert("RGB")
                    t.thumbnail((cell, cell))
                    im.paste(t, (x + (cell - t.width) // 2, y + (cell - t.height) // 2))
                except Exception:  # noqa: BLE001
                    d.rectangle([x, y, x + cell, y + cell], outline=(80, 80, 80))
                d.text((x, y + cell + 3), f"{c['n']} {c['src']}" + (" CROP" if c["crop"] else ""),
                       fill=(255, 120, 90) if c["crop"] else (150, 220, 150), font=font)
        f = work / f"folha_{pi}.jpg"
        im.save(f, quality=78)
        files.append(str(f))
    return files


# ------------------------------------------------------------------ 4. baixar
def choose(m, cands):
    p = m.get("pick", 1)
    if p in ("nada", "none"):
        return None
    if p == "ia":
        return {"src": "ia"}
    if isinstance(p, str) and p.startswith("arquivo:"):
        f = p.split(":", 1)[1]
        return {"src": "arquivo", "id": f, "file": f, "kind": "photo" if Path(f).suffix.lower() in PHOTO_EXT else "video",
                "author": m.get("credit", ""), "page": "", "orient": "?", "crop": None}
    if isinstance(p, str) and ":" in p:
        s, i = p.split(":", 1)
        return next((c for c in cands if c["src"] == s and c["id"] == i), None)
    return next((c for c in cands if c["n"] == int(p)), None)


def download(c, dst, k):
    import requests
    url = c.get("file")
    if c["src"] == "magnific":
        if ledger_today() >= k["magnific_daily"]:
            raise RuntimeError(f"limite diário Magnific ({k['magnific_daily']}) atingido neste PC")
        kind = "videos" if c["kind"] == "video" else "resources"
        r = http_json(f"{MAG}/v1/{kind}/{c['id']}/download", None, {"x-magnific-api-key": k["magnific"]})
        url = r["data"]["url"]
        c["filename"] = r["data"].get("filename")
        ledger_add()                    # the /download call is what counts (and reports) the download to Magnific
    with requests.get(url, headers=UA, stream=True, timeout=120, allow_redirects=True) as r:
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")
        ext = Path((c.get("filename") or url.split("?")[0])).suffix.lower()
        ext = ext if ext in VIDEO_EXT | PHOTO_EXT else (".mp4" if c["kind"] == "video" else ".jpg")
        dst = dst.with_suffix(ext)
        tmp = dst.with_suffix(ext + ".part")
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
        tmp.replace(dst)
    return dst


def cmd_baixar(ep, a):
    out = outdir(ep, a)
    k = keys()
    moments, _ = resolve_moments(ep, out)
    cands = rj(out / "_work" / "candidates.json")
    man, gerar = [], []
    for m in moments:
        c = choose(m, cands.get(str(m["id"]), []))
        base = f"{int(m['id']):02d}_{int(m['t'] // 60):02d}m{int(m['t'] % 60):02d}s_{slug(m.get('desc') or m['anchor'], 28)}"
        row = {"id": m["id"], "t": m["t"], "dur": m["dur"], "anchor": m["anchor"], "desc": m.get("desc", ""), "kind": m["kind"]}
        if c is None or c["src"] == "ia":
            if c is None and not cands.get(str(m["id"])) and "ia" not in settings(ep)["sources"]:
                row["status"] = "sem candidato"
            elif c is None and m.get("pick") in ("nada", "none"):
                row["status"] = "nada"
            else:
                row["status"] = "gerar com IA"
                gerar.append({"id": m["id"], "file": base, "prompt": m.get("prompt_ia") or q_en(m), "frame": frame_of(ep),
                              "kind": m["kind"], "dur": m["dur"]})
            man.append(row)
            continue
        row.update({k_: c.get(k_) for k_ in ("src", "id", "author", "author_url", "page", "title", "orient", "crop", "premium")})
        row["id"] = m["id"]
        row["source_id"] = c["id"]
        prev = next(iter(sorted(out.glob(base + ".*"))), None)
        try:
            if prev and prev.suffix != ".part":
                dst = prev
            elif c["src"] in ("local", "arquivo"):
                dst = out / (base + Path(c["file"]).suffix.lower())
                shutil.copy2(c["file"], dst)
            else:
                dst = download(c, out / base, k)
            row["file"], row["status"] = dst.name, "ok"
            print(f"{m['id']:>3} {c['src']:8s} {dst.name}" + (f"  ({c['crop']})" if c.get("crop") else ""))
        except Exception as e:  # noqa: BLE001
            row["status"] = f"erro: {e}"
            print(f"{m['id']:>3} {c['src']:8s} ERRO {e}")
        man.append(row)
    wj(out / "manifest.json", {"episode": str(ep), "frame": frame_of(ep), "made": dt.datetime.now().isoformat(timespec="seconds"), "moments": man})
    if gerar:
        wj(out / "gerar_ia.json", gerar)
    credits(out, man)
    ok = sum(r["status"] == "ok" for r in man)
    print(f"{ok}/{len(man)} baixados -> {out}" + (f" | {len(gerar)} para gerar com IA (gerar_ia.json, skill media-use)" if gerar else ""))


def credits(out, man):
    L = ["# Créditos das imagens de apoio", "",
         "| # | tempo | arquivo | fonte | autor | licença | link | id |", "|---|---|---|---|---|---|---|---|"]
    for r in man:
        if r.get("status") != "ok":
            continue
        lic, lurl = LICENSE.get(r["src"], ("", ""))
        if r["src"] == "magnific":
            lic += " — premium" if r.get("premium") else " — gratuito (pode exigir atribuição)"
        L.append(f"| {r['id']} | {tc(r['t'])} | {r['file']} | {r['src']} | {r.get('author') or ''} | {lic}{' ' + lurl if lurl else ''} "
                 f"| {r.get('page') or ''} | {r['source_id'] if r['src'] not in ('local', 'arquivo') else Path(r['source_id']).name} |")
    L += ["", "Pexels e Pixabay: uso livre, sem atribuição obrigatória (dar crédito é bem-vindo). Magnific: o uso segue o plano "
          "da conta e os termos da API; itens gratuitos podem pedir atribuição. Material do cliente: uso do próprio cliente.", ""]
    (out / "CREDITOS.md").write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------ 5. marcas
def cmd_marcas(ep, a):
    out = outdir(ep, a)
    src = rj(out / "_work" / "source.json")
    if not src.get("xml"):
        sys.exit("palavras ran without --xml: no XML to copy markers into")
    man = rj(out / "manifest.json")["moments"] if (out / "manifest.json").exists() else None
    if man is None:
        man = [{**m, "status": "sem download"} for m in resolve_moments(ep, out)[0]]
    xmlp = Path(src["xml"])
    root = ET.parse(xmlp).getroot()
    seq = pick_seq(root, src.get("seq"))
    fps = rate(seq)
    for r in man:
        mk = ET.SubElement(seq, "marker")
        what = r.get("file") or r.get("status", "")
        src_ = f" [{r['src']}]" if r.get("src") else ""
        ET.SubElement(mk, "name").text = f"APOIO {r['id']}: {r.get('desc') or r['anchor']}"[:60]
        ET.SubElement(mk, "comment").text = (f"{r.get('desc') or r['anchor']} | {what}{src_}" + (f" | {r['crop']}" if r.get("crop") else "")
                                             + f" | fala: \"{r['anchor']}\"")
        ET.SubElement(mk, "in").text = str(round(r["t"] * fps))
        ET.SubElement(mk, "out").text = str(round((r["t"] + r["dur"]) * fps))
    seq.find("name").text = (seq.findtext("name") or "seq").strip() + "_APOIO"
    dst = Path(opt(a, "--xml-out")) if opt(a, "--xml-out") else out / f"{xmlp.stem}_apoio.xml"
    n, base = 2, dst
    while dst.exists() or dst.resolve() == xmlp.resolve():
        dst = base.with_name(f"{base.stem}_v{n}.xml")
        n += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    body = ET.tostring(root, encoding="unicode")
    dst.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body, encoding="utf-8")
    print(f"{len(man)} marcas -> {dst}  (sequência {seq.findtext('name')})")


# ------------------------------------------------------------------ CLI
def cmd_fontes(ep, a):
    for s, ok, note in sources_status():
        print(f"  [{'OK' if ok else '--'}] {s:9s} {note}")
    if ep:
        st = settings(ep)
        print(f"ordem do cliente: {' > '.join(st['sources'])} | formato {target_orient(ep)} | pastas locais: "
              f"{[str(d) for d in local_dirs(ep, st, a)] or 'nenhuma'}")


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd, rest = a[0], a[1:]
    ep = Path(rest[0]) if rest and not rest[0].startswith("--") else None
    fn = {"fontes": cmd_fontes, "chaves": cmd_chaves, "palavras": cmd_palavras, "checar": cmd_checar, "buscar": cmd_buscar,
          "baixar": cmd_baixar, "marcas": cmd_marcas}.get(cmd)
    if not fn:
        print(__doc__)
        sys.exit(2)
    if ep is None and cmd not in ("fontes", "chaves"):
        sys.exit("pass the episode folder")
    fn(ep, rest[1:] if ep else rest)


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    main(sys.argv[1:])
