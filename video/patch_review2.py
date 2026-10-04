import pathlib

REPO = "https://github.com/vikramchowdhry-ship-it/arctic-passage-atlas"


def edit(path, pairs):
    p = pathlib.Path(path)
    s = p.read_text(encoding="utf-8")
    for old, new in pairs:
        assert old in s, (path, old[:60])
        s = s.replace(old, new, 1)
    p.write_text(s, encoding="utf-8")


BANDS_HTML = '''          <div class="panel" style="margin:1.2rem 0">
            <h3>Bands used</h3>
            <p class="sub" style="margin-bottom:.4rem">
              Change magnitude is the Euclidean distance between two six-band surface-reflectance vectors from Landsat 8 OLI
              (Collection 2 Level 2, scaled to reflectance):
            </p>
            <ul>
              <li>Band 2, blue, 0.45–0.51 µm</li>
              <li>Band 3, green, 0.53–0.59 µm</li>
              <li>Band 4, red, 0.64–0.67 µm</li>
              <li>Band 5, near-infrared, 0.85–0.88 µm</li>
              <li>Band 6, shortwave infrared 1, 1.57–1.65 µm</li>
              <li>Band 7, shortwave infrared 2, 2.11–2.29 µm</li>
            </ul>
            <p class="sub" style="margin-bottom:0">
              Not used: the thermal bands (10 and 11) measure emitted temperature, a different quantity from reflectance, at a coarser native
              resolution. Band 8 is a single 15 m panchromatic band with no spectral information to compare. Bands 1 and 9 are
              coastal-aerosol and cirrus diagnostic bands. Pixels flagged for dilated cloud, cirrus, cloud, cloud shadow, snow or saturation
              are masked before the distance is computed.
            </p>
          </div>
'''

ICE_NOTE = '''          <div class="panel" style="margin:1.2rem 0">
            <h3>How this relates to operational ice charts</h3>
            <p class="sub" style="margin-bottom:0">
              Operational sea-ice monitoring in the Canadian Arctic, such as Canadian Ice Service charts, is produced by analysts who combine
              several sensors and report ice using the WMO egg code and the MANICE procedures: concentration, stage of development (new, grey,
              thin and thick first-year, old ice) and floe size. This layer is different. It applies one backscatter threshold to Sentinel-1
              C-band SAR as a screening baseline for ice versus open water. It does not classify stage of development, floe size or ridges, and
              it is not a substitute for an ice chart.
            </p>
          </div>
'''

# --- change page
edit("site/layers/change.html", [
    ("          <h2>Principal limitations</h2>", BANDS_HTML + "          <h2>Principal limitations</h2>"),
    ("<code>notebooks/03_infrastructure_change.ipynb</code>.", f'<a href="{REPO}/blob/main/notebooks/03_infrastructure_change.ipynb">notebooks/03_infrastructure_change.ipynb</a> on GitHub.'),
])
# --- ice page
edit("site/layers/ice.html", [
    ("          <h2>Principal limitations</h2>", ICE_NOTE + "          <h2>Principal limitations</h2>"),
    ("<code>notebooks/02_ice_extent_s1.ipynb</code>.", f'<a href="{REPO}/blob/main/notebooks/02_ice_extent_s1.ipynb">notebooks/02_ice_extent_s1.ipynb</a> on GitHub.'),
])
# --- vessels page
edit("site/layers/vessels.html", [
    ("<code>notebooks/04_vessel_events_gfw.ipynb</code>.", f'<a href="{REPO}/blob/main/notebooks/04_vessel_events_gfw.ipynb">notebooks/04_vessel_events_gfw.ipynb</a> on GitHub.'),
])

