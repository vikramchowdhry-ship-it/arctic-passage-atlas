from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .files import write_json

OPTICAL_BANDS = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]


def _mask_and_scale_landsat(image: Any) -> Any:
    # QA_PIXEL bits 1-5: dilated cloud, cirrus, cloud, cloud shadow and snow.
    clear = image.select("QA_PIXEL").bitwiseAnd(0b111110).eq(0)
    saturation = image.select("QA_RADSAT").eq(0)
    optical = image.select(OPTICAL_BANDS).multiply(0.0000275).add(-0.2)
    return optical.updateMask(clear).updateMask(saturation).copyProperties(image, image.propertyNames())


def _download_thumbnail(image: Any, path: Path, region: Any, vis: dict[str, Any]) -> None:
    rendered = image.visualize(**vis)
    url = rendered.getThumbURL({"region": region, "dimensions": 1200, "format": "png"})
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)


def run_change(config: ProjectConfig, ee: Any) -> list[Path]:
    settings = config.data["change"]
    geometry = ee.Geometry(config.geometry)
    source = ee.ImageCollection(settings["dataset"]).filterBounds(geometry)

    def collection(period: list[str]) -> Any:
        return (
            source.filterDate(period[0], period[1])
            .filter(ee.Filter.lte("CLOUD_COVER", settings["cloud_cover_max"]))
            .map(_mask_and_scale_landsat)
        )

    before_collection = collection(settings["before"])
    after_collection = collection(settings["after"])
    before_count = int(before_collection.size().getInfo())
    after_count = int(after_collection.size().getInfo())
    if before_count == 0 or after_count == 0:
        raise RuntimeError(
            f"No usable Landsat scenes for a configured period (before={before_count}, after={after_count}). "
            "Change the AOI, dates, or cloud-cover ceiling after inspecting the catalog."
        )

    before = before_collection.median().clip(geometry)
    after = after_collection.median().clip(geometry)
    difference = after.subtract(before)
    # Water (open sea, sea ice margins, turbidity) dominates reflectance change here, so only
    # land pixels are compared. The mask is a fixed coast mask, not a land-cover claim.
    excluded = ee.List(settings["mask_exclude_classes"])
    land = (
        ee.ImageCollection(settings["mask_dataset"])
        .first()
        .select("Map")
        .clip(geometry)
        .remap(excluded, ee.List.repeat(0, excluded.size()), 1)
        .eq(1)
    )
    magnitude = (
        difference.pow(2).reduce(ee.Reducer.sum()).sqrt().rename("change_magnitude").updateMask(land)
    )
    threshold = float(settings["change_threshold"])
    sensitivity = float(settings["sensitivity"])
    scale = int(settings["vector_scale_m"])
    minimum_pixels = int(settings["minimum_candidate_pixels"])

    def candidate_mask(level: float) -> Any:
        raw = magnitude.gte(level).rename("candidate").toByte().selfMask()
        return raw.updateMask(raw.connectedPixelCount(1_000, True).gte(minimum_pixels)).selfMask()

    candidates = candidate_mask(threshold)

    def candidate_area_km2_at(level: float) -> float:
        mask = candidate_mask(level)
        value = (
            ee.Image.pixelArea()
            .updateMask(mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(), geometry=geometry, scale=scale, maxPixels=1_000_000_000
            )
            .get("area")
        )
        return float(ee.Number(value).divide(1_000_000).getInfo() or 0)

    candidate_area_km2 = candidate_area_km2_at(threshold)
    sensitivity_km2 = {
        "low_threshold": round(candidate_area_km2_at(threshold - sensitivity), 3),
        "high_threshold": round(candidate_area_km2_at(threshold + sensitivity), 3),
    }

    vectors = candidates.reduceToVectors(
        geometry=geometry,
        scale=scale,
        geometryType="polygon",
        eightConnected=False,
        labelProperty="candidate",
        reducer=ee.Reducer.countEvery(),
        maxPixels=1_000_000_000,
    )
    vectors = vectors.map(
        lambda feature: feature.set(
            {
                "interpretation": "Unverified surface-change candidate",
                "threshold": threshold,
                "demo": False,
            }
        )
    )
    geojson = vectors.getInfo()
    geojson["notice"] = "Automated candidates are not confirmed construction."
    geojson["demo"] = False

    processed = config.root / "data" / "processed"
    geojson_path = processed / "change_candidates.geojson"
    summary_path = processed / "change_summary.json"
    write_json(geojson_path, geojson)
    write_json(
        summary_path,
        {
            "mode": "live",
            "dataset": settings["dataset"],
            "before_period": settings["before"],
            "after_period": settings["after"],
            "before_scene_count": before_count,
            "after_scene_count": after_count,
            "threshold": threshold,
            "candidate_count": len(geojson.get("features", [])),
            "candidate_area_km2": round(candidate_area_km2, 3),
            "candidate_area_km2_sensitivity": sensitivity_km2,
            "sensitivity": sensitivity,
            "vector_scale_m": scale,
            "minimum_candidate_pixels": minimum_pixels,
            "mask": "Pixels in WorldCover classes " + str(settings["mask_exclude_classes"]) + " are excluded.",
            "claim": "Candidates require manual and documentary validation; they are not confirmed construction.",
        },
    )

    image_dir = config.root / "site" / "assets" / "generated"
    before_path, after_path, magnitude_path = (
        image_dir / "change-before.png",
        image_dir / "change-after.png",
        image_dir / "change-magnitude.png",
    )
    rgb = {"bands": ["SR_B4", "SR_B3", "SR_B2"], "min": 0.02, "max": 0.3, "gamma": 1.1}
    _download_thumbnail(before, before_path, geometry, rgb)
    _download_thumbnail(after, after_path, geometry, rgb)
    _download_thumbnail(
        magnitude,
        magnitude_path,
        geometry,
        {"min": 0, "max": threshold * 2.5, "palette": ["071521", "2f7e9e", "ffb454", "f24b5f"]},
    )
    return [geojson_path, summary_path, before_path, after_path, magnitude_path]

