# Methodology notes

## Boundary

The configured bounding box is a compact analytical study area around Cambridge Bay. It is not an official municipal, harbour or administrative boundary. All providers receive the same GeoJSON polygon.

## Surface change

The pipeline uses Landsat 8 Collection 2 Tier 1 Level 2 for both periods to avoid a cross-sensor comparison. It masks QA-flagged dilated cloud, cirrus, cloud, cloud shadow, snow and radiometric saturation. Surface-reflectance scale and offset are applied before median compositing.

Only land pixels are compared. Pixels in the configured WorldCover classes (water by default) are excluded, because sea-ice break-up, turbidity and tide change reflectance far more than anything built on land. The mask is a fixed coast mask and can be wrong at the shoreline. Candidates are vectorised at the Landsat native 30 m and kept only if they cover at least `minimum_candidate_pixels` pixels. The candidate area is also recomputed at the threshold plus and minus `change.sensitivity`.

Change magnitude is the Euclidean distance between the two six-band reflectance vectors. The bands are Landsat 8 OLI bands 2 to 7: blue (0.45-0.51 um), green (0.53-0.59 um), red (0.64-0.67 um), near-infrared (0.85-0.88 um), SWIR-1 (1.57-1.65 um) and SWIR-2 (2.11-2.29 um). The thermal bands (10, 11) measure emitted temperature rather than reflectance at a coarser native resolution, band 8 is a single 15 m panchromatic band, and bands 1 and 9 are coastal-aerosol and cirrus diagnostics, so none is used. Pixels above `change_threshold` become candidates. This is a screening method. A candidate needs visual and documentary corroboration before it can be described as a particular development.

## Sea ice

Sentinel-1 scenes differ by acquisition mode, polarization and orbit. The pipeline counts four common mode/polarization combinations over the full configured year and selects the one with the most scenes unless the configuration pins a choice. The resolved choice is written to `ice_summary.json`.

A monthly median backscatter composite is thresholded within a WorldCover water mask. The area is recomputed at the configured threshold plus and minus `sensitivity_db`. The OISST ice band supplies a coarse 15% concentration reference for seasonal comparison. It is not a local validation surface.

### Threshold selection (status: blocked pending calibration)

There is one threshold per polarisation (`ice.thresholds_db`), because a dB value only means something for the band it was chosen on. Co-polarised bands (HH, VV) respond to wind-roughened open water, which raises backscatter toward ice values, so a co-pol threshold can overstate ice in windy months. Cross-polarised bands (HV, VH) are less sensitive to wind, but open water sits close to the sensor noise floor, so the noise level of the chosen product limits what can be separated.

No live threshold is supplied in the checked-in configuration. This is deliberate: choosing a generic dB value would create an unvalidated result. The synthetic demonstration has its own value and never represents an observation. The live pipeline refuses to classify until a threshold is configured for the selected polarisation. The procedure to finish this section is:

1. Inspect the monthly percentiles and histograms for a clearly open-water month and a clearly ice-covered month.
2. Choose per-polarisation thresholds and write the reasoning here, including the noise floor of the product.
3. Compare the result with an independent source (an ice chart, or manually labelled Sentinel-2 summer scenes) and report the agreement.
4. Change `threshold_status` to `validated` in the config only after step 3.

With the checked-in configuration, use `arctic-atlas ice-inventory` before setting a live threshold. It selects an available cross-polarized acquisition, writes monthly water-masked percentiles to `data/processed/ice_inventory.json`, and does not create a classified ice layer or public manifest.

An automatic histogram method such as Otsu's is not used yet. It assumes a two-peaked histogram, which fails in months that are almost entirely ice or water.

Each monthly composite spans the whole calendar month. Use `period`; no representative acquisition date is invented. The run also stops if the WorldCover water-mask fraction lies outside the configured plausible range, prompting an explicit coast-mask review.

This method does not distinguish all ice types, calibrate a universal threshold or replace operational ice charts.

Operational sea-ice monitoring in the Canadian Arctic (Canadian Ice Service charts) is produced by analysts who combine several sensors and report ice with the WMO egg code and MANICE procedures: concentration, stage of development and floe size. This project's single-threshold C-band SAR classification is a screening baseline for ice versus open water. It does not classify stage of development, floe size or ridging, and it is not a substitute for an ice chart.

## Projection and area

The interactive map is drawn in Web Mercator for tile compatibility, which stretches lengths by about 1 / cos(latitude): roughly 2.8 times at Cambridge Bay (69 N) and about 7.8 times for areas. Areas are not measured on the map. They come from Earth Engine's pixel-area image (ellipsoidal ground area), and study-area dimensions use geodesic distance. For desktop GIS work with the exported GeoJSON (EPSG:4326), reproject to EPSG:3413 (NSIDC Sea Ice Polar Stereographic North) or EPSG:3978 (Canada Atlas Lambert) before measuring lengths or areas.

