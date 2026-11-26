"""Build the review storyboard page from motion_map.json (see the storyboard skill).
  python tools/build_storyboard.py <episode_dir> <review_collection> [--frames "<reference edit.mp4>"] [--version N]
Writes <episode>/storyboard/index.html (frames/ next to it). Reviews go to the artifact's `db`
collection (doc id "s<id>": {status, note, at}); use a new collection per version (review1, review2...).
--frames extracts the background frames: one per scene from the reference edit, the generated clips
(wall1..5) and the partner site print.
Typography = justified keyword lockups measured with the client's real fonts (client.json fonts).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import studio  # noqa: E402

ep = Path(sys.argv[1]).resolve()
COLL = sys.argv[2] if len(sys.argv) > 2 and not sys.argv[2].startswith("--") else "review1"
_opt = lambda k: sys.argv[sys.argv.index(k) + 1] if k in sys.argv else None  # noqa: E731
CJ = studio.client_json(studio.client_of(ep))
EPJ = studio.episode_json(ep)
PARTNER = EPJ.get("partner") or {}
mm = json.loads((ep / "motion" / "motion_map.json").read_text(encoding="utf-8"))
spec = json.loads((ep / "motion" / "scenes_spec.json").read_text(encoding="utf-8"))
fix = [(re.compile(rf"\b({k})\b", re.I), v) for k, v in spec.get("brand_names", {}).items()]
FR = ep / "storyboard" / "frames"
FR.mkdir(parents=True, exist_ok=True)
if _opt("--frames"):
    ref = _opt("--frames")
    grab = lambda src, t, dst, vf="scale=960:-2": subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1", "-vf", vf, "-q:v", "3", str(dst)])  # noqa: E731
    for s in mm["scenes"]:
        grab(ref, s["t"] + min(1.5, (s["te"] - s["t"]) * 0.5), FR / f"s{s['id']:02d}.jpg")
    for i, src in enumerate(studio.generated_media(ep)[:5], 1):
        grab(src, 2.5, FR / f"wall{i}.jpg", "scale=-2:480")
    if PARTNER:
        site = studio.resolve(PARTNER.get("site") or "after/assets/partner_site.png", ep)
        if site.exists():
            grab(site, 0, FR / "partner_site.jpg", "scale=1280:-2")
        elif PARTNER.get("site_from_reference_at_s") is not None:
            vf = (f"crop={PARTNER['site_crop']}," if PARTNER.get("site_crop") else "") + "scale=1280:-2"
            grab(ref, PARTNER["site_from_reference_at_s"], FR / "partner_site.jpg", vf)
    print("frames ->", FR)
SITE = "frames/partner_site.jpg" if (FR / "partner_site.jpg").exists() else "frames/hf_site.jpg"
F = CJ["fonts"]
C = CJ["colors"]
font_css = lambda f: f'{"italic " if f.get("italic") else ""}{f.get("weight", 400)} 100px "{f["family"]}"'  # noqa: E731
FONTS_JS = json.dumps({k: font_css(F[k]) for k in ("key", "ser", "sm")})
HEAD = f'{CJ.get("name") or CJ["slug"]} · {mm["episode"]} · versão {_opt("--version") or COLL.replace("review", "")} · {len(mm["scenes"])} cenas'.upper()
LEDE = EPJ.get("storyboard_note") or ("O texto na tela são as palavras exatas da pessoa, na ordem em que fala. Marque cada cena como ok, ajustar "
                                      "ou remover e escreva a nota por baixo; a nota da versão anterior aparece em cada cena.")


def clean(t):
    for rx, v in fix:
        t = rx.sub(v, t)
    return t


KEYS = ("id", "tc", "t", "te", "type", "caminho", "cam", "cam_measured", "pos", "setup", "punch", "hero", "small", "items", "cols", "tiles",
        "icon", "motion", "sfx", "lock", "key", "serif", "rows", "title", "strike", "media", "el", "pill", "sub", "hf")
scenes = [{k: s.get(k) for k in KEYS} | {"said": clean(s.get("said", "")), "frame": f"frames/s{s['id']:02d}.jpg"} for s in mm["scenes"]]
DATA = json.dumps({"episode": mm["episode"], "coll": COLL, "scenes": scenes, "partner": PARTNER.get("name") or "parceiro", "site": SITE}, ensure_ascii=False)

html = r"""<title>Storyboard __EPN__</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?__GFONTS__&display=swap">
<style>
/* Layout: an edit-room review sheet — quiet chrome, the frames carry the client's identity. */
:root{
  --bg:#F3F2EF; --surface:#FFFFFF; --ink:#18171A; --muted:#6B6870; --line:#E2E0DC;
  --ok:#1F8A4C; --warn:#B7791F; --no:#B42318; --accent:#3B5BDB;
  --paper:__PAPER__; --tinta:__INK__; --red:__RED__; --hf-bg:__PBG__; --hf-lime:__PACC__;
  --f-ui:"__FUI__",system-ui,sans-serif; --f-play:"__FPLAY__",Georgia,serif;
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#141316;--surface:#1D1C20;--ink:#ECEAE6;--muted:#A19DA6;--line:#2E2C33;--ok:#4CC27F;--warn:#E3A73F;--no:#F0645A;--accent:#F0453E;color-scheme:dark}}
:root[data-theme="dark"]{--bg:#141316;--surface:#1D1C20;--ink:#ECEAE6;--muted:#A19DA6;--line:#2E2C33;--ok:#4CC27F;--warn:#E3A73F;--no:#F0645A;--accent:#F0453E;color-scheme:dark}
body{background:var(--bg);color:var(--ink);font-family:var(--f-ui);font-size:14px;line-height:1.5}
.wrap{max-width:1240px;margin:0 auto;padding-block:28px 64px;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
header{display:grid;gap:14px;margin-bottom:22px}
h1{font:italic 900 clamp(34px,5vw,54px)/1 var(--f-play);margin:0;text-wrap:balance}
h1 b{font:800 .4em var(--f-ui);font-style:normal;letter-spacing:.02em;display:block;margin-bottom:8px;color:var(--muted)}
.lede{max-width:72ch;color:var(--muted);margin:0}
.bar{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.chip{border:1px solid var(--line);background:var(--surface);border-radius:999px;padding:4px 11px;font-size:12px;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums}
.chip.on{background:var(--ink);color:var(--bg);border-color:var(--ink)}
button.chip{cursor:pointer}
.progress{font-variant-numeric:tabular-nums;font-weight:600}
.legend,.font-note{font-size:12px;color:var(--muted)}
.section-h{grid-column:1/-1;display:flex;gap:12px;align-items:baseline;margin-top:10px}
.section-h h2{font:italic 900 26px var(--f-play);margin:0}
.section-h span{color:var(--muted);font-size:13px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,520px),1fr));gap:18px}
.card{background:var(--surface);border:1px solid var(--line);border-radius:10px;overflow:hidden;display:grid;min-width:0}
.card[data-status="ok"]{box-shadow:inset 0 3px 0 var(--ok)}
.card[data-status="ajustar"]{box-shadow:inset 0 3px 0 var(--warn)}
.card[data-status="remover"]{box-shadow:inset 0 3px 0 var(--no);opacity:.72}
.meta{display:flex;flex-wrap:wrap;gap:8px 12px;align-items:baseline;padding:12px 14px 4px}
.num{font:italic 900 28px/1 var(--f-play)}
.tc{font-variant-numeric:tabular-nums;font-weight:600}
.type{font-size:11px;font-weight:700;letter-spacing:.08em;text-transform:uppercase;color:var(--accent)}
.cam{font-size:12px;color:var(--muted)}
.prev{font-size:12px;color:var(--muted);border-left:3px solid var(--warn);padding-left:8px;margin:0}
.body{padding:6px 14px 14px;display:grid;gap:8px;min-width:0}
.said{margin:0;color:var(--muted);font-size:13px}
.said q{color:var(--ink)}
dl{margin:0;display:grid;grid-template-columns:auto 1fr;gap:4px 12px;font-size:13px}
dt{color:var(--muted);font-weight:600}
dd{margin:0;min-width:0}
dd a{color:var(--accent)}
.review{display:flex;flex-wrap:wrap;gap:8px;align-items:center;border-top:1px solid var(--line);padding:10px 14px}
.review button{font:600 12px var(--f-ui);border-radius:6px;border:1px solid var(--line);background:transparent;color:var(--ink);padding:6px 12px;cursor:pointer}
.review button[aria-pressed="true"][data-v="ok"]{background:var(--ok);border-color:var(--ok);color:#fff}
.review button[aria-pressed="true"][data-v="ajustar"]{background:var(--warn);border-color:var(--warn);color:#fff}
.review button[aria-pressed="true"][data-v="remover"]{background:var(--no);border-color:var(--no);color:#fff}
.review button:disabled{opacity:.45;cursor:not-allowed}
.review textarea{flex:1 1 100%;min-height:52px;font:13px var(--f-ui);color:var(--ink);background:var(--bg);border:1px solid var(--line);border-radius:6px;padding:8px;resize:vertical}
.review .st{font-size:12px;color:var(--muted);margin-left:auto}
:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* ---------- the frame (client identity) ---------- */
.frame{position:relative;aspect-ratio:16/9;max-width:100%;container-type:inline-size;overflow:hidden;background:#000;color:#fff}
.frame>img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover}
.paper{position:absolute;inset:0;background:var(--paper);color:var(--tinta)}
.hfbg{position:absolute;inset:0;background:radial-gradient(70% 90% at 80% 40%,#1a1a1a,var(--hf-bg) 70%);color:#fff}
.shade{position:absolute;inset:0;background:radial-gradient(42% 70% at 20% 50%,rgba(10,8,8,.62),rgba(10,8,8,0) 72%)}
.shade.r{background:radial-gradient(42% 70% at 80% 50%,rgba(10,8,8,.62),rgba(10,8,8,0) 72%)}
.shade.b{background:linear-gradient(to top,rgba(8,6,6,.82),rgba(8,6,6,0) 58%)}
.shade.c{background:radial-gradient(50% 40% at 50% 74%,rgba(10,8,8,.65),rgba(10,8,8,0) 75%)}
/* justified lockup: sizes are set by JS in cqw */
.lk{position:relative;display:flex;flex-direction:column;align-items:flex-start;width:max-content}
.lk.mid{align-items:center}
.ln{white-space:nowrap;display:flex;align-items:baseline;gap:0;position:relative}
.ln .key{font-weight:800;font-family:var(--f-ui);letter-spacing:-.05em;line-height:.8;position:relative}
.ln .ser{font:italic 900 1em/.9 var(--f-play);color:var(--red);position:relative;z-index:2}
.ln .sm{font-weight:600;font-family:var(--f-ui);letter-spacing:-.01em;line-height:1.05}
.ln .stack{display:flex;flex-direction:column;justify-content:center;align-self:center}
.on .key{background:linear-gradient(180deg,#fff 40%,#cfcdd3 100%);-webkit-background-clip:text;background-clip:text;color:transparent;filter:drop-shadow(0 .03em .08em rgba(0,0,0,.45))}
.on .sm{color:#fff;text-shadow:0 .1em .4em rgba(0,0,0,.6)}
.on .ser{filter:drop-shadow(0 .03em .06em rgba(0,0,0,.5))}
.dark .key,.dark .sm{color:#fff}
.dark .sm{color:#bdbdbd}
.strike::after{content:"";position:absolute;left:-3%;right:-3%;top:50%;height:.085em;background:var(--red);border-radius:1em;transform:rotate(-2deg)}
.el{width:var(--s);aspect-ratio:1;border-radius:32%;background:radial-gradient(circle at 34% 28%,#ffffff 0%,#e9e4dc 28%,#c9c1b5 70%,#a89f92 100%);box-shadow:0 1.6cqw 3.2cqw rgba(40,25,15,.32),inset 0 -.6cqw 1.2cqw rgba(0,0,0,.12);display:grid;place-items:center;text-align:center;padding:1cqw;font:700 calc(var(--s)*.085)/1.15 var(--f-ui);color:#5b544b}
.el b{display:block;color:var(--red);font-size:1.1em;letter-spacing:.08em}
.tile{width:var(--s);aspect-ratio:1;background:#fff;border-radius:22%;box-shadow:0 1cqw 2.6cqw rgba(40,25,15,.25);display:grid;place-items:center;text-align:center;font:700 calc(var(--s)*.1)/1.1 var(--f-ui);color:#6B6870;padding:.6cqw}
.tile b{display:block;color:var(--red);font-size:1.15em;margin-bottom:.15em}
.tile.hf{background:#151515;color:#fff;border:.25cqw solid #2a2a2a}
.tile.hf b{color:var(--hf-lime)}
.browser{position:absolute;width:50cqw;border-radius:1.2cqw;overflow:hidden;background:#111;box-shadow:0 3cqw 6cqw rgba(0,0,0,.6);transform:rotateY(-20deg) rotateX(7deg) rotateZ(-1deg);border:.2cqw solid #2b2b2b}
.browser i{display:flex;gap:.6cqw;padding:.8cqw;background:#1b1b1b}
.browser i::before{content:"";width:1cqw;height:1cqw;border-radius:50%;background:#444;box-shadow:1.6cqw 0 #444,3.2cqw 0 #444}
.browser img{display:block;width:100%}
.persp{position:absolute;inset:0;perspective:90cqw}
.limepill{background:var(--hf-lime);color:#0D0D0D;border-radius:.8cqw;padding:.7cqw 1.6cqw;font:800 1.7cqw var(--f-ui);display:inline-block}
.panel{position:absolute;right:2.2cqw;top:50%;transform:translateY(-50%);width:27cqw;background:var(--paper);color:var(--tinta);border-radius:1.2cqw;padding:2cqw;display:grid;gap:1cqw;box-shadow:0 1cqw 3cqw rgba(0,0,0,.45)}
.note3d{position:absolute;left:2cqw;bottom:1.6cqw;font:700 1.1cqw var(--f-ui);color:rgba(20,18,18,.45);letter-spacing:.08em;text-transform:uppercase}
.dark .note3d{color:rgba(255,255,255,.35)}
svg.hand{position:absolute;inset:0;width:100%;height:100%;overflow:visible;pointer-events:none}
svg.hand path{fill:none;stroke-linecap:round}
.phone{width:var(--s);aspect-ratio:9/19;border-radius:calc(var(--s)*.16);background:#111;padding:calc(var(--s)*.045);box-shadow:0 2cqw 4cqw rgba(0,0,0,.4);transform:rotateY(-16deg) rotateZ(3deg)}
.phone img{width:100%;height:100%;object-fit:cover;border-radius:calc(var(--s)*.12);display:block}
.sq3{display:flex;gap:1.4cqw}
.sq3 div{width:var(--s);aspect-ratio:1;border-radius:18%;background:#fff;box-shadow:0 1cqw 2.4cqw rgba(40,25,15,.22);display:grid;place-items:end start;padding:.9cqw;font:800 1.4cqw var(--f-ui);color:var(--tinta);background-size:cover;background-position:center;position:relative;overflow:hidden}
.sq3 div span{background:#fff;border-radius:.5cqw;padding:.2cqw .6cqw;position:relative}
.sq3 div:nth-child(2){transform:translateY(-1.5cqw)} .sq3 div:nth-child(3){transform:translateY(-3cqw)}
.wall{position:absolute;inset:0;perspective:70cqw;display:flex;justify-content:center;align-items:center}
.wall .row5{display:flex;gap:1.6cqw;transform:rotateY(-22deg) rotateX(8deg) translateZ(-6cqw);transform-style:preserve-3d}
.wall img{width:13cqw;border-radius:1cqw;box-shadow:0 2cqw 4cqw rgba(0,0,0,.6)}
.wall img:nth-child(odd){transform:translateY(-2.5cqw)}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<div class="wrap">
  <header>
    <h1><b>__HEAD__</b>Storyboard das animações</h1>
    <p class="lede">__LEDE__</p>
    <div class="bar" id="filters"></div>
    <div class="bar"><span class="progress" id="progress">—</span><span class="font-note">Elemento: o quadro cinza mostra qual objeto, ícone ou logo entra ali; o asset real entra na etapa do After.</span></div>
  </header>
  <main class="grid" id="grid"></main>
</div>

<script id="data" type="application/json">__DATA__</script>
<script id="prev" type="application/json">__PREV__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const PREV = JSON.parse(document.getElementById('prev').textContent);
const CAM = {frontal:'câmera frontal', lateral:'câmera lateral', tela:'gravação de tela', broll_ia:'insert IA'};
const reviews = {}; let db = null, filter = 'todas', dbTried = false;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const cap = s => s ? s.charAt(0).toUpperCase() + s.slice(1) : s;
const fmt = t => `${String(Math.floor(t/60)).padStart(2,'0')}:${(t%60).toFixed(2).padStart(5,'0')}`;
const fi = term => 'https://www.flaticon.com/animated-icons?word=' + encodeURIComponent(String(term).replace(/^LOGO\s*/,'').split(/[|+]/)[0].trim());

/* ---- measurement with the real fonts: width of text at font-size 1 (unitless ratio) ---- */
const cv = document.createElement('canvas').getContext('2d');
const FONTS = __FONTSJS__;
const LS = {key:-5, ser:0, sm:-1};
function r(kind, text){ cv.font = FONTS[kind]; try { cv.letterSpacing = LS[kind] + 'px'; } catch {} return cv.measureText(text).width / 100; }

/* lines for each pattern: [[{k,t,strike}], ...]; first reading item capitalised */
function linesOf(s){
  const sm = s.small || [], L = [];
  const K = (t, strike) => ({k:'key', t, strike}), S = t => ({k:'ser', t}), M = t => ({k:'sm', t});
  switch (s.lock) {
    case 'A': L.push([K(cap(s.key), s.strike)], [S(s.serif)]); if (sm[0]) L.push([M(sm[0])]); break;
    case 'B': if (sm[0]) L.push([M(cap(sm[0]))]); L.push([K(sm[0] ? s.key : cap(s.key), s.strike)]); L.push(sm[1] ? [M(sm[1]), S(s.serif)] : [S(s.serif)]); break;
    case 'C': L.push([K(cap(s.key), s.strike)], sm[0] ? [M(sm[0]), S(s.serif)] : [S(s.serif)]); if (sm[1]) L.push([M(sm[1])]); break;
    case 'D': L.push([S(cap(s.serif))], [K(s.key), {k:'stack', t: sm}]); break;
    case 'LIST': if (s.title) L.push([M(cap(s.title[0]))], [K(s.title[1])]); (s.rows||[]).forEach(rw => L.push([M(cap(rw[0])), K(rw[1], true)])); L.push([S(cap(s.serif))]); break;
    case 'PUNCH': L.push([S(cap(s.serif))]); break;
    default: L.push([S(cap(s.serif || ''))]);
  }
  return L;
}
/* justify: every line scaled to width W (cqw); key size capped at maxK; block scaled to fit height H */
function lockupHTML(s, W, maxK, cls, H){
  H = H || 30;
  let L = linesOf(s);
  // a long connector next to the serif gets its own line (so the serif can stay big)
  L = L.flatMap(l => (l.length === 2 && l[0].k === 'sm' && l[1].k === 'ser' && r('sm', l[0].t) * .3 > .3 * W / maxK * 1.0 && l[0].t.length > 9) ? [[l[0]], [l[1]]] : [l]);
  const keyLines = L.filter(l => l.length === 1 && l[0].k === 'key');
  let k = maxK;
  keyLines.forEach(l => { k = Math.min(k, W / r('key', l[0].t)); });
  L.forEach(l => { if (l.length > 1 && l.some(x => x.k === 'key')) { const sm = l.find(x => x.k==='sm'), ky = l.find(x => x.k==='key'), st = l.find(x => x.k==='stack');
      const smw = sm ? r('sm', sm.t)*.3 + .16 : 0, stw = st ? Math.max(...st.t.map(t => r('sm', t)))*.3 + .16 : 0;
      if (!keyLines.length || st) k = Math.min(k, W / (r('key', ky.t) + smw + stw)); } });
  // pass 1: sizes and heights in units of cqw
  const rows = []; let prev = null;
  L.forEach(l => {
    const row = {l, size: 0, h: 0, mt: 0, kind: ''};
    if (l.length === 1 && l[0].k === 'key') { row.kind='key'; row.size = k; row.h = .98*k; }
    else if (l.length === 1 && l[0].k === 'ser') { row.kind='ser'; row.size = Math.min(k*1.12, W / r('ser', l[0].t)); row.h = 1.08*row.size; }
    else if (l.length === 1 && l[0].k === 'sm') { row.kind='sm'; row.size = Math.min(k*.3*1.2, W / r('sm', l[0].t)); row.h = 1.35*row.size; }
    else if (l[0].k === 'sm' && l[1].k === 'ser') { row.kind='smser'; const smw = r('sm', l[0].t)*k*.3; row.size = Math.min(k*1.05, (W - smw - k*.16) / r('ser', l[1].t)); row.h = 1.08*row.size; }
    else if (l[0].k === 'sm' && l[1].k === 'key') { row.kind='row'; const smw = r('sm', l[0].t)*k*.3; row.size = Math.min(k, (W - smw - k*.16) / r('key', l[1].t)); row.h = 1.0*row.size; }
    else { row.kind='keystack'; row.size = k; row.h = .98*k; }
    const serLike = row.kind === 'ser' || row.kind === 'smser';
    if (serLike && prev && (prev.kind==='key'||prev.kind==='keystack') && !prev.l[0].strike && row.size >= .6*k) row.mt = -.22*k;
    else if (serLike && prev && prev.l.some(x => x.strike)) row.mt = .06*k;
    else if (row.kind === 'sm' && prev) row.mt = .05*k;
    else if (row.kind === 'row' && prev) row.mt = .02*k;
    rows.push(row); prev = row;
  });
  const total = rows.reduce((a, r0) => a + r0.h + r0.mt, 0);
  const f = total > H ? H / total : 1;
  const smS = k*.3*f, gap = k*.16*f;
  const html = rows.map(rw => {
    const sz = rw.size*f, l = rw.l; let segs = '';
    if (rw.kind==='key') segs = `<span class="key ${l[0].strike?'strike':''}" style="font-size:${sz}cqw">${esc(l[0].t)}</span>`;
    if (rw.kind==='ser') segs = `<span class="ser" style="font-size:${sz}cqw">${esc(l[0].t)}</span>`;
    if (rw.kind==='sm') segs = `<span class="sm" style="font-size:${sz}cqw">${esc(l[0].t)}</span>`;
    if (rw.kind==='smser') segs = `<span class="sm" style="font-size:${smS}cqw;align-self:flex-start;margin-top:${(sz*.2).toFixed(2)}cqw">${esc(l[0].t)}</span><span style="width:${gap}cqw"></span><span class="ser" style="font-size:${sz}cqw">${esc(l[1].t)}</span>`;
    if (rw.kind==='row') segs = `<span class="sm" style="font-size:${smS}cqw;width:${(W*f - sz*r('key', l[1].t) - gap).toFixed(2)}cqw;text-align:right">${esc(l[0].t)}</span><span style="width:${gap}cqw"></span><span class="key ${l[1].strike?'strike':''}" style="font-size:${sz}cqw">${esc(l[1].t)}</span>`;
    if (rw.kind==='keystack') segs = `<span class="key" style="font-size:${sz}cqw">${esc(l[0].t)}</span><span style="width:${gap}cqw"></span><span class="stack">${l[1].t.map(t => `<span class="sm" style="font-size:${smS}cqw">${esc(t)}</span>`).join('')}</span>`;
    return `<div class="ln" style="margin-top:${(rw.mt*f).toFixed(2)}cqw">${segs}</div>`;
  }).join('');
  return `<div class="lk${cls ? ' ' + cls : ''}">${html}</div>`;
}
const elBox = (s, size) => {
  if (!s.el) return '';
  if (/^SITE/.test(s.el)) return '';
  if (s.el === 'PHONE') return `<div class="phone" style="--s:${size*.7}cqw"><img src="frames/wall3.jpg" alt=""></div>`;
  if (s.el === 'SQUARES3') return `<div class="sq3" style="--s:${size*.5}cqw">${[3,4,5].map((n,i)=>`<div style="background-image:url(frames/wall${n}.jpg)"><span>Hook ${i+1}</span></div>`).join('')}</div>`;
  if (/^LOGO/.test(s.el)) return `<div class="tile ${s.hf?'hf':''}" style="--s:${size}cqw"><div><b>logo</b>${esc(s.el.replace(/^LOGO\s*/,'').replace(/\(.*\)/,''))}</div></div>`;
  return `<div class="el" style="--s:${size}cqw"><div><b>3D</b>${esc(s.el)}</div></div>`;
};

function frame(s){
  const t = s.type;
  if (t === 'OPEN-WALL')
    return `<div class="paper"></div><div class="wall" style="align-items:flex-start;padding-top:4cqw"><div class="row5">${[1,2,3,4,5].map(n=>`<img src="frames/wall${n}.jpg" alt="">`).join('')}</div></div>
      <div style="position:absolute;left:50%;top:79%;transform:translate(-50%,-50%);color:var(--tinta)">${lockupHTML(s, 40, 9, 'mid', 20)}</div><div class="note3d">câmera 3D a avançar · 5 vídeos surgem a cada 3 frames</div>`;
  if (t === 'OPEN-TRIPTYCH')
    return `<img src="${s.frame}" alt=""><div class="shade b"></div>
      <div style="position:absolute;left:50%;top:76%;transform:translate(-50%,-50%)" class="on">${lockupHTML(s, 34, 9, 'mid').replace('class="lk mid"','class="lk mid" style="position:relative"')}</div>`;
  if (t === 'HF-CARD' || t === 'PARTNER-CARD') {
    return `<div class="hfbg dark"><div class="persp"><div class="browser" style="right:-3cqw;top:14%"><i></i><img src="${D.site}" alt=""></div></div>
      <div style="position:absolute;left:7cqw;top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:2.2cqw;align-items:flex-start">
        <div class="tile hf" style="--s:7.5cqw"><div><b>logo</b>${esc(D.partner)}</div></div>
        <div style="position:relative">${lockupHTML(s, 40, 13).replace('class="lk "','class="lk" style="position:relative"')}</div>
        ${s.pill?`<span class="limepill">${esc(s.pill)}</span>`:''}${s.sub?`<span style="font:600 1.6cqw var(--f-ui);color:#bdbdbd">${esc(s.sub)}</span>`:''}
      </div><div class="note3d">mundo ${esc(D.partner)} · câmera 3D push-in no navegador</div></div>`;
  }
  const isCard = t.startsWith('CARD') || t.startsWith('3D');
  if (isCard) {
    const is3d = t.startsWith('3D');
    if (t === 'CARD-CONNECT')
      return `<div class="paper"><div style="position:absolute;inset:14% 24% 50%;display:flex;justify-content:space-between;align-items:center"><div class="tile" style="--s:12cqw"><div><b>logo</b>${esc((s.tiles||[])[0]||'logo 1')}</div></div><div class="tile" style="--s:12cqw"><div><b>logo</b>${esc((s.tiles||[])[1]||'logo 2')}</div></div></div>
        <svg class="hand" viewBox="0 0 100 56.25" preserveAspectRatio="none"><path d="M38 18 C 46 12, 54 24, 62 18" stroke="#D22121" stroke-width=".5"/></svg>
        <div style="position:absolute;left:50%;top:72%;transform:translate(-50%,-50%)">${lockupHTML(s, 30, 14, 'mid').replace('class="lk mid"','class="lk mid" style="position:relative"')}</div></div>`;
    const hasEl = !!s.el;
    const block = `<div style="position:absolute;left:${hasEl?8:50}cqw;top:50%;transform:translate(${hasEl?0:-50}%,-50%)${is3d?' rotateY(-12deg) rotateX(5deg)':''}">${lockupHTML(s, hasEl?(s.el==='SQUARES3'?38:48):60, 18, hasEl?'':'mid', s.lock==='LIST'?34:38).replace(/class="lk( mid)?"/,'class="lk$1" style="position:relative"')}</div>`;
    const el = hasEl ? `<div style="position:absolute;left:${s.el==='SQUARES3'?72:74}cqw;top:50%;transform:translate(-50%,-50%)${is3d?' rotateY(-12deg)':''}">${elBox(s, 22)}</div>` : '';
    return `<div class="paper"><div class="persp">${block}${el}</div>${is3d?'<div class="note3d">câmera 3D · dolly + órbita suave</div>':''}</div>`;
  }
  if (s.lock) {                                 // on camera
    const where = s.pos || 'left';
    if (where === 'center')
      return `<img src="${s.frame}" alt=""><div class="shade c"></div><div class="on" style="position:absolute;left:50%;top:74%;transform:translate(-50%,-50%);display:flex;align-items:center;gap:2cqw">${elBox(s, 9)}<div style="position:relative">${lockupHTML(s, 42, 9, '', 24)}</div></div>`;
    const side = where === 'right' ? 'right:6cqw;align-items:flex-end' : 'left:6cqw;align-items:flex-start';
    return `<img src="${s.frame}" alt=""><div class="shade ${where==='right'?'r':''}"></div>
      <div class="on" style="position:absolute;${side};top:50%;transform:translateY(-50%);display:flex;flex-direction:column;gap:1.8cqw">${elBox(s, 9)}<div style="position:relative">${lockupHTML(s, 33, 10, '', 30).replace('class="lk "','class="lk" style="position:relative"')}</div></div>`;
  }
  return `<img src="${s.frame}" alt="">`;
}

function onScreen(s){
  if (s.lock === 'LIST') return [...(s.title||[]), ...(s.rows||[]).map(r=>r.join(' ')), s.serif].filter(Boolean).join(' / ');
  if (s.lock) return [...(s.small||[]).filter(Boolean), s.key, s.serif].filter(Boolean).join(' / ');
  return [...(s.setup||[]), s.hero, s.punch].filter(Boolean).join(' / ');
}
function card(s){
  const r = reviews['s'+s.id] || {}, st = r.status || '';
  const isCard = s.type.startsWith('CARD') || s.type.startsWith('3D') || s.type.startsWith('OPEN') || s.type === 'HF-CARD' || s.type === 'PARTNER-CARD';
  const pv = PREV[s.anchor_key || ''] || PREV[s.id] || null;
  return `<article class="card" id="s${s.id}" data-status="${st}">
    <div class="frame">${frame(s)}</div>
    <div class="meta"><span class="num">${s.id}</span><span class="tc">${s.tc} → ${fmt(s.te)}</span><span class="type">${esc(s.type)}${s.caminho?' · '+esc(s.caminho):''}</span><span class="cam">${isCard?'tela cheia':CAM[s.cam_measured]||''}</span></div>
    <div class="body">
      ${pv?`<p class="prev">Versão anterior · ${pv.status==='ok'?'aprovada':'a sua nota'}: ${esc(pv.note||'—')}</p>`:''}
      <p class="said">Fala: <q>${esc(s.said)}</q></p>
      <dl><dt>Na tela</dt><dd>${esc(onScreen(s))}</dd>
      ${s.el?`<dt>Elemento</dt><dd>${esc(s.el)}</dd>`:''}
      ${s.media?`<dt>Vídeos</dt><dd>${s.media.map(esc).join(' · ')}</dd>`:''}
      ${s.icon?`<dt>Ícone</dt><dd>${esc(s.icon)} · <a href="${fi(s.icon)}" target="_blank" rel="noopener">buscar no Flaticon</a></dd>`:''}
      <dt>Movimento</dt><dd>${esc(s.motion)}</dd>${s.sfx?`<dt>Som</dt><dd>${esc(s.sfx)}</dd>`:''}</dl>
    </div>
    <div class="review" data-id="s${s.id}">
      ${['ok','ajustar','remover'].map(v=>`<button type="button" data-v="${v}" aria-pressed="${st===v}" ${db?'':'disabled'}>${{ok:'Aprovar',ajustar:'Ajustar',remover:'Remover'}[v]}</button>`).join('')}
      <span class="st">${db===null&&dbTried?'Abra no claude.ai com sessão iniciada para guardar':(r.at?'guardado':'')}</span>
      <textarea id="note-s${s.id}" placeholder="O que mudar nesta cena?" ${db?'':'disabled'}>${esc(r.note||'')}</textarea>
    </div></article>`;
}
function render(){
  const list = D.scenes.filter(s => filter==='todas' || (filter==='pendentes' ? !reviews['s'+s.id]?.status : reviews['s'+s.id]?.status===filter));
  const hook = list.filter(s => s.t < 41.4), rest = list.filter(s => s.t >= 41.4);
  document.getElementById('grid').innerHTML =
    (hook.length ? `<div class="section-h"><h2>O gancho</h2><span>0:00 → 0:41 · ${hook.length} cenas · prioridade</span></div>` + hook.map(card).join('') : '') +
    (rest.length ? `<div class="section-h"><h2>O resto do vídeo</h2><span>0:41 → 11:20 · ${rest.length} cenas</span></div>` + rest.map(card).join('') : '') ||
    '<p class="legend">Nenhuma cena neste filtro.</p>';
  const c = {ok:0,ajustar:0,remover:0}; Object.values(reviews).forEach(r=>{ if(c[r.status]!==undefined) c[r.status]++ });
  document.getElementById('progress').textContent = `${c.ok+c.ajustar+c.remover}/${D.scenes.length} revistas · ${c.ok} aprovadas · ${c.ajustar} a ajustar · ${c.remover} removidas`;
  document.getElementById('filters').innerHTML = ['todas','pendentes','ok','ajustar','remover'].map(f=>`<button class="chip ${f===filter?'on':''}" data-f="${f}">${{todas:'Todas ('+D.scenes.length+')',pendentes:'Pendentes',ok:'Aprovadas',ajustar:'A ajustar',remover:'Removidas'}[f]}</button>`).join('');
}
document.addEventListener('click', async e => {
  const f = e.target.closest('[data-f]'); if (f) { filter = f.dataset.f; render(); return; }
  const b = e.target.closest('.review button'); if (!b || !db) return;
  const id = b.closest('.review').dataset.id, v = b.dataset.v;
  const note = document.getElementById('note-'+id).value, prev = reviews[id]?.status;
  const status = prev === v ? '' : v;
  reviews[id] = {status, note, at: Date.now()}; render();
  try { await db.collection(D.coll).doc(id).set({status, note, at: Date.now()}); } catch (err) { reviews[id] = {...reviews[id], status: prev}; render(); }
});
document.addEventListener('change', async e => {
  if (!e.target.matches('.review textarea') || !db) return;
  const id = e.target.closest('.review').dataset.id, note = e.target.value, cur = reviews[id] || {};
  reviews[id] = {...cur, note, at: Date.now()};
  try { await db.collection(D.coll).doc(id).set({status: cur.status || '', note, at: Date.now()}); } catch {}
});
(async () => {
  try { await Promise.all(Object.values(FONTS).map(f => document.fonts.load(f.replace('100px','40px')))); await document.fonts.ready; } catch {}
  render();
  const c = window.claude?.use ? await window.claude.use('db') : null;
  dbTried = true;
  if (!c) { render(); return; }
  db = c;
  const timer = setTimeout(render, 10000);
  db.collection(D.coll).onSnapshot(snap => {
    clearTimeout(timer);
    snap.docs.forEach(d => { const v = d.data(); if (v) reviews[d.id] = v; });
    if (!document.activeElement || !document.activeElement.matches('textarea')) render();
  }, () => { clearTimeout(timer); render(); });
  render();
})();
</script>
"""
prev_path = ep / "storyboard" / "prev_notes.json"
PREV = prev_path.read_text(encoding="utf-8") if prev_path.exists() else "{}"
html = html.replace("__DATA__", DATA.replace("</", "<\\/")).replace("__PREV__", PREV.replace("</", "<\\/"))
for k, v in {"__EPN__": mm["episode"], "__GFONTS__": CJ.get("google_fonts", ""), "__PAPER__": C["paper"], "__INK__": C["ink"], "__RED__": C["accent"],
             "__PBG__": PARTNER.get("bg", "#0D0D0D"), "__PACC__": PARTNER.get("accent", C["accent"]), "__FUI__": F["key"]["family"],
             "__FPLAY__": F["ser"]["family"], "__HEAD__": HEAD, "__LEDE__": LEDE, "__FONTSJS__": FONTS_JS}.items():
    html = html.replace(k, v)
(ep / "storyboard" / "index.html").write_text(html, encoding="utf-8")
print("storyboard written:", len(scenes), "scenes ->", COLL)
