from __future__ import annotations

import calendar
from typing import Any

from .config import ProjectConfig, ice_threshold, usable_acquisitions
from .files import feature_collection, write_json

ACQUISITION_CANDIDATES = [("EW", "HH"), ("EW", "HV"), ("IW", "VV"), ("IW", "VH")]


def _property_tagger(properties: dict[str, Any]):
    def tag(feature: Any) -> Any:
        return feature.set(properties)

    return tag


def _period(year: int, month: int) -> tuple[str, str]:
    start = f"{year}-{month:02d}-01"
    if month == 12:
        end = f"{year + 1}-01-01"
    else:
        end = f"{year}-{month + 1:02d}-01"
    return start, end


def _area_fraction(ee: Any, mask: Any, denominator_m2: float, geometry: Any, scale: int) -> float:
    if denominator_m2 <= 0:
        return 0.0
    value = (
        ee.Image.pixelArea()
        .updateMask(mask)
        .reduceRegion(
            reducer=ee.Reducer.sum(), geometry=geometry, scale=scale, maxPixels=1_000_000_000
        )
        .get("area")
    )
    square_metres = float(ee.Number(value).getInfo() or 0)
    return square_metres / denominator_m2


def _select_acquisition(config: ProjectConfig, ee: Any, geometry: Any, source: Any) -> tuple[str, str, dict[str, int]]:
    settings = config.data["ice"]
    year = int(settings["year"])
    start, end = f"{year}-01-01", f"{year + 1}-01-01"
    configured_mode = settings["instrument_mode"]
    configured_pol = settings["polarization"]
    candidates = usable_acquisitions(config.data, ACQUISITION_CANDIDATES)
    if not candidates:
        raise RuntimeError("No acquisition candidate has a configured ice threshold.")
    if configured_mode != "AUTO" and configured_pol != "AUTO":
        candidates = [(configured_mode, configured_pol)]
        ice_threshold(config.data, configured_pol)
    counts: dict[str, int] = {}
    for mode, pol in candidates:
        count = int(
            source.filterDate(start, end)
            .filterBounds(geometry)
            .filter(ee.Filter.eq("instrumentMode", mode))
            .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
            .size()
            .getInfo()
        )
        counts[f"{mode}/{pol}"] = count
    mode, pol = max(candidates, key=lambda pair: counts[f"{pair[0]}/{pair[1]}"])
    if counts[f"{mode}/{pol}"] == 0:
        raise RuntimeError(f"No Sentinel-1 scenes intersect the configured AOI/year. Counts: {counts}")
    return mode, pol, counts


