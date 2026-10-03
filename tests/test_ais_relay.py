"""The AIS relay's anonymising logic (ais-relay/logic.mjs), run under Node (skipped without Node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
import { reduce, classify, summarise, BOXES } from './ais-relay/logic.mjs';
const now = Date.parse('2026-10-03T12:00:00Z');
const pos = (mmsi, lat, lon, sog, cog, extra = {}) => ({ MessageType: 'PositionReport', MetaData: { MMSI: mmsi, ShipName: 'SECRET NAME', time_utc: '2026-10-03 11:59:00.000000000 +0000 UTC', ...extra },
  Message: { PositionReport: { Valid: true, Latitude: lat, Longitude: lon, Sog: sog, Cog: cog, UserID: mmsi } } });
const stat = (mmsi, type) => ({ MessageType: 'ShipStaticData', MetaData: { MMSI: mmsi, ShipName: 'SECRET NAME' }, Message: { ShipStaticData: { Type: type, Destination: 'SECRET PORT', CallSign: 'XYZ' } } });
const msgs = [
  pos(1, 70.123456, -50.987654, 12.34, 180.4), pos(1, 70.2, -50.9, 12.4, 181), stat(1, 71),        // cargo, two reports: keep the latest
  pos(2, 78, 15, 0, 0), stat(2, 35),                                                                  // military: dropped
  pos(3, 69, 33, 9.9, 90), stat(3, 80),                                                               // tanker
  pos(4, 91, 181, 0, 0),                                                                              // AIS "not available" position: dropped
  pos(5, 66, 30, 102.3, 360),                                                                         // unknown speed and course, unknown type
  { MessageType: 'PositionReport', MetaData: { MMSI: 6 }, Message: { PositionReport: { Valid: false, Latitude: 60, Longitude: 10 } } },
];
const out = reduce(msgs, now);
console.log(JSON.stringify({ out, text: JSON.stringify(out), counts: summarise(out), classes: [classify(0), classify(30), classify(52), classify(36), classify(65), classify(75), classify(85), classify(95), classify(51), classify(55)], boxes: BOXES.length }));
"""


@pytest.fixture(scope="module")
def result():
    if shutil.which("node") is None:
        pytest.skip("Node is not installed")
    run = subprocess.run(["node", "--input-type=module", "-e", SCRIPT], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(run.stdout)


def test_no_identifiers_leave_the_relay(result):
    text = result["text"].upper()
    for secret in ("SECRET", "XYZ", "MMSI", "NAME", "DESTINATION"):
        assert secret not in text
    for vessel in result["out"]:
        assert set(vessel) == {"lat", "lon", "sog", "cog", "cls", "age_s"}


def test_dedupes_rounds_and_drops_military_and_invalid(result):
    out = result["out"]
    assert len(out) == 3                                       # cargo, tanker, unknown; military, invalid and Valid=false are gone
    cargo = next(v for v in out if v["cls"] == "cargo")
    assert cargo["lat"] == 70.2 and cargo["lon"] == -50.9      # latest report wins, rounded to 3 decimals
    assert cargo["age_s"] == 60
    unknown = next(v for v in out if v["cls"] == "unknown")
    assert unknown["sog"] is None and unknown["cog"] is None   # AIS "not available" values become null
    assert result["counts"] == {"cargo": 1, "tanker": 1, "unknown": 1}


def test_classification_table(result):
    assert result["classes"] == ["unknown", "fishing", "service", "pleasure", "passenger", "cargo", "tanker", "other", None, None]


def test_search_boxes_cover_the_arctic_and_split_the_antimeridian(result):
    assert result["boxes"] == 6
    text = (ROOT / "ais-relay" / "logic.mjs").read_text(encoding="utf-8")
    assert "[[50, 160], [75, 180]]" in text and "[[50, -180], [75, -140]]" in text


def test_the_relay_never_ships_a_key_or_a_wildcard_origin():
    worker = (ROOT / "ais-relay" / "worker.mjs").read_text(encoding="utf-8")
    assert "env.AISSTREAM_API_KEY" in worker and '"*"' not in worker
    for path in ROOT.rglob("*"):
        if path.is_file() and path.suffix in {".js", ".mjs", ".toml", ".json", ".md"} and "node_modules" not in path.parts:
            assert "APIKey\": \"" not in path.read_text(encoding="utf-8", errors="ignore")
