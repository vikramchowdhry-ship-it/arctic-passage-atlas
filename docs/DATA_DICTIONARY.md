# Processed data dictionary

## `change_candidates.geojson`

- `candidate_id`: stable only for demonstration fixtures.
- `change_magnitude`: demonstration value when present. Live polygons store the configured threshold and pixel counts rather than an average magnitude.
- `interpretation`: required restrained label.
- `demo`: whether the feature is synthetic.

## `ice_extent.geojson`

- `period`: calendar month represented by the composite; it is not a synthetic mid-month date.
- `period_start`, `period_end`: exact live query bounds, with the end treated as exclusive.
- `threshold_db`: threshold applied to the selected backscatter band.
- `instrument_mode`, `polarization`: resolved Sentinel-1 acquisition fields for live outputs.
- `classified_fraction`: demonstration-only convenience field.
- `demo`: whether the feature is synthetic.

## `vessel_events.geojson`

- `event_id`: provider or fixture identifier.
- `event_type`: always labelled as an AIS gap event.
- `start`, `end`: provider timestamps when available.
- `duration_hours`: provider duration when available; never inferred from a missing value.
- `vessel_type`, `flag`: provider fields when available. Direct vessel identifiers are not published.
- `interpretation`: states that cause is not established.
- `demo`: whether the feature is synthetic.

Geometry is a start-to-end line when both coordinates are available, otherwise a provider event point.

## `sar_detections.geojson`

- `cell_id`: publication identifier for an aggregated report cell.
- `date`: report time bucket.
- `detections`: count reported for the cell.
- `matched_filter`: whether the API query requested unmatched records only.
- `interpretation`: explicitly rejects an inference of AIS disabling.
- `demo`: whether the feature is synthetic.

## Summary files

Each analytical layer has a JSON summary used for public statistics. The `mode` field must be `demo` or `live`. Missing observations remain `null`; the site does not interpolate them.

