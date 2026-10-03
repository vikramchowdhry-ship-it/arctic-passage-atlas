import json
import shutil
from pathlib import Path

import pytest

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.pipeline import run_demo
from arctic_passage_atlas.verify import VerificationError, verify_project

ROOT = Path(__file__).resolve().parents[1]


def _temp_project(tmp_path: Path):
    (tmp_path / "configs").mkdir()
    shutil.copy(ROOT / "configs" / "cambridge-bay.json", tmp_path / "configs" / "cambridge-bay.json")
    shutil.copytree(ROOT / "site", tmp_path / "site")
    return load_config(tmp_path / "configs" / "cambridge-bay.json")


def test_verify_rejects_changed_published_output(tmp_path):
    config = _temp_project(tmp_path)
    run_demo(config)
    summary = tmp_path / "data" / "processed" / "change_summary.json"
    summary.write_text(summary.read_text(encoding="utf-8") + "\n", encoding="utf-8")

    with pytest.raises(VerificationError, match="checksum mismatch"):
        verify_project(config)


def test_verify_rejects_manifest_summary_mode_mismatch(tmp_path):
    config = _temp_project(tmp_path)
    run_demo(config)
    manifest_path = tmp_path / "data" / "processed" / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["mode"] = "live"
    manifest["demo_data"] = False
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(VerificationError, match="does not match summaries"):
        verify_project(config)
