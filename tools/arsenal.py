"""Arsenal: a local page (Portuguese) that shows what motion-studio and its video skills can do, and the state of this PC.

  python tools/studio.py arsenal                 write arsenal.html (not in git: it lists this PC's clients) and open it
  python tools/studio.py arsenal --no-open       only write it
  python tools/studio.py arsenal --serve [--port 8766]
        serve the page on 127.0.0.1 only, with a closed list of actions that call studio.py functions:
        doctor, clients, add-client, new-client, new-episode, open-folder, open-file (only the files the page lists for an episode). No shell.

Catalog sources (all in git, never a client's name):
  - the front matter of every SKILL.md in .claude/skills and .agents/skills (name, description)
  - the `arsenal:` block in the front matter of our own skills and agents (.claude/agents/*.md):
        arsenal:
          etapa: 3                      pipeline position (omit for skills outside the pipeline)
          ao_lado: storyboard           optional stage drawn under that pipeline stage (V2 lane), no etapa
          area: pipeline                pipeline | hyperframes | remotion | figma-midia | agentes
          titulo: "Decupagem"
          resumo: "one line in Portuguese"
          entradas: ["xml|what goes in", ...]      type|label; type picks the file icon
          saidas: ["aep|what comes out", ...]      (xml mp4 aep prproj md json html png wav pasta fonte)
          ferramentas: ["decup.py"]
          modelo: "Opus"
          pedidos: ["a ready-to-paste request", ...]
    every value is JSON on one line (valid YAML too)
  - arsenal/extras.json (Portuguese cards for the external skills: `npx skills update` overwrites their files)
  - arsenal/receitas.json (skills chained into recipes)
  - arsenal/ferramentas.json (Portuguese lines for tools/ and the studio.py commands; English docstring if missing)
  - the studio.py CLI docstring and the files in tools/
"""
import ast
import base64
import contextlib
import datetime as dt
import io
import json
import os
import re
import secrets
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import studio  # noqa: E402

ROOT = studio.ROOT
OUT = ROOT / "arsenal.html"
CAT = ROOT / "arsenal"

# Pipeline as the page draws it. The Premiere edit is done by the editor, not by a skill.
PIPELINE = ["novo-cliente", "motion-refs", "decupagem", "premiere", "storyboard", "after-handoff", "estudo-final"]
PREMIERE = {"name": "premiere", "titulo": "Edição no Premiere", "area": "pipeline", "manual": True,
            "resumo": "O editor monta o corte final a partir do XML da decupagem e exporta o XML final e um MP4 leve.",
            "entradas": ["xml|premiere/<ep>_decupagem.xml"], "saidas": ["xml|XML final (exportado)", "mp4|MP4 leve do corte final"],
            "ferramentas": [], "modelo": "nenhum: é você no Premiere", "pedidos": []}


# ------------------------------------------------------------------ catalog
def front_matter(path):
    """name/description + the `arsenal:` block (one JSON value per line) of a SKILL.md or agent .md."""
    t = Path(path).read_text(encoding="utf-8", errors="replace")
    if not t.startswith("---"):
        return {}
    body = t.split("\n", 1)[1]
    end = re.search(r"^---\s*$", body, re.M)
    lines = body[: end.start()].splitlines() if end else []
    out, block = {}, None
    for ln in lines:
        if not ln.strip():
            continue
        if not ln.startswith((" ", "\t")):
            k, _, v = ln.partition(":")
            k, v = k.strip(), v.strip()
            block = None
            if k == "arsenal" and not v:
                block = out.setdefault("arsenal", {})
            else:
                out[k] = _val(v)
        elif block is not None:
            k, _, v = ln.strip().partition(":")
            block[k.strip()] = _val(v.strip())
    return out


def _val(v):
    try:
        return json.loads(v)
    except ValueError:
        return v.strip("'\"")


def _skill_dirs():
    seen = {}
    for base in (ROOT / ".claude" / "skills", ROOT / ".agents" / "skills"):
        for p in sorted(base.glob("*/SKILL.md")):
            seen.setdefault(p.parent.name, p)
    return seen


