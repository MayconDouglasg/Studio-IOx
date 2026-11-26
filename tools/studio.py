"""Where things live on THIS PC, and the client / episode helpers every tool uses.

Per-PC settings live in `studio.config.json` next to CLAUDE.md (never in git; see studio.config.example.json):
  {
    "after_effects": "C:/Program Files/Adobe/Adobe After Effects 2026/Support Files/AfterFX.exe",
    "clients": {
      "<slug>": "D:/Trabalho/Clientes/<Nome>/motion"                    (client folder, episodes in <folder>/projects)
      "<slug>": {"dir": "...", "projects": "..."}                          (episodes somewhere else)
    },
    "keys": {"magnific": "...", "pexels": "...", "pixabay": "...", "magnific_daily": 100}   (imagens-apoio; or env vars)
  }
A client folder holds: client.json (brand tokens the tools read), STYLE.md (the brief Claude reads),
brand/ (fonts, logos), refs/canal + refs/inspiracao, _digest/, projects/<episode>/.
Clients not in the config fall back to the legacy layout inside motion-studio: clients/<slug>, projects/<slug>.

CLI (run from motion-studio/):
  python tools/studio.py doctor                         check this PC
  python tools/studio.py clients                        list clients and where they live
  python tools/studio.py new-client <slug> "<folder>" [--name "Nome"]   create + register a client
  python tools/studio.py add-client <slug> "<folder>" [--projects "<folder>"]   register an existing one
  python tools/studio.py refs <slug> <url...> [--inspiracao] [--playlist [--max N]] [--altura 1080]   download reference videos into refs/
  python tools/studio.py new-episode <slug> <episode>   create the episode folder, print its path
  python tools/studio.py where <slug> [<episode>]       print a path
  python tools/studio.py set-after "<AfterFX.exe>"      set the After Effects executable
  python tools/studio.py arsenal [--serve] [--no-open]   catalog page of skills + this PC (--serve: local control panel)
"""
import glob
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "studio.config.json"
TEMPLATE = ROOT / "clients" / "_template"


# ------------------------------------------------------------------ config
def config_path():
    """studio.config.json of this checkout; in a git worktree without one, the main checkout's (it is per PC, not per branch)."""
    if CFG.exists():
        return CFG
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], cwd=ROOT,
                                capture_output=True, text=True, timeout=10).stdout.strip()
        main = Path(common).parent / CFG.name if common else None
        if main and main.exists():
            return main
    except Exception:
        pass
    return CFG


def config():
    p = config_path()
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return {"after_effects": None, "clients": {}}


def save_config(c):
    config_path().write_text(json.dumps(c, indent=2, ensure_ascii=False), encoding="utf-8")


def known_client(slug):
    """True when the slug is registered on this PC or has a legacy clients/<slug>/client.json."""
    return _entry(slug) is not None or (ROOT / "clients" / slug / "client.json").exists()


def _entry(slug):
    e = config().get("clients", {}).get(slug)
    if e is None:
        return None
    return {"dir": e} if isinstance(e, str) else e


def client_dir(slug):
    e = _entry(slug)
    return Path(e["dir"]) if e else ROOT / "clients" / slug


def projects_dir(slug):
    e = _entry(slug)
    if e:
        return Path(e.get("projects") or Path(e["dir"]) / "projects")
    return ROOT / "projects" / slug


def episode_dir(slug, episode):
    return projects_dir(slug) / episode


def clients():
    seen = dict(config().get("clients", {}))
    for d in (ROOT / "clients").glob("*"):
        if d.is_dir() and not d.name.startswith("_") and d.name not in seen:
            seen[d.name] = str(d)
    return sorted(seen)


