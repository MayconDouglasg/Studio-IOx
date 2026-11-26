"""Check frames from the project open in After Effects.
  python tools/ae_shots.py <out_dir> <layout|motion> [only-regex | sheets] [t1,t2,...]   (negative t = from the end)
Then builds <out_dir>/sheet_*.jpg contact sheets (one row per scene)."""
import subprocess, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
out = Path(sys.argv[1]).resolve(); out.mkdir(parents=True, exist_ok=True)
motion = sys.argv[2] == "motion"
only = sys.argv[3] if len(sys.argv) > 3 else ""
times = "[" + sys.argv[4] + "]" if len(sys.argv) > 4 else "null"
SHEETS_ONLY = only == "sheets"   # frames already being written by the build itself
if SHEETS_ONLY: only = ""
if not SHEETS_ONLY:
    for f in (out.glob(f"S{only[-2:]}_*.png") if only else out.glob("*.png")): f.unlink()   # with a filter, pass it as ^S07 so only that scene is replaced
    t = (ROOT / "tools" / "ae_shots.jsx").read_text(encoding="utf-8")
    t = t.replace("__OUT__", out.as_posix()).replace("__MOTION__", "true" if motion else "false").replace("__ONLY__", only).replace("__TIMES__", times)
    jsx = out / "shots_run.jsx"; jsx.write_text(t, encoding="utf-8-sig")
    r = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "tools" / "ae_run.ps1"), "-Jsx", str(jsx), "-Done", str(out / "shots_done.txt"), "-Timeout", "900"], capture_output=True, text=True)
    print(r.stdout.strip(), r.stderr.strip()[:300])
    print((out / "shots_done.txt").read_text(encoding="utf-8") if (out / "shots_done.txt").exists() else "no log")
# saveFrameToPng is asynchronous: wait until the PNG count stops growing
import time
last, still = -1, 0
while still < 4:
    n = len(list(out.glob("*.png"))); still = still + 1 if n == last else 0; last = n; time.sleep(1.5)
print(last, "frames")
# contact sheets
pngs = sorted(out.glob("S*.png"))
ids = sorted({p.name[1:3] for p in pngs})
if motion or only:
    for group in [ids[i:i + 6] for i in range(0, len(ids), 6)]:
        rows = [sorted(out.glob(f"S{i}_*.png")) for i in group]
        n = max(len(r_) for r_ in rows)
        ins, lay = [], []
        for ri, r_ in enumerate(rows):
            for ci, p in enumerate(r_):
                ins += ["-i", str(p)]; lay.append(f"{ci * 480}_{ri * 270}")
        k = len(lay)
        fc = "".join(f"[{i}]scale=480:270[v{i}];" for i in range(k)) + "".join(f"[v{i}]" for i in range(k)) + f"xstack=inputs={k}:layout={'|'.join(lay)}:fill=0x444444"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-q:v", "3", str(out / f"sheet_{group[0]}-{group[-1]}.jpg")])
else:
    for gi, group in enumerate([pngs[i:i + 9] for i in range(0, len(pngs), 9)]):
        ins, lay = [], []
        for i, p in enumerate(group):
            ins += ["-i", str(p)]; lay.append(f"{(i % 3) * 640}_{(i // 3) * 360}")
        k = len(lay)
        fc = "".join(f"[{i}]scale=640:360[v{i}];" for i in range(k)) + "".join(f"[v{i}]" for i in range(k)) + f"xstack=inputs={k}:layout={'|'.join(lay)}:fill=0x444444"
        subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-q:v", "3", str(out / f"sheet_{gi + 1}.jpg")])
ms = sorted(out.glob("M*.png"))
if ms:
    ins, lay = [], []
    for i, p in enumerate(ms):
        ins += ["-i", str(p)]; lay.append(f"{(i % 3) * 640}_{(i // 3) * 360}")
    k = len(lay)
    fc = "".join(f"[{i}]scale=640:360[v{i}];" for i in range(k)) + "".join(f"[v{i}]" for i in range(k)) + f"xstack=inputs={k}:layout={'|'.join(lay)}:fill=0x444444"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-q:v", "3", str(out / "sheet_main.jpg")])
print([p.name for p in sorted(out.glob("sheet_*.jpg"))])
