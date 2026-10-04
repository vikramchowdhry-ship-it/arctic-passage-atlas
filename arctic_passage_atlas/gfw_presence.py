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
from datetime import date, datetime, timedelta, timezone
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
}

CLASS_OF = {
    "CARGO": "cargo", "CARRIER": "cargo", "BUNKER": "tanker", "PASSENGER": "passenger", "FISHING": "fishing", "GEAR": "fishing",
}
FORBIDDEN_KEYS = {"mmsi", "imo", "shipname", "callsign", "vesselid", "flag", "name"}


def vessel_class(vessel_type: str | None) -> str:
    return CLASS_OF.get((vessel_type or "").upper(), "other")


def bin_cell(lat: float, lon: float) -> tuple[float, float]:
    """Centre of the 0.2 degree cell that contains the point."""
    return (math.floor(lat / CELL) * CELL + CELL / 2, math.floor(lon / CELL) * CELL + CELL / 2)


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
    """Drop every identifier. Each cell becomes [lat, lon, vessels, hours, {class: count}]."""
    out = []
    for (lat, lon), c in cells.items():
        counts = Counter(c["ids"].values())
        out.append([round(lat, 2), round(lon, 2), len(c["ids"]), round(c["hours"], 1), dict(counts)])
    out.sort(key=lambda x: (-x[0], x[1]))
    return out


def _fetch(token: str, polygon: list[list[float]], start: date, end: date) -> list[dict[str, Any]]:
    url = (f"{API}?temporal-resolution=ENTIRE&spatial-resolution=LOW&datasets[0]={DATASET}"
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
    return next(iter(entries[0].values())) if entries else []


def build_presence(config: ProjectConfig, days: int = DEFAULT_DAYS, today: date | None = None) -> list[Path]:
    token = os.environ.get("GFW_API_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GFW_API_ACCESS_TOKEN is not set. Create a token at https://globalfishingwatch.org/our-apis/tokens")
    end = (today or datetime.now(timezone.utc).date()) - timedelta(days=LATENCY_DAYS)
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
        "cell_degrees": CELL, "columns": ["lat", "lon", "vessels", "hours", "classes"],
        "records_by_area": per_chunk, "cells": len(data),
        "license": "CC BY-NC 4.0, non-commercial, attribution to Global Fishing Watch required",
        "caveat": ("Anonymous aggregate of AIS reports, delayed by a few days. No vessel names, identifiers or flags are kept. "
                   "AIS is self-reported and incomplete: a vessel with no AIS, or out of satellite reach, is not shown. "
                   "Presence is not fishing, intent or wrongdoing."),
        "data": data,
    })
    return [path]
