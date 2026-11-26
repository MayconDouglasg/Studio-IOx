"""Study what the editor really delivered, to learn from it (read-only, nothing is saved).
  python tools/study_final.py ae  "<final.aep>"  <out_dir> [--ae "<AfterFX.exe>"]  -> <out_dir>/study.txt
      (every comp/layer/key/expression; --ae when the project was saved by a newer After, e.g. the 2027 beta)
  python tools/study_final.py ae-detail <out_dir> [--ae ...]   -> study_detail.txt: second pass on the project left
      open (what each text animator changes, range selector, effect parameters, masks)
  python tools/study_final.py pr  "<project.prproj>" "<sequence name>" <out_dir>
                                       -> <out_dir>/sequence.json + sequence.txt (every track, clip, effect, transition)
The After study opens the project in After Effects through tools/ae_run.ps1 and never saves it.
The Premiere study reads the .prproj (gzip XML) directly; Premiere does not need to be open."""
import gzip
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
TICKS = 254016000000  # Premiere ticks per second


def ae(aep, out, ae_exe="", detail=False):
    """detail=True: second pass on the project already open (text animators, effect params, masks)"""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    t = (TOOLS / ("ae_study_detail.jsx" if detail else "ae_study.jsx")).read_text(encoding="utf-8")
    t = t.replace("__AEP__", Path(aep).resolve().as_posix() if aep else "").replace("__OUT__", out.resolve().as_posix())
    jsx = out / ("ae_detail_run.jsx" if detail else "ae_study_run.jsx"); jsx.write_text(t, encoding="utf-8-sig")
    done = out / ("detail_done.txt" if detail else "study_done.txt")
    r = subprocess.run(["powershell", "-ExecutionPolicy", "Bypass", "-File", str(TOOLS / "ae_run.ps1"), "-Jsx", str(jsx),
                        "-Done", str(done), "-Timeout", "900"] + (["-AfterExe", ae_exe] if ae_exe else []),
                       capture_output=True, text=True)
    print(r.stdout.strip())
    s = out / ("study_detail.txt" if detail else "study.txt")
    if s.exists():
        lines = s.read_text(encoding="utf-8").splitlines()
        print(f"{s}  ({len(lines)} lines, {sum(l.startswith('COMP') for l in lines)} comps)")


# ---------------- Premiere (.prproj) ----------------
BASIC = {"Motion", "Opacity", "Time Remapping", "Volume", "Channel Volume", "Panner", "Movimento", "Opacidade",
         "Remapeamento de tempo", "Volume do canal", "Panorâmica"}


def graphic_text(b64):
    """Premiere Graphic 'Source Text': 8-byte header + UTF-16LE JSON -> 'text' [font size color]"""
    import base64, re
    try:
        raw = base64.b64decode(b64)
        s = raw[8:].decode("utf-16le", "ignore")
        s = s[:s.rfind("}") + 1]
        j = json.loads(s)
    except Exception:
        return None
    tp = j.get("mTextParam", {})
    st = tp.get("mStyleSheet", {})
    text = st.get("mText") or tp.get("mText") or ""
    font = (st.get("mFontName") or {}).get("mParamValues", [[0, ""]])[0][1] if isinstance(st.get("mFontName"), dict) else st.get("mFontName")
    size = (st.get("mFontSize") or {}).get("mParamValues", [[0, ""]])[0][1] if isinstance(st.get("mFontSize"), dict) else st.get("mFontSize")
    col = None
    try:
        fc = st.get("mFillColor", {}).get("mParamValues", [[0, None]])[0][1]
        col = "#%06X" % (int(fc) & 0xFFFFFF) if fc is not None else None
    except Exception:
        pass
    text = re.sub(r"\s+", " ", text).strip()
    try:
        size = round(float(size))
    except (TypeError, ValueError):
        pass
    return '"%s" [%s %s%s]' % (text, font, size, " " + col if col else "")


