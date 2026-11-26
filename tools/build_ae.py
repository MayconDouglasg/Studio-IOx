"""Generate the After Effects build scripts from the approved motion map (see the after-handoff skill).
  python tools/build_ae.py <episode_dir> "<reference edit mp4>" [layout] [motion] [--out <folder>]
Writes <episode>/after/<episode>_01_layout_build.jsx and _02_animado_build.jsx from tools/ae_builder.jsx.
Run them with tools/ae_run.ps1. Each creates a new project, saves <episode>/after/<episode>_01_layout.aep /
_02_animado.aep and writes build_log_<mode>.txt. Then check frames with tools/ae_shots.py.

Scene flags: the film's first scene (t < 0.3 s, OPEN-WALL or "abre": true) opens close on its content and pulls
back (frame 0 never empty); the last scene (or "fecha": true) ends on a gentle pull-out and never on a whip.
PAGINAS scenes carry "blocks" (each a lockup spec: lock / key / serif / small ...): the camera travels between them.
Composed scenes: <episode>/motion/composicao_after.json ("cenas" keyed by the scene code) lists each scene's elements in
px of the approved still (texto, icone, caixa, circulo, linha, media, grupo, moeda, segmentos), each entering on a
spoken word, plus the camera (deriva | viagem between stops on the world). Built by tools/ae_composto.jsx. Its "corte"
maps the word times to a newer cut of the editor (insertions after a time), "icones" lists where icons are found
(after <episode>/assets/icones/<name>.svg, the official ones), "media" names the files the elements use.
Reads: <episode>/motion/motion_map.json, study/final_words.json (+ study.json for the length),
       episode.json (vocab, partner world, generated media), the client's client.json (colors, fonts, motion).
"""
import json
import re
import subprocess
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import studio  # noqa: E402
import svg_shapes  # noqa: E402

ep = Path(sys.argv[1]).resolve()
REF = Path(sys.argv[2]).resolve()
MODES = [a for a in sys.argv[3:] if a in ("layout", "motion")]   # optional (default both)
OUT = sys.argv[sys.argv.index("--out") + 1] if "--out" in sys.argv else None   # e.g. a test folder, so delivered .aep are never overwritten
ROOT = studio.ROOT
SLUG = studio.client_of(ep)
CJ = studio.client_json(SLUG)
EPJ = studio.episode_json(ep)
PARTNER = EPJ.get("partner") or {}
mm = json.loads((ep / "motion" / "motion_map.json").read_text(encoding="utf-8"))
W = json.loads((ep / "study" / "final_words.json").read_text(encoding="utf-8"))
out = Path(OUT).resolve() if OUT else ep / "after"
(out / "assets").mkdir(parents=True, exist_ok=True)
fwd = lambda p: str(Path(p).resolve()).replace("\\", "/")  # noqa: E731
res = lambda p: fwd(studio.resolve(p, ep))  # noqa: E731


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9%]+", " ", t).split()


def mixhex(a, b, k):
    A, B = [int(a.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)], [int(b.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x + (y - x) * k):02X}" for x, y in zip(A, B))


def cap(s):
    return s[:1].upper() + s[1:] if s else s


# ---- composed scenes (motion/composicao_after.json): element lists per scene code, built by ae_composto.jsx
COMPF = ep / "motion" / "composicao_after.json"
COMPO = json.loads(COMPF.read_text(encoding="utf-8")) if COMPF.exists() else {}
INS = sorted((COMPO.get("corte") or {}).get("insercoes") or [])


def shift(t):
    """word time of the cut the map was made on -> time on the reference cut (insertions the editor made after it)"""
    return round(t + sum(d for at, d in INS if t >= at), 3)


# ---- generated clips (wall, phone screens, hook squares)
results = studio.generated_media(ep)