def catalog():
    extras = json.loads((CAT / "extras.json").read_text(encoding="utf-8"))
    recipes = json.loads((CAT / "receitas.json").read_text(encoding="utf-8"))["receitas"]
    items, missing = [], []
    for name, p in _skill_dirs().items():
        fm = front_matter(p)
        name = fm.get("name", name)
        card = fm.get("arsenal") or extras["skills"].get(name)
        if not card:
            missing.append(name)
            continue
        card = dict(card)
        card.setdefault("entradas", card.pop("entra", []))
        card.setdefault("saidas", card.pop("sai", []))
        card.setdefault("pedidos", [card.pop("pedido")] if card.get("pedido") else [])
        card.update(name=name, description=fm.get("description", ""), kind="skill",
                    own="arsenal" in fm, path=str(p.relative_to(ROOT)).replace("\\", "/"))
        items.append(card)
    for p in sorted((ROOT / ".claude" / "agents").glob("*.md")):
        fm = front_matter(p)
        card = dict(fm.get("arsenal") or {})
        if not card:
            missing.append(fm.get("name", p.stem) + " (agente)")
        card.setdefault("area", "agentes")
        card.setdefault("titulo", fm.get("name", p.stem))
        card.update(name=fm.get("name", p.stem), description=fm.get("description", ""), kind="agente", own=True,
                    path=str(p.relative_to(ROOT)).replace("\\", "/"))
        items.append(card)
    items.append(PREMIERE)
    return {"areas": extras["areas"], "items": items, "receitas": recipes, "pipeline": PIPELINE,
            "sem_bloco": sorted(missing), "tools": tools_list(), "cli": cli_commands()}


def tools_list():
    out, pt = [], _pt().get("ferramentas", {})
    for p in sorted((ROOT / "tools").iterdir()):
        if p.suffix not in (".py", ".jsx", ".mjs", ".ps1"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        doc = ""
        if p.suffix == ".py":
            try:
                doc = ast.get_docstring(ast.parse(t)) or ""
            except SyntaxError:
                pass
        if not doc:
            m = re.search(r"^\s*(?://|#|/\*+|\*)\s*(\S.*)$", t, re.M)
            doc = m.group(1) if m else ""
        doc = pt.get(p.name) or (doc.strip().splitlines()[0][:160] if doc.strip() else "")
        out.append({"file": p.name, "doc": doc, "pt": p.name in pt})
    return out


def _pt():
    f = CAT / "ferramentas.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


def cli_commands():
    doc = studio.__doc__ or ""
    part = doc.split("CLI (run from motion-studio/):", 1)[-1]
    rows, pt = [], _pt().get("comandos", {})
    for ln in part.splitlines():
        m = re.match(r"\s*python tools/studio.py (.+?)\s{2,}(.+)$", ln)
        if m:
            cmd = m.group(1).strip().replace("<folder>", "<pasta>").replace("<episode>", "<episódio>")
            rows.append({"cmd": cmd, "what": pt.get(cmd.split()[0]) or m.group(2).strip()})
    return rows


# ------------------------------------------------------------------ this PC
STAGES = [  # (pipeline index, label, how we know it was reached)
    (0, "criado", lambda ep: (ep / "episode.json").exists()),
    (2, "decupado", lambda ep: any((ep / "premiere").glob("*decupagem*.xml")) or (ep / "manifest.json").exists()),
    (3, "editado", lambda ep: any((ep / "premiere").glob("*Final*.xml")) or (ep / "study" / "final_words.json").exists()),
    (4, "storyboard", lambda ep: (ep / "motion" / "scenes_spec.json").exists() or (ep / "motion" / "motion_map.json").exists()),
    (5, "After entregue", lambda ep: any((ep / "after").glob("*_01_layout.aep")) or any((ep / "after").glob("*_02_animado.aep"))),
    (6, "estudo final", lambda ep: (ep / "final_study" / "ANALISE.md").exists()),
]

# Files the page can show and open, per pipeline stage. Closed list: the server only opens a path that
# this function returns for that episode.
EP_FILES = [  # (stage index, glob, label)
    (2, "report.md", "relatório da decupagem"),
    (2, "premiere/*decupagem*.xml", "XML da decupagem"),
    (3, "premiere/*Final*.xml", "XML final do editor"),
    (3, "study/final_transcript.md", "transcrição do corte final"),
    (4, "storyboard/index.html", "página de revisão"),
    (4, "motion/motion_map.json", "motion_map"),
    (4, "APOIO/*/CREDITOS.md", "imagens de apoio: créditos"),
    (4, "APOIO/*/*_apoio*.xml", "imagens de apoio: XML com as marcas"),
    (5, "after/*_01_layout.aep", "After: layout"),
    (5, "after/*_02_animado.aep", "After: animado"),
    (6, "final_study/ANALISE.md", "análise do estudo final"),
]


def episode_state(ep):
    """Last pipeline stage whose files exist (read-only: only globs)."""
    done = []
    for idx, label, test in STAGES:
        try:
            if test(ep):
                done.append({"i": idx, "label": label})
        except OSError:
            pass
    return done


def episode_files(ep):
    out = []
    for i, pat, label in EP_FILES:
        try:
            hits = sorted(ep.glob(pat), key=lambda x: x.stat().st_mtime)
        except OSError:
            hits = []
        for h in hits[-2:]:
            if h.is_file():
                out.append({"i": i, "label": label, "rel": h.relative_to(ep).as_posix(), "tipo": h.suffix.lstrip(".").lower()})
    return out


def _episode(ep, name, part=False):
    e = {"name": name, "part": part, "done": episode_state(ep), "files": episode_files(ep),
         "motion_map": (ep / "motion" / "motion_map.json").exists()}
    try:
        raw = studio.episode_json(ep).get("raw")
        if isinstance(raw, str):
            e["raw"] = raw
    except (OSError, ValueError):
        pass
    return e


EP_MARKS = ("episode.json", "manifest.json", "premiere", "motion", "after", "final_study", "APOIO")
VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".m4v", ".avi"}


