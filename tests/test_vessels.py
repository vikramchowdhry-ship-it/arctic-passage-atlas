import asyncio
import json
import re
from pathlib import Path

import pytest

from arctic_passage_atlas.config import load_config
from arctic_passage_atlas.demo import generate_demo
from arctic_passage_atlas.vessels import (
    GAP_INTERPRETATION,
    _normalise_gap,
    redact_fixture,
    run_vessels,
)

ROOT = Path(__file__).resolve().parents[1]


def _temp_config(tmp_path: Path, max_events: int = 1000):
    source = (ROOT / "configs" / "cambridge-bay.json").read_text(encoding="utf-8")
    source = source.replace('"max_events": 1000', f'"max_events": {max_events}')
    path = tmp_path / "configs" / "cambridge-bay.json"
    path.parent.mkdir()
    path.write_text(source, encoding="utf-8")
    return load_config(path)


def _assumed_gap_record():
    """Hand-written schema assumption; replace with a redacted real response after first live use."""
    return {
        "id": "event-1",
        "start": "2024-01-01T00:00:00Z",
        "end": "2024-01-02T00:00:00Z",
        "gap": {
            "off_position": {"lat": 69.1, "lon": -105.2},
            "on_position": {"lat": 69.2, "lon": -105.0},
            "duration_hours": 24,
        },
        "vessel": {"id": "private-vessel-id", "type": "cargo"},
    }


def test_gap_with_two_positions_becomes_line():
    feature = _normalise_gap(_assumed_gap_record())
    assert feature is not None
    assert feature["geometry"]["type"] == "LineString"
    assert "vessel_id" not in feature["properties"]
    assert feature["properties"]["interpretation"] == GAP_INTERPRETATION


@pytest.mark.parametrize(
    ("record", "expected"),
    [
        ({"position": {"longitude": -105.2, "latitude": 69.1}}, [-105.2, 69.1]),
        ({"gap": {"start_position": {"lon": -105.3, "lat": 69.2}}}, [-105.3, 69.2]),
        ({"nested": {"startPosition": {"coordinates": [-105.4, 69.3]}}}, [-105.4, 69.3]),
        ({"gap": {"end_position": {"lon": -105.0, "lat": 69.0}}}, [-105.0, 69.0]),
        ({"nested": {"endPosition": {"coordinates": [-104.9, 69.1]}}}, [-104.9, 69.1]),
    ],
)
def test_single_position_variants_become_points(record, expected):
    feature = _normalise_gap(record)
    assert feature is not None
    assert feature["geometry"] == {"type": "Point", "coordinates": expected}


def test_missing_duration_and_non_dict_nested_values_are_safe():
    feature = _normalise_gap(
        {
            "position": {"lon": -105.1, "lat": 69.1},
            "gap": "not-an-object",
            "vessel": "not-an-object",
        }
    )
    assert feature is not None
    assert feature["properties"]["duration_hours"] is None
    assert feature["properties"]["vessel_type"] is None
    assert feature["properties"]["flag"] is None


def test_gap_without_position_is_not_mapped():
    assert _normalise_gap({"id": "event-2"}) is None


def test_fixture_redaction_preserves_shape_and_removes_vessel_identifiers():
    response = {
        "id": "event-1",
        "vessel": {"mmsi": "123456789", "shipname": "Example", "flag": "CA"},
        "nested": [{"callsign": "CALL", "imo": "123"}],
    }
    redacted = redact_fixture(response)

    assert redacted["id"] == "event-1"
    assert redacted["vessel"]["mmsi"] == "REDACTED"
    assert redacted["vessel"]["shipname"] == "REDACTED"
    assert redacted["vessel"]["flag"] == "CA"
    assert redacted["nested"][0]["callsign"] == "REDACTED"


def test_missing_token_fails_before_client_use(tmp_path, monkeypatch):
    config = _temp_config(tmp_path)
    monkeypatch.delenv("GFW_API_ACCESS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="GFW_API_ACCESS_TOKEN is not set"):
        asyncio.run(run_vessels(config))


def test_run_vessels_filters_skips_invalid_sar_and_warns_on_limit(tmp_path, monkeypatch):
    config = _temp_config(tmp_path, max_events=2)
    monkeypatch.setenv("GFW_API_ACCESS_TOKEN", "test-token")
    calls = {}

    class Result:
        def __init__(self, records):
            self.records = records

        def data(self):
            return self.records

    class Events:
        async def get_all_events(self, **kwargs):
            calls["events"] = kwargs
            second = {"id": "event-2", "position": {"lon": -105.0, "lat": 69.0}}
            return Result([_assumed_gap_record(), second])

    class FourWings:
        async def create_sar_presence_report(self, **kwargs):
            calls["sar"] = kwargs
            return Result(
                [
                    {
                        "lon": -105.1,
                        "lat": 69.1,
                        "detections": 3,
                        "vessel_ids": ["private-vessel-id"],
                    },
                    {"lat": 69.2, "detections": 8},
                ]
            )

    class Client:
        def __init__(self, access_token):
            calls["token"] = access_token
            self.events = Events()
            self.fourwings = FourWings()

    monkeypatch.setattr("gfwapiclient.Client", Client)
    outputs = asyncio.run(run_vessels(config))

    assert len(outputs) == 3
    assert calls["token"] == "test-token"
    assert calls["events"]["limit"] == 2
    assert calls["sar"]["filters"] == ["matched='false'"]
    summary = json.loads((tmp_path / "data" / "processed" / "vessel_summary.json").read_text())
    sar = json.loads((tmp_path / "data" / "processed" / "sar_detections.geojson").read_text())
    gaps = json.loads((tmp_path / "data" / "processed" / "vessel_events.geojson").read_text())
    assert summary["possibly_truncated"] is True
    assert "may be truncated" in summary["limitations"][-1]
    assert summary["sar_cell_count"] == 1
    assert any("50 nautical miles" in limitation for limitation in summary["limitations"])
    assert any("empty SAR layer is not evidence" in limitation for limitation in summary["limitations"])
    assert "vessel_ids" not in json.dumps(sar)
    assert "private-vessel-id" not in json.dumps(gaps)
    assert re.search(
        r"\b(dark|suspicious|evasion)\b",
        json.dumps([summary, sar, gaps]),
        re.IGNORECASE,
    ) is None


def test_demo_vessel_outputs_do_not_assign_prohibited_labels(tmp_path):
    config = _temp_config(tmp_path)
    generate_demo(config)
    processed = tmp_path / "data" / "processed"
    values = [
        json.loads((processed / name).read_text(encoding="utf-8"))
        for name in ("vessel_events.geojson", "sar_detections.geojson", "vessel_summary.json")
    ]
    public_output = json.dumps(values)
    assert re.search(r"\b(dark|suspicious|evasion)\b", public_output, re.IGNORECASE) is None
    assert any("50 nautical miles" in limitation for limitation in values[2]["limitations"])