# ---- partner world still (real site print) for partner cards
site_png = None
if PARTNER:
    site_png = studio.resolve(PARTNER.get("site") or "after/assets/partner_site.png", ep)
    if not site_png.exists() and PARTNER.get("site_from_reference_at_s") is not None:
        site_png.parent.mkdir(parents=True, exist_ok=True)
        vf = ["-vf", f"crop={PARTNER['site_crop']}"] if PARTNER.get("site_crop") else []
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(PARTNER["site_from_reference_at_s"]), "-i", str(REF), "-frames:v", "1", *vf, str(site_png)])
    if not site_png.exists():
        site_png = None


def lines_of(s):
    sm = s.get("small") or []
    K = lambda t, st=False: {"k": "key", "t": t, "strike": bool(st)}  # noqa: E731
    S = lambda t: {"k": "ser", "t": t}  # noqa: E731
    M = lambda t: {"k": "sm", "t": t}  # noqa: E731
    L, lk = [], s.get("lock")
    if lk == "A":
        L += [[K(cap(s["key"]), s.get("strike"))], [S(s["serif"])]]
        if sm: L.append([M(sm[0])])
    elif lk == "B":
        if sm and sm[0]: L.append([M(cap(sm[0]))])
        L.append([K(s["key"] if sm and sm[0] else cap(s["key"]), s.get("strike"))])
        L.append([M(sm[1]), S(s["serif"])] if len(sm) > 1 and sm[1] else [S(s["serif"])])
    elif lk == "C":
        L += [[K(cap(s["key"]), s.get("strike"))], [M(sm[0]), S(s["serif"])] if sm else [S(s["serif"])]]
        if len(sm) > 1: L.append([M(sm[1])])
    elif lk == "D":
        L += [[S(cap(s["serif"]))], [K(s["key"]), {"k": "stack", "t": sm}]]
    elif lk == "LIST":
        if s.get("title"): L += [[M(cap(s["title"][0]))], [K(s["title"][1])]]
        for rw in s.get("rows") or []: L.append([M(cap(rw[0])), K(rw[1], True)])
        L.append([S(cap(s["serif"]))])
    else:
        L.append([S(cap(s.get("serif") or ""))])
    return L


# ---- when is each row said? Anchor on the row's meaningful words, not its first word
STOP = set(norm("a o e de da do das dos em no na nos nas um uma uns umas que se ou para pra por com sem nao nem eu tu ele ela "
                "isto isso ao as os mais muito ja the and of to in is it"))
SPEECH = [(t, w["t"]) for w in W for t in norm(w["w"]) if t not in STOP]


def _eq(a, b):
    return a == b or (len(a) >= 5 and len(b) >= 5 and a[:5] == b[:5])


def row_time(row, t0, t1, after):
    segs = [x for x in row if x["k"] in ("key", "ser")] or row
    txt = " ".join(x["t"] if isinstance(x["t"], str) else " ".join(x["t"]) for x in segs)
    c = [t for t in norm(txt) if t not in STOP] or norm(txt)
    if not c:
        return None
    win = [(t, tt) for t, tt in SPEECH if max(t0 - .4, after) <= tt <= t1]
    for i in range(len(win)):                                   # 1) the row's words in order
        if all(i + k < len(win) and _eq(win[i + k][0], c[k]) for k in range(len(c))):
            return win[i][1]
    for tok in sorted(c, key=len, reverse=True):                # 2) its strongest word, 3) any of its words
        hit = next((tt for t, tt in win if _eq(t, tok)), None)
        if hit is not None:
            return hit
    return None


# ---- transitions of full-frame cards: rotate, never the same twice in a row (override per scene with "trans")
CYCLE = CJ["motion"].get("transitions") or ["wipe", "whip", "cut", "iris"]
LONG = CJ["motion"].get("long_scene_s", 6)
prev_tr, k_tr = None, 0

GRADE = CJ.get("grade") or {}
RITMO = CJ.get("ritmo") or {}


def timed_rows(rows, t0, t1, last):
    times = []
    for rw in rows:
        tt = row_time(rw, t0, t1, last)
        if tt is not None:
            last = tt
        times.append(None if tt is None else round(max(0.0, tt - t0 - .12), 3))
    out_, prev = [], -0.3
    for rw, t_ in zip(rows, times):                 # missing / out-of-order times: enter 0.3 s after the previous row
        if t_ is None or t_ < prev:
            t_ = round(prev + 0.3, 3)
        out_.append({"segs": rw, "t0": t_})
        prev = t_
    return out_, last