## Vessel events

The official Global Fishing Watch Python client supplies:

- AIS gap events at or above the configured duration.
- A high-resolution, monthly SAR presence report over the custom GeoJSON boundary.

When requested, the SAR report is filtered to provider records marked unmatched. The output remains an aggregated detection cell, not evidence that a particular vessel intentionally stopped transmitting.

### Provider caveats that apply to this study area

Source: [Global Fishing Watch data caveats](https://api-doc.globalfishingwatch.org/our-apis/documentation/docs/v3/general-api-doc/data-caveats), read 2026-10-02. Recheck before publishing.

- The provider treats AIS gaps as reliable indicators of intentional disabling only when the gap lasts at least 12 hours, starts at least 50 nautical miles from shore, and lies in an area with more than 10 satellite positions per day. The study box measures about 43.9 km by 44.5 km. Cambridge Bay (69.11389 N, 105.05278 W, from Wikipedia, read 2026-10-02) lies inside it, so every point in the box is at most 19.0 nautical miles from that shoreline location. The nearest-coast distance is smaller, and 50 nautical miles is not approached anywhere in the area, so these gaps do not meet that standard. The calculation is `arctic_passage_atlas/distance.py`, checked in `tests/test_distance.py`. This project therefore reports gap events as events only and draws no conclusion about cause.
- The provider states that satellite AIS reception generally decreases closer to shore, and that more than 99% of its terrestrial AIS messages come from within 50 nautical miles of shore. Which receivers cover Cambridge Bay has not been established here, so reception quality in the study area is unknown.
- The provider states that its SAR product leaves out much of the Arctic because sea ice produces too many false positives, and that Sentinel-1 does not sample most of the open ocean. The SAR layer may therefore be empty or sparse here. An empty layer means no usable data from this product, not an absence of vessels.

The explanations for gaps that this project can support from the provider documentation are limited to the above. Other mechanisms (satellite revisit timing, message collisions, GNSS interference) are plausible but are not tested here and are not stated as causes.

## Live context and route timing

These features use third-party feeds. They are context, not project results, and they are never mixed into the analytical layers.

- **Station weather.** Environment and Climate Change Canada real-time observations (SWOB) for Cambridge Bay and six other stations on the Northwest Passage corridor. The visitor's browser asks the provider directly and shows the observation time. If the request fails, a dated snapshot is shown and the page says so. Values are the provider's, unvalidated here.
- **Imagery.** NASA GIBS true-colour tiles for a chosen date. Recent days can be incomplete near swath edges, and optical imagery shows cloud and has no data in the polar night.
- **Sea-ice extent.** NSIDC daily Northern Hemisphere extent, downloaded on a schedule because the file does not allow browser reads. It is pan-Arctic. It says nothing local to the study area.
- **Worldwide route planner.** A 0.1 degree land/water grid built from Natural Earth 1:10m land (public domain) with the Suez and Panama canals, the Gulf of Suez, Bab-el-Mandeb, Gibraltar, the Bosphorus and Dardanelles and the Singapore Strait opened by hand, because they are narrower than a cell. The browser runs A* over eight neighbours, wrapping at the antimeridian, then straightens the path with line-of-sight checks. Sea ice is avoided using the NSIDC Sea Ice Index daily concentration (version 4, 25 km passive-microwave cells, resampled by `ice-grid`): cells at or above a chosen concentration (15, 40 or 70 percent) are blocked. It is one past day, not a forecast, misses thin ice and understates concentration in summer melt, and is not an ice chart. It covers the Northern Hemisphere only, so the Southern Ocean is kept out of the search. If the ice file cannot be loaded the browser falls back to approximate polar boxes. Conditions come from Open-Meteo forecast and marine models at up to nine points along the path, read at the hour the ship would arrive, and are blank beyond the 16-day horizon. The sea-state bands are a simple guide, not a safety assessment. Shortest means shortest, never best or safe.
- **Arctic corridor planner.** The same router on a finer 0.05 x 0.02 degree grid with Environment Canada observations and hourly forecasts.
- **Timing and sun.** Sailing time is path length divided by the speed you choose; daylight and twilight use the NOAA solar-position method. Ice, charts, tides, vessel class and regulations are not modelled. It is not for navigation.

## Reproducibility boundary

Published files are exactly checksummed, but exact re-creation from provider APIs is not guaranteed indefinitely. Earth Engine catalogs can be reprocessed, and Global Fishing Watch identifiers using `:latest` are mutable. The manifest therefore records both the query configuration and the resulting artifacts.

