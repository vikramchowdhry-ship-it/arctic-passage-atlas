"""Export helpers and the EPSG:3413 maths in site/assets/tools.js, run under Node (skipped without Node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = r"""
const fs = require('fs'), vm = require('vm');
const win = {};
const ctx = { window: win, document: { addEventListener() {} }, setInterval() {}, URL, Blob, CustomEvent: class {}, maplibregl: {} };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), ctx);
const X = win.AtlasExport;
const csv = X.toCsv([{ a: 'x,y', b: 'say "hi"', c: 1 }, { a: 'line\nbreak', b: null, c: 2 }]);
const kml = X.toKml([{ type: 'Feature', properties: { name: 'A & B <1>', note: 'x' }, geometry: { type: 'Polygon', coordinates: [[[0, 0], [1, 0], [1, 1], [0, 0]]] } }], 'Layer <x>', 'SYNTHETIC & unverified');
console.log(JSON.stringify({
  csv, kml,
  origin: X.epsg3413(-45, 90),
  ts: X.epsg3413(-45, 70),
  east: X.epsg3413(45, 70),
  cb: X.epsg3413(-105.1, 69.1),
}));
"""


@pytest.fixture(scope="module")
def out():
    if shutil.which("node") is None:
        pytest.skip("Node is not installed")
    run = subprocess.run(["node", "-e", SCRIPT, str(ROOT / "site" / "assets" / "tools.js")], check=True, capture_output=True, text=True)
    return json.loads(run.stdout)


def test_csv_quotes_commas_quotes_and_newlines(out):
    rows = out["csv"].split("\r\n")
    assert rows[0] == "a,b,c"
    assert rows[1] == '"x,y","say ""hi""",1'
    assert out["csv"].count('"line\nbreak"') == 1


def test_kml_escapes_markup_and_keeps_the_notice(out):
    kml = out["kml"]
    assert "SYNTHETIC &amp; unverified" in kml and "Layer &lt;x&gt;" in kml and "A &amp; B &lt;1&gt;" in kml
    assert "<Polygon>" in kml and "<coordinates>0.00000,0.00000,0" in kml


def test_polar_stereographic_origin_and_true_scale(out):
    assert abs(out["origin"][0]) < 1e-3 and abs(out["origin"][1]) < 1e-3          # the pole is the origin
    assert out["ts"][0] == pytest.approx(0, abs=1e-3)                            # 45 W is the central meridian
    assert out["ts"][1] == pytest.approx(-2188, abs=3)                           # about 2,188 km from the pole at 70 N
    assert out["east"][0] == pytest.approx(2188, abs=3)                          # 45 E is 90 degrees round: all x, no y
    assert abs(out["east"][1]) < 1e-3


def test_cambridge_bay_is_in_the_expected_quadrant(out):
    x, y = out["cb"]
    assert x < 0 and y < 0                                      # west of 45 W and south of the pole in this projection