def pr(prproj, seq_name, out):
    """Every track of a sequence: clips (media, nested sequence, After linked comp, mogrt), times, disabled,
    effects with keyframed params, transitions. With two sequences of the same name, the exported one wins."""
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    root = ET.fromstring(gzip.open(prproj).read())
    by_id = {e.get("ObjectID"): e for e in root if e.get("ObjectID")}
    by_uid = {e.get("ObjectUID"): e for e in root if e.get("ObjectUID")}
    blobs = {}
    for e in root.iter("StartKeyframeValue"):
        if e.get("BinaryHash") and e.text and e.text.strip(): blobs.setdefault(e.get("BinaryHash"), e.text.strip())

    def ref(e):
        if e is None: return None
        return by_id.get(e.get("ObjectRef")) if e.get("ObjectRef") else by_uid.get(e.get("ObjectURef"))

    def txt(e, p, d=None):
        x = e.find(p) if e is not None else None
        return x.text if x is not None and x.text is not None else d

    seqs = [s for s in root.findall("Sequence") if txt(s, "Name") == seq_name]
    if not seqs:
        sys.exit(f"sequence not found: {seq_name!r}; sequences: {sorted({txt(s, 'Name') or '' for s in root.findall('Sequence')})}")

    def exported(s):
        v = txt(s, "Node/Properties/ExportSettings.Info.SaveAsFile") or ""
        return (1 if '"DoExport":true' in v else 0, len(ET.tostring(s)))
    seq = max(seqs, key=exported)

    def sec(t):
        return round(int(t) / TICKS, 3)

    def source_of(sub):
        clip = ref(sub.find("Clip")); info = {"name": txt(sub, "Name")}
        if clip is None: return info
        info["in"] = sec(txt(clip, "Clip/InPoint", "0")); info["out"] = sec(txt(clip, "Clip/OutPoint", "0"))
        src = ref(clip.find("Clip/Source"))
        if src is not None:
            if src.find("MediaSource/Media") is not None:
                m = ref(src.find("MediaSource/Media"))
                path = txt(m, "FilePath") or txt(m, "Title") or ""
                info["media"] = path
                if path.lower().endswith(".aep") or "Linked Comp" in (info["name"] or ""): info["kind"] = "after"
            elif src.find("SequenceSource/Sequence") is not None:
                info["seq"] = txt(ref(src.find("SequenceSource/Sequence")), "Name")
        return info

    def effects(ti):
        chain = ref(ti.find("ClipTrackItem/ComponentOwner/Components"))
        res = []
        if chain is None: return res
        for c in chain.findall("ComponentChain/Components/Component"):
            comp = ref(c)
            if comp is None: continue
            name = txt(comp, "Component/DisplayName") or comp.tag
            keyed, vals = [], {}
            for p in comp.findall("Component/Params/Param"):
                pp = ref(p)
                if pp is None: continue
                pn = txt(pp, "Name") or ""
                skv = pp.find("StartKeyframeValue")
                if name == "Text" and pn == "Source Text" and skv is not None:
                    # identical blobs are stored once: later copies carry only the BinaryHash
                    t = graphic_text((skv.text or "").strip() or blobs.get(skv.get("BinaryHash"), ""))
                    if t: vals["_text"] = t
                    continue
                kf = txt(pp, "Keyframes")
                if kf:
                    ks = [k for k in kf.split(";") if k.strip()]
                    pts = []
                    for k in ks[:4]:
                        f = k.split(",")
                        try: pts.append(f"{sec(f[0]):.2f}s={f[1].rstrip('.')}")
                        except (ValueError, IndexError): pass
                    keyed.append(f"{pn}[{len(ks)}k {' '.join(pts)}]")
                else:
                    cv = txt(pp, "CurrentValue")
                    if cv is None:
                        sk = (txt(pp, "StartKeyframe") or "").split(",")
                        cv = sk[1] if len(sk) > 1 else None
                    if cv not in (None, ""): vals[pn] = cv
            res.append({"name": name, "match": txt(comp, "MatchName") or "", "keyed": keyed, "vals": vals})
        return res

    result = {"sequence": seq_name, "uid": seq.get("ObjectUID"), "tracks": []}
    for g in seq.findall("TrackGroups/TrackGroup"):
        grp = ref(g.find("Second"))
        if grp is None: continue
        kind = {"VideoTrackGroup": "V", "AudioTrackGroup": "A"}.get(grp.tag)
        if not kind: continue
        for tr in grp.findall("TrackGroup/Tracks/Track"):
            t = ref(tr)
            if t is None: continue
            items = []
            for ti_ref in t.findall("ClipTrack/ClipItems/TrackItems/TrackItem"):
                ti = ref(ti_ref)
                if ti is None: continue
                b = ti.find("ClipTrackItem/TrackItem")
                d = {"start": sec(txt(b, "Start", "0")), "end": sec(txt(b, "End", "0")),
                     "off": any(x.text == "true" for x in ti.iter("IsMuted"))}
                if ti.find(".//BE.RushInspectorPanel.MogrtIdentifier") is not None: d["kind"] = "mogrt"
                sub = ref(ti.find("ClipTrackItem/SubClip"))
                if sub is not None:
                    for k, v in source_of(sub).items():
                        if k == "kind" and d.get("kind"): continue
                        d[k] = v
                d["fx"] = effects(ti)
                items.append(d)
            for ti_ref in t.findall("ClipTrack/TransitionItems/TrackItems/TrackItem"):
                ti = ref(ti_ref)
                if ti is None: continue
                b = ti.find("TransitionTrackItem/TrackItem")
                items.append({"start": sec(txt(b, "Start", "0")), "end": sec(txt(b, "End", "0")),
                              "transition": txt(ti, "TransitionTrackItem/DisplayName")})
            items.sort(key=lambda x: x["start"])
            if items: result["tracks"].append({"track": f"{kind}{int(tr.get('Index')) + 1}", "items": items})
    (out / "sequence.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")

    lines = [f"SEQUENCE {seq_name}"]
    for t in result["tracks"]:
        n_cl = sum(1 for d in t["items"] if "transition" not in d)
        lines.append(f"\n{t['track']}: {n_cl} clips, {len(t['items']) - n_cl} transitions")
        for d in t["items"]:
            if "transition" in d:
                lines.append(f"  {d['start']:8.2f}-{d['end']:8.2f}   ~ {d['transition']}"); continue
            what = f"[nested] {d['seq']}" if d.get("seq") else (d.get("name") or "?")
            if d.get("kind"): what += f" ({d['kind']})"
            fx = []
            for c in d["fx"]:
                if c["name"] in BASIC and not c["keyed"]:
                    v = c["vals"]
                    if c["name"] in ("Motion", "Movimento") and v.get("Scale", "100").rstrip(".") != "100":
                        fx.append(f"scale {v.get('Scale').rstrip('.')}")
                    if c["name"] in ("Opacity", "Opacidade") and v.get("Opacity", "100").rstrip(".") != "100":
                        fx.append(f"opacity {v.get('Opacity')}")
                    continue
                if c["vals"].get("_text"): fx.append("TEXT " + c["vals"]["_text"])
                fx.append(c["name"] + (" " + " ".join(c["keyed"]) if c["keyed"] else ""))
            src = f" @src {d['in']:.2f}" if "in" in d else ""
            lines.append(f"  {d['start']:8.2f}-{d['end']:8.2f} {'OFF ' if d['off'] else ''}{what}{src}" + (f"  | {'; '.join(fx)}" if fx else ""))
    (out / "sequence.txt").write_text("\n".join(lines), encoding="utf-8")
    print(out / "sequence.txt", sum(len(t["items"]) for t in result["tracks"]), "items in", len(result["tracks"]), "tracks")


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a: sys.exit(__doc__)
    ae_exe = a[a.index("--ae") + 1] if "--ae" in a else ""
    if a[0] == "ae-detail": ae("", a[1], ae_exe, detail=True)
    elif a[0] == "ae": ae(a[1], a[2], ae_exe)
    elif a[0] == "pr": pr(a[1], a[2], a[3])
    else: sys.exit(__doc__)
