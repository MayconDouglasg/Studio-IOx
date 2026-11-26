"""Decupagem: multicam sync, transcription, silence + repeated-take removal, Premiere XML.
All local (ffmpeg, numpy, faster-whisper on GPU). Originals are never copied or modified.

  python tools/decup.py scan  <episode_dir> <raw_folder>   # inventory + sessions -> episode/manifest.json
  python tools/decup.py sync  <episode_dir>                # audio cross-correlation, drift -> manifest
  python tools/decup.py trans <episode_dir> [--model large-v3] [--whole] [--out dir]   # master audio -> words per session
                                                           # (default: chunked at real silences, word times aligned to the voice)
  python tools/decup.py cut   <episode_dir>                # silences + repeated takes -> edl.json + report.md
  python tools/decup.py semantic-export <episode_dir>      # rough-cut transcript with clip ids -> work/semantic_in.txt
  python tools/decup.py semantic-apply  <episode_dir>      # work/semantic.json (written by Claude) -> edl.json
  python tools/decup.py polish <episode_dir> [--edl f] [--to f] [--transcript dir]   # 2nd pass: crutch words, self-corrections
  python tools/decup.py xml   <episode_dir> [--edl f] [--name sfx] [--no-cams]   # Premiere (FCP7 xmeml) + camera switching

Camera roles by file name come from the client's client.json (decup.roles; default DJI_* = lateral = master audio,
IMG_* = frontal = home camera, screen recordings = tela).
"""
import glob
import json
import os
import re
import site
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import numpy as np

SR = 16000


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def load(ep):
    return json.loads((ep / "manifest.json").read_text(encoding="utf-8"))


def save(ep, m):
    (ep / "manifest.json").write_text(json.dumps(m, indent=1, ensure_ascii=False), encoding="utf-8")


def role_of(name, roles=None):
    """Camera role from the file name, using the client's patterns (client.json decup.roles)."""
    import fnmatch
    n = name.lower()
    for role, pats in (roles or {}).items():
        if any(fnmatch.fnmatch(n, pat.lower()) for pat in pats):
            return role
    if n.startswith("dji_"):
        return "lateral"
    if n.startswith("img_"):
        return "frontal"
    if "ecrã" in n or "ecra" in n or "screen" in n or "tela" in n:
        return "tela"
    return None


# ------------------------------------------------------------------ scan
def probe(p):
    r = run(["ffprobe", "-v", "error", "-show_entries",
             "format=duration:format_tags=creation_time:stream=codec_type,width,height,r_frame_rate,avg_frame_rate,sample_rate,channels",
             "-of", "json", str(p)], text=True)
    d = json.loads(r.stdout)
    v = next(s for s in d["streams"] if s["codec_type"] == "video")
    a = next((s for s in d["streams"] if s["codec_type"] == "audio"), None)
    fr = lambda s: (lambda n, dd: float(n) / float(dd))(*s.split("/"))  # noqa: E731
    ct = d["format"].get("tags", {}).get("creation_time")
    return {
        "duration": float(d["format"]["duration"]), "width": v["width"], "height": v["height"],
        "fps": round(fr(v["r_frame_rate"]), 4), "avg_fps": round(fr(v["avg_frame_rate"]), 4),
        "vfr": abs(fr(v["r_frame_rate"]) - fr(v["avg_frame_rate"])) > 0.01,
        "audio": bool(a), "channels": int(a["channels"]) if a else 0,
        "created": ct,
    }


def scan(ep, raw):
    import studio
    ep.mkdir(parents=True, exist_ok=True)
    cj = studio.client_json(studio.client_of(ep))["decup"]
    roles = cj.get("roles") or {}
    master_role, home_role = cj.get("master_audio", "lateral"), cj.get("home_camera", "frontal")
    files = []
    for p in sorted(Path(raw).iterdir()):
        if p.suffix.lower() not in (".mp4", ".mov", ".mxf", ".mkv"):
            continue
        r = role_of(p.name, roles)
        if not r:
            print("skip (unknown role):", p.name)
            continue
        info = probe(p)
        info.update(path=str(p.resolve()), name=p.name, role=r,
                    t0=datetime.fromisoformat(info["created"].replace("Z", "+00:00")).timestamp())
        files.append(info)
    masters = sorted([f for f in files if f["role"] == master_role], key=lambda f: f["t0"])
    sessions = []
    for i, mst in enumerate(masters):
        s = {"id": i + 1, "master": mst["name"], "members": []}
        for f in files:
            if f is mst:
                continue
            if mst["t0"] - 90 <= f["t0"] <= mst["t0"] + mst["duration"]:
                s["members"].append({"name": f["name"], "role": f["role"], "expected_offset": round(f["t0"] - mst["t0"], 2)})
        sessions.append(s)
    m = {"episode": ep.name, "raw": str(Path(raw).resolve()), "roles": {"master": master_role, "home": home_role},
         "files": {f["name"]: f for f in files}, "sessions": sessions}
    save(ep, m)
    for s in sessions:
        print(f"session {s['id']}: master {s['master']}  + " + ", ".join(f"{x['role']}:{x['name']}@{x['expected_offset']}s" for x in s["members"]))


