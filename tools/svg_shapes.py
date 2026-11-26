"""SVG -> After Effects shape paths (vertices / inTangents / outTangents, closed), for icons and drawn lines.
Used by build_ae.py for composed scenes ("composto"): an icon is looked up by name in a list of sources
(a folder with <name>.svg, or an .html / .svg file holding <symbol id="i-<name>">), then converted.
  python tools/svg_shapes.py <source> <name>      prints the converted paths (check)
Supports path commands M L H V C S Q T A Z (absolute and relative), circle, ellipse, rect (rx), line,
polyline, polygon, <use href="#id"> inside symbols is not followed. Arcs become cubic Beziers.
Each path carries "paint": "stroke" (outline drawn with a line: fill none) or "fill" (iconmonstr-style
filled outlines), so the builder strokes or fills it."""
import math
import re
import sys
from pathlib import Path

NUM = re.compile(r"[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?")


def _tok(d):
    for m in re.finditer(r"[MmLlHhVvCcSsQqTtAaZz]|" + NUM.pattern, d):
        yield m.group(0)


def _arc(p0, rx, ry, phi, large, sweep, p1):
    """Endpoint arc -> list of cubic segments [(c1, c2, end)]."""
    x1, y1 = p0
    x2, y2 = p1
    if rx == 0 or ry == 0 or (x1 == x2 and y1 == y2):
        return [((x1, y1), (x2, y2), (x2, y2))]
    rx, ry = abs(rx), abs(ry)
    cp, sp = math.cos(math.radians(phi)), math.sin(math.radians(phi))
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = cp * dx + sp * dy, -sp * dx + cp * dy
    lam = xp * xp / (rx * rx) + yp * yp / (ry * ry)
    if lam > 1:
        rx, ry = rx * math.sqrt(lam), ry * math.sqrt(lam)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    den = rx * rx * yp * yp + ry * ry * xp * xp
    co = math.sqrt(max(0.0, num / den)) if den else 0.0
    if large == sweep:
        co = -co
    cxp, cyp = co * rx * yp / ry, -co * ry * xp / rx
    cx, cy = cp * cxp - sp * cyp + (x1 + x2) / 2, sp * cxp + cp * cyp + (y1 + y2) / 2

    def ang(ux, uy, vx, vy):
        a = math.atan2(ux * vy - uy * vx, ux * vx + uy * vy)
        return a
    t1 = ang(1, 0, (xp - cxp) / rx, (yp - cyp) / ry)
    dt = ang((xp - cxp) / rx, (yp - cyp) / ry, (-xp - cxp) / rx, (-yp - cyp) / ry)
    if not sweep and dt > 0:
        dt -= 2 * math.pi
    elif sweep and dt < 0:
        dt += 2 * math.pi
    n = max(1, int(math.ceil(abs(dt) / (math.pi / 2) - 1e-9)))
    d = dt / n
    k = 4 / 3 * math.tan(d / 4)
    out, a = [], t1

    def pt(t):
        x, y = rx * math.cos(t), ry * math.sin(t)
        return (cp * x - sp * y + cx, sp * x + cp * y + cy)

    def dv(t):
        x, y = -rx * math.sin(t), ry * math.cos(t)
        return (cp * x - sp * y, sp * x + cp * y)
    for _ in range(n):
        b = a + d
        pa, pb, da, db = pt(a), pt(b), dv(a), dv(b)
        out.append(((pa[0] + k * da[0], pa[1] + k * da[1]), (pb[0] - k * db[0], pb[1] - k * db[1]), pb))
        a = b
    return out


