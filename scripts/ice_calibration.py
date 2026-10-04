"""Does a single Sentinel-1 backscatter threshold reproduce the seasonal ice cycle in the study area?

For each month of the configured year this builds the same monthly-median backscatter composite as the ice
layer, takes its histogram over the WorldCover water mask, and asks what share of water pixels a candidate
threshold would call ice. That share is compared with the NSIDC Sea Ice Index daily concentration for the
cells around the study area (mid-month). Agreement is summarised as RMSE and correlation over the 12 months.

It needs Earth Engine access (EE_PROJECT_ID and `earthengine authenticate`) and `tifffile`, because NSIDC's
final archive files are palette TIFFs that Pillow cannot read.

    python scripts/ice_calibration.py            # writes docs/ice_calibration.json

This is a check on the method, not a product. NSIDC's 25 km cells are coarse for a 44 km study area, so the
reference is itself imperfect. See docs/CALIBRATION.md for what the result means.
"""

from __future__ import annotations

import io
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.earth_engine import initialize_earth_engine
from arctic_passage_atlas.ice_grid import CELL_M, X0, Y0, _fetch, file_url, project

POLARISATIONS = [("EW", "HV"), ("EW", "HH")]
HIST_MIN, HIST_MAX, HIST_BINS = -50, 0, 100        # 0.5 dB bins


def nsidc_reference(config, year: int) -> dict[int, float]:
    import tifffile

    west, south, east, north = config.bbox
    lons, lats = np.meshgrid(np.linspace(west, east, 5), np.linspace(south, north, 5))
    x, y = project(lons.ravel(), lats.ravel())
    cols, rows = np.floor((x - X0) / CELL_M).astype(int), np.floor((Y0 - y) / CELL_M).astype(int)
    out: dict[int, float] = {}
    for month in range(1, 13):
        blob = _fetch(file_url(date(year, month, 15)))
        if blob is None:
            continue
        raw = tifffile.imread(io.BytesIO(blob))
        values = [v / 10 for v in raw[rows, cols].astype(float) if v <= 1000]   # ocean cells only; codes above 1000 are land and coast
        if values:
            out[month] = round(float(np.mean(values)) / 100, 3)
    return out


def histograms(config, ee, mode: str, pol: str, year: int) -> dict[int, list[float]]:
    settings = config.data["ice"]
    geometry = ee.Geometry.Rectangle(config.bbox)
    source = (
        ee.ImageCollection(settings["dataset"]).filterBounds(geometry).filterDate(f"{year}-01-01", f"{year + 1}-01-01")
        .filter(ee.Filter.eq("instrumentMode", mode))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", pol)).select(pol)
    )
    water = ee.ImageCollection(settings["land_mask_dataset"]).first().select("Map").eq(80).clip(geometry)
    out: dict[int, list[float]] = {}
    for month in range(1, 13):
        start = f"{year}-{month:02d}-01"
        end = f"{year + 1}-01-01" if month == 12 else f"{year}-{month + 1:02d}-01"
        composite = source.filterDate(start, end).median().updateMask(water)
        hist = composite.reduceRegion(
            reducer=ee.Reducer.fixedHistogram(HIST_MIN, HIST_MAX, HIST_BINS), geometry=geometry,
            scale=int(settings["vector_scale_m"]), maxPixels=1_000_000_000,
        ).get(pol).getInfo()
        out[month] = [count for _edge, count in hist]
    return out


def sweep(hists: dict[int, list[float]], reference: dict[int, float]) -> list[dict]:
    months = sorted(set(hists) & set(reference))
    edges = np.linspace(HIST_MIN, HIST_MAX, HIST_BINS, endpoint=False)
    ref = np.array([reference[m] for m in months])
    rows = []
    for threshold in range(-40, -4):
        share = np.array([np.asarray(hists[m])[edges >= threshold].sum() / np.sum(hists[m]) for m in months])
        with np.errstate(invalid="ignore", divide="ignore"):
            corr = float(np.corrcoef(share, ref)[0, 1])
        rows.append({
            "threshold_db": threshold,
            "rmse": round(float(np.sqrt(np.mean((share - ref) ** 2))), 3),
            "correlation": None if math.isnan(corr) else round(corr, 2),
            "ice_share_by_month": [round(float(v), 3) for v in share],
        })
    return rows


def main() -> None:
    config = load_config(ROOT / "configs" / "cambridge-bay.json")
    ee = initialize_earth_engine()
    year = int(config.data["ice"]["year"])
    reference = nsidc_reference(config, year)
    result: dict = {
        "year": year, "bbox": list(config.bbox),
        "reference": "NSIDC Sea Ice Index v4 (G02135) daily concentration, 15th of each month, ocean cells around the study area",
        "reference_ice_fraction_by_month": {str(m): v for m, v in reference.items()},
        "polarisations": {},
    }
    for mode, pol in POLARISATIONS:
        rows = sweep(histograms(config, ee, mode, pol, year), reference)
        best = min(rows, key=lambda r: r["rmse"])
        result["polarisations"][f"{mode}/{pol}"] = {
            "best_threshold_db": best["threshold_db"], "best_rmse": best["rmse"], "best_correlation": best["correlation"],
            "best_correlation_any_threshold": max(r["correlation"] for r in rows if r["correlation"] is not None), "sweep": rows,
        }
        print(f"{mode}/{pol}: best RMSE {best['rmse']} at {best['threshold_db']} dB, correlation {best['correlation']}")
    out = ROOT / "docs" / "ice_calibration.json"
    out.write_text(json.dumps(result, indent=1) + "\n", encoding="utf-8", newline="\n")
    print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
