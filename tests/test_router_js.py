"""Run the browser router under Node on the real coastline grid (skipped without Node)."""

import json
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const fs = require('fs');
const meta = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const water = new Uint8Array(fs.readFileSync(process.argv[2]));
const { createRouter } = require(process.argv[3]);
const R = createRouter({ rows: meta.rows, cols: meta.cols, bbox: meta.bbox, dlon: meta.dlon, dlat: meta.dlat, water });
const P = { tuk: [-133.021, 69.436], cb: [-105.116, 69.107], gjoa: [-95.85, 68.636], res: [-94.968, 74.706], pond: [-77.957, 72.693], clyde: [-68.517, 70.486] };
const out = {};
for (const [name, a, b] of [['tuk_cb', 'tuk', 'cb'], ['cb_gjoa', 'cb', 'gjoa'], ['gjoa_res', 'gjoa', 'res'], ['pond_clyde', 'pond', 'clyde'], ['tuk_pond', 'tuk', 'pond']]) {
  const r = R.route(P[a], P[b], 0);
  const mask = R.maskFor(0);
  const onLand = r.coords ? r.coords.slice(1, -1).filter(([lon, lat]) => { const c = R.cellOf(lon, lat); return !mask[c.r * meta.cols + c.c]; }).length : -1;
  out[name] = { km: r.km, straight: R.haversineKm(P[a], P[b]), error: r.error || null, vertices_on_land: onLand };
}
console.log(JSON.stringify(out));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_routes_exist_avoid_land_and_are_never_shorter_than_the_straight_line(tmp_path):
    water = (np.array(Image.open(ROOT / "site" / "data" / "route" / "water.png").convert("L")) > 127).astype(np.uint8)
    raw = tmp_path / "water.raw"
    raw.write_bytes(water.tobytes())
    out = subprocess.run(
        ["node", "-e", SCRIPT, str(ROOT / "site" / "data" / "route" / "water.json"), str(raw), str(ROOT / "site" / "assets" / "router.js")],
        check=True, capture_output=True, text=True,
    )
    results = json.loads(out.stdout)
    for name, r in results.items():
        assert r["error"] is None, f"{name}: {r['error']}"
        assert r["vertices_on_land"] == 0, f"{name} has route vertices on land"
        assert r["km"] >= r["straight"] * 0.999, f"{name} is shorter than the straight line"
        assert r["km"] < r["straight"] * 2.2, f"{name} is implausibly long"