class _P:
    """One subpath being built: AE wants each vertex with its in / out tangent (relative)."""
    def __init__(self, x, y):
        self.v, self.i, self.o, self.closed = [[x, y]], [[0, 0]], [[0, 0]], False

    def line(self, x, y):
        self.v.append([x, y]); self.i.append([0, 0]); self.o.append([0, 0])

    def cubic(self, c1, c2, e):
        lx, ly = self.v[-1]
        self.o[-1] = [c1[0] - lx, c1[1] - ly]
        self.v.append([e[0], e[1]]); self.i.append([c2[0] - e[0], c2[1] - e[1]]); self.o.append([0, 0])

    def close(self):
        self.closed = True
        if len(self.v) > 1 and abs(self.v[-1][0] - self.v[0][0]) < 1e-6 and abs(self.v[-1][1] - self.v[0][1]) < 1e-6:
            self.i[0] = self.i[-1]
            self.v.pop(); self.i.pop(); self.o.pop()

    def out(self):
        r = lambda a: [[round(p[0], 3), round(p[1], 3)] for p in a]  # noqa: E731
        return {"v": r(self.v), "i": r(self.i), "o": r(self.o), "c": self.closed}


def path_d(d):
    """SVG path data -> list of AE subpaths."""
    toks, subs, cur = list(_tok(d)), [], None
    x = y = sx = sy = 0.0
    lastc = lastq = None
    cmd, k = None, 0

    def num():
        nonlocal k
        v = float(toks[k]); k += 1
        return v
    while k < len(toks):
        if re.match(r"[A-Za-z]", toks[k]):
            cmd = toks[k]; k += 1
            if cmd in "Zz":
                if cur:
                    cur.close(); subs.append(cur.out()); cur = None
                x, y = sx, sy
                lastc = lastq = None
                continue
        rel = cmd.islower()
        C = cmd.upper()
        if C == "M":
            nx, ny = num(), num()
            if rel:
                nx, ny = x + nx, y + ny
            if cur:
                subs.append(cur.out())
            cur = _P(nx, ny); x, y, sx, sy = nx, ny, nx, ny
            cmd = "l" if rel else "L"
            lastc = lastq = None
            continue
        if cur is None:
            cur = _P(x, y); sx, sy = x, y
        if C in "LHV":
            if C == "L":
                nx, ny = num(), num()
                if rel:
                    nx, ny = x + nx, y + ny
            elif C == "H":
                nx, ny = num(), y
                if rel:
                    nx = x + nx
            else:
                nx, ny = x, num()
                if rel:
                    ny = y + ny
            cur.line(nx, ny); x, y = nx, ny
            lastc = lastq = None
        elif C in "CS":
            if C == "C":
                c1 = (num(), num())
                if rel:
                    c1 = (x + c1[0], y + c1[1])
            else:
                c1 = (2 * x - lastc[0], 2 * y - lastc[1]) if lastc else (x, y)
            c2, e = (num(), num()), (num(), num())
            if rel:
                c2, e = (x + c2[0], y + c2[1]), (x + e[0], y + e[1])
            cur.cubic(c1, c2, e); lastc = c2; lastq = None; x, y = e
        elif C in "QT":
            if C == "Q":
                q = (num(), num())
                if rel:
                    q = (x + q[0], y + q[1])
            else:
                q = (2 * x - lastq[0], 2 * y - lastq[1]) if lastq else (x, y)
            e = (num(), num())
            if rel:
                e = (x + e[0], y + e[1])
            c1 = (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y))
            c2 = (e[0] + 2 / 3 * (q[0] - e[0]), e[1] + 2 / 3 * (q[1] - e[1]))
            cur.cubic(c1, c2, e); lastq = q; lastc = None; x, y = e
        elif C == "A":
            rx, ry, phi, la, sw = num(), num(), num(), num(), num()
            e = (num(), num())
            if rel:
                e = (x + e[0], y + e[1])
            for c1, c2, ee in _arc((x, y), rx, ry, phi, int(la), int(sw), e):
                cur.cubic(c1, c2, ee)
            x, y = e
            lastc = lastq = None
        else:
            k += 1
    if cur:
        subs.append(cur.out())
    return [s for s in subs if len(s["v"]) > 1 or s["c"]]


def ellipse(cx, cy, rx, ry):
    k = 0.5523
    return [{"v": [[cx, cy - ry], [cx + rx, cy], [cx, cy + ry], [cx - rx, cy]],
             "i": [[-rx * k, 0], [0, -ry * k], [rx * k, 0], [0, ry * k]],
             "o": [[rx * k, 0], [0, ry * k], [-rx * k, 0], [0, -ry * k]], "c": True}]


