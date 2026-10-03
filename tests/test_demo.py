import json
import shutil
from pathlib import Path

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.demo import generate_demo
from arctic_passage_atlas.site import build_site_data

ROOT = Path(__file__).resolve().parents[1]


def _temp_project(tmp_path: Path):
    (tmp_path / "configs").mkdir()
    shutil.copy(ROOT / "configs" / "cambridge-bay.json", tmp_path / "configs" / "cambridge-bay.json")
    return load_config(tmp_path / "configs" / "cambridge-bay.json")


def test_demo_outputs_are_explicitly_synthetic(tmp_path):
    config = _temp_project(tmp_path)
    outputs = generate_demo(config)
    assert outputs
    change = json.loads((tmp_path / "data" / "processed" / "change_candidates.geojson").read_text())
    assert change["demo"] is True
    assert all(feature["properties"]["demo"] is True for feature in change["features"])


def test_site_bundle_embeds_processed_data(tmp_path):
    config = _temp_project(tmp_path)
    generate_demo(config)
    bundle = build_site_data(config)
    text = bundle.read_text(encoding="utf-8")
    assert text.startswith("window.ATLAS_DATA = ")
    assert "Synthetic demonstration fixture" in text

