"""Build the land/water grid that the Route page searches in the browser.

Land comes from Natural Earth's 1:10,000,000 land polygons (public domain). The grid is plain
longitude/latitude cells covering the Canadian Arctic, stored as a 1-bit-per-cell PNG with a small JSON
description next to it. Only polygon exterior rings are drawn, so lakes count as land and a route can
never be planned across one.

The coastline is generalised for a small scale map. Narrow straits can be closed or opened by that
generalisation, so the resulting paths are shortest-water estimates and not navigation data.
"""

from __future__ import annotations

import hashlib
import json
import urllib.request
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .config import ProjectConfig
from .files import utc_now, write_json

NATURAL_EARTH_URL = (
    "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_land.geojson"
)
BBOX = (-142.0, 60.0, -60.0, 78.5)  # west, south, east, north
DLON = 0.05
DLAT = 0.02


WORLD_BBOX = (-180.0, -78.0, 180.0, 84.0)
WORLD_D = 0.1
# Canals and straits too narrow for a 0.1 degree cell. Each is drawn as water, about 0.4 degrees wide,
# with both ends reaching into open sea. Coordinates are (lon, lat).
WATERWAYS: dict[str, list[tuple[float, float]]] = {
    "Suez Canal": [(32.30, 31.50), (32.33, 31.20), (32.38, 30.60), (32.57, 30.00), (32.62, 29.75)],
    "Gulf of Suez": [(32.62, 29.85), (32.66, 29.5), (32.85, 29.0), (33.15, 28.45), (33.55, 28.0), (34.0, 27.6)],
    "Bab-el-Mandeb": [(43.05, 13.1), (43.2, 12.8), (43.35, 12.55), (43.6, 12.4), (44.0, 12.3)],
    "Panama Canal": [(-79.93, 9.50), (-79.90, 9.30), (-79.78, 9.17), (-79.65, 9.05), (-79.56, 8.95), (-79.50, 8.70)],
    "Strait of Gibraltar": [(-5.60, 36.15), (-5.35, 35.95), (-5.10, 36.00), (-4.80, 36.00)],
    "Singapore Strait": [(103.55, 1.20), (103.85, 1.20), (104.20, 1.25)],
    "Bosphorus and Dardanelles": [
        (26.15, 40.00), (26.40, 40.20), (26.70, 40.40), (27.30, 40.40), (28.00, 40.90), (28.98, 41.00),
        (29.05, 41.25), (29.15, 41.35),
    ],
}


# Boxes the browser can close to plan "without this canal" alternatives: (west, south, east, north).
CLOSABLE_BOXES = {"suez": [32.2, 30.0, 32.75, 31.35], "panama": [-80.0, 8.88, -79.52, 9.38]}


def grid_shape(bbox: tuple[float, float, float, float] = BBOX, dlon: float = DLON, dlat: float = DLAT) -> tuple[int, int]:
    west, south, east, north = bbox
    return round((north - south) / dlat), round((east - west) / dlon)  # rows, columns


def _rings(geometry: dict[str, Any]) -> list[list[list[float]]]:
    """Exterior rings only."""
    kind, coords = geometry["type"], geometry["coordinates"]
    if kind == "Polygon":
        return [coords[0]]
    if kind == "MultiPolygon":
        return [polygon[0] for polygon in coords]
    return []


def rasterize_land(
    geojson: dict[str, Any],
    bbox: tuple[float, float, float, float] = BBOX,
    dlon: float = DLON,
    dlat: float = DLAT,
) -> np.ndarray:
    """Return a boolean array, True where there is land. Row 0 is the northern edge."""
    west, south, east, north = bbox
    rows, cols = grid_shape(bbox, dlon, dlat)
    image = Image.new("1", (cols, rows), 0)
    draw = ImageDraw.Draw(image)
    for feature in geojson.get("features", []):
        for ring in _rings(feature["geometry"]):
            lons = [p[0] for p in ring]
            lats = [p[1] for p in ring]
            if max(lons) < west or min(lons) > east or max(lats) < south or min(lats) > north:
                continue  # cannot touch the grid
            pixels = [((lon - west) / dlon, (north - lat) / dlat) for lon, lat in ring]
            draw.polygon(pixels, fill=1)
    return np.array(image, dtype=bool)


