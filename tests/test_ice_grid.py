"""Sea-ice grid: projection maths, cleaning, resampling, shipped files, and ice-aware routing under Node."""

import json
import shutil
import subprocess
from datetime import date
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from arctic_passage_atlas.ice_grid import CELL_M, E2, X0, Y0, A, clean, file_url, project, resample

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "site" / "data" / "route"


def test_projection_has_its_origin_on_the_central_meridian_and_pole():
    x, y = project(np.array([-45.0, 0.0]), np.array([70.0, 90.0]))
    assert abs(x[0]) < 1e-6                                   # on the central meridian
    true_scale_radius = A * np.cos(np.radians(70)) / np.sqrt(1 - E2 * np.sin(np.radians(70)) ** 2)
    assert y[0] == pytest.approx(-true_scale_radius, abs=1.0)  # south of the pole along 45 W
    assert abs(x[1]) < 1 and abs(y[1]) < 1                    # the pole


def test_cambridge_bay_falls_inside_the_file():
    x, y = project(np.array([-105.1]), np.array([69.1]))
    col, row = (x[0] - X0) / CELL_M, (Y0 - y[0]) / CELL_M
    assert 0 <= col < 304 and 0 <= row < 448


def test_clean_converts_tenths_fills_coast_and_treats_pole_hole_as_ice():
    raw = np.array([[500, 2540, 0], [2530, 1000, 2510], [0, 0, 0]], dtype=np.uint16)
    out = clean(raw)
    assert out[0, 0] == 50.0 and out[1, 1] == 100.0 and out[1, 2] == 100.0
    assert not np.isnan(out).any() and 0 <= out.min() and out.max() <= 100
    assert out[0, 1] > 0                                       # coast cell took its value from ocean neighbours


def test_resample_is_zero_outside_the_file_and_follows_the_data():
    conc = np.full((448, 304), 80.0, dtype=np.float32)
    inside = resample(conc, (-110.0, 69.0, -100.0, 70.0), 0.5, 0.5)
    outside = resample(conc, (0.0, -20.0, 10.0, 0.0), 1.0, 1.0)
    assert np.allclose(inside, 80.0) and not outside.any()


def test_file_url_follows_the_provider_layout():
    assert file_url(date(2026, 10, 2)).endswith("/geotiff/2026/10_Oct/N_20261002_concentration_v4.0.tif")


def test_shipped_ice_files_have_provenance_and_the_route_grid_shape():
    meta = json.loads((ROUTE / "ice_grid.json").read_text(encoding="utf-8"))
    assert meta["source_url"].startswith("https://noaadata.apps.nsidc.org/") and meta["retrieved_at"] and meta["date"]
    assert "not an ice chart" in meta["caveat"].lower()
    for name, grid in (("arctic", "water"), ("world", "world")):
        ice = Image.open(ROUTE / f"ice_{name}.png")
        shape = json.loads((ROUTE / f"{grid}.json").read_text(encoding="utf-8"))
        assert ice.size == (shape["cols"], shape["rows"])
        assert np.array(ice).max() <= 100


SCRIPT = r"""
const fs = require('fs');
const meta = JSON.parse(fs.readFileSync(process.argv[1], 'utf8'));
const water = new Uint8Array(fs.readFileSync(process.argv[2]));
const ice = new Uint8Array(fs.readFileSync(process.argv[3]));
const ports = Object.fromEntries(JSON.parse(fs.readFileSync(process.argv[5], 'utf8')).ports.map(p => [p.id, [p.lon, p.lat]]));
const { createRouter } = require(process.argv[4]);
function make(threshold) {
  const w = Uint8Array.from(water);
  if (threshold > 0) for (let i = 0; i < w.length; i++) if (ice[i] >= threshold) w[i] = 0;
  return createRouter({ rows: meta.rows, cols: meta.cols, bbox: meta.bbox, dlon: meta.dlon, dlat: meta.dlat, wrap: true, water: w });
}
const open = make(0), safe = make(15);
const a = open.route(ports.rtm, ports.yok, 0, 150), b = safe.route(ports.rtm, ports.yok, 0, 150);
let bad = 0;
for (const [lon, lat] of b.coords.slice(1, -1)) {
  const c = safe.cellOf(((lon + 540) % 360) - 180, lat);
  if (ice[c.r * meta.cols + (c.c % meta.cols)] >= 15) bad++;
}
console.log(JSON.stringify({ open: a.km / 1.852, avoiding: b.km / 1.852, iceVertices: bad }));
"""


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")
def test_avoiding_ice_never_shortens_the_route_and_keeps_vertices_off_ice(tmp_path):
    water = (np.array(Image.open(ROUTE / "world.png").convert("L")) > 127).astype(np.uint8)
    ice = np.array(Image.open(ROUTE / "ice_world.png").convert("L")).astype(np.uint8)
    (tmp_path / "w.raw").write_bytes(water.tobytes())
    (tmp_path / "i.raw").write_bytes(ice.tobytes())
    out = subprocess.run(
        ["node", "-e", SCRIPT, str(ROUTE / "world.json"), str(tmp_path / "w.raw"), str(tmp_path / "i.raw"),
         str(ROOT / "site" / "assets" / "router.js"), str(ROUTE / "ports.json")],
        check=True, capture_output=True, text=True, timeout=180,
    )
    r = json.loads(out.stdout)
    assert r["avoiding"] >= r["open"] - 1
    assert r["iceVertices"] == 0
