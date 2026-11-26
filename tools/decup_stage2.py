"""Stage 2 of decup.py: transcription, cut decisions, Premiere XML."""
import glob
import json
import os
import re
import site
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote

import numpy as np

from decup import load, save, wav_path, read_wav, SR

import sys as _sys
_sys.path.insert(0, str(Path(__file__).parent))


# ------------------------------------------------------------------ transcription
def _cuda_dlls():
    """Windows: register the CUDA DLLs of the pip nvidia-* packages. Elsewhere the loader finds them itself."""
    if not hasattr(os, "add_dll_directory"):
        return
    roots = site.getsitepackages() + [site.getusersitepackages()]
    for d in sorted({os.path.dirname(p) for r in roots for p in glob.glob(os.path.join(r, "nvidia", "*", "bin", "*.dll"))}):
        os.add_dll_directory(d)
        os.environ["PATH"] = d + os.pathsep + os.environ["PATH"]


def whisper_model(name="large-v3"):
    """faster-whisper on the NVIDIA GPU; without one (or with a broken driver) on the CPU: slower, same text.
    MOTION_STUDIO_WHISPER_DEVICE=cpu forces the CPU."""
    _cuda_dlls()
    from faster_whisper import WhisperModel
    if os.environ.get("MOTION_STUDIO_WHISPER_DEVICE", "").lower() != "cpu":
        try:
            return WhisperModel(name, device="cuda", compute_type="float16")
        except Exception as e:  # no CUDA device / driver / DLLs
            print(f"  cuda unavailable ({str(e).splitlines()[0][:120]}), transcribing on the cpu (slower)")
    return WhisperModel(name, device="cpu", compute_type="int8")


def level_db(x):
    """Per-10 ms level (dB) of the master audio (Hann window, chunked so memory stays small)."""
    n = len(x) // 160 - 2
    db = np.empty(n, np.float32)
    win = np.hanning(400).astype(np.float32)
    for c in range(0, n, 20000):
        idx = np.arange(c, min(n, c + 20000))
        fr = np.lib.stride_tricks.sliding_window_view(x, 400)[idx * 160] * win
        db[idx] = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-10)
    return db


def speech_level(db):
    """Room floor (10th percentile) and typical speech level (75th percentile of what is 15 dB above it)."""
    floor = float(np.percentile(db, 10))
    hi = db > floor + 15
    return floor, (float(np.percentile(db[hi], 75)) if hi.any() else floor + 30)


def voice_chunks(db, min_silence=0.45):
    """Split the audio at real silences (>= min_silence): Whisper on one chunk cannot merge two takes."""
    floor, lvl = speech_level(db)
    v = db > floor + 0.30 * (lvl - floor)
    v = _fill(v, int(round(min_silence / HOP)), True)      # shorter silences stay inside a chunk
    v = _fill(v, 8, False)                                  # drop blips < 80 ms
    d = np.diff(np.concatenate([[0], v.astype(int), [0]]))
    return [(a * HOP, b * HOP) for a, b in zip(np.where(d == 1)[0], np.where(d == -1)[0]) if (b - a) * HOP >= 0.15], floor


def align_words(ws, voiced, lo, hi):
    """Whisper places a chunk's words ~0.2 s early: find the shift (-0.1..+0.4 s) that best fits the voice
    (words on voiced frames, the gaps between words on silence). Fewer than 4 words: the median shift (0.2 s)."""
    if not ws:
        return ws, 0
    a, b = max(0, int(lo / HOP)), min(len(voiced), int(hi / HOP))
    best, sh = None, 20
    if len(ws) >= 4 and b > a:
        vv = voiced[a:b]
        for k in range(-10, 41):
            ind, gaps = np.zeros(b - a, bool), np.zeros(b - a, bool)
            for w in ws:
                ind[max(0, int(w["s"] / HOP) + k - a): max(0, int(w["e"] / HOP) + k - a)] = True
            for w0, w1 in zip(ws, ws[1:]):
                if w1["s"] - w0["e"] > 0.08:
                    gaps[max(0, int(w0["e"] / HOP) + k - a): max(0, int(w1["s"] / HOP) + k - a)] = True
            sc = (vv & ind).sum() - 2 * (vv & gaps).sum() - 0.5 * (~vv & ind).sum()
            if best is None or sc > best:
                best, sh = sc, k
    return [dict(w, s=round(w["s"] + sh * HOP, 3), e=round(w["e"] + sh * HOP, 3)) for w in ws], sh


# ------------------------------------------------------------------ Whisper hallucinations
# Whisper writes stock phrases into chunks with no speech (keyboard, mouse, room noise, a breath): "Obrigado por
# assistir", "Acesse o site www.<marca>.com", "Legenda por <nome>", and it echoes the prompt back (the episode's
# vocab list as a sentence). Phrases are matched on norm() text (lower case, no accents, no punctuation).
HALLUCINATIONS = [
    # pt
    "obrigado por assistir", "obrigada por assistir", "obrigado pela atencao", "obrigado e ate a proxima",
    "acesse o site", "acesse o nosso site", "acesse o link", "acessem o link",
    "inscreva se no canal", "se inscreva no canal", "inscrevam se no canal", "ative o sininho", "deixe o seu like",
    "deixe seu like", "legenda por", "legendas por", "legendado por", "legendas pela comunidade",
    "transcricao e legendas", "transcricao por", "traducao e legendas", "sous titres",
    # en
    "thanks for watching", "thank you for watching", "thank you so much for watching", "please subscribe",
    "subscribe to my channel", "like and subscribe", "subtitles by", "captions by", "transcribed by",
    "translated by", "amara org",
    # es
    "gracias por ver", "gracias por mirar", "suscribete", "suscribanse", "subtitulos por", "subtitulado por",
    "subtitulos realizados por", "transcripcion por",
]
HALLU_TOKS = [h.split() for h in HALLUCINATIONS]


def _has_phrase(toks, phrases_toks):
    return any(toks[i:i + len(p)] == p for p in phrases_toks for i in range(len(toks) - len(p) + 1))


def hallu_phrase(text, extra=()):
    """Known stock phrase in the text (the general list + client.json decup.alucinacoes)."""
    return _has_phrase(norm(text), HALLU_TOKS + [norm(x) for x in extra])


def prompt_echo(text, prompt_toks):
    """The segment is the prompt read back: 3+ content words (3+ letters) and >= 60 % of them come from the
    prompt / vocab. Never drops anything by itself: the chunk is transcribed again without the prompt (a real
    sentence that names three tools then comes back as speech, maybe misspelled)."""
    toks = [t for t in norm(text) if len(t) >= 3]
    if len(toks) < 3 or not prompt_toks:
        return False
    return sum(t in prompt_toks for t in toks) >= 0.6 * len(toks)


def voice_strength(db, t0, t1, floor, lvl):
    """How much of [t0, t1] really sounds like the speaker: seconds above floor + 50 % of the speech range,
    and the 95th-percentile level as a fraction of that range (1.0 = typical speech, 0 = room floor)."""
    a, b = max(0, int(t0 / HOP)), min(len(db), int(t1 / HOP) + 1)
    if b <= a:
        return 0.0, 0.0
    seg = db[a:b]
    rng = max(lvl - floor, 1e-3)
    return float((seg > floor + 0.5 * rng).sum() * HOP), float((np.percentile(seg, 95) - floor) / rng)


HALLU = {                     # defaults; client.json decup.alucinacao overrides any key, decup.alucinacao = null turns it off
    "prompt_min_s": 1.5,      # a chunk shorter than this (s) is transcribed without the vocab prompt first ...
    "prompt_min_voice_s": 1.0,  # ... and so is one with less real voice than this (s). With the prompt Whisper writes
                              # a stock phrase into noise with no_speech_prob ~0.1; without it the same noise reads ~0.9
    "no_speech": 0.6,         # no_speech_prob above this = Whisper thinks there is no speech
    "logprob": -1.0,
    "weak_level": 0.55,       # a segment whose voice level is under this fraction of the speech range is "weak"
    "weak_voice_s": 0.5,      # ... or has less real voice than this (s)
    "no_voice_s": 0.15,       # a quiet segment with less voice than this (s) is dropped whatever Whisper says
    "max_compression": 2.4,   # a looping segment ("e e e e e ...") is dropped when its voice is weak
}


