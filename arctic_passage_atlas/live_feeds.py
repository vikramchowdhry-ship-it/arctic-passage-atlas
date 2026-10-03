"""Snapshots of third-party live feeds shown on the site's "Live conditions" page.

Two kinds of feed are used, chosen by what each provider allows:

* Fetched by the visitor's browser at page load: Environment Canada's real-time station observations
  and NASA GIBS imagery tiles. Both send open cross-origin headers (see docs/METHODOLOGY.md).
* Fetched here, on a schedule, and written to ``site/data/live/``: NSIDC's daily Arctic sea-ice extent
  file, which does not allow cross-origin reads. The site also carries a station snapshot as a fallback.

Nothing here is a project result. Every output records its source URL and retrieval time.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.parse
import urllib.request
from datetime import UTC, date, datetime
from pathlib import Path
from statistics import mean
from typing import Any

from .config import ProjectConfig
from .files import write_json

NSIDC_URL = "https://noaadata.apps.nsidc.org/NOAA/G02135/north/daily/data/N_seaice_extent_daily_v4.0.csv"
NSIDC_PAGE = "https://nsidc.org/data/g02135"
SWOB_URL = "https://api.weather.gc.ca/collections/swob-realtime/items"
STATION_NAME = "CAMBRIDGE BAY GSN"
BASELINE = (1981, 2010)
USER_AGENT = "arctic-passage-atlas/0.1 (open-source portfolio project)"


def _valid_slot(month: int, day: int) -> bool:
    try:
        date(2000, month, day)
    except ValueError:
        return False
    return True


# One calendar for every series: the 366 (month, day) slots of a leap year, so lines line up on a chart.
SLOTS = [(m, d) for m in range(1, 13) for d in range(1, 32) if _valid_slot(m, d)]


def _get(url: str, timeout: int = 60) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


def parse_nsidc_extent(text: str) -> dict[date, float]:
    """Parse NSIDC's daily extent CSV into {date: extent in million square km}.

    The file has two header rows (names, then units). Rows with a missing or non-positive extent are
    dropped rather than guessed."""
    rows: dict[date, float] = {}
    for record in csv.reader(io.StringIO(text)):
        if len(record) < 4:
            continue
        try:
            year, month, day = (int(value) for value in record[:3])
            extent = float(record[3])
        except ValueError:
            continue  # header rows
        if extent > 0:
            rows[date(year, month, day)] = extent
    return rows


def _day_of_year_key(d: date) -> tuple[int, int]:
    return d.month, d.day


def summarise_extent(rows: dict[date, float], today: date | None = None) -> dict[str, Any]:
    """Latest value, how it compares with the same calendar day in other years, and series for a chart."""
    if not rows:
        raise ValueError("No sea-ice extent rows to summarise.")
    latest = max(rows)
    year = latest.year
    key = _day_of_year_key(latest)
    same_day = {d.year: v for d, v in rows.items() if _day_of_year_key(d) == key and d.year != year}
    base_years = [v for y, v in same_day.items() if BASELINE[0] <= y <= BASELINE[1]]
    lower = sum(1 for v in same_day.values() if v < rows[latest])
    ranked = sorted(same_day.items(), key=lambda item: item[1])

    def series(selected_year: int) -> list[float | None]:
        out: list[float | None] = []
        for month, dom in SLOTS:
            try:
                out.append(rows.get(date(selected_year, month, dom)))
            except ValueError:  # 29 February in a non-leap year
                out.append(None)
        return out

    baseline: list[float | None] = []
    for month, dom in SLOTS:
        values = []
        for y in range(BASELINE[0], BASELINE[1] + 1):
            try:
                value = rows.get(date(y, month, dom))
            except ValueError:
                continue
            if value is not None:
                values.append(value)
        baseline.append(round(mean(values), 3) if values else None)
    return {
        "latest_date": latest.isoformat(),
        "latest_extent_million_km2": rows[latest],
        "same_day_years_compared": len(same_day),
        "years_with_lower_extent": lower,
        "rank_from_lowest": lower + 1,
        "baseline_period": f"{BASELINE[0]}-{BASELINE[1]}",
        "baseline_mean_same_day": round(mean(base_years), 3) if base_years else None,
        "lowest_on_record_same_day": {"year": ranked[0][0], "extent": ranked[0][1]} if ranked else None,
        "series": {
            "axis": "366 slots, 1 January to 31 December (29 February kept as its own slot)",
            "this_year": {"year": year, "values": series(year)},
            "previous_year": {"year": year - 1, "values": series(year - 1)},
            "record_low_year": {"year": ranked[0][0], "values": series(ranked[0][0])} if ranked else None,
            "baseline_mean": baseline,
        },
        "snapshot_for": (today or datetime.now(UTC).date()).isoformat(),
    }


def _swob_value(properties: dict[str, Any], key: str) -> dict[str, Any] | None:
    if key not in properties or properties[key] is None:
        return None
    return {"value": properties[key], "unit": properties.get(f"{key}-uom")}


def parse_station(feature: dict[str, Any]) -> dict[str, Any]:
    """Pick the few observations the page shows. Missing values stay missing."""
    p = feature["properties"]
    return {
        "station": p.get("stn_nam-value"),
        "observed_at": p.get("date_tm-value"),
        "air_temperature": _swob_value(p, "air_temp"),
        "relative_humidity": _swob_value(p, "rel_hum"),
        "station_pressure": _swob_value(p, "stn_pres"),
        "wind_speed_10m_10min": _swob_value(p, "avg_wnd_spd_10m_pst10mts"),
        "wind_direction_10m_10min": _swob_value(p, "avg_wnd_dir_10m_pst10mts"),
    }


def fetch_station() -> dict[str, Any]:
    query = urllib.parse.urlencode({
        "f": "json", "limit": 1, "stn_nam-value": STATION_NAME, "sortby": "-date_tm-value",
    })
    data = json.loads(_get(f"{SWOB_URL}?{query}"))
    if not data.get("features"):
        raise RuntimeError(f"No observations returned for {STATION_NAME}.")
    return parse_station(data["features"][0])


def refresh_live_feeds(config: ProjectConfig) -> list[Path]:
    """Download the scheduled feeds and write them under site/data/live/. Returns the files written."""
    target = config.root / "site" / "data" / "live"
    retrieved = datetime.now(UTC).replace(microsecond=0).isoformat()
    outputs: list[Path] = []

    rows = parse_nsidc_extent(_get(NSIDC_URL).decode("utf-8", errors="replace"))
    summary = summarise_extent(rows)
    extent_path = target / "nsidc_extent.json"
    write_json(extent_path, {
        "source": "NSIDC Sea Ice Index, daily Northern Hemisphere extent (G02135)",
        "source_url": NSIDC_URL,
        "dataset_page": NSIDC_PAGE,
        "retrieved_at": retrieved,
        "note": "Pan-Arctic extent. It is context for the study area, not a measurement of it.",
        **summary,
    })
    outputs.append(extent_path)

    station_path = target / "station_snapshot.json"
    write_json(station_path, {
        "source": "Environment and Climate Change Canada, MSC GeoMet real-time observations (SWOB)",
        "source_url": SWOB_URL,
        "retrieved_at": retrieved,
        **fetch_station(),
    })
    outputs.append(station_path)
    return outputs