def run_ice(config: ProjectConfig, ee: Any) -> list[Any]:
    settings = config.data["ice"]
    year = int(settings["year"])
    geometry = ee.Geometry(config.geometry)
    source = ee.ImageCollection(settings["dataset"])
    mode, pol, acquisition_counts = _select_acquisition(config, ee, geometry, source)

    collection = (
        source.filterBounds(geometry)
        .filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filter(ee.Filter.eq("instrumentMode", mode))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol))
        .select(pol)
    )
    if settings["orbit_pass"] != "BOTH":
        collection = collection.filter(ee.Filter.eq("orbitProperties_pass", settings["orbit_pass"]))

    # WorldCover water (class 80) is used only as a stable coast mask. It is not a sea-ice label.
    water = (
        ee.ImageCollection(settings["land_mask_dataset"])
        .first()
        .select("Map")
        .eq(80)
        .clip(geometry)
    )
    water_area_value = (
        ee.Image.pixelArea()
        .updateMask(water)
        .reduceRegion(
            reducer=ee.Reducer.sum(), geometry=geometry, scale=120, maxPixels=1_000_000_000
        )
        .get("area")
    )
    water_area_m2 = float(ee.Number(water_area_value).getInfo() or 0)
    if water_area_m2 <= 0:
        raise RuntimeError("The configured land-mask dataset did not identify water inside the AOI.")

    aoi_area_m2 = float(geometry.area(maxError=1).getInfo())
    water_fraction = water_area_m2 / aoi_area_m2
    expected_low, expected_high = map(float, settings["water_mask_expected_fraction"])
    if not expected_low <= water_fraction <= expected_high:
        raise RuntimeError(
            "WorldCover water-mask fraction is outside the configured plausible range "
            f"({water_fraction:.3f}; expected {expected_low:.3f}–{expected_high:.3f}). "
            "Inspect the coast mask before interpreting classification results."
        )
    threshold = ice_threshold(config.data, pol)
    sensitivity = float(settings["sensitivity_db"])
    scale = int(settings["vector_scale_m"])
    snapshot_months = {int(value) for value in settings["snapshot_months"]}
    monthly: list[dict[str, Any]] = []
    features: list[dict[str, Any]] = []

    for month in range(1, 13):
        start, end = _period(year, month)
        month_collection = collection.filterDate(start, end)
        scene_count = int(month_collection.size().getInfo())
        if scene_count == 0:
            monthly.append(
                {
                    "month": month,
                    "month_name": calendar.month_abbr[month],
                    "period": f"{year}-{month:02d}",
                    "period_start": start,
                    "period_end": end,
                    "scene_count": 0,
                    "classified_fraction": None,
                    "low_threshold_fraction": None,
                    "high_threshold_fraction": None,
                    "coarse_reference_fraction": None,
                }
            )
            continue

        backscatter = month_collection.median().clip(geometry)
        percentiles = (
            backscatter.updateMask(water)
            .reduceRegion(
                reducer=ee.Reducer.percentile([5, 25, 50, 75, 95]),
                geometry=geometry,
                scale=scale,
                maxPixels=1_000_000_000,
            )
            .getInfo()
        )
        base_mask = backscatter.gte(threshold).And(water)
        low_mask = backscatter.gte(threshold - sensitivity).And(water)
        high_mask = backscatter.gte(threshold + sensitivity).And(water)

        reference = (
            ee.ImageCollection(settings["reference_dataset"])
            .filterDate(start, end)
            .select("ice")
            .median()
            .multiply(0.01)
            .gte(0.15)
            .clip(geometry)
        )
        row = {
            "month": month,
            "month_name": calendar.month_abbr[month],
            "period": f"{year}-{month:02d}",
            "period_start": start,
            "period_end": end,
            "scene_count": scene_count,
            "backscatter_percentiles_db": {
                key.rsplit("_", 1)[-1]: round(value, 2)
                for key, value in percentiles.items()
                if value is not None
            },
            "classified_fraction": round(_area_fraction(ee, base_mask, water_area_m2, geometry, scale), 4),
            "low_threshold_fraction": round(_area_fraction(ee, low_mask, water_area_m2, geometry, scale), 4),
            "high_threshold_fraction": round(_area_fraction(ee, high_mask, water_area_m2, geometry, scale), 4),
            "coarse_reference_fraction": round(_area_fraction(ee, reference, water_area_m2, geometry, 25_000), 4),
        }
        monthly.append(row)

        if month in snapshot_months:
            vectors = base_mask.rename("ice").toByte().selfMask().reduceToVectors(
                geometry=geometry,
                scale=scale,
                geometryType="polygon",
                eightConnected=False,
                labelProperty="ice",
                reducer=ee.Reducer.countEvery(),
                maxPixels=1_000_000_000,
            )
            snapshot_properties = {
                "period": f"{year}-{month:02d}",
                "period_start": start,
                "period_end": end,
                "threshold_db": threshold,
                "instrument_mode": mode,
                "polarization": pol,
                "demo": False,
            }
            vectors = vectors.map(_property_tagger(snapshot_properties))
            features.extend(vectors.getInfo().get("features", []))

    processed = config.root / "data" / "processed"
    geojson_path = processed / "ice_extent.geojson"
    summary_path = processed / "ice_summary.json"
    write_json(
        geojson_path,
        feature_collection(
            features,
            demo=False,
            notice="Threshold-derived local classification. It is not an operational sea-ice chart.",
        ),
    )
    write_json(
        summary_path,
        {
            "mode": "live",
            "dataset": settings["dataset"],
            "reference_dataset": settings["reference_dataset"],
            "year": year,
            "threshold_db": threshold,
            "threshold_status": settings["threshold_status"],
            "sensitivity_db": sensitivity,
            "water_mask_area_km2": round(water_area_m2 / 1_000_000, 3),
            "water_mask_fraction_of_aoi": round(water_fraction, 4),
            "date_note": "Each monthly composite spans the whole calendar month; 'date' is a plotting label only.",
            "acquisition": {
                "instrument_mode": mode,
                "polarization": pol,
                "orbit": settings["orbit_pass"],
                "candidate_counts": acquisition_counts,
            },
            "monthly": monthly,
            "limitations": [
                "Backscatter threshold response changes with surface condition and acquisition geometry.",
                "WorldCover water is used as a coast mask and may omit or misclassify shoreline pixels.",
                "The coarse OISST ice band is a seasonality reference, not pixel-level ground truth.",
            ],
        },
    )
    return [geojson_path, summary_path]

