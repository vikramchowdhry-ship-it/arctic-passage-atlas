from pathlib import Path

import pytest

from arctic_passage_atlas.config import ConfigError, load_config

ROOT = Path(__file__).resolve().parents[1]


def test_config_loads_and_builds_closed_polygon():
    config = load_config(ROOT / "configs" / "cambridge-bay.json")
    ring = config.geometry["coordinates"][0]
    assert ring[0] == ring[-1]
    assert config.slug == "cambridge-bay"


def test_gap_minimum_rejects_short_events(tmp_path):
    source = (ROOT / "configs" / "cambridge-bay.json").read_text(encoding="utf-8")
    source = source.replace('"minimum_gap_minutes": 720', '"minimum_gap_minutes": 60')
    path = tmp_path / "configs" / "bad.json"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    with pytest.raises(ConfigError, match="at least 720"):
        load_config(path)



def _write(tmp_path, old, new):
    source = (ROOT / "configs" / "cambridge-bay.json").read_text(encoding="utf-8")
    assert old in source
    path = tmp_path / "configs" / "edited.json"
    path.parent.mkdir(exist_ok=True)
    path.write_text(source.replace(old, new), encoding="utf-8")
    return path


def test_missing_polarisation_threshold_is_an_error():
    from arctic_passage_atlas.config import ice_threshold

    config = load_config(ROOT / "configs" / "cambridge-bay.json")
    with pytest.raises(ConfigError, match="HH"):
        ice_threshold(config.data, "HH")


def test_auto_selection_only_considers_polarisations_with_thresholds():
    from arctic_passage_atlas.config import usable_acquisitions
    from arctic_passage_atlas.ice import ACQUISITION_CANDIDATES

    config = load_config(ROOT / "configs" / "cambridge-bay.json")
    pols = {pol for _mode, pol in usable_acquisitions(config.data, ACQUISITION_CANDIDATES)}
    assert pols == set()


def test_unknown_polarisation_and_invalid_thresholds_are_rejected(tmp_path):
    old = '"thresholds_db": { "HH": null, "VV": null, "HV": null, "VH": null }'
    with pytest.raises(ConfigError, match="unknown polarisation"):
        load_config(_write(tmp_path, old, '"thresholds_db": { "XX": -16.0 }'))
    with pytest.raises(ConfigError, match="plausible"):
        load_config(_write(tmp_path, old, '"thresholds_db": { "HH": -90 }'))


def test_no_best_effort_in_analysis_code():
    # bestEffort lets Earth Engine silently coarsen the scale, so reported areas stop matching config.
    for name in ("ice.py", "change.py"):
        assert "bestEffort" not in (ROOT / "arctic_passage_atlas" / name).read_text(encoding="utf-8")
