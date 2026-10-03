from __future__ import annotations

import json
from pathlib import Path

from .config import ProjectConfig
from .files import read_json

DATA_FILES = {
    "aoi": "aoi.geojson",
    "change": "change_candidates.geojson",
    "changeSummary": "change_summary.json",
    "ice": "ice_extent.geojson",
    "iceSummary": "ice_summary.json",
    "gaps": "vessel_events.geojson",
    "sar": "sar_detections.geojson",
    "vesselSummary": "vessel_summary.json",
    "manifest": "manifest.json",
}


def build_site_data(config: ProjectConfig) -> Path:
    processed = config.root / "data" / "processed"
    missing = [filename for filename in DATA_FILES.values() if not (processed / filename).exists()]
    # The manifest is written after the first site-data build. Use a minimal placeholder on that pass.
    missing_without_manifest = [name for name in missing if name != "manifest.json"]
    if missing_without_manifest:
        raise FileNotFoundError(f"Missing processed outputs: {missing_without_manifest}")

    bundle = {key: read_json(processed / filename) for key, filename in DATA_FILES.items() if (processed / filename).exists()}
    bundle.setdefault("manifest", {"mode": bundle["changeSummary"].get("mode", "unknown")})
    # Keep the source configuration declarative; expose the actual build time in
    # the public bundle instead of a placeholder string.
    public_config = json.loads(json.dumps(config.data))
    public_config["site"]["data_accessed"] = bundle["manifest"].get("generated_at")
    bundle["config"] = public_config
    destination = config.root / "site" / "assets" / "data.js"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "window.ATLAS_DATA = " + json.dumps(bundle, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    return destination

