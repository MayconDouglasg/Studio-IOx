"""Self-check of the repository (not of an episode): run before a commit / pull request, and in CI.

  python tools/selfcheck.py            all checks; exit 1 on any failure

1. every Python tool compiles, every .mjs passes `node --check`;
2. every JSON file of the repository parses;
3. every own skill (.claude/skills/*/SKILL.md tracked in git) has name, description and a complete `arsenal:` block,
   and the tools its block names exist in tools/;
4. nothing a client owns is tracked: no file under clients/ but the template, no projects/, no media or .aep,
   no studio.config.json; and, when this PC has a studio.config.json, no registered client slug or folder name
   appears in a tracked file (CLAUDE.md: the repository holds only general rules).
No third-party service, no GPU, no After Effects needed: it runs on any machine with Python 3.10+ (and node for 1b).
"""
import json
import py_compile
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from arsenal import front_matter  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
ARSENAL_KEYS = ("etapa", "area", "titulo", "resumo", "entradas", "saidas", "ferramentas", "modelo", "pedidos")
MEDIA = re.compile(r"\.(aep|aepx|prproj|mp4|mov|wav|mp3|m4a|mxf|braw|r3d)$", re.I)
fails = []


def bad(what):
    fails.append(what)
    print(f"  [!!] {what}")


def tracked():
    out = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    return [p for p in out.stdout.split("\0") if p]


def main():
    files = tracked()
    print(f"motion-studio self-check: {len(files)} tracked files")

    for p in [f for f in files if f.endswith(".py")]:
        try:
            py_compile.compile(str(ROOT / p), doraise=True, cfile=str(ROOT / ".selfcheck.pyc"))
        except py_compile.PyCompileError as e:
            bad(f"python: {p}: {e.msg.strip().splitlines()[-1]}")
    (ROOT / ".selfcheck.pyc").unlink(missing_ok=True)
    if shutil.which("node"):
        for p in [f for f in files if f.endswith(".mjs")]:
            r = subprocess.run(["node", "--check", str(ROOT / p)], capture_output=True, text=True)
            if r.returncode:
                bad(f"node: {p}: {(r.stderr.strip().splitlines() or ['syntax error'])[-1]}")
    else:
        print("  [--] node not found: .mjs files not checked")

    for p in [f for f in files if f.endswith(".json")]:
        try:
            json.loads((ROOT / p).read_text(encoding="utf-8"))
        except ValueError as e:
            bad(f"json: {p}: {e}")

    tools = {Path(f).name for f in files if f.startswith("tools/")}
    skills = sorted({f.split("/")[2] for f in files if re.match(r"\.claude/skills/[^/]+/SKILL\.md$", f)})
    for name in skills:
        fm = front_matter(ROOT / ".claude" / "skills" / name / "SKILL.md")
        if fm.get("name") != name:
            bad(f"skill {name}: front matter name is {fm.get('name')!r}")
        if len(str(fm.get("description", ""))) < 40:
            bad(f"skill {name}: description missing or too short (it is what makes Claude pick the skill)")
        ars = fm.get("arsenal") or {}
        missing = [k for k in ARSENAL_KEYS if k not in ars and not (k == "etapa" and ("ao_lado" in ars or
                                                                                      ars.get("area") != "pipeline"))]
        if missing:
            bad(f"skill {name}: arsenal block lacks {', '.join(missing)} (format in tools/arsenal.py)")
        for t in ars.get("ferramentas") or []:
            if isinstance(t, str) and re.search(r"\.(py|mjs|jsx|ps1)$", t) and t not in tools:
                bad(f"skill {name}: arsenal names tool {t}, not in tools/")
    print(f"  [OK] {len(skills)} own skills read")

    for p in files:
        if (p.startswith("clients/") and not p.startswith("clients/_template/")) or p.startswith("projects/") \
                or MEDIA.search(p) or p in ("studio.config.json", "apoio_downloads.json") or p.startswith(".agents/"):
            bad(f"client data / media / third-party copy tracked: {p}")

    cfg = ROOT / "studio.config.json"
    if cfg.exists():
        clients = json.loads(cfg.read_text(encoding="utf-8")).get("clients") or {}
        words = set()
        for slug, v in clients.items():
            words.add(slug)
            for d in ([v] if isinstance(v, str) else [v.get("dir"), v.get("projects")]):
                if d:
                    words.update(x for x in Path(d).parts if len(x) > 3 and not re.match(r"^[A-Za-z]:", x))
        generic = {"motion", "projects", "projetos", "clientes", "client", "clients", "trabalho", "users", "arquivos edit"}
        words = sorted(w for w in words if w.lower() not in generic)
        if words:
            r = subprocess.run(["git", "grep", "-n", "-I", "-i", "-F"] + sum([["-e", w] for w in words], []) + ["--", "."],
                               cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
            for ln in r.stdout.splitlines()[:20]:
                bad(f"client name in a tracked file: {ln[:160]}")
            print(f"  [OK] searched {len(words)} client names of this PC")

    print("all good" if not fails else f"{len(fails)} problem(s)")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