# ---- composed scenes: resolve words -> times, colours -> hex, icons -> AE paths, media -> files
COLS = {"ink": CJ["colors"]["ink"], "paper": CJ["colors"]["paper"], "acc": CJ["colors"]["accent"],
        "accL": CJ["colors"].get("accent_light", CJ["colors"]["accent"]), "accD": CJ["colors"].get("accent_deep", CJ["colors"]["accent"]),
        "glow": CJ["colors"].get("paper_glow", CJ["colors"]["paper"]), "grid": CJ["colors"].get("grid", CJ["colors"]["paper"]),
        "lime": PARTNER.get("accent", CJ["colors"]["accent"]), "hfbg": PARTNER.get("bg", CJ["colors"]["paper"])}
COLS["line2"] = mixhex(COLS["paper"], COLS["acc"], 0.3)       # paper / accent 30 % (a tint, never a new colour)
ICON_SRC = [ep / "assets" / "icones"] + [studio.resolve(p, ep) for p in COMPO.get("icones") or []]
K_ASC = {"key": (0.968, 1.219), "sm": (0.968, 1.219), "eye": (0.968, 1.219), "ser": (1.069, 1.362)}   # hhea ascent, ascent+descent (em)


def col(c):
    if c in (None, "grad", "blue"):
        return c
    return COLS.get(c, c)


