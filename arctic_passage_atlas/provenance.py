from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from .config import ProjectConfig
from .files import sha256, utc_now, write_json


def _git_commit(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, check=True, capture_output=True, text=True
        )
        return result.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def write_manifest(config: ProjectConfig, mode: str, outputs: list[Path], notes: list[str]) -> Path:
    manifest_path = config.root / "data" / "processed" / "manifest.json"
    config_bytes = json.dumps(config.data, sort_keys=True).encode("utf-8")
    manifest: dict[str, Any] = {
        "schema_version": 1,
        "generated_at": utc_now(),
        "mode": mode,
        "demo_data": mode == "demo",
        "config": str(config.source.relative_to(config.root)).replace("\\", "/"),
        "config_sha256": __import__("hashlib").sha256(config_bytes).hexdigest(),
        "git_commit": _git_commit(config.root),
        "datasets": {
            "change": config.data["change"]["dataset"],
            "ice": config.data["ice"]["dataset"],
            "ice_reference": config.data["ice"]["reference_dataset"],
            "vessel_events": config.data["vessels"]["events_dataset"],
            "sar_detections": config.data["vessels"]["sar_dataset"],
        },
        "notes": notes,
        "outputs": {},
    }
    for output in outputs:
        if output.exists() and output.is_file():
            rel = str(output.relative_to(config.root)).replace("\\", "/")
            manifest["outputs"][rel] = {"sha256": sha256(output), "bytes": output.stat().st_size}
    write_json(manifest_path, manifest)
    return manifest_path

