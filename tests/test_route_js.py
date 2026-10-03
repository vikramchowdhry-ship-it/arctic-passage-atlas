"""Run the route page's sun maths and the router's distance maths under Node (skipped without Node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const fs = require('fs');
const src = fs.readFileSync(process.argv[1], 'utf8');
const code = src.slice(src.indexOf('function rad'), src.indexOf('function utc')) +
  src.slice(src.indexOf('function solar'), src.indexOf('function sunState')) + ';globalThis.F = { elevation, daylightMs };';
eval(code);
const { createRouter } = require(process.argv[2]);
const R = createRouter({ rows: 2, cols: 2, bbox: [0, 0, 1, 1], dlon: 0.5, dlat: 0.5, water: new Uint8Array(4).fill(1) });
const at = (lat, lon, iso) => new Date(iso);
const london = globalThis.F.daylightMs(51.5, 0, at(0, 0, '2026-06-21T12:00:00Z')) / 3600000;
console.log(JSON.stringify({
  resolute_dec_daylight_h: globalThis.F.daylightMs(74.706, -94.968, at(0, 0, '2026-12-01T12:00:00Z')) / 3600000,
  resolute_jun_daylight_h: globalThis.F.daylightMs(74.706, -94.968, at(0, 0, '2026-06-21T12:00:00Z')) / 3600000,
  london_daylight_h: london,
  london_noon_elevation: globalThis.F.elevation(51.5, 0, at(0, 0, '2026-06-21T12:02:00Z')),
  london_midnight_elevation: globalThis.F.elevation(51.5, 0, at(0, 0, '2026-06-21T00:02:00Z')),
  one_degree_lat_km: R.haversineKm([0, 0], [0, 1]),
}));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_sun_and_distance_maths():
    out = subprocess.run(
        ["node", "-e", SCRIPT, str(ROOT / "site" / "assets" / "route.js"), str(ROOT / "site" / "assets" / "router.js")],
        check=True, capture_output=True, text=True,
    )
    r = json.loads(out.stdout)
    assert r["resolute_dec_daylight_h"] == 0                      # polar night
    assert r["resolute_jun_daylight_h"] == 24                     # midnight sun
    assert r["london_daylight_h"] == pytest.approx(16.64, abs=0.15)
    assert r["london_noon_elevation"] == pytest.approx(61.9, abs=0.6)   # 90 - 51.5 + 23.44
    assert r["london_midnight_elevation"] < -10                   # sun well below the horizon
    assert r["one_degree_lat_km"] == pytest.approx(111.19, abs=0.3)
