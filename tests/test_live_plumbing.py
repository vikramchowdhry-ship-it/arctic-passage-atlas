"""Run the live Earth Engine code paths against a stand-in `ee`.

This catches wiring mistakes (undefined names, wrong keys, bad summaries). It says nothing about
whether the analysis is scientifically right; only a real run can do that.
"""

import json
from pathlib import Path

import pytest

from arctic_passage_atlas import change, ice
from arctic_passage_atlas.config import ConfigError, load_config
from arctic_passage_atlas.ice_inventory import inventory_ice

ROOT = Path(__file__).resolve().parents[1]


class Info(dict):
    """Stands in for any getInfo() result: a feature collection, a number and a percentile dict."""

    def __init__(self, number=3.0):
        super().__init__({"type": "FeatureCollection", "features": []})
        self.number = number

    def __int__(self):
        return int(self.number)

    def __float__(self):
        return float(self.number)

    def items(self):
        return [("HH_p5", -22.0), ("HH_p50", -17.5), ("HH_p95", -9.0), ("HH_p25", None)]


class Chain:
    """Any attribute or call returns another Chain; getInfo returns Info."""

    def __init__(self, log):
        self._log = log

    def __getattr__(self, name):
        self._log.append(name)
        return self

    def __call__(self, *args, **kwargs):
        self._log.append(("call", kwargs))
        return self

    def getInfo(self):
        return Info()


NULLS = '"thresholds_db": { "HH": null, "VV": null, "HV": null, "VH": null }'
TEST_THRESHOLDS = '"thresholds_db": { "HH": null, "VV": null, "HV": -25.0, "VH": null }'


def _project(tmp_path: Path, replacements: dict[str, str] | None = None):
    (tmp_path / "configs").mkdir()
    text = (ROOT / "configs" / "cambridge-bay.json").read_text(encoding="utf-8")
    for old, new in (replacements or {}).items():
        assert old in text
        text = text.replace(old, new)
    path = tmp_path / "configs" / "cambridge-bay.json"
    path.write_text(text, encoding="utf-8")
    (tmp_path / "data" / "processed").mkdir(parents=True)
    return load_config(path)


def test_run_ice_writes_summary_with_provisional_threshold_and_percentiles(tmp_path):
    log: list = []
    config = _project(
        tmp_path,
        {
            NULLS: TEST_THRESHOLDS,
            '"water_mask_expected_fraction": [0.10, 0.95]': '"water_mask_expected_fraction": [0.0, 1.0]',
        },
    )  # test-only values, not a calibration
    outputs = ice.run_ice(config, Chain(log))
    assert len(outputs) == 2
    summary = json.loads((tmp_path / "data" / "processed" / "ice_summary.json").read_text())
    assert summary["mode"] == "live"
    assert summary["threshold_status"] == config.data["ice"]["threshold_status"]
    assert summary["threshold_db"] == -25.0
    assert summary["acquisition"]["polarization"] == "HV"
    jan = summary["monthly"][0]
    assert jan["period"] == "2024-01"
    assert jan["backscatter_percentiles_db"] == {"p5": -22.0, "p50": -17.5, "p95": -9.0}
    assert all(not (isinstance(item, tuple) and item[1].get("bestEffort")) for item in log if isinstance(item, tuple))


def test_run_ice_refuses_a_polarisation_without_a_threshold(tmp_path):
    config = _project(
        tmp_path,
        {
            NULLS: TEST_THRESHOLDS,
            '"instrument_mode": "AUTO"': '"instrument_mode": "EW"',
            '"polarization": "AUTO"': '"polarization": "VH"',
        },
    )
    with pytest.raises(ConfigError, match="VH"):
        ice.run_ice(config, Chain([]))


def test_run_change_writes_masked_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(change, "_download_thumbnail", lambda image, path, region, vis: (path.parent.mkdir(parents=True, exist_ok=True), path.touch()))
    config = _project(tmp_path)
    outputs = change.run_change(config, Chain([]))
    assert len(outputs) == 5
    summary = json.loads((tmp_path / "data" / "processed" / "change_summary.json").read_text())
    assert summary["vector_scale_m"] == 30
    assert summary["minimum_candidate_pixels"] == config.data["change"]["minimum_candidate_pixels"]
    assert set(summary["candidate_area_km2_sensitivity"]) == {"low_threshold", "high_threshold"}
    assert "WorldCover" in summary["mask"]
    assert "not confirmed construction" in summary["claim"]


def test_run_ice_refuses_when_no_threshold_is_calibrated(tmp_path):
    config = _project(tmp_path)  # shipped config: every threshold is null until calibrated
    with pytest.raises(RuntimeError, match="configured ice threshold"):
        ice.run_ice(config, Chain([]))


def test_ice_inventory_writes_calibration_evidence_without_a_threshold(tmp_path):
    config = _project(
        tmp_path,
        {'"water_mask_expected_fraction": [0.10, 0.95]': '"water_mask_expected_fraction": [0.0, 1.0]'},
    )
    outputs = inventory_ice(config, Chain([]))

    assert [path.name for path in outputs] == ["ice_inventory.json"]
    inventory = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert inventory["mode"] == "calibration_inventory"
    assert inventory["acquisition"]["polarization"] == "HV"
    assert inventory["monthly"][0]["backscatter_percentiles_db"] == {
        "p5": -22.0,
        "p50": -17.5,
        "p95": -9.0,
    }