def compose(s, cfg, warns):
    t0, t1 = s["t"], s["te"]
    dur = t1 - t0
    words = [(norm(w["w"]), w["t"]) for w in W if t0 - .6 <= w["t"] <= t1 + .6]

    def word(spec):
        ws = norm(spec["palavra"])
        hits = [tt for tk, tt in words if tk and ws and _eq(tk[0], ws[0])]
        n = int(spec.get("n", 1))
        if len(hits) > 1 and "n" not in spec:      # said twice in the scene: say which one ("n": 2), else the first wins
            warns.append(f"scene {s['code']}: '{spec['palavra']}' is said {len(hits)} times in the scene, using the 1st (add \"n\")")
        if len(hits) < n:
            warns.append(f"scene {s['code']}: word '{spec['palavra']}' not found in {t0:.2f}-{t1:.2f}")
            return 0.0
        return hits[n - 1] - t0

    def when(spec, lead=0.0):
        if spec is None:
            return None
        if isinstance(spec, (int, float)):
            return round(float(spec), 3)
        if "fim" in spec:
            return round(dur + 0.15 + spec["fim"], 3)
        base = word(spec) - lead if "palavra" in spec else float(spec.get("t", 0))
        return round(base + spec.get("d", 0), 3)

    def entra(spec):
        if not spec:
            return None
        o = dict(spec)
        o["t"] = when(spec, lead=0.08 if "palavra" in spec else 0)
        return o

    def el(E):
        E = dict(E)
        T = E["tipo"]
        if "entra" in E:
            E["entra"] = entra(E["entra"])
        if "acende" in E:
            E["acende"] = {"t": when(E["acende"])}
        if E.get("anim"):
            E["anim"] = [dict(a, t0=when(a["de"]), t1=when(a["ate"])) for a in E["anim"]]
        for k in ("cor", "fill", "brilho"):
            if isinstance(E.get(k), str) and not (k == "brilho" and E[k] in ("suave", "forte", "nenhum")):
                E[k] = col(E[k])
        if E.get("borda"):
            E["borda"] = [col(E["borda"][0])] + E["borda"][1:]
        if E.get("pilula"):
            E["pilula"] = dict(E["pilula"], cor=col(E["pilula"]["cor"]))
        if T == "texto":
            parts = []
            for p in E["partes"]:
                p = dict(p, cor=col(p.get("cor", "ink")))
                if p.get("entra"):
                    p["entra"] = entra(p["entra"])
                parts.append(p)
            E["partes"] = parts
            lh = E.get("lh", 1.0)
            E["base"] = round(E["top"] + max((lh - K_ASC[p["f"]][1]) / 2 * p["size"] + K_ASC[p["f"]][0] * p["size"] for p in parts), 2)
            wtot = sum(len(p["t"]) * p["size"] * 0.55 for p in parts)
            x0 = E["x"] - wtot / 2 if E.get("alinha") == "centro" else E["x"]
            E["bbox"] = [x0, E["top"], x0 + wtot, E["top"] + max(p["size"] for p in parts)]
        elif T == "icone":
            if E.get("svg"):
                ic = {"vb": E.get("vb") or [0, 0, 100, 100], "els": svg_shapes.elements(E["svg"], "stroke"), "from": "desenho do storyboard"}
            else:
                ic = svg_shapes.icon(E["nome"], ICON_SRC)
                if not ic:
                    warns.append(f"scene {s['code']}: icon '{E['nome']}' not found")
                    ic = {"vb": [0, 0, 100, 100], "els": [{"paint": "stroke", "op": 1, "paths": svg_shapes.rect(5, 5, 90, 90, 12)}], "from": "FALTA"}
            for e in ic["els"]:
                for k in ("stroke", "fill"):
                    e[k] = col(e.get(k)) if e.get(k) else None
            E.update(vb=E.get("vb") or ic["vb"], els=ic["els"], **{"from": Path(ic["from"]).name})
        elif T == "linha":
            P = svg_shapes.path_d(E["d"]) if E.get("d") else [{"v": E["pts"], "i": [[0, 0]] * len(E["pts"]), "o": [[0, 0]] * len(E["pts"]), "c": False}]
            E["paths"] = P
            xs = [v[0] for p in P for v in p["v"]]
            ys = [v[1] for p in P for v in p["v"]]
            E["bbox"] = [min(xs), min(ys), max(xs), max(ys)]
        elif T == "media":
            src = (COMPO.get("media") or {}).get(E["src"], E["src"])
            E["src"] = fwd(studio.resolve(src, ep))
        elif T == "grupo":
            E["els"] = [el(k) for k in E["els"]]
        if E.get("box") and "bbox" not in E:
            b = E["box"]
            E["bbox"] = [b[0], b[1], b[0] + b[2], b[1] + b[3]]
        if E.get("c") and "bbox" not in E:
            E["bbox"] = [E["c"][0] - E["r"], E["c"][1] - E["r"], E["c"][0] + E["r"], E["c"][1] + E["r"]]
        if any(a.get("ancora") == "esq" for a in E.get("anim") or []):
            E["ancoraEsq"] = True
        return E

    out = {k: v for k, v in cfg.items() if k not in ("els", "camera")}
    cam = dict(cfg.get("camera") or {"tipo": "deriva"})
    if cam.get("paragens"):
        cam["paragens"] = [dict(p, t=when(p) if ("palavra" in p or "t" in p) else 0.0) for p in cam["paragens"]]
    out["camera"] = cam
    if out.get("chao"):
        out["chao"] = dict(out["chao"], cor=col(out["chao"].get("cor", "line2")))
    if out.get("fecho"):
        out["fecho"] = dict(out["fecho"], cor=col(out["fecho"].get("cor", "paper")))
    out["els"] = [el(E) for E in cfg["els"]]
    return out

