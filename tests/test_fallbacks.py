import shutil
from pathlib import Path

import pytest

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.fallbacks import (
    FeatureGroup,
    _geometry,
    _plot_bounds,
    _point,
    _render,
    write_fallbacks,
)

ROOT = Path(__file__).resolve().parents[1]


def _temp_config(tmp_path: Path):
    (tmp_path / "configs").mkdir()
    shutil.copy(ROOT / "configs" / "cambridge-bay.json", tmp_path / "configs" / "cambridge-bay.json")
    return load_config(tmp_path / "configs" / "cambridge-bay.json")


def _point_feature(longitude=-105.1, latitude=69.15, **properties):
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [longitude, latitude]},
        "properties": properties,
    }


def test_projection_fits_bbox_without_stretching(tmp_path):
    config = _temp_config(tmp_path)
    west, south, east, north = config.bbox
    left, top, width, height = _plot_bounds(config.bbox)

    assert _point([west, north], config.bbox) == pytest.approx((left, top))
    assert _point([east, south], config.bbox) == pytest.approx((left + width, top + height))
    assert 0.9 < width / height < 1.1


def test_demo_and_live_labels_are_distinct_and_title_is_escaped(tmp_path):
    config = _temp_config(tmp_path)
    groups = [FeatureGroup([_point_feature()], "#ffffff", "points")]

    demo_path = _render(config, "test", "A <test>", groups, "demo")
    demo = demo_path.read_text(encoding="utf-8")
    live_path = _render(config, "test", "A <test>", groups, "live")
    live = live_path.read_text(encoding="utf-8")

    assert "DEMONSTRATION FIXTURE" in demo
    assert "PROVIDER-BACKED OUTPUT" in live
    assert "DEMONSTRATION" not in live
    assert "A &lt;test&gt;" in live


def test_empty_features_still_write_valid_svg(tmp_path):
    config = _temp_config(tmp_path)
    path = _render(config, "empty", "Empty", [FeatureGroup([], "#ffffff", "none")], "demo")
    text = path.read_text(encoding="utf-8")

    assert text.startswith('<svg xmlns="http://www.w3.org/2000/svg"')
    assert "0 mapped features" in text
    assert text.rstrip().endswith("</svg>")


def test_multipolygon_renders_one_path_per_polygon(tmp_path):
    config = _temp_config(tmp_path)
    polygon = [[[-105.2, 69.1], [-105.1, 69.1], [-105.1, 69.2], [-105.2, 69.1]]]
    feature = {
        "type": "Feature",
        "geometry": {"type": "MultiPolygon", "coordinates": [polygon, polygon]},
        "properties": {},
    }

    assert _geometry(feature, config.bbox, "#ffffff").count("<path ") == 2


def test_mode_must_be_demo_or_live(tmp_path):
    config = _temp_config(tmp_path)
    with pytest.raises(ValueError, match="mode must"):
        write_fallbacks(config, [], [], [], [], mode="typo")  # type: ignore[arg-type]


def test_vessel_legend_and_detection_scaled_markers(tmp_path):
    config = _temp_config(tmp_path)
    gaps = [_point_feature()]
    sar = [_point_feature(detections=1), _point_feature(-105.0, 69.2, detections=16)]
    path = write_fallbacks(config, [], [], gaps, sar, mode="live")[2]
    text = path.read_text(encoding="utf-8")

    assert "AIS gap" in text
    assert "SAR detections" in text
    assert 'r="8.0"' in text
    assert 'r="17.0"' in text


def test_renderer_caps_large_feature_collections(tmp_path, monkeypatch):
    config = _temp_config(tmp_path)
    monkeypatch.setattr("arctic_passage_atlas.fallbacks.MAX_TOTAL_FEATURES", 2)
    features = [_point_feature(longitude=-105.4 + index * 0.1) for index in range(4)]
    path = _render(
        config,
        "capped",
        "Capped",
        [FeatureGroup(features, "#ffffff", "points")],
        "live",
    )
    text = path.read_text(encoding="utf-8")

    assert "2 of 4 mapped features shown" in text
    assert text.count("<circle ") == 3  # two features plus one legend marker
