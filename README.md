# Arctic Passage Atlas

Arctic Passage Atlas is a reproducible portfolio project combining three public-data layers over one compact study area around Cambridge Bay, Nunavut:

1. Landsat summer surface-change candidates.
2. Sentinel-1 monthly sea-ice classification with threshold sensitivity.
3. Global Fishing Watch AIS gap events and aggregated SAR-detection cells.

The project does **not** call AIS gaps suspicious, treat unmatched detections as proof of AIS disabling, or describe spectral changes as confirmed construction.

## Current status

Demo mode is implemented and tested. It generates deterministic synthetic fixtures, needs no accounts and visibly labels every public page as a demonstration.

Live mode is implemented but has not been run against Earth Engine or Global Fishing Watch in this repository. It requires provider credentials, AOI-specific threshold calibration and manual review before its outputs are publishable. The code should therefore be treated as a reproducible analysis starting point, not as a validated Cambridge Bay result.

The configured Cambridge Bay boundary is real. The committed demonstration observations and statistics are synthetic and must never be presented as findings.

## Quick start

Python 3.11 or newer is required.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m arctic_passage_atlas demo
python -m arctic_passage_atlas verify
python -m pytest
python -m arctic_passage_atlas serve
```

Open <http://127.0.0.1:8000>. The site also opens directly from `site/index.html`, although the interactive map and external basemap require an internet connection. Every map has an SVG fallback.

Both modes write to `data/processed/`. Run `python -m arctic_passage_atlas demo` at any time to restore the visibly labelled fixtures after development work with live layers.

## Live setup

1. Create or select a Google Cloud project, enable Earth Engine, register it for eligible noncommercial or commercial use, and authenticate once:

   ```powershell
   earthengine authenticate
   ```

2. Obtain a Global Fishing Watch API token.
3. Copy `.env.example` to `.env`, set `EE_PROJECT_ID`, and set `GFW_API_ACCESS_TOKEN`.
4. Run all live layers:

   ```powershell
   python -m arctic_passage_atlas live
   python -m arctic_passage_atlas verify
   ```

Individual development runs are supported with `live --parts change`, `ice`, or `vessels`. A partial run updates only its processed outputs: it does not rewrite the public bundle or manifest. A complete live publication is refused unless all three summary files say `live`.

The ice workflow makes many sequential Earth Engine requests because it records monthly coverage and sensitivity results. Runtime depends on provider load and scene availability; allow several minutes and do not treat a slow run as a hang without checking the console. Earth Engine registration requires choosing the appropriate noncommercial or commercial use category.

The configured thresholds are unvalidated starting values. Before a live publication, choose the ice threshold from mode/polarization-specific histograms, inspect the WorldCover water mask, add a land/water mask and sensitivity test to the change layer, and visually review a candidate sample. Those analysis checks require real provider data and are deliberately not claimed as complete here.

Current provider references used when this repository was prepared:

- [Earth Engine authentication](https://developers.google.com/earth-engine/guides/auth)
- [Landsat 8 Collection 2 Tier 1 Level 2](https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1_L2)
- [Sentinel-1 GRD](https://developers.google.com/earth-engine/datasets/catalog/COPERNICUS_S1_GRD)
- [NOAA OISST V2.1](https://developers.google.com/earth-engine/datasets/catalog/NOAA_CDR_OISST_V2_1)
- [Global Fishing Watch Python client](https://globalfishingwatch.github.io/gfw-api-python-client/)
- [Global Fishing Watch data caveats](https://api-doc.globalfishingwatch.org/our-apis/documentation/docs/v3/general-api-doc/data-caveats)

Provider APIs, licences and dataset aliases can change. Recheck these pages before modifying the client code or publishing a new run.

## Repository layout

```text
arctic-passage-atlas/
├── AGENTS.md
├── configs/cambridge-bay.json
├── arctic_passage_atlas/       # reusable pipeline code
├── notebooks/                  # thin explanatory entry points
├── data/
│   ├── raw/                    # ignored
│   ├── exports/                # ignored large exports
│   └── processed/              # small publishable results + manifest
├── docs/
├── site/                       # static GitHub Pages-ready website
└── tests/
```

Notebooks call package functions; they do not contain a second copy of the analysis.

## Commands

```text
python -m arctic_passage_atlas demo
python -m arctic_passage_atlas live [--parts change ice vessels]
python -m arctic_passage_atlas ice-inventory
python -m arctic_passage_atlas gfw-fixture
python -m arctic_passage_atlas verify
python -m arctic_passage_atlas serve [--port 8000]
python -m arctic_passage_atlas live-feeds     # refresh third-party snapshots (sea-ice extent, station)
python -m arctic_passage_atlas ice-grid       # newest NSIDC sea-ice concentration, resampled for the Route page
python -m arctic_passage_atlas route-grid     # rebuild the Arctic and worldwide land/water grids (downloads Natural Earth)
python -m arctic_passage_atlas pages          # re-apply the shared header, footer and metadata
```

`data/processed/manifest.json` records the configuration hash, Git commit when available, dataset identifiers and SHA-256 checksum of each published artifact. The generated browser bundle is intentionally excluded because it embeds the manifest itself. `verify` recomputes every recorded checksum and rejects a manifest whose mode disagrees with any layer summary.

When the checked-in live ice thresholds are unset, run `python -m arctic_passage_atlas ice-inventory` first. It writes non-public `data/processed/ice_inventory.json` with cross-polarized acquisition coverage, water-mask coverage and monthly backscatter percentiles. It does not classify ice, change the public site, or create a live manifest.

Before treating the vessel parser as provider-verified, set `GFW_API_ACCESS_TOKEN` in `.env` and run `python -m arctic_passage_atlas gfw-fixture`. It captures one event with `limit=1`, redacts direct vessel identifiers, and writes `tests/fixtures/gfw_event_sample.json`. Inspect that fixture before committing it, then revise the parser tests to use its documented fields. The command refuses to overwrite an existing fixture unless `--replace` is supplied.

## Publication checklist

- Replace the placeholder contact details in `site/about.html`.
- Initialize Git and make a source commit before the live run so the manifest can record a commit hash.
- Run the complete live pipeline and inspect every generated layer.
- Calibrate the ice threshold for the selected polarization and document its derivation.
- Inspect the water masks, review threshold sensitivity and visually check a sample of change candidates.
- Check that the vessel result is not truncated and contains enough events to support the layer.
- Confirm data-source licences and attribution on the publication date.
- Test the site at narrow mobile widths and with the basemap disconnected.
- Confirm that the manifest and all three `*_summary.json` files say `live`.
- Open every SVG fallback and confirm that it says `PROVIDER-BACKED OUTPUT`, not `DEMONSTRATION FIXTURE`.
- Confirm that `site.data_accessed` in the generated browser bundle contains the manifest timestamp.
- Never remove the demo banner while using fixtures.
- Publish `site/` with GitHub Pages or another static host.

## Licence

The repository code is MIT-licensed. Provider data and services are not. Global Fishing Watch API data is restricted to non-commercial use under CC BY-NC 4.0 and requires attribution; OpenFreeMap, OpenStreetMap and Open-Meteo have their own attribution terms, and the Open-Meteo free API is non-commercial. See [DATA_LICENSE.md](DATA_LICENSE.md) before publishing.