# ------------------------------------------------------------------ audio
def wav_path(ep, name):
    return ep / "work" / "audio" / (Path(name).stem + ".wav")


def extract(ep, m):
    (ep / "work" / "audio").mkdir(parents=True, exist_ok=True)
    for f in m["files"].values():
        w = wav_path(ep, f["name"])
        if not w.exists():
            print("extract", f["name"], flush=True)
            run(["ffmpeg", "-v", "error", "-y", "-i", f["path"], "-vn", "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(w)])


def read_wav(p):
    import soundfile as sf
    x, sr = sf.read(str(p), dtype="float32")
    assert sr == SR
    return x


def envelope(x, rate=1000):
    """Band-limited energy envelope at `rate` Hz: robust to different mics."""
    from scipy.signal import butter, sosfiltfilt
    sos = butter(4, [200 / (SR / 2), 4000 / (SR / 2)], "band", output="sos")
    y = np.abs(sosfiltfilt(sos, x))
    hop = SR // rate
    n = len(y) // hop
    e = y[: n * hop].reshape(n, hop).mean(axis=1)
    e = np.log1p(e * 50)
    return (e - e.mean()) / (e.std() + 1e-9)


def xcorr_best(a, b):
    """Position of b inside a (lag >= 0 means b starts at a[lag]) and normalized peak."""
    n = len(a) + len(b)
    nfft = 1 << (n - 1).bit_length()
    c = np.fft.irfft(np.fft.rfft(a, nfft) * np.conj(np.fft.rfft(b, nfft)), nfft)
    c = np.concatenate([c[-(len(b) - 1):], c[: len(a)]])
    lags = np.arange(-(len(b) - 1), len(a))
    i = int(np.argmax(c))
    peak = c[i] / (np.sqrt(np.sum(b ** 2) * len(b)) + 1e-9)
    return int(lags[i]), float(peak)


def sync(ep):
    m = load(ep)
    extract(ep, m)
    for s in m["sessions"]:
        A = read_wav(wav_path(ep, s["master"]))
        EA = envelope(A)
        for mem in s["members"]:
            Bx = read_wav(wav_path(ep, mem["name"]))
            EB = envelope(Bx)
            dur = len(Bx) / SR
            probes = []
            for frac in (0.06, 0.2, 0.35, 0.5, 0.65, 0.8, 0.94):
                win = min(30.0, dur * 0.5)
                ws = max(0.0, min(dur - win, frac * dur - win / 2))
                seg = EB[int(ws * 1000): int((ws + win) * 1000)]
                lag, pk = xcorr_best(EA, seg)               # coarse, whole master, 1 ms resolution
                off = lag / 1000 - ws
                # refine on the waveform (+-12 ms) for sub-millisecond precision
                a0 = int((ws + off) * SR)
                ref = Bx[int(ws * SR): int((ws + min(win, 8)) * SR)]
                lo, hi = max(0, a0 - int(.012 * SR)), a0 + int(.012 * SR) + len(ref)
                if lo < hi <= len(A) and len(ref) > 100:
                    l2, _ = xcorr_best(A[lo:hi], ref)
                    off = (lo + l2) / SR - ws
                probes.append({"at": round(ws + win / 2, 2), "offset": round(off, 5), "conf": round(pk, 3)})
            mdur = len(A) / SR
            inside = [p for p in probes if 0 <= p["at"] + p["offset"] <= mdur and p["conf"] > 0.3]
            med = float(np.median([p["offset"] for p in inside])) if inside else 0.0
            good = [p for p in inside if abs(p["offset"] - med) < 0.08]   # consensus, rejects repeated-phrase matches
            ats = np.array([p["at"] for p in good])
            offs = np.array([p["offset"] for p in good])
            k = float(np.polyfit(ats, offs, 1)[0]) if len(good) >= 2 else 0.0
            # offset as a curve over the member's own time: absorbs VFR drift (iPhone)
            curve = [[round(float(a), 2), round(float(o), 5)] for a, o in zip(ats, offs)]
            mem.update(offset=round(med, 5), curve=curve, drift_ms_per_min=round(k * 60000, 2), probes=probes,
                       ok=len(good) >= 3, delta_vs_clock=round(med - mem["expected_offset"], 2))
            flag = "OK " if mem["ok"] else "CHECK"
            print(f"[{flag}] s{s['id']} {mem['role']:7s} {mem['name'][-24:]:24s} offset {med:9.4f}s  "
                  f"drift {k*60000:+6.2f} ms/min  probes {len(good)}/{len(probes)}  vs clock {med - mem['expected_offset']:+.2f}s")
    save(ep, m)


if __name__ == "__main__":
    cmd, ep = sys.argv[1], Path(sys.argv[2])
    if cmd == "scan":
        scan(ep, sys.argv[3])
    elif cmd == "sync":
        sync(ep)
    else:
        import decup_stage2 as st2  # noqa: E402  (transcription / cut / xml)
        getattr(st2, cmd.replace("-", "_"))(ep, sys.argv[3:])