def client_of(ep):
    """Episode folder -> client slug (config first, then <client>/projects/<ep>, then legacy projects/<slug>/<ep>)."""
    ep = Path(ep).resolve()
    for slug in config().get("clients", {}):
        if projects_dir(slug).resolve() == ep.parent:
            return slug
    if (ep.parent.parent / "client.json").exists():
        return json.loads((ep.parent.parent / "client.json").read_text(encoding="utf-8")).get("slug", ep.parent.parent.name)
    return ep.parent.name


def client_json(slug):
    """Brand tokens; missing keys fall back to the template so old clients keep working."""
    base = json.loads((TEMPLATE / "client.json").read_text(encoding="utf-8"))
    p = client_dir(slug) / "client.json"
    if p.exists():
        base.pop("_template", None)                  # the flag belongs to the template, not to a merged client
        _merge(base, json.loads(p.read_text(encoding="utf-8")))
    base["slug"] = slug
    return base


def _merge(a, b):
    for k, v in b.items():
        if isinstance(v, dict) and isinstance(a.get(k), dict):
            _merge(a[k], v)
        else:
            a[k] = v
    return a


def episode_json(ep):
    p = Path(ep) / "episode.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def resolve(path, ep):
    """Asset path written in a spec: absolute, or relative to the episode, the client folder or motion-studio."""
    p = Path(path)
    if p.is_absolute():
        return p
    ep = Path(ep).resolve()
    for base in (ep, client_dir(client_of(ep)), ROOT):
        if (base / p).exists():
            return (base / p).resolve()
    return (ROOT / p).resolve()


def generated_media(ep):
    """Generated clips of an episode (opening wall, phone screens, hook squares): episode.json "media" (paths
    relative to the episode), else the clips named like episode.json "media_prefix" (default "result-") on the
    editor's final XML (premiere/*Final*.xml), in edit order."""
    import xml.etree.ElementTree as ET
    from urllib.parse import unquote
    ep = Path(ep).resolve()
    epj = episode_json(ep)
    if epj.get("media"):
        return [str(resolve(x, ep)).replace("\\", "/") for x in epj["media"]]
    xs = sorted((ep / "premiere").glob("*Final*.xml"))
    if not xs:
        return []
    r = ET.parse(xs[0]).getroot()
    seq = next((q for q in r.iter("sequence") if q.findtext("name") == "01_DECUPADO"), None) or next(r.iter("sequence"), None)
    if seq is None:
        return []
    paths = {f.findtext("name"): unquote(f.findtext("pathurl").replace("file://localhost/", ""))
             for f in r.iter("file") if f.findtext("name") and f.findtext("pathurl")}
    found = []
    for tr in seq.find("media/video").findall("track"):
        for c in tr.findall("clipitem"):
            n = c.findtext("name") or ""
            if n.startswith(epj.get("media_prefix", "result-")) and n in paths and int(c.findtext("start")) >= 0:
                found.append((int(c.findtext("start")), paths[n]))
    return [x for _, x in sorted(found)]


def after_effects_installed():
    return [Path(p) for p in sorted(glob.glob(r"C:\Program Files\Adobe\Adobe After Effects *\Support Files\AfterFX.exe"))]


def after_effects_running():
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", "(Get-Process AfterFX -ErrorAction SilentlyContinue | Select-Object -First 1).Path"],
                           capture_output=True, text=True, timeout=20)
        p = r.stdout.strip()
        return Path(p) if p and Path(p).exists() else None
    except Exception:  # noqa: BLE001
        return None


def after_effects():
    """config 'after_effects' > the After Effects that is open now > the newest installed."""
    c = config().get("after_effects")
    if c and Path(c).exists():
        return Path(c)
    run = after_effects_running()
    if run:
        return run
    found = after_effects_installed()
    return found[-1] if found else None


