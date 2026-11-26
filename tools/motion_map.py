"""Resolve a scenes spec against the final-timeline words -> exact motion map.
  python tools/motion_map.py <episode_dir>
Reads  <episode>/motion/scenes_spec.json + study/final_words.json + study/study.json (segments)
Writes <episode>/motion/motion_map.json   (single source for storyboard and After Effects script)
Each scene is anchored to the first word of its `anchor` phrase near `near` seconds; it is trimmed so it
never overlaps the next scene, an AI insert or the logo sting.
"""
import json
import sys
import unicodedata
import re
from pathlib import Path


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9% ]+", " ", t).split()


ep = Path(sys.argv[1])
spec = json.loads((ep / "motion" / "scenes_spec.json").read_text(encoding="utf-8"))
W = json.loads((ep / "study" / "final_words.json").read_text(encoding="utf-8"))
segs = json.loads((ep / "study" / "study.json").read_text(encoding="utf-8"))["segments"]
blocked = [(s["s"], s["e"], s["role"]) for s in segs if s["role"] in ("broll_ia", "logo")]
toks = [(" ".join(norm(w["w"])), i) for i, w in enumerate(W)]


def find(anchor, near):
    a = norm(anchor)
    best = None
    for i in range(len(W)):
        j, k = i, 0
        while k < len(a) and j < len(W):
            wt = " ".join(norm(W[j]["w"])).replace(" ", "")
            if not wt:
                j += 1
                continue
            if wt != a[k].replace(" ", ""):
                break
            j += 1
            k += 1
        if k == len(a):
            d = abs(W[i]["t"] - near)
            if best is None or d < best[0]:
                best = (d, i, j)
    return best


def cam_at(t):
    for s in segs:
        if s["s"] <= t < s["e"]:
            return s["role"]
    return "?"


out, misses = [], []
for n, sc in enumerate(spec["scenes"], 1):
    hit = find(sc["anchor"], sc["near"])
    if not hit or hit[0] > 8:
        misses.append((n, sc["anchor"], sc["near"], hit[0] if hit else None))
        t = sc["near"]
        said = ""
    else:
        _, i, j = hit
        t = W[i]["t"]
        said = " ".join(w["w"] for w in W[max(0, i - 6): j + 10])
    if sc.get("at") is not None:            # fixed start (e.g. an opening that begins before the first word)
        t = sc["at"]
    out.append({**sc, "id": n, "t": round(t, 3), "said": said, "cam_measured": cam_at(t + .05)})

# trims: no overlap with next scene, AI inserts or the logo sting
for k, sc in enumerate(out):
    end = sc["t"] + sc["dur"]
    if k + 1 < len(out):
        end = min(end, out[k + 1]["t"] - .1)
    for a, b, r in blocked:
        if sc["t"] < a < end:
            end = a - .1
    sc["te"] = round(max(sc["t"] + 1.2, end), 3)
    sc["tc"] = f"{int(sc['t'] // 60):02d}:{sc['t'] % 60:05.2f}"
    sc["warn"] = [f"{r} at {a:.1f}s" for a, b, r in blocked if sc["t"] < b and sc["te"] > a]

(ep / "motion" / "motion_map.json").write_text(json.dumps({"episode": spec["episode"], "types": spec.get("types", {}), "scenes": out}, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"{len(out)} scenes resolved, {len(misses)} anchors not found")
for m in misses:
    print("  MISS", m)
for sc in out:
    flag = " !" + ";".join(sc["warn"]) if sc["warn"] else ""
    cm = {"frontal": "F", "lateral": "L", "tela": "TELA", "broll_ia": "IA"}.get(sc["cam_measured"], sc["cam_measured"])
    exp = sc.get("cam", "-")
    mism = "" if exp in ("-",) or exp == cm else f"  (cam spec {exp} vs real {cm})"
    print(f"{sc['id']:2d} {sc['tc']} {sc['te']-sc['t']:4.1f}s {sc['type']:15s} {cm:4s}{mism}{flag}")
