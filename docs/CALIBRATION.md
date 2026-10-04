# Sea-ice threshold calibration attempt (2024)

**Result: a single backscatter threshold did not reproduce the seasonal ice cycle in this study area. The ice
threshold stays uncalibrated, and the Ice layer stays a labelled demonstration.**

## What was tested

For each month of 2024, the same monthly-median Sentinel-1 composite the Ice layer uses (Extra Wide swath mode,
the only mode with scenes here: 83 EW/HV scenes and no IW/VH scenes) was clipped to the ESA WorldCover water mask
inside the study box. For every candidate threshold from -40 to -5 dB, the share of water pixels at or above it
was compared with the NSIDC Sea Ice Index (G02135, version 4) daily ice concentration on the 15th of each month,
averaged over the ocean cells around the study area. Agreement is the RMSE and correlation over 12 months.

Run it again with `python scripts/ice_calibration.py` (needs Earth Engine access and `tifffile`). The numbers are in
`docs/ice_calibration.json`.

## Result

| Channel | Best threshold by RMSE | RMSE (ice fraction) | Correlation at that threshold | Highest correlation at any threshold |
| --- | --- | --- | --- | --- |
| EW / HV | -34 dB | 0.28 | 0.11 | 0.54 |
| EW / HH | -24 dB | 0.27 | 0.40 | 0.74 |

A model that always predicts the yearly mean ice fraction (0.77) has an RMSE of 0.21, so the best thresholds are
**worse than a constant guess**.

- **HH at -24 dB** calls the winter months ice (about 0.98 of water pixels in Jan, Feb, Mar and Dec) but also calls
  about 0.78 of water pixels ice in August and September, when the reference shows roughly 0.45. A high-backscatter
  open-water surface (wind roughening) is not separated from ice by one threshold.
- **HV** sits close to the sensor noise floor here. Winter ice and summer water both have median backscatter near
  -30 dB, so a single threshold cannot separate them (winter share 0.64, August-September 0.47).

## Why this may be the method and not only the reference

The reference is coarse: NSIDC cells are 25 km, the study box is 44 km, and coastline and land contamination are
likely in a narrow channel area. Each month's composite uses only 4 to 9 scenes. Both can explain part of the
disagreement. They do not make the threshold validated.

## What it would take to calibrate this layer

- A finer independent reference, such as Canadian Ice Service regional ice charts for Cambridge Bay, or Sentinel-2
  and Landsat imagery in the ice-free season, analyst-checked.
- Wind and incidence-angle handling for HH, or a two-channel rule (HH with HV) instead of one threshold.
- Per-scene classification rather than a monthly median.

Until one of those is done, the project does not publish a classified ice layer as an observation.
