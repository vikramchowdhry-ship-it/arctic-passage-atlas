from __future__ import annotations

import urllib.request
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .files import write_json

OPTICAL_BANDS = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
# Earth Engine refuses one 6-band computation over millions of pixels; smaller tiles give the same result.
TILE_SCALE = 16


def _mask_and_scale_landsat(image: Any, snow_ndsi_max: float = 0.4, snow_nir_min: float = 0.11) -> Any:
    # QA_PIXEL bits 1-5: dilated cloud, cirrus, cloud, cloud shadow and snow.
    clear = image.select("QA_PIXEL").bitwiseAnd(0b111110).eq(0)
    saturation = image.select("QA_RADSAT").eq(0)
    optical = image.select(OPTICAL_BANDS).multiply(0.0000275).add(-0.2)
    # The QA snow flag misses patches of old snow and ice in this area. Summer snow patches in one year and bare
    # ground in the other would otherwise be the largest "changes". NDSI (green vs SWIR-1) with a NIR floor is the
    # standard snow test; pixels it flags are masked in every scene before the composite.
    ndsi = optical.normalizedDifference(["SR_B3", "SR_B6"])
    snow = ndsi.gt(snow_ndsi_max).And(optical.select("SR_B5").gt(snow_nir_min))
    return (
        optical.updateMask(clear).updateMask(saturation).updateMask(snow.Not()).copyProperties(image, image.propertyNames())
    )


def _download_thumbnail(image: Any, path: Path, region: Any, vis: dict[str, Any]) -> None:
    rendered = image.visualize(**vis)
    url = rendered.getThumbURL({"region": region, "dimensions": 1200, "format": "png"})
    path.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(url, path)


def run_change(config: ProjectConfig, ee: Any) -> list[Path]:
    settings = config.data["change"]
    geometry = ee.Geometry(config.geometry)
    source = ee.ImageCollection(settings["dataset"]).filterBounds(geometry)

    snow_ndsi_max = float(settings.get("snow_ndsi_max", 0.4))
    snow_nir_min = float(settings.get("snow_nir_min", 0.11))

    def collection(period: list[str]) -> Any:
        return (
            source.filterDate(period[0], period[1])
            .filter(ee.Filter.lte("CLOUD_COVER", settings["cloud_cover_max"]))
            .map(lambda image: _mask_and_scale_landsat(image, snow_ndsi_max, snow_nir_min))
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

    # A composite pixel built from one or two surviving scenes can be a single unflagged bright scene. Require
    # a minimum number of valid observations in both periods before a pixel can be compared at all.
    minimum_observations = int(settings.get("minimum_valid_observations", 3))

    # Late-lying snow and ice patches stay far brighter than tundra, gravel or roofs at 30 m. A pixel whose mean
    # visible reflectance is above this ceiling in either period is not compared.
    maximum_visible = float(settings.get("maximum_visible_reflectance", 0.35))

    def composite(scenes: Any) -> Any:
        enough = scenes.select("SR_B4").count().gte(minimum_observations)
        median = scenes.median()
        too_bright = median.select(["SR_B2", "SR_B3", "SR_B4"]).reduce(ee.Reducer.mean()).gt(maximum_visible)
        return median.updateMask(enough).updateMask(too_bright.Not()).clip(geometry)

    before = composite(before_collection)
    after = composite(after_collection)
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

    def magnitude_of(earlier: Any, later: Any) -> Any:
        return later.subtract(earlier).pow(2).reduce(ee.Reducer.sum()).sqrt().rename("change_magnitude").updateMask(land)

    magnitude = magnitude_of(before, after)
    # A change that is real should appear against a second, independent pair of years as well. Snow patches, wet
    # ground and growing-season differences are usually specific to one summer, so requiring the same pixel to
    # exceed the threshold in both pairs removes most of them. Optional: configured as before_confirm/after_confirm.
    confirm_before_period, confirm_after_period = settings.get("before_confirm"), settings.get("after_confirm")
    confirm_magnitude = None
    if confirm_before_period and confirm_after_period:
        confirm_magnitude = magnitude_of(
            composite(collection(confirm_before_period)), composite(collection(confirm_after_period))
        )
    threshold = float(settings["change_threshold"])
    sensitivity = float(settings["sensitivity"])
    scale = int(settings["vector_scale_m"])
    minimum_pixels = int(settings["minimum_candidate_pixels"])

    def candidate_mask(level: float) -> Any:
        passes = magnitude.gte(level)
        if confirm_magnitude is not None:
            passes = passes.And(confirm_magnitude.gte(level))
        raw = passes.rename("candidate").toByte().selfMask()
        # Counting connected pixels only up to the minimum size answers "are there at least that many?" exactly,
        # and keeps Earth Engine's neighbourhood window small.
        return raw.updateMask(raw.connectedPixelCount(minimum_pixels, True).gte(minimum_pixels)).selfMask()

    candidates = candidate_mask(threshold)

    def candidate_area_km2_at(level: float) -> float:
        mask = candidate_mask(level)
        value = (
            ee.Image.pixelArea()
            .updateMask(mask)
            .reduceRegion(
                reducer=ee.Reducer.sum(), geometry=geometry, scale=scale, maxPixels=1_000_000_000,
                tileScale=TILE_SCALE,
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
        tileScale=TILE_SCALE,
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
            "confirmation_before_period": confirm_before_period,
            "confirmation_after_period": confirm_after_period,
            "candidate_count": len(geojson.get("features", [])),
            "candidate_area_km2": round(candidate_area_km2, 3),
            "candidate_area_km2_sensitivity": sensitivity_km2,
            "sensitivity": sensitivity,
            "vector_scale_m": scale,
            "minimum_candidate_pixels": minimum_pixels,
            "mask": "Pixels in WorldCover classes " + str(settings["mask_exclude_classes"]) + " are excluded.",
            "rule": (
                "A pixel is a candidate only if its change magnitude is at or above the threshold in both the main "
                "pair of years and the confirmation pair, outside snow, bright-surface and water pixels."
                if confirm_magnitude is not None
                else "A pixel is a candidate if its change magnitude is at or above the threshold."
            ),
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