def _subdirs(d):
    try:
        return sorted(x for x in d.iterdir() if x.is_dir() and not x.name.startswith(("_", ".")))
    except OSError:
        return []


def _looks_episode(d):
    """An episode (or one reel of a batch) has at least one of the files/folders the pipeline writes."""
    return any((d / m).exists() for m in EP_MARKS)


def style_state(slug, d):
    """How far the client's style is: references, digests, own tokens, last feedback date."""
    s = {"refs": 0, "digests": 0, "in_style": 0, "gaps": [], "feedback": None, "style_md": (d / "STYLE.md").exists()}
    for sub in ("refs/canal", "refs/inspiracao"):
        try:
            s["refs"] += sum(1 for x in (d / sub).rglob("*") if x.suffix.lower() in VIDEO)
        except OSError:
            pass
    try:
        idx = json.loads((d / "_digest" / "index.json").read_text(encoding="utf-8"))
        s["digests"] = len(idx)
        s["in_style"] = sum(1 for v in idx.values() if isinstance(v, dict) and v.get("in_style"))
    except (OSError, ValueError):
        pass
    try:
        own = json.loads((d / "client.json").read_text(encoding="utf-8"))
        s["gaps"] = [k for k in ("colors", "fonts", "decup") if k not in own] + (["_template"] if own.get("_template") else [])
    except (OSError, ValueError):
        s["gaps"] = ["client.json"]
    if s["style_md"]:
        try:
            txt = (d / "STYLE.md").read_text(encoding="utf-8", errors="replace")
            dates = re.findall(r"\b(20\d\d-\d\d-\d\d)\b", txt.split("## 7.", 1)[-1])
            s["feedback"] = max(dates) if dates else None
        except OSError:
            pass
    s["ok"] = s["style_md"] and not s["gaps"]
    return s


def pc_state(run_doctor=True):
    clients = []
    for slug in studio.clients():
        d, pdir = studio.client_dir(slug), studio.projects_dir(slug)
        eps = []
        if pdir.exists():
            for ep in _subdirs(pdir):
                parts = [x for x in _subdirs(ep) if _looks_episode(x)]
                if _looks_episode(ep) or parts:
                    e = _episode(ep, ep.name)
                    e["parts"] = [f"{ep.name}/{x.name}" for x in parts]
                    eps.append(e)
                    eps += [_episode(x, f"{ep.name}/{x.name}", part=True) for x in parts]
        name = slug
        try:
            name = studio.client_json(slug).get("name") or slug
        except Exception:  # noqa: BLE001
            pass
        clients.append({"slug": slug, "name": name, "dir": str(d), "projects": str(pdir), "exists": d.exists(),
                        "style": style_state(slug, d), "episodes": eps})
    doc = {"ok": None, "text": ""}
    if run_doctor:
        doc = doctor()
    return {"clients": clients, "doctor": doc, "root": str(ROOT)}


