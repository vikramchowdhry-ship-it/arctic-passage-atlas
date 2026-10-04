"""Anonymous 30-day AIS vessel presence for the Arctic, from the Global Fishing Watch 4Wings API.

The API returns one record per vessel and grid cell with names, MMSI, IMO and call signs. None of that is kept.
Records are rebinned to 0.2 degree cells and reduced to: the number of distinct vessels, the hours spent, and a
count per broad class. Identifiers are used only in memory to count distinct vessels, then dropped. The result
is a pattern of shipping, not a list of vessels, and it is delayed by a few days.

Global Fishing Watch data are CC BY-NC 4.0 (non-commercial) and need attribution. The token is read from the
GFW_API_ACCESS_TOKEN environment variable and is never written anywhere.
"""

from __future__ import annotations

import json
import math
import os
import urllib.error
import urllib.request
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .files import utc_now, write_json

API = "https://gateway.api.globalfishingwatch.org/v3/4wings/report"
DATASET = "public-global-presence:latest"
PAGE = "https://globalfishingwatch.org/our-apis/documentation"
CELL = 0.2
LATENCY_DAYS = 3        # the newest days are incomplete
DEFAULT_DAYS = 30

# Chunks keep each response a manageable size. West to east, north of 60 N (Russia north of 66 N).
CHUNKS: dict[str, list[list[float]]] = {
    "Alaska and the Chukchi and Beaufort seas": [[-180, 60], [-141, 60], [-141, 84], [-180, 84], [-180, 60]],
    "Canadian Arctic, Baffin Bay and Hudson Bay": [[-141, 60], [-52, 60], [-52, 84], [-141, 84], [-141, 60]],
    "Greenland and Iceland": [[-52, 60], [-10, 60], [-10, 84], [-52, 84], [-52, 60]],
    "Siberian Arctic coast": [[60, 66], [180, 66], [180, 84], [60, 84], [60, 66]],
    # North America south of 60 N, in windows so each response stays a manageable size.
    "North Pacific coast and Alaska Gulf, 44-60 N": [[-180, 44], [-130, 44], [-130, 60], [-180, 60], [-180, 44]],
    "British Columbia and the prairies, 44-60 N": [[-130, 44], [-110, 44], [-110, 60], [-130, 60], [-130, 44]],
    "Great Lakes and Hudson Bay, 44-60 N": [[-110, 44], [-80, 44], [-80, 60], [-110, 60], [-110, 44]],
    "St. Lawrence, Gulf and Labrador, 44-60 N": [[-80, 44], [-60, 44], [-60, 60], [-80, 60], [-80, 44]],
    "Newfoundland and the Grand Banks, 44-60 N": [[-60, 44], [-45, 44], [-45, 60], [-60, 60], [-60, 44]],
    # Northern and western Europe, in windows for the same reason.
    "Norway, the Barents Sea and Kola, 60-82 N": [[-10, 60], [60, 60], [60, 82], [-10, 82], [-10, 60]],
    "North Sea, 51-60 N": [[-4, 51], [10, 51], [10, 60], [-4, 60], [-4, 51]],
    "British Isles and the Atlantic approaches, 48-60 N": [[-12, 48], [-4, 48], [-4, 60], [-12, 60], [-12, 48]],
    "Baltic Sea and Gulf of Finland, 53-66 N": [[10, 53], [32, 53], [32, 66], [10, 66], [10, 53]],
    "English Channel and Bay of Biscay, 44-51 N": [[-10, 44], [4, 44], [4, 51], [-10, 51], [-10, 44]],
}
CLASS_ORDER = ["cargo", "tanker", "passenger", "fishing", "other"]

CLASS_OF = {
    "CARGO": "cargo", "CARRIER": "cargo", "BUNKER": "tanker", "PASSENGER": "passenger", "FISHING": "fishing", "GEAR": "fishing",
}
FORBIDDEN_KEYS = {"mmsi", "imo", "shipname", "callsign", "vesselid", "flag", "name"}


def vessel_class(vessel_type: str | None) -> str:
    return CLASS_OF.get((vessel_type or "").upper(), "other")


def lon_bins(lat_centre: float) -> int:
    """Number of longitude cells in the 0.2 degree latitude row centred on lat_centre.

    Cells are 0.2 degrees tall and about as wide on the ground, so a row near the pole has far fewer, wider
    cells than one at the equator. The site draws them with the same formula.
    """
    return max(1, round(360 * math.cos(math.radians(lat_centre)) / CELL))


def bin_cell(lat: float, lon: float) -> tuple[float, float]:
    """Centre of the near-equal-area cell that contains the point."""
    row = math.floor(lat / CELL) * CELL + CELL / 2
    n = lon_bins(row)
    width = 360 / n
    index = min(n - 1, math.floor((((lon + 180) % 360)) / width))
    return (row, -180 + (index + 0.5) * width)


def aggregate(rows: list[dict[str, Any]], into: dict | None = None) -> dict:
    """Add API records to the cell table. Returns the table: cell -> {hours, vessels(set), classes(Counter of ids by class)}."""
    cells: dict = into if into is not None else {}
    for r in rows:
        if r.get("lat") is None or r.get("lon") is None:
            continue
        key = bin_cell(float(r["lat"]), float(r["lon"]))
        cell = cells.setdefault(key, {"hours": 0.0, "ids": {}})
        vid = r.get("vesselId") or r.get("mmsi") or id(r)
        cell["hours"] += float(r.get("hours") or 0)
        cell["ids"][vid] = vessel_class(r.get("vesselType"))      # one class per vessel per cell
    return cells