# --- methodology page
edit("site/methodology.html", [
    ("""            change magnitude. Pixels above the configured threshold are
            vectorized as candidates.
          </p>""", """            change magnitude. Pixels above the configured threshold are
            vectorized as candidates. The six bands are Landsat 8 OLI bands 2
            to 7 (blue, green, red, near-infrared, shortwave infrared 1 and 2).
            The thermal bands (10, 11) and the panchromatic band (8) are not
            used: they measure a different quantity or carry no spectral
            information to compare. See the Surface change layer page for the
            wavelengths.
          </p>"""),
    ("""            seasonal reference.
          </p>
          <h2>Projection and area</h2>""", """            seasonal reference.
          </p>
          <p>
            Operational sea-ice monitoring in the Canadian Arctic (Canadian
            Ice Service charts) is produced by analysts combining several
            sensors and reporting ice with the WMO egg code and MANICE
            procedures: concentration, stage of development and floe size.
            This project's single-threshold C-band SAR classification is a
            screening baseline for ice versus open water. It does not
            classify stage of development, floe size or ridging.
          </p>
          <h2>Projection and area</h2>"""),
    ("""            never treated as square metres. The configured polar projection is
            available for exported cartographic work.
          </p>""", """            never treated as square metres. The configured polar projection is
            available for exported cartographic work.
          </p>
          <p>
            The interactive map is drawn in Web Mercator for tile
            compatibility. Web Mercator stretches distances by about 1 ÷
            cos(latitude), so at Cambridge Bay (69°N) lengths look about 2.8
            times larger than they are, and areas about 7.8 times. Areas in this
            project are not measured on the map: they come from Earth Engine's
            pixel-area image, which gives ground area on the WGS 84 ellipsoid,
            and the study-area dimensions use geodesic distance. For desktop GIS
            work with the exported GeoJSON (EPSG:4326), reproject to EPSG:3413
            (NSIDC Sea Ice Polar Stereographic North) or EPSG:3978 (Canada
            Atlas Lambert) before measuring.
          </p>"""),
    ("""          <h2>Known limitations</h2>""", f"""          <h2>How to cite this work</h2>
          <p>
            Chowdhary, M. (2026). <em>Arctic Passage Atlas: an open-source
            method for observing Arctic surface, sea-ice and vessel-event
            change from public data</em> [Software]. GitHub.
            <a href="{REPO}">{REPO}</a>
          </p>
          <p class="sub">GitHub also offers a "Cite this repository" button from the repository's CITATION.cff file.</p>
          <h2>Known limitations</h2>"""),
])

# --- METHODOLOGY.md
m = pathlib.Path("docs/METHODOLOGY.md")
t = m.read_text(encoding="utf-8")
t = t.replace("Change magnitude is the Euclidean distance between the two six-band reflectance vectors.", "Change magnitude is the Euclidean distance between the two six-band reflectance vectors. The bands are Landsat 8 OLI bands 2 to 7: blue (0.45-0.51 um), green (0.53-0.59 um), red (0.64-0.67 um), near-infrared (0.85-0.88 um), SWIR-1 (1.57-1.65 um) and SWIR-2 (2.11-2.29 um). The thermal bands (10, 11) measure emitted temperature rather than reflectance at a coarser native resolution, band 8 is a single 15 m panchromatic band, and bands 1 and 9 are coastal-aerosol and cirrus diagnostics, so none is used.", 1)
t = t.replace("## Vessel events", """Operational sea-ice monitoring in the Canadian Arctic (Canadian Ice Service charts) is produced by analysts who combine several sensors and report ice with the WMO egg code and MANICE procedures: concentration, stage of development and floe size. This project's single-threshold C-band SAR classification is a screening baseline for ice versus open water. It does not classify stage of development, floe size or ridging, and it is not a substitute for an ice chart.

## Projection and area

The interactive map is drawn in Web Mercator for tile compatibility, which stretches lengths by about 1 / cos(latitude): roughly 2.8 times at Cambridge Bay (69 N) and about 7.8 times for areas. Areas are not measured on the map. They come from Earth Engine's pixel-area image (ellipsoidal ground area), and study-area dimensions use geodesic distance. For desktop GIS work with the exported GeoJSON (EPSG:4326), reproject to EPSG:3413 (NSIDC Sea Ice Polar Stereographic North) or EPSG:3978 (Canada Atlas Lambert) before measuring lengths or areas.

## Vessel events""", 1)
m.write_text(t, encoding="utf-8")

# --- CITATION.cff
pathlib.Path("CITATION.cff").write_text(f"""cff-version: 1.2.0
message: "If you use this software or method, please cite it as below."
title: "Arctic Passage Atlas: an open-source method for observing Arctic surface, sea-ice and vessel-event change from public data"
type: software
authors:
  - family-names: Chowdhary
    given-names: Maheep
repository-code: "{REPO}"
license: MIT
date-released: "2026-10-04"
keywords:
  - Arctic
  - sea ice
  - remote sensing
  - Sentinel-1
  - Landsat
  - geospatial
""", encoding="utf-8")
print("review items applied")
