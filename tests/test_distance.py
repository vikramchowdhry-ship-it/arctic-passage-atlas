from pathlib import Path

import pytest

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.distance import haversine_m, max_distance_to_point_nmi

ROOT = Path(__file__).resolve().parents[1]
PROVIDER_THRESHOLD_NMI = 50


def test_one_degree_of_latitude_is_about_111_km():
    assert haversine_m(0, 0, 0, 1) == pytest.approx(111_195, rel=0.002)


def test_reference_point_must_be_inside_box():
    with pytest.raises(ValueError):
        max_distance_to_point_nmi((0, 0, 1, 1), 5, 5)


def test_study_area_is_entirely_within_provider_threshold_of_a_known_land_point():
    config = load_config(ROOT / "configs" / "cambridge-bay.json")
    ref = config.data["aoi"]["shore_reference_point"]
    bound = max_distance_to_point_nmi(config.bbox, ref["lon"], ref["lat"])
    assert 15 < bound < 20  # recorded in docs/DECISIONS.md
    assert bound < PROVIDER_THRESHOLD_NMI