def screen_segments(segs, db, floor, lvl, cfg, extra=()):
    """Split Whisper segments (dicts: s, e absolute, text, lp, ns, cr) into kept and dropped.
    Rules, each checked against the segment's real voice energy:
      silent   - no_speech_prob > no_speech and (weak voice or avg_logprob < logprob). Whisper's own rule needs the
                 low logprob, but its stock phrases come out fluent (logprob about -0.6), so the voice decides;
      novoice  - almost no voice at all (under no_voice_s and quiet), whatever Whisper's own numbers say;
      phrase  - a known stock phrase where the voice is weak (with real voice it stays, flagged);
      lowconf  - avg_logprob < logprob where the voice is weak;
      loop     - compression ratio > max_compression where the voice is weak."""
    kept, dropped = [], []
    for sg in segs:
        vs, rel = voice_strength(db, sg["s"], sg["e"], floor, lvl)
        weak = rel < cfg["weak_level"] or vs < cfg["weak_voice_s"]
        why = None
        if sg["ns"] > cfg["no_speech"] and (weak or sg["lp"] < cfg["logprob"]):
            why = "silent"
        elif vs < cfg["no_voice_s"] and rel < cfg["weak_level"] + 0.05:
            why = "novoice"
        elif hallu_phrase(sg["text"], extra):
            why = "phrase" if weak else None
            if not weak:
                sg["flag"] = "frase-feita com voz: confirmar"
        elif weak and sg["lp"] < cfg["logprob"]:
            why = "lowconf"
        elif weak and sg["cr"] > cfg["max_compression"]:
            why = "loop"
        sg["voice_s"], sg["level"] = round(vs, 2), round(rel, 2)
        (dropped if why else kept).append(dict(sg, why=why) if why else sg)
    return kept, dropped


def transcribe_chunk(tr, a0, a, b, db, floor, lvl, prompt, prompt_toks, cfg, extra=()):
    """One silence chunk [a, b] (audio cut from a0). tr(prompt) -> Whisper segments with times relative to a0.
    A chunk long and loud enough to be speech gets the vocab prompt; a result that reads the prompt back is
    transcribed again without it ("eco-refeito": on a long episode three such chunks hid real speech).
    A short or quiet chunk is transcribed WITHOUT the prompt first: noise then shows as noise (no_speech_prob
    ~0.9) instead of a fluent stock phrase. Only when that result is speech is it transcribed again with the
    prompt (better words: the prompt also carries the language and accent), and the prompted text is kept
    unless it is a stock phrase or the prompt read back ("prompt-confirmado").
    Returns (kept segments, dropped segments, how), times absolute."""
    vs, _ = voice_strength(db, a, b, floor, lvl)
    absol = lambda sgs: [dict(sg, s=a0 + sg["s"], e=a0 + sg["e"]) for sg in sgs]  # noqa: E731
    bad = lambda sgs: any(prompt_echo(sg["text"], prompt_toks) or hallu_phrase(sg["text"], extra) for sg in sgs)  # noqa: E731
    if prompt and b - a >= cfg["prompt_min_s"] and vs >= cfg["prompt_min_voice_s"]:
        segs, how = tr(prompt), "prompt"
        if any(prompt_echo(sg["text"], prompt_toks) for sg in segs):
            segs, how = tr(""), "eco-refeito"
        return (*screen_segments(absol(segs), db, floor, lvl, cfg, extra), how)
    kept, dropped = screen_segments(absol(tr("")), db, floor, lvl, cfg, extra)
    how = "sem-prompt"
    if prompt and kept:
        k2, d2 = screen_segments(absol(tr(prompt)), db, floor, lvl, cfg, extra)
        if k2 and not d2 and not bad(k2):
            kept, dropped, how = k2, d2, "prompt-confirmado"
    return kept, dropped, how


def _whisper_segments(res):
    return [{"s": sg.start, "e": sg.end, "text": sg.text.strip(), "lp": round(sg.avg_logprob, 3),
             "ns": round(sg.no_speech_prob, 3), "cr": round(sg.compression_ratio, 2),
             "words": [{"s": w.start, "e": w.end, "w": w.word.strip(), "p": round(w.probability, 3)} for w in sg.words]}
            for sg in res]


def trans(ep, args):
    """Default (client.json decup.transcribe = "chunks"): split at real silences, transcribe every chunk on its own,
    align its word times to the voice. "whole" (or --whole) = one Whisper pass over the file (merges quick retakes).
    --out <dir> writes the words elsewhere (a test must not replace the transcript an episode already used)."""
    model_name = args[args.index("--model") + 1] if "--model" in args else "large-v3"
    m = load(ep)
    import studio
    cj, epj = studio.client_json(studio.client_of(ep)), studio.episode_json(ep)
    dc = cj.get("decup", {})
    mode = "whole" if "--whole" in args else "chunks" if "--chunks" in args else dc.get("transcribe", "chunks")
    tdir = Path(args[args.index("--out") + 1]) if "--out" in args else ep / "work" / "transcript"
    if not tdir.is_absolute():
        tdir = ep / tdir
    tdir.mkdir(parents=True, exist_ok=True)
    model = whisper_model(model_name)
    prompt = cj.get("transcribe_prompt", "") + (" " + ", ".join(epj.get("vocab", [])) + "." if epj.get("vocab") else "")
    prompt_toks = {t for t in norm(prompt) if len(t) >= 3}
    lang = (cj.get("language") or "pt").split("-")[0]
    hcfg = None if "alucinacao" in dc and dc["alucinacao"] is None else {**HALLU, **(dc.get("alucinacao") or {})}
    extra = dc.get("alucinacoes", [])                   # client's own stock phrases, added to HALLUCINATIONS

    def whisper(x, p, **kw):
        res, _ = model.transcribe(x, language=lang, word_timestamps=True, condition_on_previous_text=False,
                                  initial_prompt=p or None, beam_size=5, **kw)
        return _whisper_segments(res)

    def words_of(sgs, **extra_keys):
        return [dict({"s": round(w["s"], 3), "e": round(w["e"], 3), "w": w["w"], "p": w["p"]}, **extra_keys,
                     **({"h": sg["flag"]} if sg.get("flag") else {})) for sg in sgs for w in sg["words"]]

    for s in m["sessions"]:
        outp = tdir / f"s{s['id']}.json"
        if outp.exists() and "--force" not in args:
            continue
        print(f"transcribing session {s['id']} ({s['master']}), {mode}", flush=True)
        X = read_wav(wav_path(ep, s["master"]))
        db = level_db(X)
        floor, lvl = speech_level(db)
        words, gone, hows, nflag = [], [], {}, 0
        if mode == "whole":
            segs = whisper(X, prompt, vad_filter=True, vad_parameters={"min_silence_duration_ms": 400})
            if hcfg:
                segs, gone = screen_segments(segs, db, floor, lvl, hcfg, extra)
            words, nflag = words_of(segs), sum(bool(sg.get("flag")) for sg in segs)
        else:
            chunks, floor = voice_chunks(db, dc.get("chunk_silence_s", 0.45))
            voiced, shifts = db > floor + 12, []
            for ci, (a, b) in enumerate(chunks):
                a0, b0 = max(0.0, a - 0.2), min(len(X) / SR, b + 0.2)
                x = X[int(a0 * SR): int(b0 * SR)]
                if hcfg:
                    segs, dropped, how = transcribe_chunk(lambda p: whisper(x, p, vad_filter=False), a0, a, b, db, floor, lvl,
                                                          prompt, prompt_toks, hcfg, extra)
                    gone += [dict(d, c=ci + 1) for d in dropped]
                    hows[how] = hows.get(how, 0) + 1
                else:
                    segs = [dict(sg, s=a0 + sg["s"], e=a0 + sg["e"]) for sg in whisper(x, prompt, vad_filter=False)]
                for sg in segs:
                    sg["words"] = [dict(w, s=a0 + w["s"], e=a0 + w["e"]) for w in sg["words"]]
                ws, nflag = words_of(segs, c=ci + 1), nflag + sum(bool(sg.get("flag")) for sg in segs)
                if ws:
                    ws, sh = align_words(ws, voiced, a - 0.5, b + 0.5)
                    shifts.append(sh)
                words += ws
            words.sort(key=lambda w: w["s"])
            print(f"  {len(chunks)} chunks ({', '.join(f'{k} {v}' for k, v in hows.items()) or 'filter off'}), "
                  f"word shift median {np.median(shifts) * 10 if shifts else 0:.0f} ms", flush=True)
        gone = [{"s": round(d["s"], 2), "e": round(d["e"], 2), "text": d["text"], "why": d["why"], "c": d.get("c"),
                 "lp": d["lp"], "ns": d["ns"], "level": d["level"], "voice_s": d["voice_s"]} for d in gone]
        outp.write_text(json.dumps({"session": s["id"], "mode": mode, "words": words, "hallucinations": gone},
                                   ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"  {len(words)} words, {words[-1]['e'] if words else 0:.0f}s -> {outp}; "
              f"{len(gone)} hallucinated segments dropped, {nflag} stock phrases with real voice flagged (h)", flush=True)


# ------------------------------------------------------------------ cut decisions
FILLERS = {"é", "ã", "hum", "hmm", "eh", "ah", "tipo", "pronto", "portanto", "então", "ok"}


def norm(t):
    t = unicodedata.normalize("NFD", t.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9 ]+", " ", t).split()


def phrases(words, gap=0.55):
    """Group words into phrases split by pauses or sentence punctuation."""
    out, cur = [], []
    for i, w in enumerate(words):
        if cur and (w["s"] - cur[-1]["e"] > gap):
            out.append(cur)
            cur = []
        cur.append(w)
        if re.search(r"[.!?…]$", w["w"]) and i + 1 < len(words) and words[i + 1]["s"] - w["e"] > 0.06:
            out.append(cur)
            cur = []
    if cur:
        out.append(cur)
    return [{"s": p[0]["s"], "e": p[-1]["e"], "words": p, "text": " ".join(x["w"] for x in p), "toks": norm(" ".join(x["w"] for x in p))} for p in out]


def similar(a, b):
    """Is `b` (later) a retake of `a` (earlier)?  Conservative on purpose: when unsure, keep both.
    - near-duplicate: SequenceMatcher ratio >= .6 with comparable lengths (shorter >= 50% of longer)
    - restart: the earlier one is shorter and opens with the same 3+ words as the later one"""
    if not a or not b:
        return 0.0
    la, lb = len(a), len(b)
    r = SequenceMatcher(None, a, b, autojunk=False).ratio() if min(la, lb) >= .5 * max(la, lb) else 0.0
    n = min(la, lb, 5)
    restart = 0.9 if la <= lb and n >= 3 and a[:n] == b[:n] else 0.0
    return max(r, restart)


def quality(p):
    toks = p["toks"]
    fill = sum(t in FILLERS for t in toks)
    lowp = sum(w["p"] < 0.45 for w in p["words"])
    ends = 1 if re.search(r"[.!?]$", p["words"][-1]["w"]) else 0
    return len(toks) * 0.15 + ends * 1.5 - fill * 0.8 - lowp * 0.6


HOP = 0.01                       # VAD frame hop (10 ms)
PAD = 2 / (30000 / 1001)         # legacy symmetric pad (2 frames)
PAD_IN, PAD_OUT = 0.05, 0.035    # defaults learned from an editor's final cut: ~1.5 frame lead, ~1 frame tail (client.json decup.pad_*)
META = re.compile(r"(camera|camara) (1|um|2|dois)|nota para o editor|editor|corta|gravacao (do|da) ecra|gravar o ecra"
                  r"|parar a gravacao|vou parar|vou repetir|nao curti|esconde|escondo|boleia|ninguem ver|mete para tras|meto a gravacao"
                  r"|irmao|esta merda|tudo bugado")
GAP = 0.25                       # pauses >= 250 ms inside a phrase are cut (client.json decup.inner_gap_s)
SETTLE = 0.12                    # a cut point only lands where the voice has decayed to floor + 12 % of the speech range
                                 # (client.json decup.settle); the VAD threshold alone ends clips on the last word's tail


def speech_mask(x, words):
    """Per-10 ms speech mask from the master audio: loud enough, near a transcribed word, not a breath.
    Breath = audible but quiet, noise-like (high spectral flatness), outside any word's own span."""
    n = len(x) // 160 - 2
    db = np.empty(n, np.float32)
    flat = np.empty(n, np.float32)
    win = np.hanning(400).astype(np.float32)
    for c in range(0, n, 20000):                          # chunked STFT keeps memory small
        idx = np.arange(c, min(n, c + 20000))
        fr = np.lib.stride_tricks.sliding_window_view(x, 400)[idx * 160] * win
        db[idx] = 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-10)
        mag = np.abs(np.fft.rfft(fr, axis=1))[:, 8:160] + 1e-7     # 320 Hz - 6.4 kHz
        flat[idx] = np.exp(np.mean(np.log(mag), axis=1)) / np.mean(mag, axis=1)
    inword = np.zeros(n, bool)
    near = np.zeros(n, bool)
    for w in words:
        a, b = int(w["s"] / HOP), int(w["e"] / HOP) + 1
        inword[a:b] = True
        near[max(0, a - 25): b + 25] = True
    floor = float(np.percentile(db, 10))
    speech_lvl = float(np.percentile(db[inword], 75)) if inword.any() else floor + 30
    thr = floor + 0.38 * (speech_lvl - floor)
    loud = db > thr
    breath = (db > floor + 5) & (db < floor + 0.7 * (speech_lvl - floor)) & (flat > 0.32) & ~inword
    sp = loud & near & ~breath
    # closing: fill gaps <= 70 ms, then drop islands < 60 ms
    sp = _fill(sp, 7, True)
    sp = _fill(sp, 6, False)
    nb = int(np.sum(np.diff(np.concatenate([[0], _fill(breath & ~sp, 5, True).astype(int), [0]])) == 1))
    return sp, breath, {"floor": floor, "thr": thr, "breaths": nb, "db": db, "speech": speech_lvl}


