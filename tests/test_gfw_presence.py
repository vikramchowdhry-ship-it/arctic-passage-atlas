"""Anonymous shipping presence: binning, class mapping, and the guarantee that identifiers never survive."""

import json
from pathlib import Path

from arctic_passage_atlas.gfw_presence import (
    CELL,
    FORBIDDEN_KEYS,
    aggregate,
    bin_cell,
    finish,
    vessel_class,
)

ROOT = Path(__file__).resolve().parents[1]


def row(vid, lat, lon, hours, vtype, **extra):
    return {"vesselId": vid, "lat": lat, "lon": lon, "hours": hours, "vesselType": vtype, "mmsi": "123456789",
            "imo": "9999999", "shipName": "SECRET NAME", "callsign": "ABC", "flag": "XXX", **extra}


def test_cells_are_0_2_degree_and_centred():
    assert CELL == 0.2
    lat, lon = bin_cell(69.1, -105.12)
    assert abs(lat - 69.1) <= 0.1 and abs(lon + 105.1) <= 0.1
    assert bin_cell(69.01, -105.01) == bin_cell(69.19, -105.19)          # same cell
    assert bin_cell(69.01, -105.01) != bin_cell(69.21, -105.01)          # next cell north


def test_distinct_vessels_hours_and_classes_with_no_identifiers():
    rows = [row("a", 69.05, -105.05, 3, "CARGO"), row("a", 69.06, -105.06, 2, "CARGO"), row("b", 69.07, -105.04, 4, "PASSENGER"),
            row("c", 69.08, -105.03, 1, "FISHING"), row("d", 69.5, -104.0, 9, "SOMETHING_NEW")]
    out = finish(aggregate(rows))
    cell = next(c for c in out if abs(c[0] - 69.1) < 0.11 and abs(c[1] + 105.1) < 0.11)
    assert cell[2] == 3 and cell[3] == 10.0                               # vessels a, b, c; hours 3+2+4+1
    assert cell[4] == [1, 0, 1, 1, 0]                                      # cargo, tanker, passenger, fishing, other
    other = next(c for c in out if c[4] == [0, 0, 0, 0, 1])
    assert other[2] == 1 and vessel_class("TUG") == "other" and vessel_class(None) == "other"
    text = json.dumps(out).lower()
    for secret in ("secret", "123456789", "9999999", "abc", "xxx", "mmsi", "imo", "callsign", "flag"):
        assert secret not in text


def test_class_mapping():
    assert [vessel_class(x) for x in ("CARGO", "CARRIER", "BUNKER", "PASSENGER", "FISHING", "GEAR", "SEISMIC_VESSEL", "")] == [
        "cargo", "cargo", "tanker", "passenger", "fishing", "fishing", "other", "other"]


def test_the_published_file_has_provenance_and_no_identifier_keys():
    path = ROOT / "site" / "data" / "live" / "gfw_presence.json"
    if not path.exists():
        return
    d = json.loads(path.read_text(encoding="utf-8"))
    for field in ("source", "dataset", "date_start", "date_end", "retrieved_at", "license", "caveat", "cells"):
        assert d.get(field), field
    assert "CC BY-NC" in d["license"] and d["cells"] == len(d["data"])
    assert d["columns"] == ["lat", "lon", "vessels", "hours", "classes"]
    text = path.read_text(encoding="utf-8").lower()
    for key in FORBIDDEN_KEYS:
        assert f'"{key}"' not in text, key
    assert all(len(r) == 5 and isinstance(r[4], list) and len(r[4]) == 5 for r in d["data"][:200])
    assert d["class_order"] == ["cargo", "tanker", "passenger", "fishing", "other"]