def finish(cells: dict) -> list[list[Any]]:
    """Drop every identifier. Each cell becomes [lat, lon, vessels, hours, [cargo, tanker, passenger, fishing, other]]."""
    out = []
    for (lat, lon), c in cells.items():
        counts = Counter(c["ids"].values())
        out.append([round(lat, 2), round(lon, 2), len(c["ids"]), round(c["hours"]), [counts.get(k, 0) for k in CLASS_ORDER]])
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def _fetch(token: str, polygon: list[list[float]], start: date, end: date, resolution: str = "LOW") -> list[dict[str, Any]]:
    url = (f"{API}?temporal-resolution=ENTIRE&spatial-resolution={resolution}&datasets[0]={DATASET}"
           f"&date-range={start.isoformat()},{end.isoformat()}&format=JSON")
    body = json.dumps({"geojson": {"type": "Polygon", "coordinates": [polygon]}}).encode()
    request = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json", "User-Agent": "arctic-passage-atlas/0.1"})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Global Fishing Watch returned HTTP {error.code}. Check the token and its use.") from error
    entries = payload.get("entries") or []
    return (next(iter(entries[0].values())) if entries else []) or []


def build_presence(config: ProjectConfig, days: int = DEFAULT_DAYS, today: date | None = None) -> list[Path]:
    token = os.environ.get("GFW_API_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GFW_API_ACCESS_TOKEN is not set. Create a token at https://globalfishingwatch.org/our-apis/tokens")
    end = (today or datetime.now(UTC).date()) - timedelta(days=LATENCY_DAYS)
    start = end - timedelta(days=days)
    cells: dict = {}
    per_chunk: dict[str, int] = {}
    for name, polygon in CHUNKS.items():
        rows = _fetch(token, polygon, start, end)
        per_chunk[name] = len(rows)
        aggregate(rows, cells)
        del rows                                              # identifiers leave memory with the raw response
    data = finish(cells)
    target = config.root / "site" / "data" / "live"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "gfw_presence.json"
    write_json(path, {
        "source": "Global Fishing Watch 4Wings API, AIS vessel presence",
        "source_url": API, "dataset": DATASET, "dataset_page": PAGE,
        "date_start": start.isoformat(), "date_end": end.isoformat(), "retrieved_at": utc_now(),
        "cell_degrees": CELL, "cell_shape": "rows 0.2 degrees tall; longitude cells per row = max(1, round(360 * cos(row latitude) / 0.2))", "columns": ["lat", "lon", "vessels", "hours", "classes"], "class_order": CLASS_ORDER,
        "records_by_area": per_chunk, "cells": len(data),
        "license": "CC BY-NC 4.0, non-commercial, attribution to Global Fishing Watch required",
        "caveat": ("Anonymous aggregate of AIS reports, delayed by a few days. No vessel names, identifiers or flags are kept. "
                   "AIS is self-reported and incomplete: a vessel with no AIS, or out of satellite reach, is not shown. "
                   "Presence is not fishing, intent or wrongdoing."),
        "data": data,
    })
    return [path]


RECENT_DAYS = 3


def latest_positions(rows: list[dict[str, Any]], into: dict | None = None) -> dict:
    """Keep each vessel's most recent grid cell. Identifiers are used only as in-memory keys."""
    seen: dict = into if into is not None else {}
    for r in rows:
        if r.get("lat") is None or r.get("lon") is None:
            continue
        key = r.get("vesselId") or r.get("mmsi") or id(r)
        stamp = r.get("exitTimestamp") or r.get("entryTimestamp") or ""
        if key not in seen or stamp > seen[key][0]:
            seen[key] = (stamp, float(r["lat"]), float(r["lon"]), vessel_class(r.get("vesselType")))
    return seen


def finish_recent(seen: dict) -> list[list[Any]]:
    """[lat, lon, class, hour last seen]. No identifier survives."""
    out = [[round(lat, 2), round(lon, 2), cls, stamp[:13]] for stamp, lat, lon, cls in seen.values()]
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def build_recent(config: ProjectConfig, days: int = RECENT_DAYS, today: date | None = None) -> list[Path]:
    """Last-seen position of each vessel over the last few days, one anonymous dot per vessel."""
    token = os.environ.get("GFW_API_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GFW_API_ACCESS_TOKEN is not set. Create a token at https://globalfishingwatch.org/our-apis/tokens")
    end = (today or datetime.now(UTC).date()) - timedelta(days=LATENCY_DAYS - 1)     # the newest day or two are not published yet
    start = end - timedelta(days=days)
    seen: dict = {}
    per_chunk: dict[str, int] = {}
    for name, polygon in CHUNKS.items():
        rows = _fetch(token, polygon, start, end, resolution="HIGH")
        per_chunk[name] = len(rows)
        latest_positions(rows, seen)
        del rows
    data = finish_recent(seen)
    target = config.root / "site" / "data" / "live"
    target.mkdir(parents=True, exist_ok=True)
    path = target / "gfw_recent.json"
    write_json(path, {
        "source": "Global Fishing Watch 4Wings API, AIS vessel presence (high resolution)",
        "source_url": API, "dataset": DATASET, "dataset_page": PAGE,
        "date_start": start.isoformat(), "date_end": end.isoformat(), "retrieved_at": utc_now(),
        "columns": ["lat", "lon", "class", "last_seen_hour_utc"], "vessels": len(data), "records_by_area": per_chunk,
        "license": "CC BY-NC 4.0, non-commercial, attribution to Global Fishing Watch required",
        "caveat": ("Each dot is one vessel's last reported AIS position in the window, one to four days old. No names, identifiers or "
                   "flags are kept. AIS is self-reported and incomplete, and a vessel can have moved since. Not live, not for navigation."),
        "data": data,
    })
    return [path]
