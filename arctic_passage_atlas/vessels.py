from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .environment import load_dotenv
from .files import feature_collection, utc_now, write_json

GAP_INTERPRETATION = "AIS-derived gap event; cause is not established."
SAR_INTERPRETATION = "Aggregated SAR-detection cell; not proof of AIS disabling."
VESSEL_LIMITATIONS = (
    "AIS event detection depends on satellite and terrestrial reception quality.",
    "A recorded gap does not establish why messages were absent.",
    (
        "GFW's intended AIS-off criterion applies to gaps starting at least 50 nautical miles offshore. "
        "This project does not establish whether an individual nearshore event meets that condition."
    ),
    (
        "GFW limits SAR detections in much of the Arctic where sea ice can produce false positives. "
        "A sparse or empty SAR layer is not evidence of no vessels."
    ),
    "SAR detections can contain false positives and coverage is not spatially uniform.",
)
FIXTURE_REDACTION_KEYS = {
    "callsign",
    "imo",
    "mmsi",
    "name",
    "shipname",
    "ssvid",
    "vessel_id",
}


def _dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return value
    return dict(value)


def redact_fixture(value: Any, key: str | None = None) -> Any:
    """Keep an API response's schema while removing direct vessel identifiers."""
    if key and key.casefold() in FIXTURE_REDACTION_KEYS:
        return "REDACTED"
    if isinstance(value, dict):
        out = {str(item_key): redact_fixture(item_value, str(item_key)) for item_key, item_value in value.items()}
        if key == "vessel" and "id" in out:
            out["id"] = "REDACTED"        # the provider's vessel id identifies a vessel as directly as an MMSI
        return out
    if isinstance(value, list):
        return [redact_fixture(item) for item in value]
    return value