# ------------------------------------------------------------------ CLI
def _new_client(slug, folder, name):
    d = Path(folder).resolve()
    if (d / "client.json").exists():
        print(f"{d} already has a client.json — registering it as is")
    else:
        d.mkdir(parents=True, exist_ok=True)
        for sub in ("brand/fonts", "brand/logos", "refs/canal", "refs/inspiracao", "projects"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        if not (d / "STYLE.md").exists():
            shutil.copy(TEMPLATE / "STYLE.md", d / "STYLE.md")
        cj = json.loads((TEMPLATE / "client.json").read_text(encoding="utf-8"))
        cj["slug"], cj["name"] = slug, name or slug
        (d / "client.json").write_text(json.dumps(cj, indent=2, ensure_ascii=False), encoding="utf-8")
    c = config()
    c.setdefault("clients", {})[slug] = str(d).replace("\\", "/")
    save_config(c)
    print(f"client '{slug}' -> {d}\nnext: put fonts in brand/fonts, logos in brand/logos, channel videos in refs/canal,"
          f" then fill client.json and ask Claude to run the motion-refs skill")


VIDEO_EXT = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}   # what tools/ingest.py digests


def _js_runtimes():
    """yt-dlp needs a JavaScript runtime for YouTube; deno is its default, node is what install.ps1 installs."""
    return {name: {} for name in ("deno", "node") if shutil.which(name)}


def _refs(target, urls, inspiracao=False, playlist=False, limit=None, height=1080):
    """Download reference videos with yt-dlp into <client>/refs/canal (or refs/inspiracao), one mp4 per video
    (H.264 first, up to `height` px), named by the video title; files already there are skipped.
    Only the client's own channel or references the client sent (motion-refs skill): never footage for use inside a video."""
    try:
        from yt_dlp import YoutubeDL
    except ImportError:
        print("yt-dlp is not installed -> python -m pip install --user -r requirements.txt")
        return 1
    if known_client(target):
        base = client_dir(target)
    elif Path(target).is_dir():
        base = Path(target).resolve()
    else:
        print(f"unknown client '{target}' -> python tools/studio.py clients (or pass the client folder)")
        return 1
    dest = base / "refs" / ("inspiracao" if inspiracao else "canal")
    dest.mkdir(parents=True, exist_ok=True)
    h = int(height)
    common = {"outtmpl": str(dest / "%(title).150B.%(ext)s"), "windowsfilenames": True, "noplaylist": not playlist,
              "js_runtimes": _js_runtimes() or None}
    if not common["js_runtimes"]:
        print("  warning: no deno/node on PATH; YouTube downloads may fail (install.ps1 installs node)")
    lister = YoutubeDL(common | {"extract_flat": "in_playlist", "skip_download": True, "quiet": True, "no_warnings": True})
    getter = YoutubeDL(common | {
        "format": f"bv*[height<={h}][vcodec^=avc1]+ba[ext=m4a]/b[height<={h}][vcodec^=avc1]/bv*[height<={h}][ext=mp4]+ba[ext=m4a]"
                  f"/bv*[height<={h}]+ba/b[height<={h}]/b",
        "merge_output_format": "mp4", "overwrites": False, "noprogress": not sys.stdout.isatty()})
    have = {p.stem.casefold() for p in dest.iterdir() if p.suffix.lower() in VIDEO_EXT}
    got, skipped, failed = [], [], []
    for url in urls:
        try:
            info = lister.extract_info(url, download=False)
        except Exception as e:  # noqa: BLE001
            failed.append((url, str(e).splitlines()[0]))
            continue
        entries = info.get("entries")
        if entries is not None:
            entries = [e for e in entries if e]
            if not playlist:
                print(f"  {url}: a playlist / channel with {len(entries)} videos — pass --playlist [--max N] to download it")
                continue
            entries = entries[: int(limit)] if limit else entries
        else:
            entries = [info]
        for e in entries:
            link = e.get("webpage_url") or e.get("url") or url
            title = e.get("title") or link
            if e.get("live_status") in ("is_live", "is_upcoming"):
                skipped.append((title, "live / not aired yet"))
                continue
            stem = Path(lister.prepare_filename(e)).stem if e.get("title") else None
            if stem and stem.casefold() in have:
                skipped.append((title, "already in " + dest.name))
                continue
            try:
                getter.extract_info(link, download=True)
                got.append(title)
                if stem:
                    have.add(stem.casefold())
            except Exception as ex:  # noqa: BLE001
                failed.append((title, str(ex).splitlines()[0]))
    print(f"\nrefs/{dest.name}: {len(got)} downloaded, {len(skipped)} skipped, {len(failed)} failed  ({dest})")
    for t, why in skipped:
        print(f"  skip  {t}  ({why})")
    for t, why in failed:
        print(f"  !!    {t}: {why}")
    n = sum(1 for p in dest.iterdir() if p.suffix.lower() in VIDEO_EXT)
    if not inspiracao and n < 3:
        print(f"  refs/canal has {n} video(s); the style needs 3–6 of the client's own channel videos")
    if got:
        print("next: ask Claude to run the motion-refs skill for this client (python tools/ingest.py, then STYLE.md)")
    return 1 if failed and not got else 0


