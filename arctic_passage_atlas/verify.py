from __future__ import annotations

import json

from .config import ProjectConfig
from .files import sha256
from .site import DATA_FILES


class VerificationError(RuntimeError):
    pass


def verify_project(config: ProjectConfig) -> list[str]:
    root = config.root
    messages: list[str] = []
    required_site = [
        "index.html",
        "methodology.html",
        "about.html",
        "live.html",
        "route.html",
        "contact.html",
        "defence.html",
        "sources.html",
        "layers/change.html",
        "layers/ice.html",
        "layers/vessels.html",
        "assets/site.css",
        "assets/site.js",
        "assets/data.js",
        "assets/pro.css",
        "assets/live.js",
        "assets/route.js",
        "assets/router.js",
        "assets/home.js",
        "assets/tabs.js",
        "assets/world.js",
        "assets/tools.js",
        "assets/vessels-live.js",
        "assets/stations.js",
        "assets/contact.js",
        "assets/site-config.js",
        "data/route/water.png",
        "data/route/water.json",
        "data/route/world.png",
        "data/route/world.json",
        "data/route/ice_world.png",
        "data/route/ice_arctic.png",
        "data/route/ice_grid.json",
        "assets/ui.js",
        "assets/video/explainer.mp4",
        "data/live/nsidc_extent.json",
        "data/live/station_snapshot.json",
    ]
    # Pages that show analytical layers must carry the demonstration banner in demo mode. The Live and
    # Sources pages show only third-party feeds and carry their own notice instead.
    third_party_pages = {"live.html", "sources.html", "route.html", "contact.html", "defence.html"}
    missing_site = [path for path in required_site if not (root / "site" / path).exists()]
    if missing_site:
        raise VerificationError(f"Missing site files: {missing_site}")
    messages.append(f"site files: {len(required_site)} present")

    processed = root / "data" / "processed"
    missing_data = [filename for filename in DATA_FILES.values() if not (processed / filename).exists()]
    if missing_data:
        raise VerificationError(f"Missing processed files: {missing_data}")
    messages.append(f"processed files: {len(DATA_FILES)} present")

    manifest = json.loads((processed / "manifest.json").read_text(encoding="utf-8"))
    for relative_path, metadata in manifest.get("outputs", {}).items():
        output = root / relative_path
        if not output.exists():
            raise VerificationError(f"Manifest output is missing: {relative_path}")
        if sha256(output) != metadata.get("sha256"):
            raise VerificationError(f"Manifest checksum mismatch: {relative_path}")
    messages.append("manifest checksums: valid")
    manifest_mode = manifest.get("mode")
    summary_files = ["change_summary.json", "ice_summary.json", "vessel_summary.json"]
    inconsistent = [
        filename
        for filename in summary_files
        if json.loads((processed / filename).read_text(encoding="utf-8")).get("mode") != manifest_mode
    ]
    if inconsistent:
        raise VerificationError(
            f"Manifest mode {manifest_mode!r} does not match summaries: {', '.join(inconsistent)}"
        )
    messages.append(f"publication mode: {manifest_mode} across manifest and summaries")
    if manifest_mode == "demo":
        pages = [
            root / "site" / path
            for path in required_site
            if path.endswith(".html") and path not in third_party_pages
        ]
        for page in pages:
            if "demo-banner" not in page.read_text(encoding="utf-8"):
                raise VerificationError(f"Demo banner missing from {page}")
        messages.append("demo labelling: present on every public page")

    for filename in ("change_candidates.geojson", "ice_extent.geojson", "vessel_events.geojson", "sar_detections.geojson"):
        value = json.loads((processed / filename).read_text(encoding="utf-8"))
        if value.get("type") != "FeatureCollection" or not isinstance(value.get("features"), list):
            raise VerificationError(f"Invalid GeoJSON FeatureCollection: {filename}")
    messages.append("GeoJSON structure: valid")

    for path in ("live.html", "route.html"):
        if "info-banner" not in (root / "site" / path).read_text(encoding="utf-8"):
            raise VerificationError(f"Third-party notice missing from {path}")
    for filename in ("nsidc_extent.json", "station_snapshot.json"):
        snapshot = json.loads((root / "site" / "data" / "live" / filename).read_text(encoding="utf-8"))
        if not snapshot.get("retrieved_at") or not snapshot.get("source_url"):
            raise VerificationError(f"Live snapshot lacks provenance fields: {filename}")
    ice = json.loads((root / "site" / "data" / "route" / "ice_grid.json").read_text(encoding="utf-8"))
    if not (ice.get("retrieved_at") and ice.get("source_url") and ice.get("date") and ice.get("caveat")):
        raise VerificationError("Sea-ice route grid lacks provenance or caveat fields")
    for presence in (root / "site" / "data" / "live" / "gfw_presence.json", root / "site" / "data" / "live" / "gfw_recent.json"):
        if not presence.exists():
            continue
        text = presence.read_text(encoding="utf-8")
        meta = json.loads(text)
        if not (meta.get("retrieved_at") and meta.get("source_url") and meta.get("license") and meta.get("caveat")):
            raise VerificationError(f"Shipping snapshot lacks provenance, licence or caveat fields: {presence.name}")
        for key in ("mmsi", "imo", "shipname", "callsign", "vesselid", "flag"):
            if f'"{key}"' in text.lower():
                raise VerificationError(f"Shipping snapshot contains an identifier field ({key}): {presence.name}")
    messages.append("live feeds: third-party notice and snapshot provenance present")
    return messages

