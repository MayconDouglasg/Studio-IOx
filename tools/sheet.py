"""Contact sheet of one scene's check frames:  python tools/sheet.py <check_dir> <scene id e.g. 01> [cols=4] [tile width=960]"""
import subprocess, sys
from pathlib import Path
d = Path(sys.argv[1]); sid = sys.argv[2]; cols = int(sys.argv[3]) if len(sys.argv) > 3 else 4; w = int(sys.argv[4]) if len(sys.argv) > 4 else 960
fs = sorted(d.glob(f"S{sid}_*.png")); h = w * 9 // 16
ins, lay = [], []
for i, p in enumerate(fs):
    ins += ["-i", str(p)]; lay.append(f"{(i % cols) * w}_{(i // cols) * h}")
k = len(fs)
fc = "".join(f"[{i}]scale={w}:{h}[v{i}];" for i in range(k)) + "".join(f"[v{i}]" for i in range(k)) + f"xstack=inputs={k}:layout={'|'.join(lay)}:fill=0x777777"
subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-q:v", "3", str(d / f"scene_{sid}.jpg")])
print(d / f"scene_{sid}.jpg", k)
