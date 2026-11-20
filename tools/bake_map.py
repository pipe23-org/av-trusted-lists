r"""Bake Natural Earth country outlines into SVG path strings for a map of Europe.

Run once; the output file is committed and the nightly build reads it as data.

    python tools/bake_map.py ne_50m_admin_0_countries.geojson \\
        src/av_trusted_lists/data/basemap.json

The input is the 1:50m "Admin 0 - Countries" GeoJSON from Natural Earth
(https://www.naturalearthdata.com/, public domain).

Projection: Lambert azimuthal equal-area on a sphere, centred 52N 10E (the
centre ETRS89-LAEA uses). Output width is 1000 units.
"""

import json
import math
import sys

LAT0 = math.radians(52.0)
LON0 = math.radians(10.0)
WIDTH = 1000.0

EU27 = set(
    "AT BE BG HR CY CZ DK EE FI FR DE GR HU IE IT LV LT LU MT NL PL PT RO SK SI ES SE".split()
)
# The frame is fitted to these. Iceland and Norway are in it so a listing there can be shown.
FRAME = EU27 | {"IS", "NO"}


def project(lon: float, lat: float) -> tuple[float, float]:
    """Project a longitude and latitude in degrees; y grows southward."""
    lam = math.radians(lon) - LON0
    phi = math.radians(lat)
    denom = 1 + math.sin(LAT0) * math.sin(phi) + math.cos(LAT0) * math.cos(phi) * math.cos(lam)
    k = math.sqrt(2 / max(denom, 1e-9))
    x = k * math.cos(phi) * math.sin(lam)
    y = k * (math.cos(LAT0) * math.sin(phi) - math.sin(LAT0) * math.cos(phi) * math.cos(lam))
    return x, -y


def rings(geometry: dict) -> list[list[list[float]]]:
    """Return the outer ring of every polygon; holes are dropped."""
    if geometry["type"] == "Polygon":
        return [geometry["coordinates"][0]]
    return [polygon[0] for polygon in geometry["coordinates"]]


def in_europe(ring: list[list[float]]) -> bool:
    """Keep a ring whose centre is in the European window (drops overseas territories)."""
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    return -25 <= lon <= 45 and 33 <= lat <= 72


def near(ring: list[list[float]]) -> bool:
    """Report whether any point of a ring is near enough to Europe to reach the frame."""
    return any(-60 <= p[0] <= 90 and 15 <= p[1] <= 88 for p in ring)


def clip(ring: list[tuple[float, float]], box: tuple[float, float, float, float]):
    """Sutherland-Hodgman clip of a ring to an axis-aligned box."""
    x0, y0, x1, y1 = box
    edges = [
        (
            lambda p: p[0] >= x0,
            lambda a, b: (x0, a[1] + (b[1] - a[1]) * (x0 - a[0]) / (b[0] - a[0])),
        ),
        (
            lambda p: p[0] <= x1,
            lambda a, b: (x1, a[1] + (b[1] - a[1]) * (x1 - a[0]) / (b[0] - a[0])),
        ),
        (
            lambda p: p[1] >= y0,
            lambda a, b: (a[0] + (b[0] - a[0]) * (y0 - a[1]) / (b[1] - a[1]), y0),
        ),
        (
            lambda p: p[1] <= y1,
            lambda a, b: (a[0] + (b[0] - a[0]) * (y1 - a[1]) / (b[1] - a[1]), y1),
        ),
    ]
    out = ring
    for inside, cross in edges:
        if not out:
            return []
        src, out = out, []
        prev = src[-1]
        for cur in src:
            if inside(cur):
                if not inside(prev):
                    out.append(cross(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cross(prev, cur))
            prev = cur
    return out


def simplify(points: list[tuple[float, float]], tol: float) -> list[tuple[float, float]]:
    """Douglas-Peucker."""
    if len(points) < 3:
        return points
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        a, b = stack.pop()
        ax, ay = points[a]
        bx, by = points[b]
        dx, dy = bx - ax, by - ay
        norm = math.hypot(dx, dy) or 1e-12
        worst, index = 0.0, -1
        for i in range(a + 1, b):
            px, py = points[i]
            d = (
                abs(dy * (px - ax) - dx * (py - ay)) / norm
                if norm > 1e-9
                else math.hypot(px - ax, py - ay)
            )
            if d > worst:
                worst, index = d, i
        if worst > tol and index > 0:
            keep[index] = True
            stack += [(a, index), (index, b)]
    return [p for p, k in zip(points, keep, strict=True) if k]


def area(points: list[tuple[float, float]]) -> float:
    """Return the area of a ring."""
    return (
        abs(
            sum(
                a[0] * b[1] - b[0] * a[1]
                for a, b in zip(points, points[1:] + points[:1], strict=True)
            )
        )
        / 2
    )


def main(source: str, target: str) -> None:
    """Read the Natural Earth GeoJSON at ``source`` and write the base map to ``target``."""
    features = json.load(open(source, encoding="utf-8"))["features"]
    projected: dict[str, dict] = {}
    for feature in features:
        props = feature["properties"]
        code = props["ISO_A2_EH"] if props["ISO_A2_EH"] != "-99" else props["ADM0_A3"]
        kept = []
        for ring in rings(feature["geometry"]):
            if code in FRAME and not in_europe(ring):
                continue
            if not near(ring):
                continue
            kept.append([project(lon, lat) for lon, lat in ring])
        if kept:
            projected[code] = {"name": props["NAME_EN"], "rings": kept}

    xs = [p[0] for c in FRAME for r in projected[c]["rings"] for p in r]
    ys = [p[1] for c in FRAME for r in projected[c]["rings"] for p in r]
    pad = 0.012
    x0, x1, y0, y1 = min(xs) - pad, max(xs) + pad, min(ys) - pad, max(ys) + pad
    scale = WIDTH / (x1 - x0)
    height = (y1 - y0) * scale
    box = (-20.0, -20.0, WIDTH + 20.0, height + 20.0)

    countries = {}
    for code, entry in sorted(projected.items()):
        member = code in FRAME
        parts = []
        for ring in entry["rings"]:
            pts = [((x - x0) * scale, (y - y0) * scale) for x, y in ring]
            pts = clip(pts, box)
            if len(pts) < 3:
                continue
            pts = simplify(pts + pts[:1], 0.3 if member else 0.6)[:-1]
            if len(pts) < 3 or area(pts) < (0.4 if member else 2.0):
                continue
            parts.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        if parts:
            countries[code] = {"name": entry["name"], "d": "".join(parts)}

    json.dump(
        {"width": WIDTH, "height": round(height, 1), "eu27": sorted(EU27), "countries": countries},
        open(target, "w", encoding="utf-8"),
        ensure_ascii=False,
        separators=(",", ":"),
    )
    print(f"{len(countries)} countries, {WIDTH:.0f} x {height:.0f}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