def doctor():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            ok = studio._doctor()
        except Exception as e:  # noqa: BLE001
            print(f"doctor failed: {type(e).__name__}: {e}")
            ok = False
    return {"ok": bool(ok), "text": buf.getvalue()}


# ------------------------------------------------------------------ page
def _font(name):
    p = ROOT / "fonts" / name
    return base64.b64encode(p.read_bytes()).decode() if p.exists() else ""


def build(serve=False, token="", run_doctor=True):
    data = {"cat": catalog(), "pc": pc_state(run_doctor), "serve": serve, "token": token,
            "gerado": dt.datetime.now().strftime("%d/%m/%Y %H:%M")}
    js = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = (Path(__file__).with_name("arsenal_page.html")).read_text(encoding="utf-8")
    return (page.replace("/*FONT_ARCHIVO*/", _font("archivo.woff2"))
                .replace("/*FONT_MONO*/", _font("mono.woff2"))
                .replace("/*DATA*/null", js))


def write(open_it=True):
    OUT.write_text(build(), encoding="utf-8")
    print(f"arsenal: {OUT}")
    if open_it:
        webbrowser.open(OUT.as_uri())


# ------------------------------------------------------------------ server (127.0.0.1 only, closed action list)
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
EPISODE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}$")
EP_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,79}(/[A-Za-z0-9][A-Za-z0-9_.-]{0,79})?$")  # episode or episode/reel


class Refused(Exception):
    pass


def _folder(v, what="pasta"):
    v = (v or "").strip().strip('"')
    if not v or not Path(v).is_absolute():
        raise Refused(f"{what}: use um caminho completo, como D:\\Trabalho\\Clientes\\Nome\\motion")
    return v


def _slug(v):
    v = (v or "").strip()
    if not SLUG.match(v):
        raise Refused("slug: só letras minúsculas, números e hífen (ex.: nome-do-cliente)")
    return v


def _known(slug):
    if slug not in studio.clients():
        raise Refused(f"cliente '{slug}' não está cadastrado neste PC")
    return slug


def _run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        studio.main(argv)
    return "> python tools/studio.py " + " ".join(f'"{a}"' if " " in a else a for a in argv) + "\n" + buf.getvalue()


def act(name, b):
    """The only things the page can do. Writes need confirm=true (the page asks first)."""
    writes = {"add-client", "new-client", "new-episode"}
    if name in writes and b.get("confirm") is not True:
        raise Refused("confirmação ausente")
    if name == "doctor":
        d = doctor()
        return {"ok": d["ok"], "out": "> python tools/studio.py doctor\n" + d["text"]}
    if name == "clients":
        return {"ok": True, "out": _run(["clients"])}
    if name == "state":
        return {"ok": True, "pc": pc_state(run_doctor=False)}
    if name == "add-client":
        slug = _slug(b.get("slug"))
        if slug in studio.config().get("clients", {}):
            raise Refused(f"'{slug}' já está cadastrado; escolha outro slug")
        argv = ["add-client", slug, _folder(b.get("folder"))]
        if (b.get("projects") or "").strip():
            argv += ["--projects", _folder(b.get("projects"), "pasta dos episódios")]
        return {"ok": True, "out": _run(argv)}
    if name == "new-client":
        slug = _slug(b.get("slug"))
        if slug in studio.config().get("clients", {}):
            raise Refused(f"'{slug}' já está cadastrado; escolha outro slug")
        argv = ["new-client", slug, _folder(b.get("folder"))]
        if (b.get("name") or "").strip():
            argv += ["--name", b["name"].strip()[:80]]
        return {"ok": True, "out": _run(argv)}
    if name == "new-episode":
        slug = _known(_slug(b.get("slug")))
        ep = (b.get("episode") or "").strip()
        if not EPISODE.match(ep):
            raise Refused("episódio: letras, números, hífen, ponto ou _ (ex.: ep07-nome)")
        if studio.episode_dir(slug, ep).exists():
            raise Refused(f"o episódio '{ep}' já existe em {studio.episode_dir(slug, ep)}")
        return {"ok": True, "out": _run(["new-episode", slug, ep])}
    if name == "open-folder":
        slug = _known(_slug(b.get("slug")))
        ep = (b.get("episode") or "").strip()
        p = studio.episode_dir(slug, ep) if ep else studio.client_dir(slug)
        if ep and (not EP_PATH.match(ep) or not p.is_dir()
                   or studio.projects_dir(slug).resolve() not in p.resolve().parents):
            raise Refused("episódio não encontrado")
        if not p.is_dir():
            raise Refused(f"a pasta não existe: {p}")
        os.startfile(str(p))  # noqa: S606 (registered folder only)
        return {"ok": True, "out": f"pasta aberta: {p}"}
    if name == "open-file":
        slug = _known(_slug(b.get("slug")))
        ep = (b.get("episode") or "").strip()
        if not EP_PATH.match(ep):
            raise Refused("episódio não encontrado")
        d = studio.episode_dir(slug, ep)
        if not d.is_dir() or studio.projects_dir(slug).resolve() not in d.resolve().parents:
            raise Refused("episódio não encontrado")
        rel = b.get("rel") or ""
        if rel not in {f["rel"] for f in episode_files(d)}:
            raise Refused("esse arquivo não está na lista do episódio")
        f = d / rel
        if f.suffix.lower() in (".aep", ".xml", ".prproj"):  # delivered/imported files: show, never launch
            subprocess.run(["explorer", "/select,", str(f)], check=False)
            return {"ok": True, "out": f"mostrado na pasta: {f}"}
        os.startfile(str(f))  # noqa: S606 (closed list above)
        return {"ok": True, "out": f"aberto: {f}"}
    raise Refused(f"ação desconhecida: {name}")


