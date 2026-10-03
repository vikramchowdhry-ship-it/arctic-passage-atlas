from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .fallbacks import write_fallbacks
from .files import feature_collection, write_json
from .vessels import VESSEL_LIMITATIONS

DEMO_NOTICE = "Synthetic demonstration fixture. It is not an observation of Cambridge Bay."


def _feature(geometry: dict[str, Any], properties: dict[str, Any]) -> dict[str, Any]:
    return {"type": "Feature", "geometry": geometry, "properties": properties}


def _rect(west: float, south: float, east: float, north: float) -> dict[str, Any]:
    return {
        "type": "Polygon",
        "coordinates": [[[west, south], [east, south], [east, north], [west, north], [west, south]]],
    }


def generate_demo(config: ProjectConfig) -> list[Path]:
    """Create deterministic fixtures for exercising the site without provider credentials."""
    target = config.root / "data" / "processed"
    target.mkdir(parents=True, exist_ok=True)
    west, south, east, north = config.bbox
    width, height = east - west, north - south

    aoi_path = target / "aoi.geojson"
    write_json(
        aoi_path,
        feature_collection(
            [_feature(config.geometry, {"name": config.data["aoi"]["name"], "demo": False})],
            name="Configured analysis boundary",
        ),
    )

    change_features = [
        _feature(
            _rect(west + width * x, south + height * y, west + width * (x + dx), south + height * (y + dy)),
            {
                "candidate_id": f"DEMO-C{index:02d}",
                "change_magnitude": round(value, 3),
                "interpretation": "Unverified surface-change candidate",
                "demo": True,
            },
        )
        for index, (x, y, dx, dy, value) in enumerate(
            [(0.48, 0.38, 0.07, 0.09, 0.23), (0.57, 0.52, 0.10, 0.06, 0.18), (0.40, 0.61, 0.05, 0.08, 0.16)],
            start=1,
        )
    ]
    change_path = target / "change_candidates.geojson"
    write_json(change_path, feature_collection(change_features, demo=True, notice=DEMO_NOTICE))
    change_summary = target / "change_summary.json"
    write_json(
        change_summary,
        {
            "mode": "demo",
            "notice": DEMO_NOTICE,
            "before_period": config.data["change"]["before"],
            "after_period": config.data["change"]["after"],
            "candidate_count": len(change_features),
            "candidate_area_km2": 2.74,
            "threshold": config.data["change"]["change_threshold"],
            "claim": "Candidates require manual and documentary validation; they are not confirmed construction.",
        },
    )

    ice_features: list[dict[str, Any]] = []
    for month, fraction in ((2, 0.91), (5, 0.68), (8, 0.14), (11, 0.62)):
        ice_east = west + width * (0.12 + 0.78 * fraction)
        ice_features.append(
            _feature(
                _rect(west + width * 0.06, south + height * 0.06, ice_east, north - height * 0.06),
                {
                    "period": f"{config.data['ice']['year']}-{month:02d}",
                    "classified_fraction": fraction,
                    "threshold_db": float(config.data["ice"]["demo_threshold_db"]),
                    "demo": True,
                },
            )
        )
    ice_path = target / "ice_extent.geojson"
    write_json(ice_path, feature_collection(ice_features, demo=True, notice=DEMO_NOTICE))

    monthly = []
    for month in range(1, 13):
        seasonal = 0.54 + 0.40 * math.cos((month - 2) * math.tau / 12)
        base = max(0.04, min(0.96, seasonal))
        monthly.append(
            {
                "month": month,
                "period": f"{config.data['ice']['year']}-{month:02d}",
                "classified_fraction": round(base, 3),
                "low_threshold_fraction": round(min(1, base + 0.08), 3),
                "high_threshold_fraction": round(max(0, base - 0.08), 3),
                "coarse_reference_fraction": round(max(0, min(1, base * 0.94 + 0.02)), 3),
                "scene_count": 4 + month % 3,
            }
        )
    ice_summary = target / "ice_summary.json"
    write_json(
        ice_summary,
        {
            "mode": "demo",
            "notice": DEMO_NOTICE,
            "year": config.data["ice"]["year"],
            "threshold_db": float(config.data["ice"]["demo_threshold_db"]),
            "sensitivity_db": config.data["ice"]["sensitivity_db"],
            "acquisition": {"instrument_mode": "DEMO", "polarization": "DEMO", "orbit": "DEMO"},
            "monthly": monthly,
        },
    )

    gap_specs = [
        ("DEMO-G01", 0.18, 0.33, 0.42, 0.47, 18.5, "cargo"),
        ("DEMO-G02", 0.64, 0.22, 0.54, 0.56, 14.0, "passenger"),
        ("DEMO-G03", 0.30, 0.72, 0.73, 0.64, 25.2, "other"),
    ]
    gaps = []
    for event_id, x1, y1, x2, y2, duration, vessel_type in gap_specs:
        gaps.append(
            _feature(
                {
                    "type": "LineString",
                    "coordinates": [
                        [west + width * x1, south + height * y1],
                        [west + width * x2, south + height * y2],
                    ],
                },
                {
                    "event_id": event_id,
                    "event_type": "AIS gap event",
                    "duration_hours": duration,
                    "vessel_type": vessel_type,
                    "start": "2024-08-01T00:00:00Z",
                    "end": "2024-08-01T18:30:00Z",
                    "demo": True,
                },
            )
        )
    gaps_path = target / "vessel_events.geojson"
    write_json(gaps_path, feature_collection(gaps, demo=True, notice=DEMO_NOTICE))

    sar = []
    for index, (x, y, count) in enumerate(((0.28, 0.44, 1), (0.61, 0.70, 2), (0.76, 0.37, 1)), 1):
        sar.append(
            _feature(
                {"type": "Point", "coordinates": [west + width * x, south + height * y]},
                {
                    "cell_id": f"DEMO-S{index:02d}",
                    "detections": count,
                    "matched": False,
                    "interpretation": "Aggregated unmatched SAR-detection cell; not proof of AIS disabling",
                    "demo": True,
                },
            )
        )
    sar_path = target / "sar_detections.geojson"
    write_json(sar_path, feature_collection(sar, demo=True, notice=DEMO_NOTICE))
    vessel_summary = target / "vessel_summary.json"
    write_json(
        vessel_summary,
        {
            "mode": "demo",
            "notice": DEMO_NOTICE,
            "gap_event_count": len(gaps),
            "sar_cell_count": len(sar),
            "sar_detection_sum": sum(item["properties"]["detections"] for item in sar),
            "minimum_gap_hours": config.data["vessels"]["minimum_gap_minutes"] / 60,
            "limitations": list(VESSEL_LIMITATIONS),
        },
    )

    fallbacks = write_fallbacks(config, change_features, ice_features, gaps, sar, mode="demo")
    return [
        aoi_path,
        change_path,
        change_summary,
        ice_path,
        ice_summary,
        gaps_path,
        sar_path,
        vessel_summary,
        *fallbacks,
    ]