def _fill(mask, k, value):
    """Turn runs of (not value) shorter than k frames into value."""
    m = mask.copy()
    d = np.diff(np.concatenate([[value], m == value, [value]]).astype(int))
    starts, ends = np.where(d == -1)[0], np.where(d == 1)[0]
    for a, b in zip(starts, ends):
        if b - a < k and a > 0 and b < len(m):
            m[a:b] = value
    return m


def islands(sp, lo, hi):
    a, b = max(0, int(lo / HOP)), min(len(sp), int(hi / HOP) + 1)
    seg = sp[a:b].astype(int)
    d = np.diff(np.concatenate([[0], seg, [0]]))
    return [[(a + s) * HOP, (a + e) * HOP] for s, e in zip(np.where(d == 1)[0], np.where(d == -1)[0])]


def settle(st, t, limit, step):
    """Move a cut point (step +1 = out, -1 = in) until the voice has really decayed, never past limit.
    Learned from an editor's cut: our outs landed 7-28 dB under the speech peak (word still sounding),
    the editor's at 38-46 dB (silence)."""
    if SETTLE is None:                                   # client.json decup.settle = null turns it off
        return t
    db, lvl = st["db"], st["floor"] + SETTLE * (st["speech"] - st["floor"])
    i, lim = int(round(t / HOP)), int(round(limit / HOP))
    while 0 <= i < len(db) and (i < lim if step > 0 else i > lim) and db[i] > lvl:
        i += step
    return i * HOP


def audit(sp, ranges):
    """Measure what the cut actually contains: non-speech at the head, tail and longest pause inside."""
    lead, tail, inner = [], [], []
    for a, b, _ in ranges:
        seg = sp[int(a / HOP): int(b / HOP) + 1]
        if not seg.any():
            continue
        on = np.where(seg)[0]
        lead.append(on[0] * HOP)
        tail.append((len(seg) - 1 - on[-1]) * HOP)
        gaps = np.diff(on) - 1
        inner.append((gaps.max() if len(gaps) else 0) * HOP)
    return lead or [0], tail or [0], inner or [0]