def _doctor():
    ok = True

    def line(good, what, hint=""):
        nonlocal ok
        ok &= bool(good)
        print(f"  [{'OK' if good else '!!'}] {what}" + (f"   -> {hint}" if not good and hint else ""))

    print(f"motion-studio: {ROOT}")
    print(f"config: {CFG if CFG.exists() else 'none yet (run install.ps1 or set-after / add-client)'}")
    for mod in ("numpy", "scipy", "librosa", "soundfile", "sklearn", "faster_whisper", "ctranslate2"):
        try:
            __import__(mod)
            line(True, f"python: {mod}")
        except Exception as e:  # noqa: BLE001
            line(False, f"python: {mod} ({type(e).__name__})", "pip install -r requirements.txt")
    try:
        import ctranslate2
        n = ctranslate2.get_cuda_device_count()
    except Exception:  # noqa: BLE001
        n = 0
    if n > 0:
        line(True, f"GPU for transcription: {n} CUDA device(s)")
    else:  # not a failure: faster-whisper falls back to the CPU (several times slower on a long episode)
        print("  [--] GPU for transcription: none, Whisper runs on the CPU (slower)"
              "   -> optional: NVIDIA card + driver, then pip install -r requirements.txt")
    for exe in ("ffmpeg", "ffprobe", "node", "git"):
        line(shutil.which(exe), exe, "install.ps1 installs it with winget")
    line((ROOT / "node_modules" / "playwright").exists(), "node: playwright", "npm install && npx playwright install chromium")
    try:
        import yt_dlp
        import yt_dlp_ejs  # noqa: F401  (YouTube's JavaScript challenges; comes with yt-dlp[default])
        rt = ", ".join(_js_runtimes())
        line(rt, f"yt-dlp {yt_dlp.version.__version__} (reference videos; JS runtime: {rt or 'none'})",
             "install.ps1 installs node (YouTube needs deno or node)")
    except Exception as e:  # noqa: BLE001
        line(False, f"yt-dlp ({type(e).__name__}: {e})", "pip install -r requirements.txt")
    ae = after_effects()
    line(ae, f"After Effects: {ae or 'not found'}", 'python tools/studio.py set-after "<...AfterFX.exe>"')
    inst = after_effects_installed()
    if len(inst) > 1:
        print(f"       {len(inst)} versions installed: " + " | ".join(p.parent.parent.name for p in inst)
              + '  -> to use another one: python tools/studio.py set-after "<...AfterFX.exe>"')
    try:
        import apoio
        for src, good, note in apoio.sources_status():
            print(f"  [{'OK' if good else '--'}] imagens de apoio: {src} ({note})"
                  + ("" if good else "   -> optional: python tools/apoio.py chaves (GUIA.md, 'Imagens de apoio')"))
    except Exception as e:  # noqa: BLE001
        line(False, f"imagens de apoio ({type(e).__name__}: {e})", "python tools/apoio.py fontes")
    lib = config().get("sfx_library")                         # optional: the SFX library (tools/sfx.py)
    if not lib:
        print('  [--] biblioteca de SFX: not set   -> optional: python tools/sfx.py biblioteca "<SFX_LIBRARY folder>"')
    else:
        idx = Path(lib) / "_sistema" / "dados" / "sfx_motion.json"
        good = (Path(lib) / "_sistema" / "dados" / "catalogo.json").exists()
        print(f"  [{'OK' if good else '--'}] biblioteca de SFX: {lib}" + ("" if idx.exists() else " (no index yet: python tools/sfx.py index)")
              + ("" if good else "   -> folder or catalogo.json missing on this PC"))
    for slug in clients():
        d = client_dir(slug)
        line(d.exists(), f"client {slug}: {d}", "fix the path in studio.config.json")
        if d.exists():
            line((d / "client.json").exists() or not _entry(slug), f"client {slug}: client.json", "copy clients/_template/client.json")
            if (d / "client.json").exists():
                own = json.loads((d / "client.json").read_text(encoding="utf-8"))
                gaps = [k for k in ("colors", "fonts", "decup") if k not in own] + (["_template"] if own.get("_template") else [])
                line(not gaps, f"client {slug}: own brand tokens" + (f" (still template: {', '.join(gaps)})" if gaps else ""),
                     "fill these in the client's client.json (novo-cliente skill)")
    print("all good" if ok else "fix the [!!] lines above")
    return ok