def serve(port=8766, open_it=True):
    token = secrets.token_urlsafe(24)
    origin = f"http://127.0.0.1:{port}"

    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            raw = body.encode("utf-8") if isinstance(body, str) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(raw)

        def _host_ok(self):
            return self.headers.get("Host") in (f"127.0.0.1:{port}", f"localhost:{port}")

        def do_GET(self):  # noqa: N802
            if not self._host_ok():
                return self._send(403, "{}")
            if self.path.split("?")[0] in ("/", "/index.html"):
                return self._send(200, build(serve=True, token=token, run_doctor=False), "text/html; charset=utf-8")
            self._send(404, "{}")

        def do_POST(self):  # noqa: N802
            if (not self._host_ok() or self.headers.get("X-Arsenal-Token") != token
                    or self.headers.get("Origin") not in (None, origin, f"http://localhost:{port}")
                    or not (self.headers.get("Content-Type") or "").startswith("application/json")
                    or not self.path.startswith("/api/")):
                return self._send(403, json.dumps({"ok": False, "out": "recusado"}))
            try:
                n = min(int(self.headers.get("Content-Length") or 0), 20000)
                b = json.loads(self.rfile.read(n) or b"{}")
                res = act(self.path[5:], b if isinstance(b, dict) else {})
            except Refused as e:
                res = {"ok": False, "out": f"recusado: {e}"}
            except SystemExit as e:
                res = {"ok": e.code in (0, None), "out": "comando terminou"}
            except Exception as e:  # noqa: BLE001
                res = {"ok": False, "out": f"erro: {type(e).__name__}: {e}"}
            self._send(200, json.dumps(res, ensure_ascii=False))

        def log_message(self, fmt, *a):
            sys.stderr.write("arsenal: " + fmt % a + "\n")

    try:
        class Srv(ThreadingHTTPServer):
            allow_reuse_address = os.name != "nt"  # on Windows reuse lets a second panel bind the same port

        srv = Srv(("127.0.0.1", port), H)
    except OSError:
        print(f"arsenal: a porta {port} já está em uso (o painel já está aberto?) — abrindo {origin}")
        if open_it:
            webbrowser.open(origin)
        return
    print(f"arsenal: {origin}  (só neste PC; Ctrl+C para parar)")
    if open_it:
        webbrowser.open(origin)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main(a):
    port = int(a[a.index("--port") + 1]) if "--port" in a else 8766
    if "--serve" in a:
        serve(port, open_it="--no-open" not in a)
    else:
        write(open_it="--no-open" not in a)


if __name__ == "__main__":
    main(sys.argv[1:])