def cut(ep, args):
    global PAD_IN, PAD_OUT, GAP, SETTLE
    import studio
    dc = studio.client_json(studio.client_of(ep))["decup"]
    PAD_IN, PAD_OUT = dc.get("pad_in_s", PAD_IN), dc.get("pad_out_s", PAD_OUT)
    GAP, SETTLE = dc.get("inner_gap_s", GAP), dc.get("settle", SETTLE)
    pad_in, pad_out = 0.12, 0.18
    m = load(ep)
    edl, report = [], ["# Decupagem — relatório\n"]
    for s in m["sessions"]:
        T = json.loads((ep / "work" / "transcript" / f"s{s['id']}.json").read_text(encoding="utf-8"))
        W, hallu = T["words"], T.get("hallucinations", [])
        P = phrases(W)
        keep = [True] * len(P)
        groups = []
        # repeated takes: compare each phrase with the next ones inside a 75 s window
        for i in range(len(P)):
            if not keep[i]:
                continue
            grp = [i]
            for j in range(i + 1, len(P)):
                if P[j]["s"] - P[grp[-1]]["e"] > 45:
                    break
                if keep[j] and similar(P[grp[-1]]["toks"], P[j]["toks"]) >= 0.6:
                    grp.append(j)
            if len(grp) > 1:
                # best take: highest quality, ties -> the latest attempt
                longest = max(len(P[k]["toks"]) for k in grp)
                complete = [k for k in grp if len(P[k]["toks"]) >= .8 * longest]
                best = complete[-1]                      # editor's rule: the last complete attempt
                for k in grp:
                    if k != best:
                        keep[k] = False
                groups.append((grp, best))
        # tiny false starts (1-3 words) directly followed by a phrase that begins the same way
        for i in range(len(P) - 1):
            if keep[i] and len(P[i]["toks"]) <= 3 and P[i + 1]["toks"][: len(P[i]["toks"])] == P[i]["toks"]:
                keep[i] = False
                groups.append(([i, i + 1], i + 1))
        # ---- rules learned from editors' final cuts ---------------------------------------------
        meta_hits, frag_hits, restart_hits = [], [], []
        for k, p in enumerate(P):
            if not keep[k]:
                continue
            t = " ".join(p["toks"])
            # (1) production talk: slates, notes to the editor, "corta", recording/screen instructions
            if META.search(t):
                # drop only the clause(s) that carry the production talk, keep the rest of the phrase
                cl, cur = [], []
                for i, w in enumerate(p["words"]):
                    if cur and (w["s"] - cur[-1]["e"] > .3 or re.search(r"[.,!?…]$", cur[-1]["w"])):
                        cl.append(cur)
                        cur = []
                    cur.append(w)
                cl.append(cur)
                rest = [c for c in cl if not META.search(" ".join(norm(" ".join(x["w"] for x in c))))]
                meta_hits.append((k, " / ".join(" ".join(x["w"] for x in c) for c in cl if c not in rest)))
                if sum(len(c) for c in rest) < 3:
                    keep[k] = False
                    continue
                if len(rest) < len(cl):          # keep the longest contiguous run of clean clauses
                    runs, run = [], []
                    for c in cl:
                        if c in rest:
                            run += c
                        else:
                            if run:
                                runs.append(run)
                            run = []
                    if run:
                        runs.append(run)
                    p["words"] = max(runs, key=len)
                    p["s"], p["e"] = p["words"][0]["s"], p["words"][-1]["e"]
                    p["text"] = " ".join(w["w"] for w in p["words"])
                    p["toks"] = norm(p["text"])
                    continue
            # (2) restart INSIDE a phrase: same 3 words reappear -> keep from the second occurrence
            wt = [" ".join(norm(w["w"])) for w in p["words"]]
            for i0 in range(0, min(6, len(wt) - 3)):
                tri = wt[i0:i0 + 3]
                if not all(tri):
                    continue
                j = next((j for j in range(i0 + 3, min(len(wt) - 2, i0 + 30)) if wt[j:j + 3] == tri), None)
                if j is not None:
                    p["words"] = p["words"][j:]
                    p["s"], p["text"] = p["words"][0]["s"], " ".join(w["w"] for w in p["words"])
                    p["toks"] = norm(p["text"])
                    restart_hits.append(k)
                    break
            # (3) orphan fragments: 1-2 words isolated by pauses on both sides
            before = p["s"] - P[k - 1]["e"] if k else 9
            after = P[k + 1]["s"] - p["e"] if k + 1 < len(P) else 9
            if len(p["toks"]) <= 2 and before >= .35 and after >= .35:
                keep[k] = False
                frag_hits.append(k)
        report.append(f"<!-- s{s['id']} learned rules: meta {len(meta_hits)}, in-phrase restarts {len(restart_hits)}, fragments {len(frag_hits)} -->")
        for k, gone in meta_hits:
            report.append(f"- **Bastidor** @{P[k]['s']:.1f}s removido: “{gone[:110]}”")
        # kept ranges from the REAL audio: speech frames (energy VAD minus breaths) inside each kept phrase,
        # internal pauses >= GAP cut, every speech island padded by exactly PAD (2 frames)
        X = read_wav(wav_path(ep, s["master"]))
        sp, br, st = speech_mask(X, W)
        # guarantee: the core (middle 50%) of every word in a kept phrase is always inside the cut
        for k, p in enumerate(P):
            if keep[k]:
                for w in p["words"]:
                    d = w["e"] - w["s"]
                    sp[int((w["s"] + .25 * d) / HOP): int((w["e"] - .25 * d) / HOP) + 1] = True
        ranges = []
        for k, p in enumerate(P):
            if not keep[k]:
                continue
            lo = max(p["s"] - .3, (P[k - 1]["e"] + p["s"]) / 2 if k else 0)
            hi = min(p["e"] + .3, (p["e"] + P[k + 1]["s"]) / 2 if k + 1 < len(P) else p["e"] + .3)
            isl = islands(sp, lo, hi)
            if not isl:
                isl = [[p["s"], p["e"]]]
            merged = [isl[0][:]]
            for a, b in isl[1:]:
                if a - merged[-1][1] < GAP:
                    merged[-1][1] = b
                else:
                    merged.append([a, b])
            for a, b in merged:
                a, b = settle(st, a, lo, -1), settle(st, b, hi, +1)    # never cut while the voice still sounds
                a, b = max(lo, a - PAD_IN), min(hi, b + PAD_OUT)
                txt = " ".join(w["w"] for w in p["words"] if w["e"] > a and w["s"] < b)
                if ranges and a - ranges[-1][1] < 0.02:          # touching islands -> one clip
                    ranges[-1][1] = b
                    ranges[-1][2] += " " + txt
                else:
                    ranges.append([a, b, txt])
        ranges = [r for r in ranges if r[1] - r[0] > 0.12]
        lead, tail, inner = audit(sp, ranges)
        report.append(f"<!-- s{s['id']} audit: lead silence median {np.median(lead)*1000:.0f} ms, tail {np.median(tail)*1000:.0f} ms, "
                      f"longest pause left inside a clip {max(inner)*1000:.0f} ms, breaths detected {st['breaths']} -->")
        print(f"  s{s['id']}: lead {np.median(lead)*1000:.0f}ms / tail {np.median(tail)*1000:.0f}ms (target {PAD*1000:.0f}), "
              f"max inner pause {max(inner)*1000:.0f}ms, breaths {st['breaths']}, floor {st['floor']:.0f} dB, thr {st['thr']:.0f} dB")
        dropped = [{"s": P[k]["s"] - pad_in, "e": P[k]["e"] + pad_out, "text": P[k]["text"]} for k in range(len(P)) if not keep[k]]
        total = W[-1]["e"] if W else 0
        kept = sum(r[1] - r[0] for r in ranges)
        edl.append({"session": s["id"], "keep": [{"s": round(a, 3), "e": round(b, 3), "text": t} for a, b, t in ranges],
                    "alternates": dropped, "groups": [{"takes": g, "best": b} for g, b in groups]})
        report.append(f"## Sessão {s['id']} — {s['master']}\n- bruto {total/60:.1f} min → mantido {kept/60:.1f} min "
                      f"({len(ranges)} trechos, {len(dropped)} takes/falsos inícios removidos)")
        if hallu:
            report.append(f"- transcrição: {len(hallu)} alucinações do Whisper descartadas (ruído sem voz; lista em "
                          f"work/transcript/s{s['id']}.json `hallucinations`)")
        hw = [w["s"] for i, w in enumerate(W) if w.get("h") and not (i and W[i - 1].get("h"))]   # first word of each
        if hw:
            report.append("- frase-feita de alucinação dita com voz real, confirmar no áudio: "
                          + ", ".join(f"@{t:.1f}s" for t in hw[:20]))
        report.append("")
        for g, b in groups[:400]:
            report.append(f"- **Repetição** @{P[g[0]]['s']:.1f}s — mantido take {g.index(b)+1}/{len(g)}: “{P[b]['text'][:110]}”")
            for k in g:
                if k != b:
                    report.append(f"    - descartado @{P[k]['s']:.1f}s: “{P[k]['text'][:110]}”")
        report.append("")
    (ep / "edl.json").write_text(json.dumps(edl, indent=1, ensure_ascii=False), encoding="utf-8")
    (ep / "report.md").write_text("\n".join(report), encoding="utf-8")
    for e in edl:
        print(f"session {e['session']}: {len(e['keep'])} ranges kept, {len(e['alternates'])} alternates")


# ------------------------------------------------------------------ semantic pass (Claude reads, the tool applies)
def _ranges(edl):
    for e in edl:
        for i, k in enumerate(e["keep"]):
            yield f"s{e['session']}-{i + 1:03d}", e, k


def _screen_cover(m, sess):
    """Master-time intervals of a session covered by a screen recording."""
    S = m["sessions"][sess - 1]
    out = []
    for mem in S["members"]:
        if mem["role"] == "tela":
            dur = m["files"][mem["name"]]["duration"]
            out.append((mem["offset"], mem["offset"] + dur))
    return out


def semantic_export(ep, args):
    """Compact transcript of the rough cut for Claude: one line per kept clip, with ids."""
    m, edl = load(ep), json.loads((ep / "edl.json").read_text(encoding="utf-8"))
    lines, words, pos = ["# id | tempo no corte | [TELA] = havia gravação de tela | [FRASE-FEITA?] = frase típica de "
                         "alucinação do Whisper dita com voz real (confirmar no áudio) | texto", ""], 0, 0.0
    flags = {}                                  # session -> times of words trans flagged (stock phrase with real voice)
    for s in m["sessions"]:
        p = ep / "work" / "transcript" / f"s{s['id']}.json"
        flags[s["id"]] = [(w["s"] + w["e"]) / 2 for w in json.loads(p.read_text(encoding="utf-8"))["words"]
                          if w.get("h")] if p.exists() else []
    for rid, e, k in _ranges(edl):
        scr = any(a <= (k["s"] + k["e"]) / 2 <= b for a, b in _screen_cover(m, e["session"]))
        hf = any(k["s"] <= t <= k["e"] for t in flags.get(e["session"], []))
        lines.append(f"{rid} [{int(pos // 60):02d}:{pos % 60:04.1f}]{' [TELA]' if scr else ''}{' [FRASE-FEITA?]' if hf else ''} {k['text']}")
        pos += k["e"] - k["s"]
        words += len(k["text"].split())
    p = ep / "work" / "semantic_in.txt"
    p.write_text("\n".join(lines), encoding="utf-8")
    print(f"{p}\n  {len(lines) - 2} clips, {words} words, {pos / 60:.1f} min. Write the decisions to work/semantic.json (see the decupagem skill).")


def _expand(spec, ids):
    """'s1-010' or 's1-010..s1-014' -> list of ids present in the edl."""
    if ".." in spec:
        a, b = spec.split("..")
        if a in ids and b in ids:
            return ids[ids.index(a): ids.index(b) + 1]
        return []
    return [spec] if spec in ids else []