def main(a):
    if not a or a[0] in ("-h", "--help"):
        print(__doc__)
        return
    cmd = a[0]
    opt = lambda k: a[a.index(k) + 1] if k in a else None  # noqa: E731
    if cmd == "doctor":
        sys.exit(0 if _doctor() else 1)
    elif cmd == "clients":
        for s in clients():
            print(f"{s:20s} {client_dir(s)}   episodes: {projects_dir(s)}")
    elif cmd == "new-client":
        _new_client(a[1], a[2], opt("--name"))
    elif cmd == "add-client":
        c = config()
        c.setdefault("clients", {})[a[1]] = {"dir": str(Path(a[2]).resolve()).replace("\\", "/")} | (
            {"projects": str(Path(opt("--projects")).resolve()).replace("\\", "/")} if opt("--projects") else {})
        save_config(c)
        print(f"registered {a[1]} -> {client_dir(a[1])} (episodes in {projects_dir(a[1])})")
    elif cmd == "refs":
        valued = {"--max", "--altura"}
        pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and a[i - 1] not in valued]
        if len(pos) < 2:
            print("usage: python tools/studio.py refs <slug> <url...> [--inspiracao] [--playlist [--max N]] [--altura 1080]")
            sys.exit(2)
        sys.exit(_refs(pos[0], pos[1:], "--inspiracao" in a, "--playlist" in a, opt("--max"), opt("--altura") or 1080))
    elif cmd == "new-episode":
        d = episode_dir(a[1], a[2])
        for sub in ("assets", "premiere", "motion", "after"):
            (d / sub).mkdir(parents=True, exist_ok=True)
        if not (d / "episode.json").exists():
            (d / "episode.json").write_text(json.dumps({"client": a[1], "episode": a[2], "vocab": [], "partner": None}, indent=2), encoding="utf-8")
        print(d)
    elif cmd == "where":
        print(episode_dir(a[1], a[2]) if len(a) > 2 else client_dir(a[1]))
    elif cmd == "arsenal":
        import arsenal
        arsenal.main(a[1:])
    elif cmd == "set-after":
        c = config()
        c["after_effects"] = str(Path(a[1])).replace("\\", "/")
        save_config(c)
        print("After Effects:", c["after_effects"])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == "__main__":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    main(sys.argv[1:])