async def capture_gfw_event_fixture(config: ProjectConfig, destination: Path, replace: bool = False) -> Path:
    """Capture one redacted provider response for schema tests; never touch public outputs."""
    if destination.exists() and not replace:
        raise FileExistsError(f"Fixture already exists: {destination}. Pass --replace after reviewing it.")
    load_dotenv(config.root)
    token = os.environ.get("GFW_API_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GFW_API_ACCESS_TOKEN is not set. Copy .env.example to .env and add an API token.")
    try:
        import gfwapiclient as gfw
    except ImportError as exc:
        raise RuntimeError("Install the project first: python -m pip install -e .") from exc

    settings = config.data["vessels"]
    result = await gfw.Client(access_token=token).events.get_all_events(
        datasets=[settings["events_dataset"]],
        types=["GAP"],
        start_date=settings["start_date"],
        end_date=settings["end_date"],
        duration=int(settings["minimum_gap_minutes"]),
        geometry=config.geometry,
        limit=1,
    )
    records = [_dict(item) for item in result.data()]
    if not records:
        raise RuntimeError("The configured query returned no gap events, so no schema fixture was written.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_json(destination, redact_fixture(records[0]))
    return destination


def _coordinate(value: Any) -> list[float] | None:
    if not isinstance(value, dict):
        return None
    lon = value.get("lon", value.get("longitude"))
    lat = value.get("lat", value.get("latitude"))
    if lon is not None and lat is not None:
        return [float(lon), float(lat)]
    coordinates = value.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        return [float(coordinates[0]), float(coordinates[1])]
    return None


def _find_named_coordinate(record: dict[str, Any], names: tuple[str, ...]) -> list[float] | None:
    for name in names:
        result = _coordinate(record.get(name))
        if result:
            return result
    for value in record.values():
        if isinstance(value, dict):
            result = _find_named_coordinate(value, names)
            if result:
                return result
    return None


def _normalise_gap(record: dict[str, Any]) -> dict[str, Any] | None:
    start_coord = _find_named_coordinate(record, ("off_position", "start_position", "startPosition"))
    end_coord = _find_named_coordinate(record, ("on_position", "end_position", "endPosition"))
    position = _coordinate(record.get("position"))
    if start_coord and end_coord:
        geometry = {"type": "LineString", "coordinates": [start_coord, end_coord]}
    elif position or start_coord or end_coord:
        geometry = {"type": "Point", "coordinates": position or start_coord or end_coord}
    else:
        return None

    start = record.get("start")
    end = record.get("end")
    duration_hours = None
    gap = record.get("gap") if isinstance(record.get("gap"), dict) else {}
    for key in ("duration_hours", "durationHours", "duration"):
        if key in gap and gap[key] is not None:
            duration_hours = gap[key]
            break
    vessel = record.get("vessel") if isinstance(record.get("vessel"), dict) else {}
    return {
        "type": "Feature",
        "geometry": geometry,
        "properties": {
            "event_id": record.get("id"),
            "event_type": "AIS gap event",
            "start": start,
            "end": end,
            "duration_hours": duration_hours,
            "vessel_type": vessel.get("type", vessel.get("vessel_type")),
            "demo": False,
            "interpretation": GAP_INTERPRETATION,
        },
    }


async def run_vessels(config: ProjectConfig) -> list[Path]:
    load_dotenv(config.root)
    token = os.environ.get("GFW_API_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("GFW_API_ACCESS_TOKEN is not set. Copy .env.example to .env and add an API token.")
    try:
        import gfwapiclient as gfw
    except ImportError as exc:
        raise RuntimeError("Install the project first: python -m pip install -e .") from exc

    settings = config.data["vessels"]
    client = gfw.Client(access_token=token)
    gap_result = await client.events.get_all_events(
        datasets=[settings["events_dataset"]],
        types=["GAP"],
        start_date=settings["start_date"],
        end_date=settings["end_date"],
        duration=int(settings["minimum_gap_minutes"]),
        geometry=config.geometry,
        limit=int(settings["max_events"]),
    )
    gap_records = [_dict(item) for item in gap_result.data()]
    gap_features = [feature for record in gap_records if (feature := _normalise_gap(record))]

    filters = ["matched='false'"] if settings["sar_unmatched_only"] else None
    sar_result = await client.fourwings.create_sar_presence_report(
        spatial_resolution="HIGH",
        temporal_resolution="MONTHLY",
        start_date=settings["start_date"],
        end_date=settings["end_date"],
        geojson=config.geometry,
        filters=filters,
    )
    sar_records = [_dict(item) for item in sar_result.data()]
    sar_features = []
    for index, record in enumerate(sar_records, 1):
        if record.get("lon") is None or record.get("lat") is None:
            continue
        sar_features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(record["lon"]), float(record["lat"])]},
                "properties": {
                    "cell_id": f"SAR-CELL-{index:05d}",
                    "date": record.get("date"),
                    "detections": record.get("detections"),
                    "matched_filter": "unmatched only" if settings["sar_unmatched_only"] else "all",
                    "demo": False,
                    "interpretation": SAR_INTERPRETATION,
                },
            }
        )

    processed = config.root / "data" / "processed"
    gaps_path = processed / "vessel_events.geojson"
    sar_path = processed / "sar_detections.geojson"
    summary_path = processed / "vessel_summary.json"
    possibly_truncated = len(gap_records) >= int(settings["max_events"])
    write_json(
        gaps_path,
        feature_collection(
            gap_features,
            demo=False,
            notice="AIS gap events have technical and reception-related causes; no intent is inferred.",
        ),
    )
    write_json(
        sar_path,
        feature_collection(
            sar_features,
            demo=False,
            notice="SAR cells are aggregated detections and may include false positives.",
        ),
    )
    write_json(
        summary_path,
        {
            "mode": "live",
            "events_dataset": settings["events_dataset"],
            "sar_dataset": settings["sar_dataset"],
            "period": [settings["start_date"], settings["end_date"]],
            "queried_at": utc_now(),
            "minimum_gap_hours": settings["minimum_gap_minutes"] / 60,
            "gap_records_returned": len(gap_records),
            "gap_result_limit": int(settings["max_events"]),
            "possibly_truncated": possibly_truncated,
            "gap_features_mappable": len(gap_features),
            "sar_cell_count": len(sar_features),
            "sar_detection_sum": sum(int(item["properties"].get("detections") or 0) for item in sar_features),
            "limitations": [
                *VESSEL_LIMITATIONS,
                *(["Gap results reached the configured maximum and may be truncated."] if possibly_truncated else []),
            ],
        },
    )
    return [gaps_path, sar_path, summary_path]

