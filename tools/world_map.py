"""Make site/assets/data/world.json, the world map on the Analysis page, from world-atlas's
countries-110m.json (Natural Earth 1:110m, public domain; world-atlas by Mike Bostock, ISC licence):

    npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz
    pip install pycountry
    python tools/world_map.py package/countries-110m.json

Each country becomes an SVG path in the Equal Earth projection, keyed by its ISO 3166-1 alpha-2 code
(the codes of config/countries.yaml). Antarctica is left out. Run once; the result is committed."""
from __future__ import annotations

import json
import math
import sys
from pathlib import Path

import pycountry

W = 960
OUT = Path(__file__).resolve().parent.parent / "site" / "assets" / "data" / "world.json"
A1, A2, A3, A4, M = 1.340264, -0.081106, 0.000893, 0.003796, math.sqrt(3) / 2


def equal_earth(lon: float, lat: float) -> tuple[float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    th = math.asin(M * math.sin(phi))
    t2, t6 = th * th, th ** 6
    x = 2 * math.sqrt(3) * lam * math.cos(th) / (3 * (9 * A4 * t6 * t2 + 7 * A3 * t6 + 3 * A2 * t2 + A1))
    y = th * (A4 * t6 * t2 + A3 * t6 + A2 * t2 + A1)
    return x, y


def unwrap(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Make longitudes continuous: a ring that crosses ±180° goes on past it instead of jumping back."""
    out, off = [], 0.0
    for i, (x, y) in enumerate(pts):
        if i:
            d = x + off - out[-1][0]
            if d > 180:
                off -= 360
            elif d < -180:
                off += 360
        out.append((x + off, y))
    return out


def clip(pts: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Cut a ring to -180° ≤ longitude ≤ 180° (Sutherland–Hodgman, one edge at a time)."""
    for edge, inside in ((180, lambda x: x <= 180), (-180, lambda x: x >= -180)):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur[0]) != inside(prev[0]):
                t = (edge - prev[0]) / (cur[0] - prev[0])
                out.append((edge, prev[1] + t * (cur[1] - prev[1])))
            if inside(cur[0]):
                out.append(cur)
        pts = out
        if not pts:
            break
    return pts


def main(src: str) -> None:
    topo = json.loads(Path(src).read_text(encoding="utf-8"))
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    arcs = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    xmax = equal_earth(180, 0)[0]
    ymax = equal_earth(0, 90)[1]
    k = W / (2 * xmax)
    ymin = equal_earth(0, -60)[1]  # cut below 60°S: Antarctica is left out
    H = round((ymax - ymin) * k)

    def ring(idx: list[int]) -> str:
        pts = []
        for i in idx:
            a = arcs[i] if i >= 0 else arcs[~i][::-1]
            pts.extend(a if not pts else a[1:])
        pts = unwrap(pts)
        lo, hi = min(p[0] for p in pts), max(p[0] for p in pts)
        pieces = [pts]
        if hi > 180 or lo < -180:  # crosses the antimeridian (Russia, Fiji): cut into two
            shift = -360 if hi > 180 else 360
            pieces = [clip(pts), clip([(x + shift, y) for x, y in pts])]
        return "".join(draw(p) for p in pieces if len(p) > 2)

    def draw(pts: list[tuple[float, float]]) -> str:
        out, last = [], None
        for x, y in (equal_earth(*p) for p in pts):
            p = (round((x + xmax) * k, 1), round((ymax - y) * k, 1))
            if p != last:
                out.append(p)
                last = p
        return "M" + "L".join(f"{x:g},{y:g}" for x, y in out) + "Z"

    paths = {}
    for g in topo["objects"]["countries"]["geometries"]:
        num = g.get("id")
        c = pycountry.countries.get(numeric=num) if num else None
        if not c or c.alpha_2 == "AQ":
            continue
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        paths[c.alpha_2] = "".join(ring(r) for p in polys for r in p)
    OUT.write_text(json.dumps({"w": W, "h": H, "c": paths}, separators=(",", ":")), encoding="utf-8")
    print(f"{len(paths)} countries, {OUT.stat().st_size // 1024} KB → {OUT}")


if __name__ == "__main__":
    main(sys.argv[1])
