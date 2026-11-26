"""SFX for motion events: measure the team's SFX library, rank a sound pool per movement, plan an episode's cues.

The library is the team's own folder of sounds with its catalog (`_sistema/dados/catalogo.json`: id, n name, c category,
s subcategory, p relative path, d duration, k pack, t tags) and favourites (`_sistema/dados/usuario.json`). This tool only
READS the sounds, the catalog and the favourites; everything it learns goes to ONE new file next to them,
`_sistema/dados/sfx_motion.json` (features, ranked pools, the user's ok / não per sound, the licence per pack, the editor's
usage). No sound is ever picked automatically before the user approved it by ear on the review page.

  python tools/sfx.py biblioteca "<SFX_LIBRARY folder>"
        save this PC's library path in studio.config.json (`sfx_library`; never in the repository)
  python tools/sfx.py index [--refazer] [--workers 8]
        measure every sound a movement can use (cached by id + size + date: a re-run only measures new files) and rank
        each movement's pool and shortlist -> sfx_motion.json (keeps approvals, licences and the editor's usage)
  python tools/sfx.py movimentos
        the vocabulary: movement, the motion events that trigger it, pool size, approved / shortlist
  python tools/sfx.py pick <movimento> [--intensidade subtil|medio|forte] [--n 3] [--client <slug>] [--todos]
        best APPROVED sounds for a movement (ok on the review page); --todos also lists the shortlist still to hear
  python tools/sfx.py revisar [--port 8767] [--no-open]
        local review page (127.0.0.1 only): 6-10 sounds per movement with play buttons, ok / não, licence per pack
  python tools/sfx.py aprender <episode>
        read the editor's final sequence (<episode>/final_study/premiere/sequence.json, estudo-final skill): which library
        sounds he put on which movement -> a ranking bonus (still needs the user's ok to be picked)
  python tools/sfx.py plan <episode | code folder> [--xml <final.xml>] [--seq <name>] [--xml-out <file>] [--musica <file>]
                     [--intensidade ...] [--client <slug>] [--previa] [--out <file>]
        motion events -> <folder>/work/sfx_plan.json (time, movement, file, gain, layer) and, with --xml, a NEW copy of the
        editor's XML with the cues on new audio tracks (never overwrites: _v2, _v3 ...). Events come from
        after/*_build.jsx (row times as built) or motion/motion_map.json (After path), or out/timeline.json (code path:
        node render.mjs --project <folder> --timeline). --previa fills movements with no approved sound with the top of
        the shortlist, marked PREVIA, only to hear them in context (file and sequence names say PREVIA).

Rules of the plan: every cue lands on its spoken word / motion event (the sound's measured peak sits on the event); one
sound per movement in an episode and the same sound always on the same layer (track); stacked cues stay under -1 dBTP
(sum of measured sample peaks, 0.5 dB margin); music bed 20 dB under the -14 LUFS voice, ending 2 s after the last
motion event with a fade over those 2 s.
Levels are measured locally (K-weighted loudness, BS.1770 filters; no AI listening).
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import threading
import unicodedata
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import quote

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio  # noqa: E402

DATA_NAME = "sfx_motion.json"
VERSION = 1
INTENS = ("subtil", "medio", "forte")
# off by default: music (part of it is copyrighted and gets YouTube claims), memes / famous sounds, the unsorted folder,
# video overlays; themes (horror, weapons) only when a client.json `sfx.incluir` names them
EXCLUIR = ["80_Musica", "15_Memes_Cartoon_Famosos", "98_Revisar", "90_Video_Overlays_LUTs"]
# names that point to a sound ripped from a video site or a meme: licence unknown, never offered
NAO_GLOBAL = r"y2mate|youtube|tiktok|\bmeme|taco bell|vine boom|bruh|savefrom|ssyoutube|\bfamous"
TEMAS = {"horror": ["12_Horror_Fantasia_Magia/Horror-Tensao", "12_Horror_Fantasia_Magia/Monstros-Criaturas",
                    "12_Horror_Fantasia_Magia/Medieval-Batalhas"],
         "armas": ["13_Armas_Combate"]}

# ------------------------------------------------------------------ vocabulary
# pools: (category, subcategory or None = all, regex the name/tags should match or None); "nao": names left out.
# alvo: measured targets at intensity medio — dur (s), ataque (s, onset -> peak), brilho (spectral centroid, Hz),
# grave (energy share under 150 Hz), cauda (s, peak -> -30 dB). nivel: loudness of the cue (LUFS, momentary max).
# prefere: names that rank up. ancora: "pico" = the sound's peak on the event, "inicio" = its onset on the event. eventos: what triggers it.
M = {
    "entrada_texto": {"nome": "Entrada de texto / linha de card", "eventos": "cada linha que entra na palavra (LEG, CARD, titulo)",
                      "pools": [("01_Transicoes", "Whooshes/Curtos", None), ("01_Transicoes", "Whooshes/UI", None),
                                ("01_Transicoes", "Slides", None), ("03_UI_Interface", "Pop Up", None)],
                      "dur": (0.12, 1.4), "alvo": dict(dur=0.45, ataque=0.08, brilho=3500, grave=0.08, cauda=0.3), "nivel": -31},
    "pop_palavra": {"nome": "Pop de palavra / nó / tile", "eventos": "palavra que salta, nó de diagrama, tile do ícone",
                    "pools": [("03_UI_Interface", "Pop Up", None), ("03_UI_Interface", "Selecao", None),
                              ("03_UI_Interface", "Cliques-Botoes", None), ("03_UI_Interface", "Geral", r"pop|bubble|blip|plop")],
                    "dur": (0.03, 0.7), "alvo": dict(dur=0.15, ataque=0.01, brilho=3000, grave=0.05, cauda=0.12), "nivel": -30},
    "contador": {"nome": "Contador de número / ticks em sequência", "eventos": "número que conta, onda de cards acendendo",
                 "pools": [("03_UI_Interface", "Progresso", None), ("03_UI_Interface", "HUD-Dados", None),
                           ("04_Tecnologia_Dispositivos", "Bipes-Sinais", r"tick|beep|blip|count|digit|data"),
                           ("05_Foley_Objetos", "Relogios-Timer", r"tick|clock|timer|relogio")],
                 "nao": r"alarm|siren|sirene", "dur": (0.05, 3.5), "alvo": dict(dur=0.7, ataque=0.01, brilho=4000, grave=0.04, cauda=0.2),
                 "nivel": -32, "ancora": "inicio"},
    "carrossel": {"nome": "Carrossel / slide lateral", "eventos": "cards que deslizam de lado",
                  "pools": [("01_Transicoes", "Slides", None), ("01_Transicoes", "Whooshes/UI", None),
                            ("05_Foley_Objetos", "Movimento-Manuseio", r"slide|swipe|swish|desliz")],
                  "dur": (0.2, 1.6), "alvo": dict(dur=0.6, ataque=0.15, brilho=2500, grave=0.1, cauda=0.3), "nivel": -29},
    "viagem_camera": {"nome": "Viagem de câmera entre blocos", "eventos": "PAGINAS / rota: a câmera chega no bloco seguinte",
                      "pools": [("01_Transicoes", "Whooshes", None), ("01_Transicoes", "Whooshes/Longos", None),
                                ("08_Elementos", "Ar-Vento/Whooshes", None), ("08_Elementos", "Ar-Vento/Transicoes", None)],
                      "nao": r"hit|impact|boom|glitch|explos", "dur": (0.4, 2.6),
                      "alvo": dict(dur=1.0, ataque=0.45, brilho=1800, grave=0.15, cauda=0.35), "nivel": -28},
    "transicao": {"nome": "Transição curta / whip", "eventos": "card de tela cheia entra ou sai, whip, zoom-blur",
                  "pools": [("01_Transicoes", "Whips", None), ("01_Transicoes", "Whooshes/Curtos", None),
                            ("01_Transicoes", "Whoosh Hits", None), ("01_Transicoes", "Whooshes", None)],
                  "dur": (0.15, 1.3), "alvo": dict(dur=0.55, ataque=0.2, brilho=2200, grave=0.15, cauda=0.2), "nivel": -27},
    "glitch": {"nome": "Glitch (corte forte)", "eventos": "transição glitch, título com cópias deslocadas",
               "pools": [("01_Transicoes", "Glitch", None), ("03_UI_Interface", "Glitch", None), ("11_SciFi_Futurista", "Glitches", None)],
               "dur": (0.05, 1.6), "alvo": dict(dur=0.4, ataque=0.02, brilho=4000, grave=0.08, cauda=0.1), "nivel": -31},
    "flash_luz": {"nome": "Flash de luz / light leak", "eventos": "clarão, light leak, abertura de cena com luz",
                  "pools": [("01_Transicoes", "Reverse", None), ("02_Impactos", "Sweeteners", None), ("14_Brilhos_Sinos", "Brilhos", None),
                            ("10_Atmosferas_Drones", "Airy", r"shine|flash|light|air|swell|rise")],
                  "dur": (0.3, 3.2), "alvo": dict(dur=1.2, ataque=0.6, brilho=4500, grave=0.05, cauda=0.5), "nivel": -31},
    "brilho": {"nome": "Brilho / sparkle / glow", "eventos": "elemento que acende, glow, ícone que brilha",
               "pools": [("14_Brilhos_Sinos", None, None), ("12_Horror_Fantasia_Magia", "Magia", r"sparkle|shine|glitter|chime|twinkle|magic")],
               "dur": (0.2, 3.2), "alvo": dict(dur=0.9, ataque=0.03, brilho=6000, grave=0.02, cauda=0.7), "nivel": -33},
    "ui_clique": {"nome": "Clique de UI / mouse", "eventos": "clique na gravação de tela, botão, cursor",
                  "pools": [("04_Tecnologia_Dispositivos", "Mouse", r"click|clique|clic"), ("03_UI_Interface", "Cliques-Botoes", None)],
                  "nao": r"scroll|drag|wheel|roda", "dur": (0.02, 0.5), "alvo": dict(dur=0.08, ataque=0.003, brilho=3500, grave=0.05, cauda=0.05),
                  "nivel": -31},
    "ui_digitar": {"nome": "Digitação", "eventos": "texto sendo escrito numa busca / campo",
                   "pools": [("04_Tecnologia_Dispositivos", "Teclado", None), ("04_Tecnologia_Dispositivos", "Teclado/Mecanico", None),
                             ("04_Tecnologia_Dispositivos", "Teclado/Notebook", None), ("03_UI_Interface", "Texto", None)],
                   "dur": (0.3, 8.0), "alvo": dict(dur=1.6, ataque=0.01, brilho=3000, grave=0.05, cauda=0.1), "nivel": -33, "ancora": "inicio"},
    "ui_notificacao": {"nome": "Notificação / mensagem", "eventos": "notificação, mensagem, CTA que aparece",
                       "pools": [("03_UI_Interface", "Notificacao-Alerta", None), ("03_UI_Interface", "Confirmacao", None),
                                 ("04_Tecnologia_Dispositivos", "Celular", r"notif|message|ding|alert|sms|mensag")],
                       "nao": r"alarm|siren|error|erro", "dur": (0.1, 1.6), "alvo": dict(dur=0.5, ataque=0.01, brilho=3500, grave=0.03, cauda=0.35),
                       "nivel": -31},
    "check": {"nome": "Check / confirmação de item", "eventos": "item de lista marcado, check",
              "pools": [("03_UI_Interface", "Confirmacao", None), ("03_UI_Interface", "Selecao", None)],
              "dur": (0.05, 1.0), "alvo": dict(dur=0.25, ataque=0.01, brilho=3500, grave=0.03, cauda=0.2), "nivel": -32},
    "escrita": {"nome": "Risco / marcador / traço à mão", "eventos": "palavra riscada, marcador, linha à mão, sublinhado",
                "pools": [("05_Foley_Objetos", "Escrita", None), ("05_Foley_Objetos", "Papel-Livros", r"pen|marker|pencil|write|scribble|caneta|lapis|marcador|risc")],
                "dur": (0.1, 2.2), "alvo": dict(dur=0.5, ataque=0.03, brilho=3500, grave=0.03, cauda=0.1), "nivel": -33, "ancora": "inicio"},
    "papel": {"nome": "Card de papel entra", "eventos": "fundo de papel que sobe (wipe), página que vira",
              "pools": [("05_Foley_Objetos", "Papel-Livros", r"paper|papel|page|slide|whoosh|flip|swish|folha")],
              "nao": r"tear|rasg|crumpl|amass|rip", "dur": (0.1, 1.4), "alvo": dict(dur=0.4, ataque=0.05, brilho=3000, grave=0.05, cauda=0.15),
              "nivel": -31},
    "impacto": {"nome": "Impacto de ênfase (número, carimbo)", "eventos": "número grande, 3D-NUM, carimbo, revelação",
                "pools": [("02_Impactos", "Hits", None), ("02_Impactos", "Sweeteners", None), ("02_Impactos", "Cinematicos", None),
                          ("02_Impactos", "Deep", None), ("02_Impactos", "Sub Drops", None), ("01_Transicoes", "Whoosh Hits", None)],
                "nao": r"explos|gun|tiro|\bcar\b|tree|barrel|lamppost|\bbin\b|cone|glass|wood|door|body|crash", "prefere": r"cinematic|sub|deep|boom|trailer|thud|low|braam|impact",
                "dur": (0.2, 4.0), "alvo": dict(dur=1.2, ataque=0.01, brilho=1200, grave=0.35, cauda=0.9), "nivel": -25},
    "riser": {"nome": "Riser antes de uma revelação", "eventos": "abertura, antes da vinheta, antes de um número",
              "pools": [("01_Transicoes", "Risers", None), ("01_Transicoes", "Reverse", None),
                        ("12_Horror_Fantasia_Magia", "Horror-Tensao/Transicoes", r"rise|riser|swell|reverse")],
              "dur": (0.8, 9.0), "alvo": dict(dur=2.5, ataque=2.0, brilho=2500, grave=0.1, cauda=0.1), "nivel": -28, "lead_max": 3.5},
    "saida_suave": {"nome": "Saída suave (pull-out final)", "eventos": "última cena: câmera recua devagar",
                    "pools": [("01_Transicoes", "Whooshes/Longos", None), ("01_Transicoes", "Whooshes", None),
                              ("08_Elementos", "Ar-Vento/Whooshes", None), ("01_Transicoes", "Reverse", None)],
                    "nao": r"hit|impact|boom|glitch", "dur": (0.8, 4.5), "alvo": dict(dur=1.8, ataque=0.9, brilho=1500, grave=0.1, cauda=0.6),
                    "nivel": -31},
    "logo_sting": {"nome": "Logo / vinheta (sting)", "eventos": "logo do cliente ou do parceiro, vinheta",
                   "pools": [("02_Impactos", "Sweeteners", None), ("01_Transicoes", "Whoosh Hits", None), ("02_Impactos", "Cinematicos", None),
                             ("14_Brilhos_Sinos", "Sinos", None), ("02_Impactos", "Braams-Horns", None)],
                   "dur": (0.5, 5.5), "alvo": dict(dur=2.0, ataque=0.05, brilho=1800, grave=0.3, cauda=1.5), "nivel": -25},
}
# intensity: subtil = shorter, less low end, shorter tail, softer onset, quieter; forte = the opposite
MOD = {"subtil": dict(dur=0.8, cauda=0.7, grave=-0.08, ataque=1.2, nivel=-4),
       "medio": dict(dur=1.0, cauda=1.0, grave=0.0, ataque=1.0, nivel=0),
       "forte": dict(dur=1.3, cauda=1.4, grave=0.12, ataque=0.9, nivel=3)}
# words of the storyboard's free `sfx` text -> movement (Portuguese and English)
KEYWORDS = [(r"riser|subida", "riser"), (r"impact|hit\b|boom|sub ?drop|grave|carimbo|stamp", "impacto"),
            (r"papel|paper|p[aá]gina", "papel"), (r"clique|click|mouse", "ui_clique"), (r"teclad|digit|typing", "ui_digitar"),
            (r"glitch", "glitch"), (r"brilho|sparkle|shine|glow", "brilho"), (r"flash|leak|clar[aã]o", "flash_luz"),
            (r"\bpop\b|pops", "pop_palavra"), (r"notifica|mensag|ding", "ui_notificacao"), (r"check|confirm", "check"),
            (r"marcador|risco|caneta|sublinh|tra[cç]o|scribble|marker", "escrita"), (r"tick|contador|count", "contador"),
            (r"whip", "transicao"), (r"whoosh|swoosh|transi", "transicao"), (r"vinheta|sting|logo", "logo_sting"),
            (r"slide|carrossel|desliz", "carrossel"), (r"viagem|travel|c[aâ]mera", "viagem_camera")]
CODE_EVENTS = {"viagem": "viagem_camera", "corte": "transicao", "titulo": "entrada_texto", "no": "pop_palavra",
               "galho": "pop_palavra", "onda": "contador", "liga": "escrita", "digita": "ui_digitar", "marca": "escrita",
               "varre": "escrita", "check": "check", "carimbo": "impacto", "fim": "saida_suave"}
FULL_FRAME = re.compile(r"^(CARD|3D|PARTNER|HF-|PAGINAS|GRADE|NOS|GALHO|PAINEL|CHECKLIST|PISO|UI-CARDS|BOARD)")


# ------------------------------------------------------------------ library + data file
def opt(a, k, d=None):
    return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


def library(a=()):
    p = opt(list(a), "--lib") or os.environ.get("SFX_LIBRARY") or studio.config().get("sfx_library")
    if not p:
        sys.exit('no SFX library on this PC: python tools/sfx.py biblioteca "<SFX_LIBRARY folder>"')
    p = Path(p)
    if not (p / "_sistema" / "dados" / "catalogo.json").exists():
        sys.exit(f"{p}: no _sistema/dados/catalogo.json (is this the SFX_LIBRARY folder?)")
    return p


def rj(p, d=None):
    p = Path(p)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else d


def wj(p, o):
    p = Path(p)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(o, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)


_lock = threading.Lock()


def data_path(lib):
    return lib / "_sistema" / "dados" / DATA_NAME


def load_data(lib):
    d = rj(data_path(lib)) or {}
    d.setdefault("versao", VERSION)
    for k in ("features", "pools", "aprovacao", "licencas", "editor"):
        d.setdefault(k, {})
    return d


def catalog(lib):
    return rj(lib / "_sistema" / "dados" / "catalogo.json", [])


def user_taste(lib):
    u = rj(lib / "_sistema" / "dados" / "usuario.json", {}) or {}
    return set(u.get("favoritos") or []), list(u.get("recentes") or [])


def norm(t):
    t = unicodedata.normalize("NFD", str(t).lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def in_area(item, area):
    """area 'cat' or 'cat/sub...' (prefix on whole path segments)."""
    path = f"{item['c']}/{item['s']}"
    return path == area or path.startswith(area.rstrip("/") + "/") or item["c"] == area


def pool_ids(cat, mov, excl=()):
    m = M[mov]
    rx_no = re.compile(m["nao"]) if m.get("nao") else None
    out = []
    for it in cat:
        if it.get("l") == "copyright" or any(in_area(it, e) for e in excl):
            continue
        txt = norm(it["n"] + " " + it.get("t", ""))
        if (rx_no and rx_no.search(txt)) or re.search(NAO_GLOBAL, txt):
            continue
        for c, s, rx in m["pools"]:
            if it["c"] != c or (s and not (it["s"] == s or it["s"].startswith(s + "/"))):
                continue
            if rx and not re.search(rx, txt):
                continue
            out.append(it["id"])
            break
    return out


def exclusions(cj=None):
    s = (cj or {}).get("sfx") or {}
    inc = list(s.get("incluir") or [])
    ex = [e for e in EXCLUIR if e not in inc]
    for tema, areas in TEMAS.items():
        if tema not in inc:
            ex += [a for a in areas if a not in inc]
    return ex + list(s.get("excluir") or [])


# ------------------------------------------------------------------ measurement
def _biquad(b, a):
    return np.array(b) / a[0], np.array(a) / a[0]


def k_filters(fs):
    """BS.1770 K-weighting (high shelf + high pass) for any sample rate."""
    G, Q, fc = 4.0, 1 / np.sqrt(2), 1500.0
    A, w0 = 10 ** (G / 40), 2 * np.pi * fc / fs
    al, c = np.sin(w0) / (2 * Q), np.cos(w0)
    sh = _biquad([A * ((A + 1) + (A - 1) * c + 2 * np.sqrt(A) * al), -2 * A * ((A - 1) + (A + 1) * c),
                  A * ((A + 1) + (A - 1) * c - 2 * np.sqrt(A) * al)],
                 [(A + 1) - (A - 1) * c + 2 * np.sqrt(A) * al, 2 * ((A - 1) - (A + 1) * c), (A + 1) - (A - 1) * c - 2 * np.sqrt(A) * al])
    Q, fc = 0.5, 38.0
    w0 = 2 * np.pi * fc / fs
    al, c = np.sin(w0) / (2 * Q), np.cos(w0)
    hp = _biquad([(1 + c) / 2, -(1 + c), (1 + c) / 2], [1 + al, -2 * c, 1 - al])
    return sh, hp


def read_audio(path, max_s=20.0):
    """-> (channels x samples float32, sample rate). wav/aiff/flac with soundfile, the rest through ffmpeg."""
    try:
        import soundfile as sf
        with sf.SoundFile(str(path)) as f:
            x = f.read(min(f.frames, int(f.samplerate * max_s)), dtype="float32", always_2d=True)
            return x.T, f.samplerate
    except Exception:  # noqa: BLE001 - mp3 / m4a / aac / odd wav headers
        fs = 44100
        r = subprocess.run(["ffmpeg", "-v", "error", "-t", str(max_s), "-i", str(path), "-ac", "2", "-ar", str(fs), "-f", "f32le", "-"],
                           capture_output=True)
        x = np.frombuffer(r.stdout, np.float32)
        if x.size < 4:
            raise ValueError("ffmpeg could not decode it")
        return x.reshape(-1, 2).T, fs


def measure(path):
    from scipy.signal import lfilter
    x, fs = read_audio(path)
    mono = x.mean(axis=0)
    n = mono.size
    peak = float(np.max(np.abs(x))) if n else 0.0
    if n < fs * 0.01 or peak < 1e-5:
        return {"mudo": True}
    hop, win = int(fs * 0.01), int(fs * 0.02)
    fr = np.lib.stride_tricks.sliding_window_view(np.pad(mono, (0, win)), win)[::hop]
    env = 20 * np.log10(np.sqrt((fr ** 2).mean(axis=1)) + 1e-9)
    ip = int(np.argmax(env))
    top = env[ip]
    above30 = np.nonzero(env > top - 30)[0]
    on, off = above30[0], above30[-1]
    sh, hp = k_filters(fs)
    k = lfilter(*hp, lfilter(*sh, x, axis=1), axis=1)
    p = (k ** 2).sum(axis=0)                                   # channel sum (weights 1, BS.1770)
    w4, h1 = int(fs * 0.4), int(fs * 0.1)
    if p.size < w4:
        blocks = np.array([p.mean()])
    else:
        cs = np.concatenate([[0], np.cumsum(p)])
        st = np.arange(0, p.size - w4 + 1, h1)
        blocks = (cs[st + w4] - cs[st]) / w4
    lk = -0.691 + 10 * np.log10(blocks + 1e-12)
    g = blocks[lk > -70]
    li = -0.691 + 10 * np.log10(g.mean() + 1e-12) if g.size else -70
    g2 = g[(-0.691 + 10 * np.log10(g + 1e-12)) > li - 10] if g.size else g
    li = -0.691 + 10 * np.log10(g2.mean() + 1e-12) if g2.size else li
    seg = mono[on * hop: off * hop + win]
    if seg.size < 2048:
        seg = np.pad(seg, (0, 2048 - seg.size))
    S = np.abs(np.fft.rfft(np.lib.stride_tricks.sliding_window_view(seg, 2048)[::1024] * np.hanning(2048), axis=1)) ** 2
    f = np.fft.rfftfreq(2048, 1 / fs)
    e = S.sum(axis=1)
    cen = float(((S * f).sum(axis=1) / (e + 1e-12) * e).sum() / (e.sum() + 1e-12))
    low = float(S[:, f < 150].sum() / (S.sum() + 1e-12))
    r = lambda v, n=3: round(float(v), n)  # noqa: E731
    return {"pico_db": r(20 * np.log10(peak), 2), "pico_t": r(ip * hop / fs), "inicio_t": r(on * hop / fs),
            "ataque": r((ip - on) * hop / fs), "cauda": r((off - ip) * hop / fs), "ativo": r((off - on) * hop / fs + 0.02),
            "lufs_m": r(lk.max(), 2), "lufs_i": r(li, 2), "brilho": int(round(cen)), "grave": r(low), "canais": int(x.shape[0]), "sr": int(fs)}


# ------------------------------------------------------------------ ranking
def target(mov, inten):
    a, m = M[mov]["alvo"], MOD[inten]
    return {"dur": a["dur"] * m["dur"], "ataque": a["ataque"] * m["ataque"], "brilho": a["brilho"] * (1.1 if inten == "subtil" else 1),
            "grave": max(0.0, a["grave"] + m["grave"]), "cauda": a["cauda"] * m["cauda"]}


def score(f, item, mov, inten, bonus):
    t = target(mov, inten)
    lo, hi = M[mov]["dur"]
    full = item.get("d") or f.get("ativo") or 0.0
    d = min(full, f.get("ativo") or full)
    s = abs(np.log((d + 0.02) / (t["dur"] + 0.02))) / np.log(2)
    s += abs(np.log((f["ataque"] + 0.01) / (t["ataque"] + 0.01))) / np.log(3)
    s += 0.8 * abs(np.log2(max(f["brilho"], 50) / t["brilho"]))
    s += 0.8 * abs(f["grave"] - t["grave"]) / 0.15
    s += 0.7 * abs(np.log((f["cauda"] + 0.05) / (t["cauda"] + 0.05))) / np.log(2.5)
    if not lo * 0.7 <= full <= hi * 1.5:
        s += 3
    if f["lufs_m"] < -45:                                  # nearly silent
        s += 3
    if f["pico_db"] > -0.1 and f["pico_db"] - f["lufs_m"] < 6:   # squashed / clipped master
        s += 0.5
    rx = [rx for c, sub, rx in M[mov]["pools"] if rx and item["c"] == c] + ([M[mov]["prefere"]] if M[mov].get("prefere") else [])
    if any(re.search(r, norm(item["n"] + " " + item.get("t", ""))) for r in rx):
        s -= 0.4
    return round(float(s - bonus), 3)


def bonuses(d, favs, recent, iid, mov):
    b = 1.2 if iid in favs else 0.0
    b += 0.2 if iid in recent[:200] else 0.0
    e = d["editor"].get(iid)
    if e:                                                      # his movement only when it is most of his uses of the sound
        n = (e.get("movimentos") or {}).get(mov, 0)
        b += 0.9 if n >= max(2, 0.5 * e.get("vezes", 1)) else 0.4
    return b


def family(item):
    return item.get("k", "") + "|" + re.sub(r"[\d_#\-\s.()]+", " ", norm(item["n"])).strip()[:18]


def rank_all(lib, d, cat, excl, keep_shortlist=True):
    by = {i["id"]: i for i in cat}
    favs, recent = user_taste(lib)
    for mov in M:
        ids = [i for i in pool_ids(cat, mov, excl) if i in d["features"] and not d["features"][i].get("mudo") and not d["features"][i].get("erro")]
        ranks = {}
        for inten in INTENS:
            sc = sorted(((score(d["features"][i], by[i], mov, inten, bonuses(d, favs, recent, i, mov)), i) for i in ids))
            ranks[inten] = [i for _, i in sc[:60]]
        old = (d["pools"].get(mov) or {}).get("shortlist") or []
        short, fam = [], {}
        for e0 in old if keep_shortlist else []:                # sounds already on the page stay there (approved or not)
            i = e0["id"]
            if i in by and i in ids:
                short.append({"id": i, "intensidade": e0.get("intensidade", "medio")})
                fam[family(by[i])] = fam.get(family(by[i]), 0) + 1
        for i, e in d["editor"].items():                       # what the editor used for this movement is always on the page
            n = (e.get("movimentos") or {}).get(mov, 0)
            if i in ids and n >= max(2, 0.5 * e.get("vezes", 1)) and not any(x["id"] == i for x in short):
                pos = {k: (ranks[k].index(i) if i in ranks[k] else 99) for k in INTENS}
                short.append({"id": i, "intensidade": min(pos, key=pos.get), "editor": True})
        want = {k: 3 for k in INTENS}
        for e in short:
            want[e["intensidade"]] = max(0, want[e["intensidade"]] - 1)
        for per_family in (2, 4):                               # a pool of near-identical variants: relax, so the page has 6+
            for inten in INTENS:
                for i in ranks[inten]:
                    if want[inten] <= 0 or len(short) >= 10:
                        break
                    if any(e["id"] == i for e in short) or fam.get(family(by[i]), 0) >= per_family:
                        continue
                    short.append({"id": i, "intensidade": inten})
                    fam[family(by[i])] = fam.get(family(by[i]), 0) + 1
                    want[inten] -= 1
            if len(short) >= 6:
                break
        d["pools"][mov] = {"n": len(ids), "rank": ranks, "shortlist": short}


# ------------------------------------------------------------------ commands
def cmd_biblioteca(a):
    if not a:
        sys.exit('python tools/sfx.py biblioteca "<SFX_LIBRARY folder>"')
    p = Path(a[0]).expanduser().resolve()
    if not (p / "_sistema" / "dados" / "catalogo.json").exists():
        sys.exit(f"{p}: no _sistema/dados/catalogo.json")
    c = studio.config()
    c["sfx_library"] = str(p).replace("\\", "/")
    studio.save_config(c)
    print(f"sfx_library = {c['sfx_library']}  ({studio.config_path()})")


def cmd_index(a):
    lib = library(a)
    workers = int(opt(a, "--workers", 8))
    cat = catalog(lib)
    by = {i["id"]: i for i in cat}
    with _lock:
        d = load_data(lib)
    want = set()
    for mov in M:                                              # every pool, themes included (a client may switch them on)
        want |= set(pool_ids(cat, mov, [e for e in EXCLUIR]))
    todo = []
    for i in sorted(want):
        p = lib / by[i]["p"]
        try:
            st = p.stat()
        except OSError:
            d["features"][i] = {"erro": "arquivo não encontrado"}
            continue
        sig = f"{st.st_size}-{int(st.st_mtime)}"
        if "--refazer" in a or (d["features"].get(i) or {}).get("sig") != sig:
            todo.append((i, p, sig))
    print(f"{len(want)} sounds in the pools, {len(todo)} to measure ({workers} workers)")
    done = [0]

    def one(job):
        i, p, sig = job
        try:
            f = measure(p)
        except Exception as e:  # noqa: BLE001
            f = {"erro": f"{type(e).__name__}: {e}"[:120]}
        f["sig"] = sig
        done[0] += 1
        if done[0] % 500 == 0:
            print(f"  {done[0]}/{len(todo)}", flush=True)
        return i, f

    with ThreadPoolExecutor(workers) as ex:
        for i, f in ex.map(one, todo):
            d["features"][i] = f
    for pack in sorted({i["k"] for i in cat}):
        d["licencas"].setdefault(pack, {"v": "?", "nota": ""})
    with _lock:
        wj(data_path(lib), {**load_data(lib), "features": d["features"]})   # the measurements first: never lost to a ranking error
    rank_all(lib, d, cat, EXCLUIR + sum(TEMAS.values(), []))
    d["atualizado"] = dt.datetime.now().isoformat(timespec="seconds")
    d["versao"] = VERSION
    with _lock:
        cur = load_data(lib)                                   # the review page may have written meanwhile: keep its marks
        d["aprovacao"], d["licencas"] = cur["aprovacao"] or d["aprovacao"], {**d["licencas"], **cur["licencas"]}
        wj(data_path(lib), d)
    bad = sum(1 for i in want if (d["features"].get(i) or {}).get("erro"))
    print(f"{data_path(lib)}: {len(want)} measured ({bad} unreadable)")
    for mov, p in d["pools"].items():
        print(f"  {mov:15s} pool {p['n']:5d}  shortlist {len(p['shortlist'])}")


def intensity_for(cj, a):
    v = opt(a, "--intensidade")
    if v:
        return v.replace("é", "e")
    s = ((cj or {}).get("sfx") or {}).get("intensidade") or "auto"
    if s != "auto":
        return s.replace("é", "e")
    k = float(((cj or {}).get("motion") or {}).get("intensity", 1.0))
    return "subtil" if k < 1.15 else "medio" if k < 1.4 else "forte"


def approved(d, mov):
    return {i for i, v in (d["aprovacao"].get(mov) or {}).items() if (v or {}).get("v") == "ok"}


def licence_of(d, item):
    return (d["licencas"].get(item.get("k", "")) or {}).get("v", "?")


def choose(d, cat_by, mov, inten, excl, n=3, previa=False):
    """approved sounds for the movement, best first for this intensity; [] when none (previa: the shortlist instead)."""
    ok = approved(d, mov)
    rank = ((d["pools"].get(mov) or {}).get("rank") or {})
    order = rank.get(inten, []) + [i for k in INTENS for i in rank.get(k, [])]
    order += sorted(ok - set(order))
    out, seen = [], set()
    for i in order:
        it = cat_by.get(i)
        if i in seen or not it or any(in_area(it, e) for e in excl) or licence_of(d, it) == "nao":
            continue
        seen.add(i)
        if i in ok:
            out.append((i, "aprovado"))
    if not out and previa:
        short = [e["id"] for e in (d["pools"].get(mov) or {}).get("shortlist") or []]
        nao = {i for i, v in (d["aprovacao"].get(mov) or {}).items() if (v or {}).get("v") == "nao"}
        pref = [e for e in short if e in order[:12]] + short
        out = [(i, "previa") for i in dict.fromkeys(pref) if i not in nao and i in cat_by][:n]
    return out[:n]


def client_cj(a, ep=None):
    slug = opt(a, "--client") or (studio.client_of(ep) if ep else None)
    if not slug:
        return {}
    try:
        return studio.client_json(slug)
    except Exception:  # noqa: BLE001
        return {}


def describe(d, it, lib=None):
    f = d["features"].get(it["id"]) or {}
    return (f"{it['id']}  {it['n'][:48]:48s} {it.get('d') or 0:5.2f}s  ataque {f.get('ataque', 0):.2f}  cauda {f.get('cauda', 0):.2f}  "
            f"{f.get('brilho', 0):5d} Hz  grave {f.get('grave', 0):.2f}  {f.get('lufs_m', 0):6.1f} LUFS  [{it['k']} · licença {licence_of(d, it)}]")


def cmd_pick(a):
    if not a or a[0].startswith("--"):
        sys.exit("python tools/sfx.py pick <movimento> [--intensidade subtil|medio|forte] [--n 3] [--client <slug>] [--todos]")
    mov = a[0]
    if mov not in M:
        sys.exit(f"unknown movement '{mov}': {', '.join(M)}")
    lib = library(a)
    d = load_data(lib)
    if not d["pools"]:
        sys.exit("no index yet: python tools/sfx.py index")
    cat_by = {i["id"]: i for i in catalog(lib)}
    cj = client_cj(a)
    inten = intensity_for(cj, a)
    n = int(opt(a, "--n", 3))
    got = choose(d, cat_by, mov, inten, exclusions(cj), n)
    print(f"{mov} ({M[mov]['nome']}) · intensidade {inten}")
    if not got:
        print("  nenhum som aprovado ainda: ouça a shortlist em  python tools/sfx.py revisar")
    for i, _ in got:
        print("  ok " + describe(d, cat_by[i]))
        print(f"     {lib / cat_by[i]['p']}")
    if "--todos" in a or not got:
        marks = d["aprovacao"].get(mov) or {}
        for e in (d["pools"].get(mov) or {}).get("shortlist") or []:
            v = (marks.get(e["id"]) or {}).get("v", "--")
            print(f"  [{v:>3s}] {e['intensidade']:6s} " + describe(d, cat_by[e["id"]]))


def cmd_movimentos(a):
    lib = library(a) if (studio.config().get("sfx_library") or os.environ.get("SFX_LIBRARY") or "--lib" in a) else None
    d = load_data(lib) if lib else {"pools": {}, "aprovacao": {}}
    for mov, m in M.items():
        p = d["pools"].get(mov) or {}
        ok = len(approved(d, mov)) if d.get("aprovacao") is not None else 0
        print(f"{mov:15s} {m['nome']:42s} pool {p.get('n', '-')!s:>5s}  aprovados {ok}/{len(p.get('shortlist') or [])}   <- {m['eventos']}")


# ------------------------------------------------------------------ review page (local)
def cmd_revisar(a):
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import mimetypes
    lib = library(a)
    port = int(opt(a, "--port", 8767))
    page = (Path(__file__).resolve().parent / "sfx_revisar.html").read_text(encoding="utf-8")
    cat_by = {i["id"]: i for i in catalog(lib)}
    waves = rj(lib / "_sistema" / "dados" / "waveforms.json", {}) or {}
    hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
    origins = {None, f"http://127.0.0.1:{port}", f"http://localhost:{port}"}

    def payload():
        d = load_data(lib)
        movs = []
        for mov, m in M.items():
            p = d["pools"].get(mov) or {}
            marks = d["aprovacao"].get(mov) or {}
            ids = [e["id"] for e in p.get("shortlist") or []] + [i for i in marks if i not in {e["id"] for e in p.get("shortlist") or []}]
            its = []
            for e in ids:
                it = cat_by.get(e)
                if not it:
                    continue
                f = d["features"].get(e) or {}
                its.append({"id": e, "n": it["n"], "k": it["k"], "area": f"{it['c']} / {it['s']}", "d": it["d"],
                            "intensidade": next((x["intensidade"] for x in p.get("shortlist") or [] if x["id"] == e), "-"),
                            "f": {k: f.get(k) for k in ("ataque", "cauda", "brilho", "grave", "lufs_m", "pico_db")},
                            "v": (marks.get(e) or {}).get("v"), "w": waves.get(e, ""), "editor": bool(d["editor"].get(e))})
            movs.append({"id": mov, "nome": m["nome"], "eventos": m["eventos"], "pool": p.get("n", 0), "itens": its})
        packs = {k: {"v": v.get("v", "?"), "nota": v.get("nota", ""), "n": sum(1 for i in cat_by.values() if i["k"] == k)}
                 for k, v in sorted(d["licencas"].items())}
        return {"movimentos": movs, "licencas": packs, "atualizado": d.get("atualizado")}

    allowed = lambda: {e["id"] for p in load_data(lib)["pools"].values() for e in p.get("shortlist") or []}  # noqa: E731

    class H(BaseHTTPRequestHandler):
        def log_message(self, *x):
            pass

        def _ok(self):
            if self.headers.get("Host") not in hosts:
                self.send_error(403)
                return False
            return True

        def _send(self, body, ctype, code=200):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._ok():
                return
            if self.path in ("/", "/index.html"):
                return self._send(page.encode("utf-8"), "text/html; charset=utf-8")
            if self.path == "/dados":
                return self._send(json.dumps(payload(), ensure_ascii=False).encode("utf-8"), "application/json")
            m = re.fullmatch(r"/audio/([0-9a-f]{6,16})", self.path)
            if m and m.group(1) in allowed() and m.group(1) in cat_by:
                f = lib / cat_by[m.group(1)]["p"]
                if f.is_file():
                    return self._send(f.read_bytes(), mimetypes.guess_type(f.name)[0] or "application/octet-stream")
            self.send_error(404)

        def do_POST(self):
            if not self._ok() or self.headers.get("Origin") not in origins:
                return self.send_error(403)
            try:
                body = json.loads(self.rfile.read(min(int(self.headers.get("Content-Length", 0)), 4096)) or b"{}")
            except ValueError:
                return self.send_error(400)
            now = dt.datetime.now().isoformat(timespec="seconds")
            with _lock:
                d = load_data(lib)
                if self.path == "/marcar" and body.get("mov") in M and body.get("id") in allowed() and body.get("v") in ("ok", "nao", None):
                    marks = d["aprovacao"].setdefault(body["mov"], {})
                    if body["v"] is None:
                        marks.pop(body["id"], None)
                    else:
                        marks[body["id"]] = {"v": body["v"], "quando": now}
                elif self.path == "/licenca" and body.get("pack") in d["licencas"] and body.get("v") in ("sim", "nao", "?"):
                    d["licencas"][body["pack"]] = {"v": body["v"], "nota": str(body.get("nota", ""))[:300], "quando": now}
                else:
                    return self.send_error(400)
                wj(data_path(lib), d)
            self._send(b'{"ok":true}', "application/json")

    try:
        srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    except OSError:
        sys.exit(f"port {port} is in use: --port <another>")
    url = f"http://127.0.0.1:{port}/"
    print(f"revisão de SFX em {url}  (Ctrl+C para parar; as marcas vão para {data_path(lib)})")
    if "--no-open" not in a:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


# ------------------------------------------------------------------ motion events
def words_find(W, word, t0, t1):
    key = [x for x in norm(word).split() if len(x) > 2] or norm(word).split()
    if not key:
        return None
    k = max(key, key=len)[:6]
    for w in W:
        if t0 - 0.05 <= w["t"] <= t1 and norm(w["w"]).strip(".,!?:;\"'").startswith(k):
            return w["t"]
    return None


def build_data(ep):
    """the D block of the newest After build script (scenes with their row times as built)."""
    fs = sorted((ep / "after").glob("*_build.jsx"), key=lambda p: p.stat().st_mtime) if (ep / "after").exists() else []
    for p in reversed(fs):
        s = p.read_text(encoding="utf-8-sig")
        i = s.find("var D = ")
        if i >= 0:
            try:
                return json.JSONDecoder().raw_decode(s[i + 8:])[0], p
            except ValueError:
                continue
    return None, None


def sfx_words(text):
    """free storyboard text ('riser curto + hit suave', 'papel por item') -> [(movement, per_row)]."""
    out = []
    for part in re.split(r"\+|,| e |;| then ", norm(text or "")):
        for rx, mov in KEYWORDS:
            if re.search(rx, part):
                out.append((mov, bool(re.search(r"por item|cada|each|per", part))))
                break
    return out


def after_events(ep, R):
    mm = rj(ep / "motion" / "motion_map.json")
    if not mm:
        return [], None
    W = rj(ep / "study" / "final_words.json", [])
    segs = (rj(ep / "study" / "study.json", {}) or {}).get("segments") or []
    D, src = build_data(ep)
    built = {s["id"]: s for s in (D or {}).get("scenes", [])}
    scenes = mm["scenes"]
    ev = []
    for k, sc in enumerate(scenes):
        t, te, typ = sc["t"], sc["te"], sc.get("type", "")
        b = built.get(sc["id"]) or {}
        rows = []
        if b.get("blocks"):
            rows = [[t + ln.get("t0", 0) for ln in bl.get("lines", [])] for bl in b["blocks"]]
        elif b.get("lines"):
            rows = [[t + ln.get("t0", 0) for ln in b["lines"]]]
        else:
            ts, prev = [], t
            items = sc.get("rows") or [[x] for x in (sc.get("small") or [])] + [[sc.get("key", "")], [sc.get("serif", "")]]
            for r in items:
                txt = " ".join(x for x in (r if isinstance(r, list) else [r]) if x)
                hit = words_find(W, txt, prev, te) if txt else None
                if hit is not None:
                    ts.append(hit)
                    prev = hit
            rows = [sorted(ts) or [t]]
        first = min((r[0] for r in rows if r), default=t)
        all_rows = sorted({round(x, 3) for r in rows for x in r})
        trans = b.get("trans") or sc.get("trans")
        full = bool(FULL_FRAME.match(typ)) or typ.startswith("OPEN")
        last, opening = k == len(scenes) - 1 or sc.get("fecha"), k == 0 or typ.startswith("OPEN") or sc.get("abre")
        base = f"cena {sc['id']} {typ}"
        if isinstance(sc.get("sfx"), list):                    # structured: [{"mov": "...", "palavra": "...", "t": s}]
            for e in sc["sfx"]:
                if e.get("mov") in M:
                    tt = e.get("t") if e.get("t") is not None else (words_find(W, e.get("palavra", ""), t, te) if e.get("palavra") else first)
                    ev.append({"t": tt if tt is not None else first, "mov": e["mov"], "de": base + " (storyboard)"})
        else:
            said = sfx_words(sc.get("sfx"))
            if said:                                           # the storyboard named the sounds: it wins
                for mov, per_row in said:
                    if mov == "transicao" and not full:
                        mov = "entrada_texto"                  # a whoosh on an overlay is a text entrance, not a cut
                    if mov == "riser":
                        sting = next((s["s"] for s in segs if s.get("role") == "logo" and t <= s["s"] <= te + 10), None)
                        to_sting = sting is not None and re.search(r"vinheta|logo|sting", norm(sc.get("sfx")))
                        ev.append({"t": sting if to_sting else first, "mov": mov, "de": base + (" até a vinheta" if to_sting else "") + " (storyboard)"})
                    elif mov == "transicao":
                        ev.append({"t": t, "mov": mov, "de": base + " entra (storyboard)"})
                    elif per_row or mov in ("ui_clique", "contador", "check"):
                        for x in all_rows:
                            ev.append({"t": x, "mov": mov, "de": base + " linha (storyboard)"})
                    else:
                        ev.append({"t": first, "mov": mov, "de": base + " (storyboard)"})
            else:
                if opening:
                    ev.append({"t": first, "mov": "riser", "de": base + " abertura"})
                if typ == "PAGINAS":
                    for r in rows[1:]:
                        if r:
                            ev.append({"t": r[0] - 0.1, "mov": "viagem_camera", "de": base + " câmera chega"})
                if full and not opening:
                    ev.append({"t": t, "mov": {"whip": "transicao", "wipe": "papel", "iris": "brilho", "glitch": "glitch",
                                               "zoom-blur": "transicao", "empurrao": "carrossel"}.get(trans or "", "transicao"),
                               "de": base + f" entra ({trans or 'transição'})"})
                kind = ("check" if "CHECKLIST" in typ or typ == "LIST" else "escrita" if "STRIKE" in typ else "entrada_texto")
                for x in all_rows:
                    ev.append({"t": x, "mov": kind if x != first or kind == "check" else "entrada_texto", "de": base + " linha"})
                if "NUM" in typ:
                    ev.append({"t": all_rows[-1] if all_rows else first, "mov": "impacto", "de": base + " número"})
                if typ.startswith("TELA") or typ == "CTA":
                    ev.append({"t": first, "mov": "ui_notificacao" if typ == "CTA" else "pop_palavra", "de": base})
        if last:
            ev.append({"t": te - R["fim_s"] * 0.5, "mov": "saida_suave", "de": base + " pull-out final"})
        elif full and not (k + 1 < len(scenes) and scenes[k + 1]["t"] - te < 0.3 and FULL_FRAME.match(scenes[k + 1].get("type", ""))):
            ev.append({"t": te, "mov": "transicao", "de": base + " sai"})
    for s in segs:
        if s.get("role") == "logo":
            ev.append({"t": s["s"] + 0.05, "mov": "logo_sting", "de": "vinheta"})
    dur = ((rj(ep / "study" / "study.json", {}) or {}).get("stats") or {}).get("final_s") or (D or {}).get("duration")
    return ev, {"fonte": str(src or ep / "motion" / "motion_map.json"), "dur": dur}


def code_events(folder, R):
    tl = rj(folder / "out" / "timeline.json")
    if not tl:
        return [], None
    ev = []
    for e in tl["events"]:
        mov = CODE_EVENTS.get(e.get("tipo"))
        if not mov:
            continue
        t = e["t"]
        if mov == "viagem_camera":
            t += 0.8 * float(e.get("dur", R["viagem_s"]))
        if mov == "saida_suave":
            t += R["fim_s"] * 0.5
        n = int(e.get("n", 1) or 1)
        if mov == "check" and n > 1:
            ev += [{"t": t + i * 0.15, "mov": mov, "de": f"timeline {e['tipo']} {i + 1}/{n}"} for i in range(n)]
            continue
        ev.append({"t": t, "mov": mov, "de": f"timeline {e['tipo']}", "n": n})
    return ev, {"fonte": str(folder / "out" / "timeline.json"), "dur": tl["film"]["dur"]}


# ------------------------------------------------------------------ plan
# longest cue per movement (s): a long file is cut there with a short fade (an editor slices a 7 s hiss to 0.4 s)
MAXLEN = {"entrada_texto": 1.0, "pop_palavra": 0.5, "contador": 2.0, "carrossel": 1.2, "viagem_camera": 2.0, "transicao": 1.2,
          "glitch": 0.5, "flash_luz": 2.5, "brilho": 2.0, "ui_clique": 0.3, "ui_digitar": 4.0, "ui_notificacao": 1.2, "check": 0.6,
          "escrita": 1.0, "papel": 1.0, "impacto": 3.0, "riser": 4.0, "saida_suave": 3.0, "logo_sting": 4.0}
GAP = {"subtil": 0.5, "medio": 0.3, "forte": 0.15}          # shortest gap between two cues of the same movement
LIMIT = 10 ** (-1.5 / 20)                                   # -1 dBTP with a 0.5 dB margin on measured sample peaks


def cmd_plan(a):
    if not a or a[0].startswith("--"):
        sys.exit("python tools/sfx.py plan <episode | code folder> [--xml <final.xml>] [--musica <file>] [--previa]")
    ep = Path(a[0]).resolve()
    lib = library(a)
    d = load_data(lib)
    if not d["pools"]:
        sys.exit("no index yet: python tools/sfx.py index")
    cat_by = {i["id"]: i for i in catalog(lib)}
    try:
        cj = client_cj(a, ep)
    except Exception:  # noqa: BLE001
        cj = {}
    inten = intensity_for(cj, a)
    if inten not in INTENS:
        sys.exit(f"intensidade '{inten}': use subtil | medio | forte")
    excl = exclusions(cj)
    ritmo = {"viagem_s": 0.6, "fim_s": 0.8, **((cj or {}).get("ritmo") or {})}
    ev, src = after_events(ep, ritmo)
    if not ev:
        ev, src = code_events(ep, ritmo)
    if not ev:
        sys.exit(f"{ep}: no motion events (motion/motion_map.json, or out/timeline.json from node render.mjs --timeline)")
    previa = "--previa" in a
    off_db = float(((cj or {}).get("sfx") or {}).get("ganho_db", 0) or 0)
    # thin out: one cue per movement within the gap (rows built at the same instant, a busy hook on a subtle client)
    ev.sort(key=lambda e: e["t"])
    kept, last = [], {}
    for e in ev:
        if e["t"] is None or e["t"] < 0:
            e["t"] = max(0.0, e["t"] or 0.0)
        if e["mov"] in last and e["t"] - last[e["mov"]] < GAP[inten]:
            continue
        last[e["mov"]] = e["t"]
        kept.append(e)
    chosen = {}                                                # one sound per movement for the whole episode
    for mov in dict.fromkeys(e["mov"] for e in kept):
        got = choose(d, cat_by, mov, inten, excl, 1, previa)
        chosen[mov] = got[0] if got else (None, "sem som aprovado")
    cues, layer_of = [], {}
    for e in kept:
        iid, status = chosen[e["mov"]]
        cue = {"t": round(e["t"], 3), "movimento": e["mov"], "de": e["de"], "status": status, "arquivo": None}
        if iid:
            it, f = cat_by[iid], d["features"][iid]
            m = M[e["mov"]]
            peak_t = f["inicio_t"] if m.get("ancora") == "inicio" else f["pico_t"]
            src_in = max(0.0, peak_t - m["lead_max"]) if m.get("lead_max") else 0.0
            start = e["t"] - (peak_t - src_in)
            if start < 0:
                src_in, start = src_in - start, 0.0
            length = min(it.get("d") or 1e9, f["inicio_t"] + f["ativo"] + 0.15) - src_in
            cut = length > MAXLEN[e["mov"]] + (peak_t - src_in if m.get("lead_max") else 0)
            length = min(length, MAXLEN[e["mov"]] + (peak_t - src_in if m.get("lead_max") else 0))
            if e["mov"] == "ui_digitar" and e.get("n"):
                length = min(length, max(0.3, e["n"] / 26 + 0.1))
            gain = m["nivel"] + MOD[inten]["nivel"] + off_db - f["lufs_m"]
            gain = min(12.0, max(-30.0, gain))
            gain = min(gain, -1.5 - f["pico_db"])
            if iid not in layer_of:
                layer_of[iid] = len(layer_of) + 1
            cue.update(arquivo=str(lib / it["p"]), id=iid, nome=it["n"], pack=it["k"], licenca=licence_of(d, it),
                       inicio=round(start, 3), entrada_fonte=round(src_in, 3), dur=round(max(0.05, length), 3),
                       ganho_db=round(gain, 1), pico_db=f["pico_db"], canais=f.get("canais", 2), camada=layer_of[iid],
                       fade_s=0.08 if cut else 0.0)
        cues.append(cue)
    placed = [c for c in cues if c["arquivo"]]
    # same file overlapping itself -> its own second layer (the same sound stays on its layers)
    busy = {}
    for c in sorted(placed, key=lambda c: c["inicio"]):
        lanes = busy.setdefault(c["id"], [])
        for li, end in enumerate(lanes):
            if c["inicio"] >= end:
                lanes[li] = c["inicio"] + c["dur"]
                c["sub"] = li
                break
        else:
            lanes.append(c["inicio"] + c["dur"])
            c["sub"] = len(lanes) - 1
    order = []
    for c in sorted(placed, key=lambda c: (c["camada"], c["sub"])):
        if (c["camada"], c["sub"]) not in order:
            order.append((c["camada"], c["sub"]))
    for c in placed:
        c["camada"] = order.index((c["camada"], c["sub"])) + 1
        c.pop("sub")
    for _ in range(3):                                          # stacked cues: sum of peaks under -1 dBTP
        for c in placed:
            grp = [x for x in placed if x["inicio"] < c["inicio"] + c["dur"] and c["inicio"] < x["inicio"] + x["dur"]]
            s = sum(10 ** ((x["pico_db"] + x["ganho_db"]) / 20) for x in grp)
            if s > LIMIT:
                cut = 20 * np.log10(s / LIMIT)
                for x in grp:
                    x["ganho_db"] = round(x["ganho_db"] - cut, 1)
    bed = None
    mus = opt(a, "--musica") or ((cj or {}).get("sfx") or {}).get("musica")
    if mus:
        mp = Path(mus) if Path(mus).is_absolute() else (ep / mus)
        if "80_Musica/Com Copyright" in str(mp).replace("\\", "/"):
            sys.exit(f"{mp}: copyrighted music (YouTube claim) - choose a licensed track")
        if not mp.exists():
            sys.exit(f"--musica {mp}: not found")
        f = measure(mp)
        prog = float(src.get("dur") or 1e9)
        length = min(_duration(mp), prog, max(c["t"] for c in cues) + 2.0)   # the tail: 2 s past the last motion event
        bed = {"arquivo": str(mp), "inicio": 0.0, "entrada_fonte": 0.0, "dur": round(length, 3),
               "ganho_db": round(min(12.0, (-14 - 20) - f["lufs_i"]), 1), "cauda_s": 2.0, "pico_db": f["pico_db"],
               "canais": f.get("canais", 2), "nota": "20 dB sob a voz (-14 LUFS); termina 2 s depois do último evento, com fade nesses 2 s"}
    out = Path(opt(a, "--out")) if opt(a, "--out") else ep / "work" / "sfx_plan.json"
    plan = {"episodio": ep.name, "fonte": src["fonte"], "intensidade": inten, "previa": previa, "gerado": dt.datetime.now().isoformat(timespec="seconds"),
            "regras": "pico do som na palavra/evento; um som por movimento; o mesmo som sempre na mesma camada; soma dos picos < -1 dBTP; trilha -20 dB sob a voz com 2 s de cauda",
            "movimentos": {mov: {"id": v[0], "status": v[1], "nome": cat_by[v[0]]["n"] if v[0] else None} for mov, v in chosen.items()},
            "cues": cues, "trilha": bed}
    out.parent.mkdir(parents=True, exist_ok=True)
    wj(out, plan)
    miss = sorted({c["movimento"] for c in cues if not c["arquivo"]})
    lic = sorted({c["pack"] for c in placed if c.get("licenca") != "sim"})
    print(f"{out}: {len(cues)} cues ({len(placed)} com som, {len({c['camada'] for c in placed})} camadas) · intensidade {inten}"
          + (" · PREVIA (sons ainda não aprovados)" if previa else ""))
    for mov, (iid, st) in chosen.items():
        n = sum(1 for c in cues if c["movimento"] == mov)
        print(f"  {mov:15s} x{n:3d}  {st:16s} {cat_by[iid]['n'][:50] if iid else '-'}")
    if miss:
        print(f"  sem som aprovado: {', '.join(miss)} -> python tools/sfx.py revisar (ou --previa para ouvir no contexto)")
    if lic:
        print(f"  licença a confirmar (packs): {', '.join(lic)}")
    if opt(a, "--xml"):
        write_xml(ep, a, placed, bed, previa)


def _duration(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ------------------------------------------------------------------ Premiere XML copy
def write_xml(ep, a, cues, bed, previa):
    import xml.etree.ElementTree as ET
    xmlp = Path(opt(a, "--xml"))
    root = ET.parse(xmlp).getroot()
    seqs = [s for s in root.iter("sequence") if s.find("media") is not None]
    seq = next((s for s in seqs if s.findtext("name") == opt(a, "--seq")), None) if opt(a, "--seq") else (seqs[0] if seqs else None)
    if seq is None:
        sys.exit(f"sequence not found in {xmlp}: {[s.findtext('name') for s in seqs]}")
    tb = int(seq.findtext("rate/timebase") or 30)
    ntsc = (seq.findtext("rate/ntsc") or "FALSE").upper() == "TRUE"
    fps = tb * 1000 / 1001 if ntsc else tb
    fr = lambda s: int(round(s * fps))  # noqa: E731
    audio = seq.find("media/audio")
    n0 = len(audio.findall("track"))
    files, nid = {}, [0]

    def sub(el, tag, text=None, **att):
        e = ET.SubElement(el, tag, att)
        if text is not None:
            e.text = str(text)
        return e

    def rate(el):
        r = sub(el, "rate")
        sub(r, "timebase", tb)
        sub(r, "ntsc", "TRUE" if ntsc else "FALSE")

    def file_el(clip, path, ch):
        if path in files:
            sub(clip, "file", id=files[path])
            return
        files[path] = f"sfx-file-{len(files) + 1}"
        f = sub(clip, "file", id=files[path])
        sub(f, "name", Path(path).name)
        sub(f, "pathurl", "file://localhost/" + quote(path.replace("\\", "/"), safe="/:"))
        rate(f)
        sub(f, "duration", fr(_duration(path)) or 1)
        au = sub(sub(f, "media"), "audio")
        sc = sub(au, "samplecharacteristics")
        sub(sc, "depth", 16)
        sub(sc, "samplerate", 48000)
        sub(au, "channelcount", ch)

    def level(clip, g, fade_out_s=0.0, length_f=0):
        eff = sub(sub(clip, "filter"), "effect")
        sub(eff, "name", "Audio Levels")
        sub(eff, "effectid", "audiolevels")
        sub(eff, "effectcategory", "audiolevels")
        sub(eff, "effecttype", "audiolevels")
        sub(eff, "mediatype", "audio")
        p = sub(eff, "parameter", authoringApp="PremierePro")
        sub(p, "parameterid", "level")
        sub(p, "name", "Level")
        sub(p, "valuemin", 0)
        sub(p, "valuemax", 3.98109)
        v = round(10 ** (min(12.0, g) / 20), 5)
        sub(p, "value", v)
        if fade_out_s and length_f:
            for when, val in ((max(0, length_f - fr(fade_out_s)), v), (length_f, 0)):
                k = sub(p, "keyframe")
                sub(k, "when", when)
                sub(k, "value", val)

    def clipitem(track, c, ch_index, stereo, label, link_ids, fade=0.0):
        nid[0] += 1
        cid = f"sfx-clip-{nid[0]}"
        att = {"id": cid}
        if stereo:
            att["premiereChannelType"] = "stereo"
        clip = sub(track, "clipitem", **att)
        sub(clip, "name", Path(c["arquivo"]).name)
        sub(clip, "enabled", "TRUE")
        rate(clip)
        s, L, i = fr(c["inicio"]), max(1, fr(c["dur"])), fr(c["entrada_fonte"])
        sub(clip, "start", s)
        sub(clip, "end", s + L)
        sub(clip, "in", i)
        sub(clip, "out", i + L)
        file_el(clip, c["arquivo"], c.get("canais", 2))
        st = sub(clip, "sourcetrack")
        sub(st, "mediatype", "audio")
        sub(st, "trackindex", ch_index)
        level(clip, c["ganho_db"], fade or c.get("fade_s", 0.0), L)
        sub(sub(clip, "labels"), "label2", label)
        return cid, clip

    def track(stereo, idx):
        att = {"TL.SQTrackAudioKeyframeStyle": "0", "TL.SQTrackShy": "0", "TL.SQTrackExpandedHeight": "17", "TL.SQTrackExpanded": "0",
               "MZ.TrackTargeted": "0", "PannerCurrentValue": "0.5", "PannerName": "Balance"}
        if stereo:
            att.update({"currentExplodedTrackIndex": str(idx), "totalExplodedTrackCount": "2", "premiereTrackType": "Stereo"})
        else:
            att.update({"premiereTrackType": "Mono"})
        t = ET.Element("track", att)
        audio.append(t)
        return t

    def lay(group, label, fade=0.0):
        stereo = any(c.get("canais", 2) >= 2 for c in group)
        tracks = [track(True, 0), track(True, 1)] if stereo else [track(False, 0)]
        base = len(audio.findall("track")) - len(tracks) + 1
        for c in sorted(group, key=lambda c: c["inicio"]):
            made = [clipitem(tr, c, k + 1 if c.get("canais", 2) >= 2 else 1, stereo, label, None, fade) for k, tr in enumerate(tracks)]
            if stereo:
                for cid, clip in made:
                    for k, (other, _) in enumerate(made):
                        ln = sub(clip, "link")
                        sub(ln, "linkclipref", other)
                        sub(ln, "mediatype", "audio")
                        sub(ln, "trackindex", base + k)
                        sub(ln, "clipindex", len(tracks[k].findall("clipitem")))
                        sub(ln, "groupindex", 1)
        return len(tracks)

    layers = {}
    for c in cues:
        layers.setdefault(c["camada"], []).append(c)
    added = 0
    for n in sorted(layers):
        added += lay(layers[n], "Caribbean" if not previa else "Rose")
    if bed:
        added += lay([bed], "Forest", fade=bed["cauda_s"])
    name = (seq.findtext("name") or "seq").strip()
    seq.find("name").text = name + ("_SFX_PREVIA" if previa else "_SFX")
    dst = Path(opt(a, "--xml-out")) if opt(a, "--xml-out") else ep / "premiere" / f"{xmlp.stem}_sfx{'_PREVIA' if previa else ''}.xml"
    n, base = 2, dst
    while dst.exists() or dst.resolve() == xmlp.resolve():
        dst = base.with_name(f"{base.stem}_v{n}.xml")
        n += 1
    dst.parent.mkdir(parents=True, exist_ok=True)
    body = ET.tostring(root, encoding="unicode")
    dst.write_text('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n' + body, encoding="utf-8")
    print(f"XML {dst}: {len(cues)} SFX em {added} faixas novas (a partir de A{n0 + 1})" + (" + trilha" if bed else "")
          + f" · sequência {seq.findtext('name')}")


# ------------------------------------------------------------------ learn from the editor's final sequence
def cmd_aprender(a):
    if not a or a[0].startswith("--"):
        sys.exit("python tools/sfx.py aprender <episode>")
    ep = Path(a[0]).resolve()
    seqf = ep / "final_study" / "premiere" / "sequence.json"
    if not seqf.exists():
        sys.exit(f"{seqf}: run the estudo-final skill first (tools/study_final.py)")
    lib = library(a)
    cat = catalog(lib)
    key = lambda s: re.sub(r"\s*#[0-9a-f]{6,}$", "", norm(Path(str(s).replace("\\", "/")).stem)).strip()  # noqa: E731
    by = {}
    for it in cat:
        by.setdefault(key(it["p"]), it)
        if it.get("o"):
            by.setdefault(key(it["o"]), it)
    seq = rj(seqf)
    # movements the editor's own video tracks show (same timeline as his sounds: always reliable)
    ev = []
    for tr in seq["tracks"]:
        if not tr["track"].startswith("V"):
            continue
        for it in tr["items"]:
            if it.get("off"):
                continue
            txt = norm((it.get("name") or "") + " " + json.dumps(it.get("fx") or [], ensure_ascii=False))
            mov = ("transicao" if re.search(r"mister horse|transition|transicao|whip|zoom in|slide", txt)
                   else "glitch" if re.search(r"digital|glitch", txt)
                   else "ui_notificacao" if re.search(r"subscribe|inscrev|like", txt) else None)
            if mov and not any(e["mov"] == mov and abs(e["t"] - it["start"]) < 0.6 for e in ev):
                ev.append({"t": it["start"], "mov": mov, "de": f"{tr['track']} {it.get('name')}"})
    # the motion plan only when the final cut has the length of the studied cut (an inserted cold open shifts every time)
    cj = client_cj(a, ep)
    ritmo = {"viagem_s": 0.6, "fim_s": 0.8, **((cj or {}).get("ritmo") or {})}
    end = max((it["end"] for tr in seq["tracks"] for it in tr["items"]), default=0)
    studied = (((rj(ep / "study" / "study.json", {}) or {}).get("stats") or {}).get("sequence_min") or 0) * 60
    aligned = studied and abs(end - studied) < 1.5
    if aligned:
        ev += after_events(ep, ritmo)[0] or code_events(ep, ritmo)[0]
    d = load_data(lib)
    seen, outside, used = {}, {}, 0
    for tr in seq["tracks"]:
        if not tr["track"].startswith("A") or tr["track"] == "A1":
            continue
        for it in tr["items"]:
            nm = it.get("name") or ""
            if not nm or nm.lower().endswith((".mp4", ".mov")) or (it["end"] - it["start"]) > 20:
                continue                                       # music beds and video audio are not SFX
            hit = by.get(key(it.get("media") or nm)) or by.get(key(nm))
            if not hit or hit["c"] in ("80_Musica",):
                outside[nm] = outside.get(nm, 0) + 1
                continue
            used += 1
            f = d["features"].get(hit["id"]) or {}
            tpk = it["start"] - float(it.get("in") or 0) + f.get("pico_t", 0)
            near = min(ev, key=lambda e: min(abs(e["t"] - tpk), abs(e["t"] - it["start"])), default=None)
            mov = near["mov"] if near and min(abs(near["t"] - tpk), abs(near["t"] - it["start"])) < 0.5 else None
            s = seen.setdefault(hit["id"], {"vezes": 0, "movimentos": {}, "n": hit["n"]})
            s["vezes"] += 1
            if mov:
                s["movimentos"][mov] = s["movimentos"].get(mov, 0) + 1
    for iid, s in seen.items():
        e = d["editor"].setdefault(iid, {"vezes": 0, "movimentos": {}, "episodios": []})
        if ep.name in e["episodios"]:
            continue                                           # an episode counts once
        e["vezes"] += s["vezes"]
        for k, v in s["movimentos"].items():
            e["movimentos"][k] = e["movimentos"].get(k, 0) + v
        e["episodios"].append(ep.name)
    with _lock:
        cur = load_data(lib)
        cur["editor"] = d["editor"]
        rank_all(lib, cur, cat, EXCLUIR + sum(TEMAS.values(), []))
        wj(data_path(lib), cur)
    print(f"{used} SFX da biblioteca na sequência final ({len(seen)} sons diferentes); {sum(outside.values())} de fora da biblioteca")
    print(f"movimentos lidos das faixas de vídeo do editor ({len(ev)} eventos)"
          + ("" if aligned else "; o motion_map não entrou: o corte final tem outra duração que o estudado (inserção no início?)"))
    for iid, s in sorted(seen.items(), key=lambda x: -x[1]["vezes"]):
        mv = ", ".join(f"{k} x{v}" for k, v in sorted(s["movimentos"].items(), key=lambda x: -x[1])) or "sem movimento perto"
        print(f"  x{s['vezes']:3d}  {s['n'][:44]:44s} -> {mv}")
    for nm, n in sorted(outside.items(), key=lambda x: -x[1])[:12]:
        print(f"  fora  x{n:3d}  {nm[:60]}")
    print("os sons usados pelo editor sobem no ranking; continuam precisando do ok na página de revisão")


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    fn = {"biblioteca": cmd_biblioteca, "index": cmd_index, "pick": cmd_pick, "plan": cmd_plan, "revisar": cmd_revisar,
          "aprender": cmd_aprender, "movimentos": cmd_movimentos}.get(a[0])
    if not fn:
        print(__doc__)
        sys.exit(2)
    fn(a[1:])


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass
    main(sys.argv[1:])