def semantic_apply(ep, args):
    """work/semantic.json -> edl: 'drop' clips go to the discarded sequence (recoverable), 'review' clips get a REVER marker."""
    src = ep / "edl.json"
    to = Path(args[args.index("--to") + 1]) if "--to" in args else src
    edl = json.loads(src.read_text(encoding="utf-8"))
    if not to.is_absolute():
        to = ep / to
    if to == src and not (ep / "edl_auto.json").exists():
        (ep / "edl_auto.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")   # untouched rule-based cut
    dec = json.loads((ep / "work" / "semantic.json").read_text(encoding="utf-8"))
    ids = [rid for rid, _, _ in _ranges(edl)]
    byid = {rid: (e, k) for rid, e, k in _ranges(edl)}
    drop, review, missing = {}, {}, []
    for kind, bucket in (("drop", drop), ("review", review)):
        for d in dec.get(kind, []):
            got = [x for spec in d["ids"] for x in _expand(spec, ids)]
            if not got:
                missing.append(d["ids"])
            for x in got:
                bucket[x] = d.get("why", "")
    for rid, why in review.items():
        if rid not in drop:
            byid[rid][1]["review"] = why
    # partial cuts: "from" = cut from the LAST occurrence of the phrase to the end of the clip,
    #               "until" = cut from the start of the clip up to the FIRST occurrence (the phrase stays)
    m = load(ep)
    trims = 0
    for d in dec.get("trim", []):
        for rid in [x for spec in d["ids"] for x in _expand(spec, ids)]:
            if rid in drop:
                continue
            e, k = byid[rid]
            ws = [w for w in json.loads((ep / "work" / "transcript" / f"s{e['session']}.json").read_text(encoding="utf-8"))["words"]
                  if w["e"] > k["s"] and w["s"] < k["e"]]
            toks = [" ".join(norm(w["w"])) for w in ws]
            ph = norm(d.get("from") or d.get("until") or "")
            hits = [i for i in range(len(toks) - len(ph) + 1) if ph and toks[i:i + len(ph)] == ph]
            if not hits:
                missing.append(f"{rid}: '{d.get('from') or d.get('until')}'")
                continue
            if d.get("from"):
                i = hits[-1]
                if i == 0:
                    drop[rid] = d.get("why", "")
                    continue
                k["e"] = round(ws[i - 1]["e"] + PAD_OUT, 3)
                gone = ws[i:]
            else:
                i = hits[0]
                k["s"] = round(max(k["s"], ws[i]["s"] - PAD_IN), 3)
                gone = ws[:i]
            k["text"] = " ".join(w["w"] for w in ws if w["e"] > k["s"] and w["s"] < k["e"] and w not in gone)
            k["trim"] = d.get("why", "")
            trims += 1
    secs = 0.0
    for e in edl:
        keep, gone = [], []
        for i, k in enumerate(e["keep"]):
            rid = f"s{e['session']}-{i + 1:03d}"
            if rid in drop:
                gone.append({"s": k["s"], "e": k["e"], "text": k["text"], "why": "semântica: " + drop[rid]})
                secs += k["e"] - k["s"]
            else:
                keep.append(k)
        e["keep"] = keep
        e["alternates"] = sorted(e["alternates"] + gone, key=lambda x: x["s"])
    to.write_text(json.dumps(edl, indent=1, ensure_ascii=False), encoding="utf-8")
    rep = ep / "report.md"
    if to == src and rep.exists():
        txt = rep.read_text(encoding="utf-8").split("\n## Passada semântica")[0]
        add = ["", "## Passada semântica", f"- {len(drop)} trechos ({secs / 60:.1f} min) foram para 02_TAKES_DESCARTADOS; {len(review)} marcados REVER no 01_DECUPADO."]
        for d in dec.get("drop", []):
            add.append(f"- **Removido** {', '.join(d['ids'])}: {d.get('why', '')}")
        for d in dec.get("review", []):
            add.append(f"- **REVER** {', '.join(d['ids'])}: {d.get('why', '')}")
        rep.write_text(txt + "\n".join(add) + "\n", encoding="utf-8")
    print(f"{to}\n  dropped {len(drop)} clips ({secs / 60:.1f} min), trimmed {trims}, review {len(review)}" + (f"\n  NOT FOUND: {missing}" if missing else ""))


# ------------------------------------------------------------------ second pass: crutch words, self-corrections, clicks
# Learned from an editor's final cut of a long episode made from our cut: the editor changed no take and still removed
# ~4 s per minute in ~8 places per minute, all small. The strongest signal is in the audio: a word Whisper stretched
# (it glued a hesitation, a false start or a pause onto the word) - the editor cut the start of ~3/4 of them, up to
# where the voice restarts, so that cut is on by default. Text rules only propose: the same editor KEPT ~90 % of the
# crutch words of that cut, with no pause or position telling them apart. Claude reads each proposal in its sentence
# (work/polish_in.txt) and decides (work/polish.json); --auto cuts every crutch / repeat, for a client whose editor
# was measured to cut them all.
MULETAS = ["e", "ou", "mas", "então", "portanto", "pronto", "ok", "basicamente"]          # client.json decup.muletas
REPEAT_OK = {"muito", "nao", "sim", "bem", "mais", "ja", "nunca", "sempre"}                # doubled on purpose (emphasis)
NARRA = [r"\bvou (clicar|carregar|selecionar|escolher|abrir|meter|por|colocar|escrever|dizer que quero)\b",
         r"\b(clico|carrego|seleciono|escolho|abro)\b", r"\baqui (eu )?vou\b"]                    # client.json decup.narra_clique
DANGLING = {"e", "ou", "mas", "que", "porque", "nem"}   # crutch words also proposed when they dangle at a group's end
STRETCH_S = 0.6                  # a word Whisper stretched past this (and past 0.12 s/letter + 0.25) hides a hesitation
                                 # or a false start before it (decup.esticada_s; null = off)
BG_PAUSE = 0.3                   # a pause this long (silence in the audio) starts a new breath group (decup.muleta_pausa_s)


def _wtok(t):
    """Lower-case words with accents kept ("é" is a verb, "e" a connective), punctuation dropped."""
    return re.sub(r"[^\w ]+", " ", unicodedata.normalize("NFC", t.lower())).split()


def _snap(db, t0, t1):
    """Quietest 10 ms point between the end of one word (t0) and the start of the next (t1)."""
    lo, hi = t0 - 0.08, t1 + 0.08
    if hi - lo < 0.1:
        lo, hi = (t0 + t1) / 2 - 0.05, (t0 + t1) / 2 + 0.05
    a, b = max(0, int(lo / HOP)), min(len(db), int(hi / HOP) + 1)
    return (a + int(np.argmin(db[a:b]))) * HOP if b > a else (t0 + t1) / 2