scenes, PHONES, warns = [], [], []
N_SC = len(mm["scenes"])
for n_sc, s in enumerate(mm["scenes"]):
    T = "PARTNER-CARD" if s["type"] in ("HF-CARD", "PARTNER-CARD") else s["type"]
    is_partner = T == "PARTNER-CARD"
    is_card = T.startswith("CARD") or T.startswith("3D") or T.startswith("OPEN")
    is_pages = T == "PAGINAS"
    bg = "world" if is_pages else ("partner" if is_partner else ("paper" if is_card else "none"))
    opening = bool(s.get("abre")) or T == "OPEN-WALL" or s["t"] < 0.3
    closing = bool(s.get("fecha")) or n_sc == N_SC - 1
    blocks = None
    if is_pages:                                  # blocks on a plane; rows of every block anchored on the words, in order
        blocks, lastb = [], s["t"] - .4
        mid_ = GRADE.get("alinhamento") == "centro"
        for b in s.get("blocks") or []:
            jr, lastb = timed_rows(lines_of(b), s["t"], s["te"], lastb)
            blocks.append({"lines": jr, "t0": jr[0]["t0"] if jr else 0,
                           "layout": dict(W=60, maxK=18, H=38, align="mid" if mid_ else "left", x=50 if mid_ else 8, cy=28.1, onCam=False)})
        if not blocks:
            warns.append(f"scene {s['id']}: PAGINAS without blocks")
    cfg = (COMPO.get("cenas") or {}).get(s.get("code"))
    if cfg:                                       # composed scene: its own element list, no lockup
        comp_ = compose(s, cfg, warns)
        m, sec = int(shift(s["t"]) // 60), int(shift(s["t"]) % 60)
        slug = re.sub(r"[^a-z0-9]+", "-", " ".join(norm(s.get("anchor") or T)))[:28].strip("-")
        notes = (f"FALA: {s.get('said','')}\nMOVIMENTO: {s.get('motion','')}\nSOM: {s.get('sfx') or '-'}\nCOMPOSIÇÃO: motion/composicao_after.json · {s.get('code')}")
        scenes.append(dict(id=s["id"], code=s.get("code"), name=f"S{s['id']:02d}_{m:02d}m{sec:02d}s_{s.get('code')}_{T}_{slug}", t=shift(s["t"]), te=shift(s["te"]), type=T,
                           bg="world" if cfg.get("fundo") == "mundo" else "none", lines=[], layout=None, el=None, shade=None, is3d=False,
                           said=s.get("said", ""), notes=notes, trans="cut", blocks=None, open=opening, close=closing, comp=comp_))
        continue
    rows = lines_of(s)
    jrows, _ = timed_rows(rows, s["t"], s["te"], s["t"] - .4)
    dur = s["te"] - s["t"]
    if dur > LONG and len(jrows) >= 3 and max(r["t0"] for r in jrows) < 0.35 * dur:
        warns.append(f"scene {s['id']} ({dur:.0f} s): every row enters in the first {max(r['t0'] for r in jrows):.1f} s — check the word times")
    # transition
    tr = None
    if is_pages:
        tr = "cut"                                    # the travel between blocks is the transition
    elif bg != "none":
        if s.get("trans"):
            tr = s["trans"]
        elif T == "OPEN-WALL" or s["t"] < 0.3:
            tr = "cut"                                # the video starts on it
        else:
            tr = CYCLE[k_tr % len(CYCLE)]
            if tr == prev_tr:
                k_tr += 1
                tr = CYCLE[k_tr % len(CYCLE)]
            k_tr += 1
        if closing and tr == "whip":
            warns.append(f"scene {s['id']}: last scene asked for a whip -> cut (the film never ends on a whip)")
            tr = "cut"
        prev_tr = tr
    a = s.get("asset") or {}
    pos = s.get("pos") or "left"
    if T == "OPEN-WALL":
        lay = dict(W=40, maxK=9, H=20, align="mid", x=50, cy=44.4, onCam=False)
    elif is_partner:
        lay = dict(W=40, maxK=13, H=26, align="left", x=7, cy=26, onCam=False, dark=True)
    elif T == "CARD-CONNECT":
        lay = dict(W=30, maxK=14, H=18, align="mid", x=50, cy=40.5, onCam=False)
    elif is_card:
        has_el = bool(a) or s.get("el") == "SQUARES3"
        wv = 38 if a.get("kind") == "SQUARES3" or s.get("el") == "SQUARES3" else 48
        lay = dict(W=wv if has_el else 60, maxK=10.5 if (s.get("lock") == "LIST" and s.get("title")) else 18, H=34 if s.get("lock") == "LIST" else 38,
                   align="left" if has_el else "mid", x=8 if has_el else 50, cy=28.1, onCam=False)
    elif pos == "center":
        lay = dict(W=42, maxK=9, H=24, align="mid", x=50, cy=41.6, onCam=True)
    else:
        lay = dict(W=33, maxK=10, H=30, align="right" if pos == "right" else "left", x=94 if pos == "right" else 6, cy=30, onCam=True)
    el = None
    kind = a.get("kind")
    pname = (PARTNER.get("name") or "").lower()
    if s.get("el") == "SQUARES3" or kind == "SQUARES3":
        el = dict(kind="SQUARES3", s=11, x=72, y=28.1, videos=[res(p) for p in a["path"]] if isinstance(a.get("path"), list) else results[2:5])
    elif kind == "ICON":
        el = dict(kind="ICON", path=res(a["path"]), s=9 if not is_card else 20)
        el.update(dict(x=74, y=28.1) if is_card else dict(place="leftof" if pos == "center" else "above"))
    elif kind in ("LOGO", "LOGO-TEASER"):
        dark = bool(a.get("dark")) or is_partner or (pname and pname in a["path"].lower())
        el = dict(kind=kind, path=res(a["path"]), dark=dark, s=(18 if kind == "LOGO-TEASER" else (7.5 if is_partner else (9 if not is_card else 18))))
        el.update(dict(x=74, y=28.1) if (is_card and not is_partner) else dict(place="above"))
    elif kind == "LOGOS":
        el = dict(kind="LOGOS", path=[res(p) for p in a["path"]], dark=[bool(pname and pname in p.lower()) for p in a["path"]], s=12, x=50, y=16.9)
    elif kind == "PHONE":
        vid = res(a["video"]) if a.get("video") else (results[len(PHONES) % len(results)] if results else None)
        el = dict(kind="PHONE", s=20, x=74 if is_card else 80, y=28.1, video=vid, mockup=res(a["path"]) if a.get("path") else None)
        PHONES.append(s["id"])
    shade = None if bg != "none" else dict(x=50 if pos == "center" else (78 if pos == "right" else 22), y=41.6 if pos == "center" else 30)
    slug = re.sub(r"[^a-z0-9]+", "-", " ".join(norm(s.get("key") or s.get("serif") or T)))[:28].strip("-")
    m, sec = int(s["t"] // 60), int(s["t"] % 60)
    notes = (f"FALA: {s.get('said','')}\nMOVIMENTO: {s.get('motion','')}\nTRANSIÇÃO: {tr or '-'}\nELEMENTO: {s.get('el') or '-'}"
             f"\nSOM: {s.get('sfx') or '-'}")
    scenes.append(dict(id=s["id"], name=f"S{s['id']:02d}_{m:02d}m{sec:02d}s_{T}_{slug}", t=s["t"], te=s["te"], type=T, bg=bg,
                       lines=jrows, layout=lay, el=el, shade=shade, is3d=T.startswith("3D"), said=s.get("said", ""), notes=notes,
                       pill=s.get("pill"), sub=s.get("sub"), trans=tr, wall=results if T == "OPEN-WALL" else None,
                       blocks=blocks, open=opening, close=closing))

mocks = [p for p in (sc["el"].get("mockup") for sc in scenes if sc["el"] and sc["el"]["kind"] == "PHONE") if p]
if not mocks:
    found = sorted(ep.glob("assets/mockups/**/*.aep")) + sorted(studio.client_dir(SLUG).glob("brand/mockups/**/*.aep"))
    mocks = [fwd(found[0])] if found else []
study = ep / "study" / "study.json"
_st = (json.loads(study.read_text(encoding="utf-8")).get("stats") or {}) if study.exists() else {}   # a hand-made study.json may lack stats
dur_total = round(_st["sequence_min"] * 60, 3) if _st.get("sequence_min") else max(sc["te"] for sc in scenes) + 5
if INS:                                           # the reference is a newer cut: its own length
    pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(REF)], capture_output=True, text=True)
    try:
        dur_total = round(float(pr.stdout.strip()), 3)
    except ValueError:
        dur_total = shift(dur_total)
