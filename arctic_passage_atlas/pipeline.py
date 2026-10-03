from __future__ import annotations

import asyncio
from pathlib import Path

from .config import ProjectConfig
from .demo import generate_demo
from .fallbacks import write_fallbacks
from .files import feature_collection, read_json, write_json
from .provenance import write_manifest
from .site import build_site_data


def publication_blockers(config: ProjectConfig) -> list[str]:
    """Return analytical checks that must be completed before a live site can be published."""
    blockers: list[str] = []
    if config.data["ice"].get("threshold_status") != "validated":
        blockers.append("ice.threshold_status must be 'validated' after AOI-specific calibration")
    if config.data["change"].get("threshold_status") != "validated":
        blockers.append("change.threshold_status must be 'validated' after threshold sensitivity review")
    if config.data["change"].get("manual_review_status") != "complete":
        blockers.append("change.manual_review_status must be 'complete' after a visual candidate review")
    return blockers


def run_demo(config: ProjectConfig) -> list[Path]:
    outputs = generate_demo(config)
    manifest = write_manifest(
        config,
        "demo",
        outputs,
        [
            "All analytical features and summary values are deterministic synthetic fixtures.",
            "The configured AOI is real; the demonstration observations are not.",
        ],
    )
    outputs.append(manifest)
    # The browser bundle embeds the manifest and is therefore intentionally not
    # checksummed by that same manifest.
    outputs.append(build_site_data(config))
    return outputs


def run_live(config: ProjectConfig, parts: list[str]) -> list[Path]:
    processed = config.root / "data" / "processed"
    aoi_path = processed / "aoi.geojson"
    write_json(
        aoi_path,
        feature_collection(
            [
                {
                    "type": "Feature",
                    "geometry": config.geometry,
                    "properties": {"name": config.data["aoi"]["name"], "demo": False},
                }
            ],
            name="Configured analysis boundary",
        ),
    )
    outputs: list[Path] = [aoi_path]
    if "change" in parts or "ice" in parts:
        from .earth_engine import initialize_earth_engine

        ee = initialize_earth_engine()
        if "change" in parts:
            from .change import run_change

            outputs.extend(run_change(config, ee))
        if "ice" in parts:
            from .ice import run_ice

            outputs.extend(run_ice(config, ee))
    if "vessels" in parts:
        from .vessels import run_vessels

        outputs.extend(asyncio.run(run_vessels(config)))

    complete_parts = {"change", "ice", "vessels"}
    if set(parts) != complete_parts:
        # Partial runs are useful during development, but must not relabel an
        # existing mixed demo/live publication as fully provider-backed.
        return outputs

    required = {
        "change": ["change_candidates.geojson", "change_summary.json"],
        "ice": ["ice_extent.geojson", "ice_summary.json"],
        "vessels": ["vessel_events.geojson", "sar_detections.geojson", "vessel_summary.json"],
    }
    missing = [name for names in required.values() for name in names if not (processed / name).exists()]
    if missing:
        raise RuntimeError(
            "A complete live publication requires all three layers. Missing: " + ", ".join(sorted(set(missing)))
        )
    summaries = ["change_summary.json", "ice_summary.json", "vessel_summary.json"]
    non_live = [name for name in summaries if read_json(processed / name).get("mode") != "live"]
    if non_live:
        raise RuntimeError("Refusing to publish a mixed demo/live site. Non-live summaries: " + ", ".join(non_live))
    blockers = publication_blockers(config)
    if blockers:
        raise RuntimeError("Refusing to publish unvalidated live analysis: " + "; ".join(blockers))
    fallbacks = write_fallbacks(
        config,
        read_json(processed / "change_candidates.geojson").get("features", []),
        read_json(processed / "ice_extent.geojson").get("features", []),
        read_json(processed / "vessel_events.geojson").get("features", []),
        read_json(processed / "sar_detections.geojson").get("features", []),
        mode="live",
    )
    outputs.extend(fallbacks)
    manifest = write_manifest(
        config,
        "live",
        outputs,
        [
            "Provider datasets using the :latest alias may change after this run.",
            "The manifest records the configuration and published-output checksums.",
        ],
    )
    outputs.append(manifest)
    outputs.append(build_site_data(config))
    return outputs