def _polish_scan(ep, edl, tdir, dc):
    """Candidates of the second pass, per session: (edl entry, pieces, db, on_screen, [candidate])."""
    m = load(ep)
    mul = sorted([x for x in (_wtok(p) for p in dc.get("muletas", MULETAS)) if x], key=len, reverse=True)
    narra = [re.compile(r) for r in dc.get("narra_clique", NARRA)]
    pausa = dc.get("muleta_pausa_s", BG_PAUSE)
    stretch = dc.get("esticada_s", STRETCH_S)
    pad = dc.get("pad_in_s", PAD_IN)
    out, n = [], 0
    for e in edl:
        S = m["sessions"][e["session"] - 1]
        W = json.loads((tdir / f"s{e['session']}.json").read_text(encoding="utf-8"))["words"]
        db = level_db(read_wav(wav_path(ep, S["master"])))
        floor = float(np.percentile(db, 10))
        quiet = db < floor + 12
        lvl = float(np.percentile(db[db > floor + 15], 75)) if (db > floor + 15).any() else floor + 30
        loud = _fill(_fill(db > floor + 0.38 * (lvl - floor), 7, True), 6, False)
        cover = _screen_cover(m, e["session"])
        on_screen = (lambda cv: lambda t: any(a <= t <= b for a, b in cv))(cover)

        def pause_between(w0, w1):
            """Longest silent run (audio) between the middles of two words: Whisper stretches words over pauses."""
            q = quiet[int((w0["s"] + w0["e"]) / 2 / HOP): int((w1["s"] + w1["e"]) / 2 / HOP)].astype(int)
            if not len(q) or not q.any():
                return 0.0
            d = np.diff(np.concatenate([[0], q, [0]]))
            return float(np.max(np.where(d == -1)[0] - np.where(d == 1)[0])) * HOP

        pieces = []                                       # a word belongs to the piece that holds its middle
        for k in e["keep"]:
            ws = [dict(w, t=" ".join(_wtok(w["w"]))) for w in W if k["s"] <= (w["s"] + w["e"]) / 2 <= k["e"]]
            pieces.append((k, ws))
        stream = [(pi, wi) for pi, (k, ws) in enumerate(pieces) for wi in range(len(ws))]
        word = lambda x: pieces[x[0]][1][x[1]]  # noqa: E731
        cands, taken = [], set()

        def add(kind, xs, why):
            cands.append({"kind": kind, "words": [list(x) for x in xs], "why": why})
            taken.update(xs)
        # (1) immediate self-correction: the same 1-3 words twice in a row -> the first copy
        for ln in (3, 2, 1):
            i = 0
            while i + 2 * ln <= len(stream):
                a = [word(stream[j])["t"] for j in range(i, i + ln)]
                b = [word(stream[j])["t"] for j in range(i + ln, i + 2 * ln)]
                if (a == b and all(a) and not taken & set(stream[i:i + 2 * ln])
                        and not (ln == 1 and " ".join(norm(a[0])) in REPEAT_OK)
                        and word(stream[i + 2 * ln - 1])["e"] - word(stream[i])["s"] < 2.5 + ln):
                    add("repete", stream[i:i + ln], "autocorreção: " + " ".join(word(y)["w"] for y in stream[i:i + 2 * ln]))
                    i += ln
                else:
                    i += 1
        # (2) stretched word: Whisper glued a hesitation / false start ("foi... foi") or a pause onto the word; the
        #     editor cut from the word's start to where the voice starts for the last time inside it
        if stretch:
            for x in stream:
                w = word(x)
                d = w["e"] - w["s"]
                if d > stretch and d > 0.12 * len(re.sub(r"\W", "", w["w"])) + 0.25:
                    to, prev = None, w["s"]           # the last restart after a real silence (not a stop consonant)
                    for r in islands(loud, w["s"], w["e"]):
                        if r[1] - r[0] >= 0.06:
                            to = r[0] if r[0] - prev >= 0.18 else to
                            prev = r[1]
                    if to is not None and to - pad - w["s"] >= 0.15:
                        cands.append({"kind": "esticada", "words": [list(x)], "cut": [w["s"], to - pad],
                                      "why": f"palavra esticada ({d:.2f} s): hesitação ou recomeço antes dela"})
        # (3) crutch words opening a breath group (piece start or a real pause before it) or dangling at its end
        starts = {0} | {j for j in range(1, len(stream)) if stream[j][0] != stream[j - 1][0]
                        or pause_between(word(stream[j - 1]), word(stream[j])) >= pausa}
        bounds = sorted(starts) + [len(stream)]
        groups = list(zip(bounds, bounds[1:]))
        for g0, g1 in groups:
            grp = [x for x in stream[g0:g1] if x not in taken]
            toks = [word(x)["t"] for x in grp]
            i = 0
            while i < len(grp):
                hit = next((ph for ph in mul if toks[i:i + len(ph)] == ph), None)
                if not hit:
                    break
                i += len(hit)
            if i:
                add("muleta", grp[:i], "muleta a abrir" + (" (o grupo todo)" if i == len(grp) else ""))
            j = len(grp)
            while j > i + 1 and not re.search(r"[.!?…]$", word(grp[j - 1])["w"]):
                hit = next((ph for ph in mul if j - len(ph) > i and toks[j - len(ph):j] == ph and ph[-1] in DANGLING), None)
                if not hit:
                    break
                j -= len(hit)
            if i < j < len(grp):
                add("muleta", grp[j:], "muleta pendurada no fim")
        # (4) short lines under the screen recording that only narrate a click
        for g0, g1 in groups:
            grp = stream[g0:g1]
            txt = " ".join(" ".join(norm(word(x)["w"])) for x in grp)
            if (grp and len(grp) <= 12 and on_screen(word(grp[0])["s"])
                    and word(grp[-1])["e"] - word(grp[0])["s"] <= 4.5 and any(r.search(txt) for r in narra)):
                cands.append({"kind": "clique", "words": [list(x) for x in grp], "why": "só narra o clique?"})
        cands.sort(key=lambda c: (c["words"][0][0], c["words"][0][1], c["kind"] == "clique"))
        for c in cands:
            n += 1
            c["id"] = f"p{n:03d}"
            xs = [tuple(x) for x in c["words"]]
            c["text"] = " ".join(word(x)["w"] for x in xs) + (f" (primeiros {c['cut'][1] - c['cut'][0]:.2f} s)" if "cut" in c else "")
            p0, p1 = stream.index(xs[0]), stream.index(xs[-1])
            c["ctx"] = (" ".join(word(x)["w"] for x in stream[max(0, p0 - 7):p0]) + " [[" + c["text"] + "]] "
                        + " ".join(word(x)["w"] for x in stream[p1 + 1:p1 + 8]))
            c["t"] = word(xs[0])["s"] if "cut" not in c else c["cut"][0]
            c["screen"] = on_screen(c["t"])
        out.append((e, pieces, db, on_screen, cands))
    return out


def polish(ep, args):
    """Second pass, after semantic-apply (the take choice):
      python decup.py polish <ep> [--edl f] [--transcript dir]        -> work/polish_in.txt (one candidate per line)
      python decup.py polish <ep> --apply [--edl f] [--to f] [--transcript dir]   work/polish.json -> edl
      python decup.py polish <ep> --auto  [...]                        cut every crutch / self-correction candidate
    polish.json: {"cut": ["p003", "p010..p012"], "keep": ["p007"], "review": [{"ids": ["p020"], "why": "..."}]}.
    Defaults: "esticada" (the start of a stretched word) is cut unless kept; "clique" gets a REVER marker unless cut
    (then the line goes whole) or kept; "muleta" and "repete" stay unless cut. Under a screen recording a cut lands on the quietest
    point between two words; where the face camera fills the frame only a piece's head or tail is cut, a cut inside the
    sentence becomes REVER (it would show as a jump)."""
    import studio
    dc = studio.client_json(studio.client_of(ep))["decup"]

    def opt(k, d):
        if k not in args:
            return d
        p = Path(args[args.index(k) + 1])
        return p if p.is_absolute() else ep / p
    src = opt("--edl", ep / "edl.json")
    to = opt("--to", src)
    tdir = opt("--transcript", ep / "work" / "transcript")
    edl = json.loads(src.read_text(encoding="utf-8"))
    scan = _polish_scan(ep, edl, tdir, dc)
    allc = [c for *_, cs in scan for c in cs]
    if "--apply" not in args and "--auto" not in args:
        kinds = {k: sum(c["kind"] == k for c in allc) for k in ("esticada", "muleta", "repete", "clique")}
        lines = ["# id | [TELA]/[CAM] | segundo no bruto | tipo | contexto com o [[candidato]]",
                 "# Por frase: corta só o que não faz falta (o editor de referência manteve a maioria das muletas).", ""]
        for c in allc:
            lines.append(f"{c['id']} [{'TELA' if c['screen'] else 'CAM'}] {c['t']:7.1f} {c['kind']}: {c['ctx']}")
        p = ep / "work" / "polish_in.txt"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        (ep / "work" / "polish_src.json").write_text(json.dumps({"edl": str(src), "texts": {c["id"]: c["text"] for c in allc}},
                                                                ensure_ascii=False, indent=0), encoding="utf-8")
        print(f"{p}\n  {len(allc)} candidates: {kinds}. Write work/polish.json, then: decup.py polish <ep> --apply")
        return
    if "--auto" in args:
        dec = {"cut": [c["id"] for c in allc if c["kind"] in ("muleta", "repete")]}
    else:
        dec = json.loads((ep / "work" / "polish.json").read_text(encoding="utf-8"))
        sp = ep / "work" / "polish_src.json"
        if sp.exists():
            old = json.loads(sp.read_text(encoding="utf-8"))["texts"]
            now = {c["id"]: c["text"] for c in allc}
            if old != now:
                raise SystemExit("the candidates changed since polish_in.txt was written (other edl or transcript): export again")
    ids = [c["id"] for c in allc]
    cut = {x for spec in dec.get("cut", []) for x in _expand(spec, ids)}
    keep = {x for spec in dec.get("keep", []) for x in _expand(spec, ids)}
    cut |= {c["id"] for c in allc if c["kind"] == "esticada" and c["id"] not in keep}      # on unless kept
    rev = {x: d.get("why", "") for d in dec.get("review", []) for spec in d["ids"] for x in _expand(spec, ids)}
    if to == src and not (ep / "edl_pre_polish.json").exists():
        (ep / "edl_pre_polish.json").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    log, n_cut, n_rev, secs = [], 0, 0, 0.0

    def flag(k, why):
        k["review"] = (k["review"] + " / " if k.get("review") else "") + why

    for e, pieces, db, on_screen, cands in scan:
        gone, part = {}, {}
        for c in cands:
            first = pieces[c["words"][0][0]][0]
            if c["id"] in rev:
                why = rev[c["id"]] or c["why"]
                flag(first, f"{why} “{c['text']}”")
                n_rev += 1
                log.append(f"- **REVER** {c['id']} @{c['t']:.1f}s {why} “{c['text']}”")
            elif c["id"] in cut and "cut" in c:
                part.setdefault(tuple(c["words"][0]), []).append((c["cut"], f"{c['id']} {c['why']}"))
            elif c["id"] in cut:
                for x in c["words"]:
                    gone[tuple(x)] = f"{c['id']} {c['why']}"
            elif c["kind"] == "clique" and c["id"] not in keep:
                flag(first, f"só narra o clique? “{c['text']}”")
                n_rev += 1
                log.append(f"- **REVER** {c['id']} @{c['t']:.1f}s só narra o clique? “{c['text']}”")
        out, alts = [], []
        for pi, (k, ws) in enumerate(pieces):
            rm = [wi for wi in range(len(ws)) if (pi, wi) in gone]
            parts = [(wi, sp, why) for wi in range(len(ws)) if wi not in rm for sp, why in part.get((pi, wi), [])]
            if not rm and not parts:
                out.append(k)
                continue
            runs = [[rm[0]]] if rm else []
            for wi in rm[1:]:
                if wi == runs[-1][-1] + 1:
                    runs[-1].append(wi)
                else:
                    runs.append([wi])
            spans, done, held = [[k["s"], k["e"]]], [], []
            for r in runs:
                head, tail = r[0] == 0, r[-1] == len(ws) - 1
                why, txt = gone[(pi, r[0])], " ".join(ws[wi]["w"] for wi in r)
                if not on_screen((k["s"] + k["e"]) / 2) and not head and not tail:   # face camera: no cut mid-sentence
                    held.append(f"{txt} ({why})")
                    continue
                x = k["s"] if head else _snap(db, ws[r[0] - 1]["e"], ws[r[0]]["s"])
                y = k["e"] if tail else _snap(db, ws[r[-1]]["e"], ws[r[-1] + 1]["s"])
                spans = [p for q in spans for p in ([[q[0], min(q[1], x)], [max(q[0], y), q[1]]] if q[0] < y and x < q[1] else [q])]
                done.append((x, y, txt, why))
            for wi, (x, y), why in parts:                              # the start of a stretched word
                head = wi == 0 or all(j in rm for j in range(wi))
                if not on_screen((k["s"] + k["e"]) / 2) and not head:
                    held.append(f"{ws[wi]['w']} ({why})")
                    continue
                x, y = (k["s"] if head else max(x, k["s"])), min(y, k["e"])
                if y - x < 0.05:                                       # the cut before already removed it
                    continue
                spans =[p for q in spans for p in ([[q[0], min(q[1], x)], [max(q[0], y), q[1]]] if q[0] < y and x < q[1] else [q])]
                done.append((x, y, ws[wi]["w"] + f" (início, {y - x:.2f} s)", why))
            spans = [p for p in spans if p[1] - p[0] > 0.12]
            kept = [wi for wi in range(len(ws)) if wi not in rm]
            for x, y, txt, why in done:
                secs += y - x
                n_cut += 1
                log.append(f"- {why.split()[0]} @{x:.1f}s tirado “{txt}” ({' '.join(why.split()[1:])})")
                if y - x >= 0.5:
                    alts.append({"s": round(x, 3), "e": round(y, 3), "text": txt, "why": "segunda passada: " + why})
            if held:
                flag(k, "câmara cheia, cortar? " + "; ".join(held))
                n_rev += 1
                log.append(f"- **REVER** @{k['s']:.1f}s câmara cheia, cortar? {'; '.join(held)}")
            for i, (x, y) in enumerate(spans):
                nk = {kk: v for kk, v in k.items() if i == 0 or kk not in ("review", "trim", "chunk")}
                nk.update(s=round(x, 3), e=round(y, 3),
                          text=" ".join(ws[wi]["w"] for wi in kept if x <= (ws[wi]["s"] + ws[wi]["e"]) / 2 <= y) or k["text"])
                out.append(nk)
        e["keep"] = out
        e["alternates"] = sorted(e["alternates"] + alts, key=lambda a: a["s"])
    to.write_text(json.dumps(edl, indent=1, ensure_ascii=False), encoding="utf-8")
    rep = ep / "report.md"
    if to == src and rep.exists():
        txt = rep.read_text(encoding="utf-8").split("\n## Segunda passada")[0]
        rep.write_text(txt + "\n## Segunda passada (muletas, autocorreções, cliques narrados)\n"
                       + f"- {n_cut} cortes ({secs:.1f} s), {n_rev} marcados REVER.\n" + "\n".join(log) + "\n", encoding="utf-8")
    print(f"{to}\n  cut {n_cut} places ({secs:.1f} s), review {n_rev}")
    for line in log[:400]:
        print(" ", line)