def rect(x, y, w, h, r=0):
    if r <= 0:
        return [{"v": [[x, y], [x + w, y], [x + w, y + h], [x, y + h]], "i": [[0, 0]] * 4, "o": [[0, 0]] * 4, "c": True}]
    r = min(r, w / 2, h / 2)
    d = f"M{x + r} {y} H{x + w - r} A{r} {r} 0 0 1 {x + w} {y + r} V{y + h - r} A{r} {r} 0 0 1 {x + w - r} {y + h} H{x + r} A{r} {r} 0 0 1 {x} {y + h - r} V{y + r} A{r} {r} 0 0 1 {x + r} {y} Z"
    return path_d(d)


def _attrs(tag):
    return dict(re.findall(r'([\w:-]+)\s*=\s*"([^"]*)"', tag))


def _paint(a, default):
    st = a.get("style", "")
    fill = a.get("fill") or (re.search(r"fill:\s*([^;]+)", st).group(1) if "fill:" in st else None)
    cls = a.get("class", "")
    if fill == "none" or "ln" in cls.split() or (a.get("stroke") and fill in (None, "none")):
        return "stroke"
    if fill:
        return "fill"
    return default


def elements(svg, default="fill"):
    """Every drawable element of an SVG fragment -> [{"paint", "op", "paths"}]."""
    out = []
    for m in re.finditer(r"<(path|circle|ellipse|rect|line|polyline|polygon)\b([^>]*)/?>", svg):
        kind, a = m.group(1), _attrs(m.group(2))
        f = lambda n, d=0.0: float(a.get(n, d))  # noqa: E731
        if kind == "path":
            P = path_d(a.get("d", ""))
        elif kind == "circle":
            P = ellipse(f("cx"), f("cy"), f("r"), f("r"))
        elif kind == "ellipse":
            P = ellipse(f("cx"), f("cy"), f("rx"), f("ry"))
        elif kind == "rect":
            P = rect(f("x"), f("y"), f("width"), f("height"), f("rx", a.get("ry", 0)))
        elif kind == "line":
            P = path_d(f"M{f('x1')} {f('y1')} L{f('x2')} {f('y2')}")
        else:
            pts = NUM.findall(a.get("points", ""))
            d = "M" + " L".join(f"{pts[i]} {pts[i + 1]}" for i in range(0, len(pts) - 1, 2)) + (" Z" if kind == "polygon" else "")
            P = path_d(d)
        out.append({"paint": _paint(a, default), "op": float(a.get("opacity", 1)), "paths": P,
                    "stroke": a.get("stroke"), "fill": a.get("fill") if a.get("fill") not in (None, "none") else None,
                    "sw": float(a["stroke-width"]) if "stroke-width" in a else None,
                    "fop": float(a["fill-opacity"]) if "fill-opacity" in a else None})
    return out


def icon(name, sources):
    """Look an icon up by name in the sources, first hit wins -> {"vb": [x, y, w, h], "els": [...], "from": src}."""
    for src in sources:
        p = Path(src)
        if p.is_dir():
            f = p / f"{name}.svg"
            if f.exists():
                t = f.read_text(encoding="utf-8")
                vb = re.search(r'viewBox="([^"]+)"', t)
                vb = [float(x) for x in NUM.findall(vb.group(1))] if vb else [0, 0, 24, 24]
                body = re.sub(r"<defs>.*?</defs>", "", t, flags=re.S)
                return {"vb": vb, "els": elements(body, "fill"), "from": str(f)}
        elif p.exists():
            t = p.read_text(encoding="utf-8")
            m = re.search(r'<symbol\s+id="i-' + re.escape(name) + r'"([^>]*)>(.*?)</symbol>', t, flags=re.S)
            if m:
                vb = re.search(r'viewBox="([^"]+)"', m.group(1))
                vb = [float(x) for x in NUM.findall(vb.group(1))] if vb else [0, 0, 100, 100]
                return {"vb": vb, "els": elements(m.group(2), "stroke"), "from": f"{p}#i-{name}"}
    return None


if __name__ == "__main__":
    import json
    r = icon(sys.argv[2], [sys.argv[1]])
    print(json.dumps(r, indent=1)[:3000] if r else "not found")
