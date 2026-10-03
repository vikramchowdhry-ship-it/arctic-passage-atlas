"""Client-side vessel logic (site/assets/vessels-live.js) under Node: anonymising and lake coverage."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const m = require('./site/assets/vessels-live.js');
const now = Date.parse('2026-10-03T12:00:00Z');
const f = (mmsi, lon, lat, sog, cog, t) => ({ type: 'Feature', geometry: { type: 'Point', coordinates: [lon, lat] }, properties: { mmsi, sog, cog, heading: 511, timestampExternal: t } });
const out = m.fromDigitraffic({ features: [f(1, 25.123456, 65.123456, 10.04, 90.2, now - 30000), f(2, 20, 60, 5, 5, now), f(3, 21, 61, 133, 400, now)] }, { 1: 72, 2: 35, 3: 0 }, now);
const rel = require('fs').readFileSync('./ais-relay/logic.mjs', 'utf8');
const boxes = [...rel.matchAll(/\[\[(-?\d+), (-?\d+)\], \[(-?\d+), (-?\d+)\]\]/g)].map(x => x.slice(1).map(Number));
const FIN = [59.5, 19, 66, 33];   // Digitraffic coverage: Finnish waters, Baltic and Gulf of Bothnia
const covered = m.LAKES.map(l => {
  const [name, , s, w, n, e, who] = l;
  const inBox = boxes.some(([s1, w1, n1, e1]) => s >= s1 && n <= n1 && w >= w1 && e <= e1);
  const inFin = s >= FIN[0] && n <= FIN[2] && w >= FIN[1] && e <= FIN[3];
  return { name, who, inBox, inFin };
});
console.log(JSON.stringify({ out, text: JSON.stringify(out), covered, n: m.LAKES.length }));
"""


@pytest.fixture(scope="module")
def result():
    if shutil.which("node") is None:
        pytest.skip("Node is not installed")
    run = subprocess.run(["node", "-e", SCRIPT], cwd=ROOT, check=True, capture_output=True, text=True)
    return json.loads(run.stdout)


def test_digitraffic_records_are_anonymous_and_clean(result):
    assert len(result["out"]) == 2                              # the military vessel (type 35) is dropped
    assert "mmsi" not in result["text"].lower()
    a = next(v for v in result["out"] if v["cls"] == "cargo")
    assert a["lat"] == 65.123 and a["lon"] == 25.123 and a["age_s"] == 30
    b = next(v for v in result["out"] if v["cls"] == "unknown")
    assert b["sog"] is None and b["cog"] is None                # "not available" speed 133 and course 400


def test_every_lake_is_heard_by_a_real_source(result):
    assert result["n"] >= 25
    for lake in result["covered"]:
        assert lake["inBox"] or lake["inFin"], lake["name"]    # inside a relay box or the Finnish feed area
        if "Digitraffic" in lake["who"]:
            assert lake["inFin"], lake["name"]                  # a lake claimed for the open feed must lie in its area
