"""Code path of a scene or a whole film (HTML -> MP4 / ProRes 4444): start a project from a starter, word times of
the voice, a synthesized bed with SFX on the film's events, and the voice + bed mix.

  python tools/codigo.py novo <folder> [--client <slug>] [--modelo paginas] [--force]
        copy starters/<modelo>/ (film.html, paginas.json) into <folder>, write <folder>/client.json (the client's
        tokens merged over the template) and copy the client's font files (fonts.<role>.file) into <folder>/fonts.
        Existing files are kept unless --force (never overwrite something delivered: use a new folder).
  python tools/codigo.py palavras <folder> <voice file> [--model large-v3] [--lang pt]
        voice -> <folder>/audio/voice.wav (48 kHz) + <folder>/words.json [{w, s, e}] (faster-whisper word timestamps)
  python tools/codigo.py trilha <folder> [--bpm 120] [--gain 1.0] [--janelas 4.6-21.2,32.75-]
        needs <folder>/out/timeline.json (node render.mjs --project <folder> --timeline); writes audio/bed.wav:
        a quiet bed on the bpm grid + SFX on the film's events (travel = whoosh, title = pop, wave = blips, ...);
        --janelas: SFX only for events inside the windows (none while the presenter is on screen)
  python tools/codigo.py mix <folder> [--bed audio/bed.wav] [--bed-gain 0.22] [--lufs -14] [--janelas 4.6-21.2,25.5-29.2]
        voice + bed * bed-gain -> audio/score.wav, loudness-normalized (two-pass loudnorm) to --lufs, true peak -1 dB.
        --janelas: the bed (and its SFX) only inside these windows (seconds), with 0.25 s fades: motion inserted over
        the presenter keeps its sound only while the motion is on screen
  python tools/codigo.py compor <folder> <source video> --janelas 4.6-21.2,... --out <new file> [--audio score|fonte]
        the source video (presenter) with the rendered motion (out/<folder>.mp4, or *_alpha.mov laid over it) cut in
        only inside the windows; audio = audio/score.wav (default) or the source's. Refuses to overwrite --out.
  Tip: node render.mjs --project <folder> --at 1,2.5,4 --name pontos  also tiles the stills into out/pontos.png

Then: node render.mjs --project <folder> --contact (look, score, fix) -> node render.mjs --project <folder> [--alpha].
The storyboard skill decides when a scene goes this way (caminho "codigo").
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio  # noqa: E402

ROOT = studio.ROOT


def opt(a, k, d=None):
    return a[a.index(k) + 1] if k in a and a.index(k) + 1 < len(a) else d


def janelas(txt, end=1e5):
    """'4.65-21.2,25.5-29.2,32.75-' -> [(4.65, 21.2), (25.5, 29.2), (32.75, end)]: when the motion is on screen."""
    out_ = []
    for w in (txt or "").split(","):
        a_, _, b_ = w.strip().partition("-")
        if a_:
            out_.append((float(a_), float(b_) if b_ else end))
    return out_


def novo(a):
    dst = Path(a[0]).resolve()
    modelo, slug, force = opt(a, "--modelo", "paginas"), opt(a, "--client"), "--force" in a
    if slug and not studio.known_client(slug):
        sys.exit(f"unknown client '{slug}': not in {studio.config_path()} (python tools/studio.py clients). "
                 "Register it first (novo-cliente skill); refusing to fall back to the template.")
    src = ROOT / "starters" / modelo
    if not src.exists():
        sys.exit(f"no starter {src}; available: {', '.join(p.name for p in (ROOT / 'starters').iterdir())}")
    (dst / "audio").mkdir(parents=True, exist_ok=True)
    (dst / "out").mkdir(exist_ok=True)
    for f in src.iterdir():
        if f.is_file() and (force or not (dst / f.name).exists()):
            shutil.copy2(f, dst / f.name)
            print("  +", f.name)
    cj = studio.client_json(slug) if slug else json.loads((studio.TEMPLATE / "client.json").read_text(encoding="utf-8"))
    if cj.get("_template") and slug:
        print(f"  ! {slug}: client.json still has template values (novo-cliente skill)")
    cdir = studio.client_dir(slug) if slug else studio.TEMPLATE
    (dst / "fonts").mkdir(exist_ok=True)
    found = sorted(p for d_ in (cdir / "brand" / "fonts", cdir / "fonts") if d_.exists()
                   for p in d_.rglob("*") if p.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2"))
    for role, f in cj.get("fonts", {}).items():
        p = None
        if f.get("file"):
            p = (cdir / f["file"]) if not Path(f["file"]).is_absolute() else Path(f["file"])
            if not p.exists():
                print(f"  ! font file not found for {role}: {p}")
                p = None
        if p is None and slug:                    # no file named: look for the family in the client's brand/fonts
            fam = re.sub(r"[^a-z0-9]", "", (f.get("family") or "").lower())
            cands = [q for q in found if fam and fam in re.sub(r"[^a-z0-9]", "", q.stem.lower())]
            want = ["black", "heavy"] if (f.get("weight") or 400) >= 850 else ["extrabold"] if (f.get("weight") or 400) >= 750 else \
                ["bold"] if (f.get("weight") or 400) >= 650 else ["semibold"] if (f.get("weight") or 400) >= 550 else ["regular", "book"]
            it = bool(f.get("italic"))
            score = lambda q: (("italic" in q.stem.lower()) == it) * 2 + any(w in q.stem.lower().replace("-", "") for w in want)  # noqa: E731
            if cands:
                p = max(cands, key=score)
                f["file"] = str(p.relative_to(cdir)) if p.is_relative_to(cdir) else str(p)
                print(f"  ~ {role}: no fonts.{role}.file in client.json, using {p.name} from the client's fonts (set it to be sure)")
        if p is not None:
            shutil.copy2(p, dst / "fonts" / p.name)
            print(f"  + fonts/{p.name} ({role})")
        else:
            print(f"  ! {role}: no font file ({f.get('family')}): the page uses the INSTALLED family, which renders differently "
                  f"on another PC. Set fonts.{role}.file in the client's client.json.")
    if force or not (dst / "client.json").exists():
        (dst / "client.json").write_text(json.dumps(cj, indent=1, ensure_ascii=False), encoding="utf-8")
        print("  + client.json", f"({slug})" if slug else "(template)")
    print(dst)


def palavras(a):
    dst, voice = Path(a[0]).resolve(), Path(a[1]).resolve()
    (dst / "audio").mkdir(parents=True, exist_ok=True)
    wav = dst / "audio" / "voice.wav"
    if voice != wav:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(voice), "-ar", "48000", "-ac", "1", str(wav)], check=True)
    cj = {}
    if (dst / "client.json").exists():
        cj = json.loads((dst / "client.json").read_text(encoding="utf-8"))
    lang = opt(a, "--lang") or (cj.get("language") or "pt").split("-")[0]
    from decup_stage2 import whisper_model
    model = whisper_model(opt(a, "--model", "large-v3"))
    w16 = dst / "audio" / "_voice16.wav"                         # numpy in: some PyAV versions break faster-whisper's decoder
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(wav), "-ar", "16000", "-ac", "1", "-c:a", "pcm_f32le", str(w16)], check=True)
    import soundfile as sf
    audio, _ = sf.read(str(w16), dtype="float32")
    w16.unlink()
    segs, _ = model.transcribe(audio, language=lang, word_timestamps=True, vad_filter=False,
                               initial_prompt=cj.get("transcribe_prompt") or None)
    words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for s in segs for w in (s.words or []) if w.word.strip()]
    (dst / "words.json").write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
    print(f"{len(words)} words, {words[-1]['e'] if words else 0:.2f} s -> {dst / 'words.json'}")
    print(" ".join(w["w"] for w in words))


def trilha(a):
    from synth import Mix, kick, hat, clap, pad, bass, blip, tick, whoosh, impact, pop, scribble, pluck, shaker  # noqa: F401
    dst = Path(a[0]).resolve()
    tl = json.loads((dst / "out" / "timeline.json").read_text(encoding="utf-8"))
    dur, bpm, g = tl["film"]["dur"], float(opt(a, "--bpm", 120)), float(opt(a, "--gain", 1.0))
    m = Mix(duration=dur, bpm=bpm)
    T = m.T
    nb = int(dur / (60 / bpm)) + 1
    for b in range(nb):                                         # quiet groove: the voice leads, the bed only moves
        m.place("drums", kick(punch=0.7, decay=0.12), T(b), gain=0.42 * g)
        m.kicks.append(T(b))
        m.place("drums", hat(), T(b + 0.5), gain=0.2 * g, pan=0.3)
        m.place("drums", shaker(), T(b + 0.25), gain=0.1 * g, pan=-0.3)
        if b % 2 == 1:
            m.place("drums", clap(), T(b), gain=0.2 * g, send=0.2)
    chords = [[261.63, 329.63, 392.0, 493.88], [220.0, 261.63, 329.63, 392.0], [174.61, 220.0, 261.63, 329.63], [196.0, 246.94, 293.66, 392.0]]
    roots = [65.41, 55.0, 43.65, 49.0]
    for i, b0 in enumerate(range(0, nb, 8)):
        m.place("music", pad(chords[i % 4], dur=8 * 60 / bpm + 0.1, cutoff=1400), T(b0), gain=0.28 * g, send=0.35)
        for b in range(b0, min(nb, b0 + 8)):
            m.place("bass", bass(roots[i % 4], dur=0.16), T(b + 0.5), gain=0.38 * g)
    W_, skipped = janelas(opt(a, "--janelas")), 0
    for e in tl["events"]:                                      # SFX land on the spoken word (the event time)
        t, k = e["t"], e["tipo"]
        if W_ and not any(x0 - 0.05 <= t <= x1 for x0, x1 in W_):
            skipped += 1
            continue
        if k == "viagem":
            m.place("sfx", whoosh(max(0.3, e.get("dur", 0.45)), up=True), max(0, t - 0.05), gain=0.5, send=0.25)
        elif k == "corte":
            m.place("sfx", whoosh(0.3, up=False), max(0, t - 0.15), gain=0.45)
        elif k in ("titulo", "no"):
            m.place("sfx", pop(), t, gain=0.45)
        elif k == "galho":
            m.place("sfx", pluck(880.0), t, gain=0.3, send=0.3)
        elif k == "onda":
            for i in range(5):
                m.place("sfx", blip(660 * 2 ** (i / 7), d=0.07), t + i * 0.1, gain=0.28, pan=-0.4 + 0.2 * i)
        elif k == "liga":
            m.place("sfx", scribble(0.3), t, gain=0.25)
        elif k == "digita":
            for i in range(min(40, e.get("n", 16))):
                m.place("sfx", tick(), t + i / 26, gain=0.2, pan=0.2)
        elif k == "marca":
            m.place("sfx", scribble(0.25), t, gain=0.3)
        elif k == "varre":
            m.place("sfx", scribble(0.5), t, gain=0.22)
        elif k == "check":
            for i in range(max(1, e.get("n", 1))):
                m.place("sfx", blip(990 + 110 * i, d=0.07), t + i * 0.15, gain=0.3)
        elif k == "carimbo":
            m.place("sfx", impact(0.7, length=1.0), t, gain=0.5, send=0.3)
    m.duck(m.kicks, depth=0.5)
    if skipped:
        print(f"  {skipped} events outside --janelas: no SFX for them")
    out = dst / "audio" / "bed.wav"
    m.render(str(out), fade=0.4)
    print(f"bed {out} ({dur:.2f} s, {len(tl['events'])} events)")


def mix(a):
    dst = Path(a[0]).resolve()
    voice, bed = dst / "audio" / "voice.wav", dst / opt(a, "--bed", "audio/bed.wav")
    gain, lufs = float(opt(a, "--bed-gain", 0.22)), float(opt(a, "--lufs", -14))
    gate = ""
    if opt(a, "--janelas"):                       # bed only inside the windows, 0.25 s fades (volume gate per sample)
        W_ = janelas(opt(a, "--janelas"))
        f_ = 0.25
        env = "+".join(f"clip(min((t-{x0:.3f})/{f_}+1,({x1:.3f}-t)/{f_}+1),0,1)" for x0, x1 in W_)
        gate = f",volume='min(1,{env})':eval=frame"
        print("  bed windows:", ", ".join(f"{x0:g}-{x1:g}" for x0, x1 in W_))
    raw, out = dst / "audio" / "_mix_raw.wav", dst / "audio" / "score.wav"
    ins = ["-i", str(voice)] + (["-i", str(bed)] if bed.exists() else [])
    if not bed.exists():
        print(f"  ! no bed at {bed}: voice only")
    fc = (f"[0:a]aformat=sample_rates=48000:channel_layouts=stereo[v];[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume={gain}{gate}[b];"
          "[v][b]amix=inputs=2:duration=longest:normalize=0[m]") if bed.exists() else "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[m]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *ins, "-filter_complex", fc, "-map", "[m]", "-c:a", "pcm_s24le", str(raw)], check=True)
    ln = f"loudnorm=I={lufs}:TP=-1:LRA=11"
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(raw), "-af", ln + ":print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    me = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
    ln2 = (f"{ln}:measured_I={me['input_i']}:measured_TP={me['input_tp']}:measured_LRA={me['input_lra']}"
           f":measured_thresh={me['input_thresh']}:offset={me['target_offset']}:linear=true")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(raw), "-af", ln2, "-ar", "48000", "-c:a", "pcm_s24le", str(out)], check=True)
    raw.unlink()
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", str(out), "-af", ln + ":print_format=json", "-f", "null", "-"], capture_output=True, text=True)
    me = json.loads(re.findall(r"\{[^{}]*\}", r.stderr)[-1])
    print(f"score {out}: {me['input_i']} LUFS, true peak {me['input_tp']} dB (bed x{gain})")


def compor(a):
    dst, src = Path(a[0]).resolve(), Path(a[1]).resolve()
    out = Path(opt(a, "--out") or sys.exit("--out <new file> is required")).resolve()
    if out.exists():
        sys.exit(f"exists: {out} (never overwrite a delivered file: pass a new name)")
    if not opt(a, "--janelas"):
        sys.exit("--janelas 4.6-21.2,25.5-29.2 is required (when the motion is on screen)")
    W_ = janelas(opt(a, "--janelas"))
    alpha = dst / "out" / f"{dst.name}_alpha.mov"
    mot = alpha if alpha.exists() and "--cheio" not in a else dst / "out" / f"{dst.name}.mp4"
    if not mot.exists():
        sys.exit(f"no render in {dst / 'out'}: node render.mjs --project \"{dst}\" [--alpha]")
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height,r_frame_rate",
                        "-show_entries", "format=duration", "-of", "json", str(src)], capture_output=True, text=True)
    pr = json.loads(r.stdout)
    st, dur = pr["streams"][0], float(pr["format"]["duration"])
    en = "+".join(f"between(t,{x0:.3f},{x1:.3f})" for x0, x1 in W_)
    fps = st["r_frame_rate"]
    fc = (f"[0:v]fps={fps},setsar=1[v];[1:v]fps={fps},scale={st['width']}:{st['height']},setsar=1[m];"
          f"[v][m]overlay=0:0:enable='{en}'[o]")
    use_score = (opt(a, "--audio", "score") == "score") and (dst / "audio" / "score.wav").exists()
    ins = ["-i", str(src), "-i", str(mot)] + (["-i", str(dst / "audio" / "score.wav")] if use_score else [])
    amap = ["-map", "2:a"] if use_score else ["-map", "0:a?"]
    subprocess.run(["ffmpeg", "-v", "error", *ins, "-filter_complex", fc, "-map", "[o]", *amap,
                    "-c:v", "libx264", "-crf", "16", "-pix_fmt", "yuv420p", "-preset", "slow",
                    "-c:a", "aac", "-b:a", "256k", "-ar", "48000", "-t", f"{dur:.3f}", "-movflags", "+faststart", str(out)], check=True)
    print(f"{out}: {src.name} + {mot.name} in {len(W_)} windows, audio = {'score.wav' if use_score else 'source'}")


if __name__ == "__main__":
    a = sys.argv[1:]
    cmds = {"novo": novo, "palavras": palavras, "trilha": trilha, "mix": mix, "compor": compor}
    if not a or a[0] not in cmds:
        print(__doc__)
        sys.exit(2)
    cmds[a[0]](a[1:])
