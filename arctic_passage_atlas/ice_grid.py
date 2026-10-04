"""Sea-ice concentration for the route planner.

NSIDC's Sea Ice Index (G02135, version 4) publishes a daily Northern Hemisphere concentration GeoTIFF from
passive microwave sensors: 25 km cells in the NSIDC polar stereographic projection (EPSG:3411), integer
values in tenths of a percent, with codes above 1000 for the pole hole, coast and land.

This module downloads the newest file, fills the non-ocean codes from neighbouring ocean cells, and resamples
it onto the two route grids as 8-bit PNGs (0 to 100 percent). The browser blocks cells above a threshold the
visitor chooses. It is an analysis of one past day, not a forecast, and passive microwave misses thin ice
and underestimates concentration under summer melt. It is not an ice chart and not a navigation product.
"""

from __future__ import annotations

import hashlib
import io
import math
import urllib.error
import urllib.request
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from .config import ProjectConfig
from .files import utc_now, write_json
from .route_grid import BBOX, DLAT, DLON, WORLD_BBOX, WORLD_D

BASE_URL = "https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/geotiff"
PAGE_URL = "https://nsidc.org/data/g02135"

# EPSG:3411: Hughes 1980 ellipsoid, true scale at 70 N, central meridian 45 W, 25 km cells.
A = 6378273.0
E2 = 0.006693883
E = math.sqrt(E2)
LAT_TS = 70.0
LON0 = -45.0
CELL_M = 25000.0
X0, Y0 = -3850000.0, 5850000.0     # top-left corner of the file (from its GeoTIFF tie point)
POLE_HOLE = 2510
MAX_CONCENTRATION = 1000


def file_url(day: date) -> str:
    stamp = day.strftime("%Y%m%d")
    return f"{BASE_URL}/{day:%Y}/{day:%m}_{day:%b}/N_{stamp}_concentration_v4.0.tif"


def project(lon: np.ndarray, lat: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Longitude and latitude in degrees to NSIDC polar stereographic metres."""
    lat_r = np.radians(np.minimum(lat, 89.999999))
    lon_r = np.radians(lon - LON0)

    def t_of(phi: Any) -> Any:
        s = np.sin(phi)
        return np.tan(math.pi / 4 - phi / 2) / ((1 - E * s) / (1 + E * s)) ** (E / 2)

    phi_c = math.radians(LAT_TS)
    m_c = math.cos(phi_c) / math.sqrt(1 - E2 * math.sin(phi_c) ** 2)
    rho = A * m_c * t_of(lat_r) / t_of(phi_c)
    return rho * np.sin(lon_r), -rho * np.cos(lon_r)


def clean(raw: np.ndarray) -> np.ndarray:
    """File values to percent (float32). Pole hole is ice; other codes above 1000 are filled from neighbours."""
    data = raw.astype(np.float32)
    invalid = data > MAX_CONCENTRATION
    pole = raw == POLE_HOLE
    data = np.where(invalid, np.nan, data / 10.0).astype(np.float32)
    data[pole] = 100.0
    for _ in range(6):                      # grow ocean values into coast and land cells
        if not np.isnan(data).any():
            break
        padded = np.pad(data, 1, constant_values=np.nan)
        stack = np.stack([padded[1 + dr: 1 + dr + data.shape[0], 1 + dc: 1 + dc + data.shape[1]]
                          for dr in (-1, 0, 1) for dc in (-1, 0, 1)])
        with np.errstate(all="ignore"):
            mean = np.nanmean(stack, axis=0)
        data = np.where(np.isnan(data), mean, data)
    return np.nan_to_num(data, nan=0.0).astype(np.float32)


def resample(conc: np.ndarray, bbox: tuple[float, float, float, float], dlon: float, dlat: float) -> np.ndarray:
    """Bilinear sample of the concentration onto a longitude/latitude grid. Outside the file the value is 0."""
    west, south, east, north = bbox
    rows, cols = round((north - south) / dlat), round((east - west) / dlon)
    lon = west + (np.arange(cols) + 0.5) * dlon
    lat = north - (np.arange(rows) + 0.5) * dlat
    lon2, lat2 = np.meshgrid(lon, lat)
    x, y = project(lon2, lat2)
    fc, fr = (x - X0) / CELL_M - 0.5, (Y0 - y) / CELL_M - 0.5
    inside = (fc >= 0) & (fr >= 0) & (fc <= conc.shape[1] - 1) & (fr <= conc.shape[0] - 1) & (lat2 > 30)
    c0, r0 = np.clip(np.floor(fc).astype(int), 0, conc.shape[1] - 2), np.clip(np.floor(fr).astype(int), 0, conc.shape[0] - 2)
    wc, wr = np.clip(fc - c0, 0, 1), np.clip(fr - r0, 0, 1)
    top = conc[r0, c0] * (1 - wc) + conc[r0, c0 + 1] * wc
    bottom = conc[r0 + 1, c0] * (1 - wc) + conc[r0 + 1, c0 + 1] * wc
    out = top * (1 - wr) + bottom * wr
    return np.where(inside, out, 0.0)


def _fetch(url: str) -> bytes | None:
    request = urllib.request.Request(url, headers={"User-Agent": "arctic-passage-atlas/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code in (403, 404):      # a day that is not published yet; the next older day is tried
            return None
        raise


def newest_file(today: date | None = None, lookback: int = 10) -> tuple[date, str, bytes]:
    today = today or datetime.now(UTC).date()
    for back in range(lookback):
        day = today - timedelta(days=back)
        url = file_url(day)
        payload = _fetch(url)
        if payload:
            return day, url, payload
    raise RuntimeError(f"No NSIDC concentration file found in the last {lookback} days")


def build_ice_grids(config: ProjectConfig, payload: tuple[date, str, bytes] | None = None) -> list[Path]:
    day, url, blob = payload or newest_file()
    raw = np.array(Image.open(io.BytesIO(blob)))
    conc = clean(raw)
    target = config.root / "site" / "data" / "route"
    target.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    grids = {"arctic": (BBOX, DLON, DLAT), "world": (WORLD_BBOX, WORLD_D, WORLD_D)}
    shapes: dict[str, Any] = {}
    for name, (bbox, dlon, dlat) in grids.items():
        percent = np.clip(np.rint(resample(conc, bbox, dlon, dlat)), 0, 100).astype(np.uint8)
        path = target / f"ice_{name}.png"
        Image.fromarray(percent, mode="L").save(path, optimize=True)
        shapes[name] = {"rows": int(percent.shape[0]), "cols": int(percent.shape[1]), "bbox": list(bbox),
                        "png_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                        "cells_at_or_above_15_percent": int((percent >= 15).sum())}
        written.append(path)
    meta = target / "ice_grid.json"
    write_json(meta, {
        "date": day.isoformat(),
        "source": "NSIDC Sea Ice Index, version 4 (G02135), daily Northern Hemisphere sea-ice concentration",
        "source_url": url,
        "dataset_page": PAGE_URL,
        "retrieved_at": utc_now(),
        "source_sha256": hashlib.sha256(blob).hexdigest(),
        "convention": "8-bit PNG, value is percent ice concentration, row 0 is the north edge",
        "grids": shapes,
        "coverage": "Northern Hemisphere only. Cells south of 30 N and the Southern Ocean are 0 and are not ice-free evidence.",
        "caveat": ("Passive microwave, 25 km cells, analysis of one past day and not a forecast. It misses thin new ice, "
                   "can underestimate concentration during summer melt and is unreliable at the coast. "
                   "Not an ice chart. Use Canadian Ice Service or national ice service charts for navigation."),
    })
    written.append(meta)
    return written
