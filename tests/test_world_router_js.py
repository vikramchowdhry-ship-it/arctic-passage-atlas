"""Run the browser router on the real worldwide grid under Node (skipped without Node).

Reference figures are approximate published port-to-port distances. The grid is 0.1 degrees, so the
checks are wide bands that catch a closed canal, a missing antimeridian wrap or a route over land, not
precise distance claims.
"""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "site" / "data" / "route"
SCRIPT = r"""
const fs = require('fs');
const meta = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const water = new Uint8Array(fs.readFileSync(process.argv[2]));
const ports = Object.fromEntries(JSON.parse(fs.readFileSync(process.argv[4], 'utf8')).ports.map(p => [p.id, [p.lon, p.lat]]));
const { createRouter } = require(process.argv[3]);
const R = createRouter({ rows: meta.rows, cols: meta.cols, bbox: meta.bbox, dlon: meta.dlon, dlat: meta.dlat, wrap: true, water });
const mask = R.maskFor(0);
const out = {};
for (const [a, b] of [['rtm', 'sin'], ['yok', 'lax'], ['nyc', 'lax'], ['psd', 'jed'], ['hnl', 'yvr'], ['syd', 'akl']]) {
  const r = R.route(ports[a], ports[b], 0, 150);
  let onLand = 0;
  if (r.coords) for (const [lon, lat] of r.coords.slice(1, -1)) {
    const c = R.cellOf(((lon + 540) % 360) - 180, lat); if (!mask[c.r * meta.cols + c.c % meta.cols]) onLand++;
  }
  out[a + '_' + b] = { nm: r.km ? r.km / 1.852 : null, error: r.error || null, onLand,
    span: r.coords ? Math.max(...r.coords.map(c => c[0])) - Math.min(...r.coords.map(c => c[0])) : null };
}
console.log(JSON.stringify(out));
"""


@pytest.fixture(scope="module")
def results(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("Node is not installed")
    water = (np.array(Image.open(ROUTE / "world.png").convert("L")) > 127).astype(np.uint8)
    raw = tmp_path_factory.mktemp("world") / "world.raw"
    raw.write_bytes(water.tobytes())
    out = subprocess.run(
        ["node", "-e", SCRIPT, str(ROUTE / "world.json"), str(raw), str(ROOT / "site" / "assets" / "router.js"), str(ROUTE / "ports.json")],
        check=True, capture_output=True, text=True, timeout=120,
    )
    return json.loads(out.stdout)


def test_every_pair_connects_and_stays_on_water(results):
    for name, r in results.items():
        assert r["error"] is None, name
        assert r["onLand"] == 0, name


def test_suez_canal_is_open(results):
    # Rotterdam to Singapore is about 8,300 nm through Suez and about 11,700 nm around the Cape.
    assert 7800 < results["rtm_sin"]["nm"] < 9000
    assert 600 < results["psd_jed"]["nm"] < 1000          # Port Said to Jeddah runs the length of the canal and Red Sea


def test_panama_canal_is_open(results):
    # New York to Los Angeles is about 5,400 nm via Panama and about 13,000 nm around Cape Horn.
    assert 4500 < results["nyc_lax"]["nm"] < 6500


def test_route_wraps_across_the_antimeridian(results):
    # Yokohama to Los Angeles across the Pacific is about 4,800 nm. Going the long way round the world would
    # be several times that.
    assert 4300 < results["yok_lax"]["nm"] < 5500
    assert results["yok_lax"]["span"] > 100                # unwrapped longitudes run continuously through 180


def test_port_lists_resolve_to_water(results):
    assert 2000 < results["hnl_yvr"]["nm"] < 2800
    assert 1000 < results["syd_akl"]["nm"] < 1700


def test_ports_file_is_complete_and_unique():
    data = json.loads((ROUTE / "ports.json").read_text(encoding="utf-8"))
    ids = [p["id"] for p in data["ports"]]
    assert len(ids) == len(set(ids)) >= 30
    assert all(-90 <= p["lat"] <= 90 and -180 <= p["lon"] <= 180 and p["name"] and p["country"] and p["region"] for p in data["ports"])
