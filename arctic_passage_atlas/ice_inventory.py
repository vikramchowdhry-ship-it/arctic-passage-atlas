"""Sentinel-1 calibration inventory that does not create a classified ice product."""

from __future__ import annotations

import calendar
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .files import write_json

CROSS_POLARIZATION_CANDIDATES = [("EW", "HV"), ("IW", "VH")]


def _period(year: int, month: int) -> tuple[str, str]:
    start = f"{year}-{month:02d}-01"
    return start, f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"


def _select_cross_pol(config: ProjectConfig, ee: Any, geometry: Any, source: Any) -> tuple[str, str, dict[str, int]]:
    settings = config.data["ice"]
    year = int(settings["year"])
    start, end = f"{year}-01-01", f"{year + 1}-01-01"
    candidates = CROSS_POLARIZATION_CANDIDATES
    if settings["instrument_mode"] != "AUTO" and settings["polarization"] != "AUTO":
        candidates = [(settings["instrument_mode"], settings["polarization"])]
    counts: dict[str, int] = {}
    for mode, pol in candidates:
        counts[f"{mode}/{pol}"] = int(
            source.filterDate(start, end)
            .filterBounds(geometry)
            .filter(ee.Filter.eq("instrumentMode", mode))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
            .size()
            .getInfo()
        )
    mode, pol = max(candidates, key=lambda pair: counts[f"{pair[0]}/{pair[1]}"])
    if not counts[f"{mode}/{pol}"]:
        raise RuntimeError(f"No cross-polarized Sentinel-1 scenes intersect the configured AOI/year. Counts: {counts}")
    return mode, pol, counts


def inventory_ice(config: ProjectConfig, ee: Any) -> list[Path]:
    """Record calibration evidence only; never write ice_extent, ice_summary, or a manifest."""
    settings = config.data["ice"]
    year = int(settings["year"])
    geometry = ee.Geometry(config.geometry)
    source = ee.ImageCollection(settings["dataset"])
    mode, pol, candidate_counts = _select_cross_pol(config, ee, geometry, source)
    collection = (
        source.filterBounds(geometry)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filter(ee.Filter.eq("instrumentMode", mode))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
        .select(pol)
    )
    if settings["orbit_pass"] != "BOTH":
        collection = collection.filter(ee.Filter.eq("orbitProperties_pass", settings["orbit_pass"]))

    water = ee.ImageCollection(settings["land_mask_dataset"]).first().select("Map").eq(80).clip(geometry)
    water_area = (
        ee.Image.pixelArea()
        .updateMask(water)
        .reduceRegion(reducer=ee.Reducer.sum(), geometry=geometry, scale=120, maxPixels=1_000_000_000)
        .get("area")
    )
    water_area_m2 = float(ee.Number(water_area).getInfo() or 0)
    aoi_area_m2 = float(geometry.area(maxError=1).getInfo())
    water_fraction = water_area_m2 / aoi_area_m2 if aoi_area_m2 else 0
    low, high = map(float, settings["water_mask_expected_fraction"])
    if not low <= water_fraction <= high:
        raise RuntimeError(
            f"WorldCover water-mask fraction {water_fraction:.3f} is outside the expected {low:.3f}–{high:.3f}."
        )

    monthly: list[dict[str, Any]] = []
    scale = int(settings["vector_scale_m"])
    for month in range(1, 13):
        start, end = _period(year, month)
        scenes = collection.filterDate(start, end)
        scene_count = int(scenes.size().getInfo())
        row: dict[str, Any] = {
            "month": month,
            "month_name": calendar.month_abbr[month],
            "period": f"{year}-{month:02d}",
            "period_start": start,
            "period_end": end,
            "scene_count": scene_count,
            "backscatter_percentiles_db": None,
        }
        if scene_count:
            values = (
                scenes.median()
                .clip(geometry)
                .updateMask(water)
                .reduceRegion(
                    reducer=ee.Reducer.percentile([5, 25, 50, 75, 95]),
                    geometry=geometry,
                    scale=scale,
                    maxPixels=1_000_000_000,
                )
                .getInfo()
            )
            row["backscatter_percentiles_db"] = {
                key.rsplit("_", 1)[-1]: round(value, 2) for key, value in values.items() if value is not None
            }
        monthly.append(row)

    output = config.root / "data" / "processed" / "ice_inventory.json"
    write_json(
        output,
        {
            "mode": "calibration_inventory",
            "dataset": settings["dataset"],
            "year": year,
            "water_mask_dataset": settings["land_mask_dataset"],
            "water_mask_area_km2": round(water_area_m2 / 1_000_000, 3),
            "water_mask_fraction_of_aoi": round(water_fraction, 4),
            "acquisition": {"instrument_mode": mode, "polarization": pol, "candidate_counts": candidate_counts},
            "monthly": monthly,
            "next_step": "Calibrate a threshold against these distributions and independent reference data.",
        },
    )
    return [output]
