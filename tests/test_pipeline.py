import json
import shutil
from pathlib import Path

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.pipeline import publication_blockers, run_demo, run_live

ROOT = Path(__file__).resolve().parents[1]


def _temp_project(tmp_path: Path):
    (tmp_path / "configs").mkdir()
    shutil.copy(ROOT / "configs" / "cambridge-bay.json", tmp_path / "configs" / "cambridge-bay.json")
    return load_config(tmp_path / "configs" / "cambridge-bay.json")


def test_partial_live_run_does_not_republish_demo_site(tmp_path, monkeypatch):
    config = _temp_project(tmp_path)
    run_demo(config)
    manifest_path = tmp_path / "data" / "processed" / "manifest.json"
    bundle_path = tmp_path / "site" / "assets" / "data.js"
    original_manifest = manifest_path.read_bytes()
    original_bundle = bundle_path.read_bytes()

    async def fake_vessels(_config):
        return []

    monkeypatch.setattr("arctic_passage_atlas.vessels.run_vessels", fake_vessels)
    run_live(config, ["vessels"])

    assert manifest_path.read_bytes() == original_manifest
    assert bundle_path.read_bytes() == original_bundle
    assert json.loads(manifest_path.read_text(encoding="utf-8"))["mode"] == "demo"


def test_live_publication_requires_analytical_review(tmp_path):
    config = _temp_project(tmp_path)
    blockers = publication_blockers(config)
    assert any("ice.threshold_status" in blocker for blocker in blockers)
    assert any("change.threshold_status" in blocker for blocker in blockers)
    assert any("manual_review_status" in blocker for blocker in blockers)

    config.data["ice"]["threshold_status"] = "validated"
    config.data["change"]["threshold_status"] = "validated"
    config.data["change"]["manual_review_status"] = "complete"
    assert publication_blockers(config) == []

