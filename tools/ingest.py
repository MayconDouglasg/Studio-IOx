"""Digest reference videos ONCE so Claude never has to watch them again.

For every new video under clients/<slug>/refs/** it writes clients/<slug>/_digest/<name>/:
  sheet.jpg    one keyframe per shot (max 30), 6 columns, row-major in time order
  digest.json  pacing (cuts/min, shot lengths), motion energy per second, palette,
               brightness/saturation, aspect, audio BPM + loudness, your notes
Already-digested files are skipped (tracked in _digest/index.json by size + mtime).
A sidecar "<video>.txt" next to a video is copied in as your notes ("gostei da transição em 0:42").

Usage:  python tools/ingest.py <client slug or folder>     (all new refs)
        python tools/ingest.py <client> --force             (redo everything)
        python tools/ingest.py <client> --max-seconds 180   (only the first 3 min of long videos)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}
FPS_A = 10          # analysis frame rate
AW = 96             # analysis width (px)


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, **kw)


def probe(path):
    r = run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height,r_frame_rate:format=duration",
             "-of", "json", str(path)], text=True)
    d = json.loads(r.stdout)
    v = next((s for s in d["streams"] if s["codec_type"] == "video"), None)
    a = any(s["codec_type"] == "audio" for s in d["streams"])
    num, den = (v["r_frame_rate"].split("/") + ["1"])[:2]
    return float(d["format"]["duration"]), v["width"], v["height"], float(num) / float(den or 1), a


def frames(path, w, h, limit):
    ah = int(round(AW * h / w / 2) * 2)
    cmd = ["ffmpeg", "-v", "error"] + (["-t", str(limit)] if limit else []) + [
        "-i", str(path), "-vf", f"fps={FPS_A},scale={AW}:{ah}:flags=area", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"]
    raw = run(cmd).stdout
    n = len(raw) // (AW * ah * 3)
    return np.frombuffer(raw[: n * AW * ah * 3], np.uint8).reshape(n, ah, AW, 3)


def palette(fr, k=6):
    from sklearn.cluster import KMeans
    px = fr[:: max(1, len(fr) // 400), ::3, ::3].reshape(-1, 3).astype(np.float32)
    km = KMeans(n_clusters=k, n_init=4, random_state=0).fit(px)
    share = np.bincount(km.labels_, minlength=k) / len(px)
    order = np.argsort(-share)
    return [{"hex": "#%02X%02X%02X" % tuple(int(c) for c in km.cluster_centers_[i]), "share": round(float(share[i]), 3)} for i in order]


def audio_stats(path, limit):
    out = {}
    with tempfile.TemporaryDirectory() as td:
        wav = os.path.join(td, "a.wav")
        run(["ffmpeg", "-v", "error", "-y"] + (["-t", str(limit)] if limit else []) + ["-i", str(path), "-vn", "-ac", "1", "-ar", "22050", wav])
        if not os.path.exists(wav):
            return out
        r = run(["ffmpeg", "-hide_banner"] + (["-t", str(limit)] if limit else []) + ["-i", str(path), "-vn", "-af", "ebur128", "-f", "null", "-"], text=True)
        m = re.findall(r"I:\s+(-?[\d.]+) LUFS", r.stderr)
        if m:
            out["lufs"] = float(m[-1])
        try:
            import librosa
            y, sr = librosa.load(wav, sr=22050, duration=180)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            out["bpm"] = round(float(np.atleast_1d(tempo)[0]), 1)
        except Exception as e:  # noqa: BLE001
            out["bpm_error"] = str(e)[:80]
    return out


def note_limit(path):
    """Read 'até 00:55' / '50sec' / '2:40' / 'segundo 42' from the sidecar .txt -> seconds."""
    n = path.with_suffix(".txt")
    if not n.exists():
        return None
    t = n.read_text(encoding="utf-8", errors="ignore").lower()
    m = re.search(r"(\d{1,2}):(\d{2})", t)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    m = re.search(r"(?:segundo|seg)\s*(\d{1,4})", t) or re.search(r"(\d{1,4})\s*(?:sec|seg|segundos|s)(?![a-z])", t)
    return int(m.group(1)) if m else None


def digest(path, outdir, limit):
    nl = note_limit(path)
    if nl:
        limit = nl + 3          # a little past the point the user named
    dur, w, h, fps, has_a = probe(path)
    span = min(dur, limit) if limit else dur
    fr = frames(path, w, h, limit)
    g = fr.mean(axis=3)
    diff = np.abs(np.diff(g, axis=0)).mean(axis=(1, 2)) if len(g) > 1 else np.zeros(0)
    # hard cuts: big spike vs the local median
    cuts = []
    for i, d in enumerate(diff):
        lo, hi = max(0, i - 15), min(len(diff), i + 16)
        if d > 22 and d > 3.0 * (np.median(diff[lo:hi]) + 1):
            t = (i + 1) / FPS_A
            if not cuts or t - cuts[-1] > 0.15:
                cuts.append(round(t, 2))
    bounds = [0.0] + cuts + [span]
    shots = np.diff(bounds)
    # motion energy per second, ignoring the cut frames themselves
    md = diff.copy()
    for c in cuts:
        md[max(0, int(c * FPS_A) - 1)] = 0
    per_sec = [round(float(md[i: i + FPS_A].mean()), 1) for i in range(0, len(md), FPS_A)]
    hsv_s = (fr.max(axis=3).astype(int) - fr.min(axis=3)) / np.maximum(fr.max(axis=3), 1)

    # keyframe sheet: the middle of each shot, max 30 evenly chosen
    mids = [(bounds[i] + bounds[i + 1]) / 2 for i in range(len(bounds) - 1)]
    if span <= 240:
        mids = list(np.linspace(0.4, span - 0.4, min(30, max(6, int(span / 1.5)))))
    elif len(mids) > 30:
        mids = [mids[int(round(j))] for j in np.linspace(0, len(mids) - 1, 30)]
    with tempfile.TemporaryDirectory() as td:
        for j, t in enumerate(mids):
            run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(path), "-frames:v", "1",
                 "-vf", "scale=-2:300:flags=lanczos,pad=iw+6:ih+6:3:3:color=0x333333", os.path.join(td, f"k{j:03d}.png")])
        rows = (len(mids) + 5) // 6
        run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", os.path.join(td, "k%03d.png"),
             "-vf", f"tile=6x{rows}:color=0x333333", "-frames:v", "1", "-q:v", "3", str(outdir / "sheet.jpg")])

    notes = path.with_suffix(".txt")
    d = {
        "file": path.name,
        "kind": path.parent.name,                       # canal | inspiracao
        "duration_s": round(dur, 2), "analyzed_s": round(span, 2),
        "resolution": f"{w}x{h}", "aspect": "vertical" if h > w else "horizontal" if w > h else "square", "fps": round(fps, 2),
        "shots": len(shots), "cuts_per_min": round(len(cuts) / span * 60, 1),
        "shot_len_s": {"median": round(float(np.median(shots)), 2), "min": round(float(shots.min()), 2), "max": round(float(shots.max()), 2)},
        "motion_energy": {"mean": round(float(md.mean()), 1) if len(md) else 0, "p90": round(float(np.percentile(md, 90)), 1) if len(md) else 0, "per_second": per_sec[:300]},
        "brightness": round(float(g.mean() / 255), 2), "saturation": round(float(hsv_s.mean()), 2),
        "palette": palette(fr),
        "audio": audio_stats(path, limit) if has_a else None,
        "sheet": "sheet.jpg", "sheet_times_s": [round(t, 2) for t in mids],
        "cuts_s": cuts[:200],
        "notes": notes.read_text(encoding="utf-8").strip() if notes.exists() else "",
    }
    (outdir / "digest.json").write_text(json.dumps(d, indent=1, ensure_ascii=False), encoding="utf-8")
    return d


def main():
    args = sys.argv[1:]
    client = Path(args[0])
    if not client.is_dir():                       # a slug: resolve the client folder on this PC
        sys.path.insert(0, str(Path(__file__).parent))
        import studio
        client = studio.client_dir(args[0])
    force = "--force" in args
    limit = float(args[args.index("--max-seconds") + 1]) if "--max-seconds" in args else None
    dg = client / "_digest"
    dg.mkdir(exist_ok=True)
    idx_p = dg / "index.json"
    idx = json.loads(idx_p.read_text(encoding="utf-8")) if idx_p.exists() else {}
    new = []
    for p in sorted((client / "refs").rglob("*")):
        if p.suffix.lower() not in VIDEO:
            continue
        rel = p.relative_to(client).as_posix()
        st = p.stat()
        sig = f"{st.st_size}:{int(st.st_mtime)}"
        if not force and idx.get(rel, {}).get("sig") == sig:
            continue
        name = re.sub(r"[^\w\-]+", "_", f"{p.parent.name}__{p.stem}")[:80]
        od = dg / name
        od.mkdir(parents=True, exist_ok=True)
        print(f"digesting {rel} ...", flush=True)
        d = digest(p, od, limit)
        idx[rel] = {"sig": sig, "digest": f"_digest/{name}", "summary":
                    f"{d['aspect']} {d['resolution']} | {d['cuts_per_min']} cuts/min | median shot {d['shot_len_s']['median']}s | "
                    f"motion {d['motion_energy']['mean']} | bpm {(d['audio'] or {}).get('bpm')} | lufs {(d['audio'] or {}).get('lufs')}",
                    "in_style": False}
        new.append(rel)
        idx_p.write_text(json.dumps(idx, indent=1, ensure_ascii=False), encoding="utf-8")
    pending = [k for k, v in idx.items() if not v.get("in_style")]
    print(f"\nnew digests: {len(new)}  |  not yet folded into STYLE.md: {len(pending)}")
    for k in pending:
        print(f"  {k}  ->  {idx[k]['digest']}/sheet.jpg   [{idx[k]['summary']}]")


if __name__ == "__main__":
    main()