# ------------------------------------------------------------------ camera switching plan (sequence frames)
def _hash01(i, salt):
    x = np.sin((i + 1) * 12.9898 + salt * 78.233) * 43758.5453
    return float(x - np.floor(x))


def camera_plan(onsets, blocked, cover, seq_end, cs, fr):
    """Home camera with short inserts of the second camera, as the editor does (client.json camera_switch).
    onsets: word starts (frames); blocked: screen parts (frames); cover: where the insert camera exists."""
    if not cs.get("enabled", True) or not onsets:
        return []
    lead = fr(cs.get("lead_s", 0.1))
    lo, hi = cs.get("insert_range_s", [1.3, 3.5])
    med = cs.get("insert_median_s", (lo + hi) / 2)
    hlo, hhi = cs.get("home_between_s", [4.0, 5.6])
    ons = sorted(set(onsets))

    def free(a, b):
        if any(a < y and b > x for x, y in blocked):
            return False
        return any(x <= a and b <= y for x, y in cover)

    def next_onset(t):
        j = int(np.searchsorted(ons, t))
        return ons[j] if j < len(ons) else None

    wins, cur, i, guard = [], fr(cs.get("skip_first_s", 0)), 0, 0
    while guard < 20000:
        guard += 1
        home = hlo + (hhi - hlo) * _hash01(i, 1)
        L = min(hi, max(lo, med + (_hash01(i, 2) - 0.5) * (hi - lo) * 0.8))
        o = next_onset(cur + fr(home))
        if o is None:
            break
        a = o - lead
        o2 = next_onset(a + fr(L))
        b = o2 - lead if o2 is not None and o2 - lead - a <= fr(hi) else a + fr(L)
        b = min(b, seq_end)
        if b - a < fr(lo) * 0.8:
            cur = o
            i += 1
            continue
        if not free(a, b):
            cur = o
            i += 1
            continue
        wins.append((a, b))
        cur, i = b, i + 1
    return wins


