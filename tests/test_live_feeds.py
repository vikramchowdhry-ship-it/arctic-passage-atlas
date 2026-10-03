from datetime import date

import pytest

from arctic_passage_atlas.live_feeds import (
    BASELINE,
    parse_nsidc_extent,
    parse_station,
    summarise_extent,
)

HEADER = (
    "Year, Month, Day,     Extent,    Missing, Source Data\n"
    "YYYY,    MM,  DD, 10^6 sq km, 10^6 sq km, Source data product web sites: http://nsidc.org\n"
)


def _csv(rows: list[tuple[int, int, int, float]]) -> str:
    body = "".join(f"{y},    {m:02d},  {d:02d},      {e:.3f},      0.000, ['/x']\n" for y, m, d, e in rows)
    return HEADER + body


def test_parse_skips_header_rows_and_non_positive_extent():
    rows = parse_nsidc_extent(_csv([(2020, 10, 2, 5.5), (2020, 10, 3, 0.0)]))
    assert rows == {date(2020, 10, 2): 5.5}


def test_summary_ranks_latest_value_against_the_same_calendar_day():
    data = [(y, 10, 2, 6.0 + 0.1 * (y - 1990)) for y in range(1990, 2000)]
    data += [(2025, 10, 2, 4.0), (2026, 10, 2, 5.0)]
    summary = summarise_extent(parse_nsidc_extent(_csv(data)))
    assert summary["latest_date"] == "2026-10-02"
    assert summary["same_day_years_compared"] == 11
    assert summary["years_with_lower_extent"] == 1          # only 2025 (4.0) is lower than 5.0
    assert summary["rank_from_lowest"] == 2
    assert summary["lowest_on_record_same_day"] == {"year": 2025, "extent": 4.0}
    assert summary["baseline_period"] == f"{BASELINE[0]}-{BASELINE[1]}"


def test_series_use_one_366_slot_axis_and_leave_gaps_as_null():
    summary = summarise_extent(parse_nsidc_extent(_csv([(2025, 1, 1, 13.0), (2026, 1, 2, 12.5)])))
    this_year = summary["series"]["this_year"]["values"]
    assert len(this_year) == 366 and len(summary["series"]["baseline_mean"]) == 366
    assert this_year[1] == 12.5 and this_year[0] is None      # 2 Jan present, 1 Jan missing -> null, not 0


def test_empty_input_is_an_error():
    with pytest.raises(ValueError):
        summarise_extent({})


def test_station_parser_keeps_units_and_leaves_missing_values_missing():
    feature = {"properties": {
        "stn_nam-value": "CAMBRIDGE BAY GSN", "date_tm-value": "2026-10-03T16:14:00.000Z",
        "air_temp": -1.3, "air_temp-uom": "C", "rel_hum": None,
    }}
    out = parse_station(feature)
    assert out["air_temperature"] == {"value": -1.3, "unit": "C"}
    assert out["relative_humidity"] is None
    assert out["wind_speed_10m_10min"] is None