def build_route_grid(config: ProjectConfig, geojson_path: Path | None = None) -> list[Path]:
    target = config.root / "site" / "data" / "route"
    if geojson_path is None:
        request = urllib.request.Request(NATURAL_EARTH_URL, headers={"User-Agent": "arctic-passage-atlas/0.1"})
        with urllib.request.urlopen(request, timeout=120) as response:
            geojson = json.loads(response.read())
    else:
        geojson = json.loads(geojson_path.read_text(encoding="utf-8"))
    land = rasterize_land(geojson)
    water = ~land
    target.mkdir(parents=True, exist_ok=True)
    png = target / "water.png"
    Image.fromarray((water * 255).astype(np.uint8), mode="L").convert("1").save(png, optimize=True)
    rows, cols = water.shape
    meta = target / "water.json"
    write_json(meta, {
        "bbox": list(BBOX), "dlon": DLON, "dlat": DLAT, "rows": rows, "cols": cols,
        "convention": "row 0 is the north edge; white pixels are water",
        "water_fraction": round(float(water.mean()), 4),
        "source": "Natural Earth 1:10m land polygons (public domain)",
        "source_url": NATURAL_EARTH_URL,
        "generated_at": utc_now(),
        "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
        "caveat": "Generalised coastline. Narrow straits may be closed or opened. Not navigation data.",
    })
    return [png, meta]


def carve_waterways(water: np.ndarray, bbox: tuple[float, float, float, float], d: float) -> np.ndarray:
    """Open the canals and narrow straits listed in WATERWAYS on a land/water grid (True = water)."""
    west, _south, _east, north = bbox
    image = Image.fromarray((water * 255).astype(np.uint8), mode="L")
    draw = ImageDraw.Draw(image)
    for points in WATERWAYS.values():
        pixels = [((lon - west) / d, (north - lat) / d) for lon, lat in points]
        draw.line(pixels, fill=255, width=4, joint="curve")
    return np.array(image) > 127


def build_world_grid(config: ProjectConfig, geojson: dict[str, Any] | None = None) -> list[Path]:
    """Worldwide 0.1 degree water grid for the global route calculator (wraps at the antimeridian)."""
    target = config.root / "site" / "data" / "route"
    if geojson is None:
        request = urllib.request.Request(NATURAL_EARTH_URL, headers={"User-Agent": "arctic-passage-atlas/0.1"})
        with urllib.request.urlopen(request, timeout=180) as response:
            geojson = json.loads(response.read())
    land = rasterize_land(geojson, WORLD_BBOX, WORLD_D, WORLD_D)
    water = carve_waterways(~land, WORLD_BBOX, WORLD_D)
    target.mkdir(parents=True, exist_ok=True)
    png = target / "world.png"
    Image.fromarray((water * 255).astype(np.uint8), mode="L").convert("1").save(png, optimize=True)
    rows, cols = water.shape
    meta = target / "world.json"
    write_json(meta, {
        "bbox": list(WORLD_BBOX), "dlon": WORLD_D, "dlat": WORLD_D, "rows": rows, "cols": cols, "wrap": True,
        "convention": "row 0 is the north edge; white pixels are water; columns wrap at 180 degrees",
        "water_fraction": round(float(water.mean()), 4),
        "source": "Natural Earth 1:10m land polygons (public domain), with canals and narrow straits opened by hand",
        "source_url": NATURAL_EARTH_URL,
        "waterways_opened": sorted(WATERWAYS),
        "closable_boxes": CLOSABLE_BOXES,
        "generated_at": utc_now(),
        "png_sha256": hashlib.sha256(png.read_bytes()).hexdigest(),
        "caveat": "Generalised coastline on a coarse grid. Not navigation data: no traffic separation, depth, piracy areas, ice or weather routing.",
    })
    return [png, meta]