EDITOR = [{"code": n.get("code", "N"), "t": 0.0, "text": f"{n.get('quando', '')} · {n.get('o_que', '')}"} for n in mm.get("editor") or []]
F = CJ["fonts"]
C = CJ["colors"]
tpl = (ROOT / "tools" / "ae_builder.jsx").read_text(encoding="utf-8").replace("//__COMPOSTO__", (ROOT / "tools" / "ae_composto.jsx").read_text(encoding="utf-8"))
# two projects: 01 = layout only (no keyframes), 02 = animated (3D camera, type animators, transitions)
for mode, tag in (("layout", "01_layout"), ("motion", "02_animado")):
    if MODES and mode not in MODES:
        continue
    D = {
        "mode": mode, "intensity": float(CJ["motion"].get("intensity", 1)), "project": f"{ep.name.upper()} · {tag.upper()}",
        "mainName": f"MAIN · {ep.name} · {tag}", "fps": 30000 / 1001 if abs(CJ.get("fps", 29.97) - 29.97) < .01 else CJ["fps"],
        "duration": dur_total, "reference": fwd(REF), "partnerSite": fwd(site_png) if site_png else None,
        "partnerName": PARTNER.get("name") or "parceiro", "mockup": mocks[0] if mocks else None,
        "ritmo": {"viagem_s": float(RITMO.get("viagem_s", 0.6)), "fim_s": float(RITMO.get("fim_s", 0.8)), "entrada_s": float(RITMO.get("entrada_s", 0.45))},
        "cols": COLS, "editorNotes": EDITOR,
        "colors": {"paper": C["paper"], "ink": C["ink"], "red": C["accent"], "world": mixhex(C["paper"], C["ink"], 0.05), "hfbg": PARTNER.get("bg", "#0D0D0D"), "lime": PARTNER.get("accent", C["accent"])},
        "fonts": {"key": F["key"]["ps"], "ser": F["ser"]["ps"], "sm": F["sm"]["ps"]},
        "tracking": {"key": F["key"].get("tracking", -50), "ser": F["ser"].get("tracking", -10), "sm": F["sm"].get("tracking", -10)},
        "scenes": scenes, "saveAs": fwd(out / f"{ep.name}_{tag}.aep"), "logFile": fwd(out / f"build_log_{mode}.txt"),
        "backup": fwd(out / f"_trabalho-nao-salvo_{mode}.aep"), "shots": None,   # check frames are shot afterwards with tools/ae_shots.py
    }
    jsx = out / f"{ep.name}_{tag}_build.jsx"
    jsx.write_text(tpl.replace("__DATA__", json.dumps(D, ensure_ascii=False, indent=1)), encoding="utf-8-sig")
    print(f"{jsx} · {len(scenes)} scenes · {len(results)} generated clips · mockup {'yes' if D['mockup'] else 'no'} · intensity {D['intensity']}")
for sc in scenes:
    rws = [[r_['t0'] for r_ in b['lines']] for b in sc['blocks']] if sc['blocks'] else [r_['t0'] for r_ in sc['lines']]
    flags = ("abre " if sc["open"] else "") + ("fecha" if sc["close"] else "")
    if sc.get("comp"):
        ens = sorted({round((E.get('entra') or {}).get('t', -9), 2) for E in sc['comp']['els'] if E.get('entra')})
        print(f"  {sc['id']:2d} {sc['name'][:52]:52s} {sc['t']:7.2f}-{sc['te']:7.2f} {len(sc['comp']['els'])} el · entra@ {ens} · câmara {sc['comp']['camera'].get('tipo')} {flags}")
        continue
    print(f"  {sc['id']:2d} {sc['name'][:46]:46s} {sc['trans'] or '-':5s} rows@ {rws}  el={sc['el']['kind'] if sc['el'] else '-'} {flags}")
for w_ in dict.fromkeys(warns):
    print("  WARN", w_)