# ------------------------------------------------------------------ Premiere XML (FCP7 xmeml v4)
def xml(ep, args):
    """python decup.py xml <ep> [--edl file] [--name suffix] [--no-cams]"""
    import xml.sax.saxutils as sx
    import studio
    m = load(ep)
    edl_path = Path(args[args.index("--edl") + 1]) if "--edl" in args else ep / "edl.json"
    if not edl_path.is_absolute():
        edl_path = ep / edl_path
    edl = json.loads(edl_path.read_text(encoding="utf-8"))
    suffix = args[args.index("--name") + 1] if "--name" in args else ""
    CJ = studio.client_json(studio.client_of(ep))
    roles = m.get("roles") or {"master": CJ["decup"].get("master_audio", "lateral"), "home": CJ["decup"].get("home_camera", "frontal")}
    HOME = roles["home"]
    INSERT = "lateral" if HOME == "frontal" else "frontal"
    cs = dict(CJ.get("camera_switch") or {})
    if "--no-cams" in args:
        cs["enabled"] = False
    TB, NTSC, FPS = 30, True, 30000 / 1001           # sequence: 29.97 (master rate)
    SW, SH = CJ["decup"].get("sequence_size") or [1920, 1080]          # e.g. [3840, 2160] to deliver in 4K
    SCREEN_ON = bool(CJ["decup"].get("screen_video_enabled", False))   # screen video on top (its audio stays off)
    SCREEN_FILL = CJ["decup"].get("screen_scale", "fit") == "fill"     # fill the frame (crop the edges) vs fit
    fr = lambda t: int(round(t * FPS))                # seconds -> sequence frames  # noqa: E731
    esc = sx.escape
    files = m["files"]
    words = {}
    for s in m["sessions"]:
        p = ep / "work" / "transcript" / f"s{s['id']}.json"
        words[s["id"]] = json.loads(p.read_text(encoding="utf-8"))["words"] if p.exists() else []

    def url(p):
        p = p.replace("\\", "/")
        return "file://localhost/" + quote(p, safe="/:")

    def offset_at(mem, t_member):
        c = mem.get("curve") or [[0, mem["offset"]]]
        return float(np.interp(t_member, [x[0] for x in c], [x[1] for x in c]))

    def member_time(mem, t_master):
        """master time -> member time, using the member's offset curve (iterate once for the curve)."""
        t = t_master - mem["offset"]
        return t_master - offset_at(mem, t)

    fid = {}

    def file_el(name):
        f = files[name]
        if name in fid:
            return f'<file id="{fid[name]}"/>'
        fid[name] = f"file-{len(fid)+1}"
        tb = 60 if f["fps"] > 50 else 30
        ntsc = "TRUE" if abs(f["fps"] - round(f["fps"])) > 0.01 else "FALSE"
        aud = f'<audio><samplecharacteristics><depth>16</depth><samplerate>48000</samplerate></samplecharacteristics><channelcount>{f["channels"]}</channelcount></audio>' if f["audio"] else ""
        return (f'<file id="{fid[name]}"><name>{esc(name)}</name><pathurl>{url(f["path"])}</pathurl>'
                f'<rate><timebase>{tb}</timebase><ntsc>{ntsc}</ntsc></rate><duration>{int(f["duration"]*tb)}</duration>'
                f'<media><video><samplecharacteristics><width>{f["width"]}</width><height>{f["height"]}</height></samplecharacteristics></video>{aud}</media></file>')

    def scale_for(name):
        f = files[name]
        fit = max if SCREEN_FILL and f.get("role") == "tela" else min
        return round(100 * fit(SW / f["width"], SH / f["height"]), 3)

    def clip(cid, name, start, end, tin, enabled=True, kind="video", label=None):
        rate = f'<rate><timebase>{TB}</timebase><ntsc>{"TRUE" if NTSC else "FALSE"}</ntsc></rate>'
        tin_f = fr(tin)
        tout_f = tin_f + (end - start)
        lab = f"<labels><label2>{label}</label2></labels>" if label else ""
        filt = ""
        if kind == "video" and abs(scale_for(name) - 100) > 0.01:
            filt = (f'<filter><effect><name>Basic Motion</name><effectid>basic</effectid><effectcategory>motion</effectcategory><effecttype>motion</effecttype>'
                    f'<mediatype>video</mediatype><parameter><parameterid>scale</parameterid><name>Scale</name><value>{scale_for(name)}</value></parameter></effect></filter>')
        st = "<sourcetrack><mediatype>audio</mediatype><trackindex>1</trackindex></sourcetrack>" if kind == "audio" else ""
        return (f'<clipitem id="{cid}"><name>{esc(name)}</name><enabled>{"TRUE" if enabled else "FALSE"}</enabled>{rate}'
                f'<start>{start}</start><end>{end}</end><in>{tin_f}</in><out>{tout_f}</out>{file_el(name)}{st}{filt}{lab}</clipitem>')

    def pieces(a, b, wins):
        """Split [a, b) at the camera windows -> [(a, b, inside_window)]."""
        cuts = sorted({a, b} | {x for w in wins for x in w if a < x < b})
        return [(x, y, any(w[0] <= x and y <= w[1] for w in wins)) for x, y in zip(cuts, cuts[1:]) if y > x]

    def build(seq_name, blocks, markers_on=True, cams=False):
        """blocks: list of (session, master_s, master_e, text, color) laid end to end."""
        V = {"lateral": [], "frontal": [], "tela": []}
        A = {"master": [], "frontal": [], "lateral": [], "tela": []}
        lay, pos = [], 0
        for sess, ms, me, text, color in blocks:
            L = fr(me - ms)
            if L > 0:
                lay.append((sess, ms, me, text, color, pos, pos + L))
                pos += L
        # ---- camera plan for this sequence
        wins = []
        if cams:
            onsets, blocked, cover = [], [], []
            for sess, ms, me, text, color, a, b in lay:
                S = m["sessions"][sess - 1]
                onsets += [a + fr(w["s"] - ms) for w in words.get(sess, []) if ms <= w["s"] < me]
                for x, y in _screen_cover(m, sess):
                    if x < me and y > ms:
                        blocked.append((a + fr(max(0, x - ms)), a + fr(min(me, y) - ms)))
                if roles["master"] == INSERT:
                    cover.append((a, b))
                else:
                    for mem in S["members"]:
                        if mem["role"] == INSERT:
                            t0, t1 = member_time(mem, ms), member_time(mem, me)
                            dur = files[mem["name"]]["duration"]
                            if t1 > 0 and t0 < dur:
                                cover.append((a + (fr(-t0) if t0 < 0 else 0), b - (fr(t1 - dur) if t1 > dur else 0)))
            merged = []                                              # contiguous coverage across blocks
            for x, y in sorted(cover):
                if merged and x <= merged[-1][1] + 1:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], y))
                else:
                    merged.append((x, y))
            wins = camera_plan(onsets, blocked, merged, pos, cs, fr)
            build.stats = wins

        def emit(trk, base, name, ca, cb, tin, label):
            enabled = trk in (HOME, roles["master"]) if trk != "tela" else SCREEN_ON
            if trk == HOME and wins:
                for k, (x, y, inside) in enumerate(pieces(ca, cb, wins)):
                    V[trk].append(clip(f"{base}-{k}", name, x, y, tin + (x - ca) / FPS, enabled=not inside,
                                       label="Lavender" if inside else label))
            else:
                V[trk].append(clip(base, name, ca, cb, tin, enabled=enabled, label=label))

        mk, n = [], 0
        for sess, ms, me, text, color, a, b in lay:
            S = m["sessions"][sess - 1]
            n += 1
            emit(roles["master"], f"v-m-{n}", S["master"], a, b, ms, color)
            A["master"].append(clip(f"a1-{n}", S["master"], a, b, ms, kind="audio", label=color))
            for mem in S["members"]:
                t0, t1 = member_time(mem, ms), member_time(mem, me)
                dur = files[mem["name"]]["duration"]
                if t1 <= 0 or t0 >= dur:
                    continue
                ca, cb, tin = a, b, t0
                if t0 < 0:
                    ca, tin = a + fr(-t0), 0.0
                if t1 > dur:
                    cb = b - fr(t1 - dur)
                if cb - ca < 2:
                    continue
                trk = mem["role"]
                emit(trk, f"v-{trk}-{n}-{len(V[trk])}", mem["name"], ca, cb, tin, color)
                A[trk].append(clip(f"a-{trk}-{n}-{len(A[trk])}", mem["name"], ca, cb, tin, enabled=False, kind="audio", label=color))
            if markers_on and text:
                mk.append(f"<marker><name>{esc(text[:60])}</name><comment>{esc(text[:900])}</comment><in>{a}</in><out>-1</out></marker>")

        def track(items, locked=False):
            return f"<track>{''.join(items)}<enabled>TRUE</enabled><locked>{'TRUE' if locked else 'FALSE'}</locked></track>"
        vfmt = (f'<format><samplecharacteristics><rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate><width>{SW}</width><height>{SH}</height>'
                f'<pixelaspectratio>square</pixelaspectratio><fielddominance>none</fielddominance></samplecharacteristics></format>')
        others = [r for r in ("lateral", "frontal") if r != roles["master"]]
        return (f'<sequence id="{esc(seq_name)}"><name>{esc(seq_name)}</name><duration>{pos}</duration>'
                f'<rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate>'
                f'<timecode><rate><timebase>{TB}</timebase><ntsc>TRUE</ntsc></rate><string>00:00:00;00</string><frame>0</frame><displayformat>DF</displayformat></timecode>'
                f'<media><video>{vfmt}{track(V[INSERT])}{track(V[HOME])}{track(V["tela"])}</video>'
                f'<audio>{track(A["master"])}{"".join(track(A[r]) for r in others)}{track(A["tela"])}</audio></media>{"".join(mk)}</sequence>')

    def label_of(k):
        return ("REVER: " + k["review"] + " | " + k["text"], "Mango") if k.get("review") else (k["text"], None)

    full = [(e["session"], 0.0, files[m["sessions"][e["session"] - 1]["master"]]["duration"], f"Sessão {e['session']} (bruto sincronizado)", None) for e in edl]
    cut_blocks = [(e["session"], k["s"], k["e"], *label_of(k)) for e in edl for k in e["keep"]]
    alt_blocks = [(e["session"], k["s"], k["e"], ("ALT " + k["why"] + ": " if k.get("why") else "ALT: ") + k["text"], "Rose") for e in edl for k in e["alternates"]]
    out = ep / "premiere"
    out.mkdir(exist_ok=True)
    fid.clear()
    build.stats = []
    seqs = build("01_DECUPADO", cut_blocks, cams=True)
    wins = build.stats
    seqs += build("02_TAKES_DESCARTADOS", alt_blocks) + build("00_SINCRONIZADO_BRUTO", full, markers_on=True)
    doc = ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE xmeml>\n<xmeml version="4"><project><name>'
           f'{esc(m["episode"])}</name><children>{seqs}</children></project></xmeml>\n')
    p = out / f"{m['episode']}_decupagem{suffix}.xml"
    p.write_text(doc, encoding="utf-8")
    secs = lambda bl: sum(b[2] - b[1] for b in bl)  # noqa: E731
    print(f"{p}\n  01_DECUPADO {secs(cut_blocks)/60:.1f} min ({len(cut_blocks)} trechos) | 02_TAKES_DESCARTADOS {secs(alt_blocks)/60:.1f} min | 00_SINCRONIZADO_BRUTO {secs(full)/60:.1f} min")
    if wins:
        d = [(b - a) / FPS for a, b in wins]
        g = [(wins[i + 1][0] - wins[i][1]) / FPS for i in range(len(wins) - 1)]
        print(f"  camera: {len(wins)} inserts of the {INSERT} camera, median {np.median(d):.2f} s ({min(d):.1f}-{max(d):.1f}), "
              f"{HOME} between them median {np.median(g) if g else 0:.1f} s; none inside screen parts. Inserts = disabled {HOME} pieces (label Lavender).")
    elif cs.get("enabled", True):
        print("  camera: no inserts planned (no word times or no second camera)")
