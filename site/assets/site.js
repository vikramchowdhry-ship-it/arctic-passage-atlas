(function () {
  "use strict";
  const data = window.ATLAS_DATA;
  if (!data) return;

  const isDemo = (data.manifest && data.manifest.mode === "demo") || data.changeSummary.mode === "demo";
  document.querySelectorAll("[data-mode]").forEach((node) => {
    node.textContent = isDemo ? "DEMONSTRATION DATA — NOT OBSERVATIONS" : "PROVIDER-BACKED LIVE OUTPUT";
  });
  document.querySelectorAll("[data-generated]").forEach((node) => {
    node.textContent = data.manifest.generated_at || "manifest pending";
  });

  const values = {
    changeCount: data.changeSummary.candidate_count,
    changeArea: format(data.changeSummary.candidate_area_km2, 2),
    gapCount: data.vesselSummary.gap_event_count ?? data.vesselSummary.gap_features_mappable,
    sarCount: data.vesselSummary.sar_detection_sum,
    iceThreshold: data.iceSummary.threshold_db,
    studyName: data.config.aoi.name,
  };
  document.querySelectorAll("[data-stat]").forEach((node) => {
    const key = node.getAttribute("data-stat");
    if (values[key] !== undefined && values[key] !== null) node.textContent = values[key];
  });
  document.querySelectorAll("[data-vessel-caveats]").forEach((node) => {
    const caveats = data.vesselSummary.limitations || [];
    node.replaceChildren(...caveats.map((caveat) => {
      const item = document.createElement("li");
      item.textContent = String(caveat);
      return item;
    }));
  });

  renderIceChart(document.querySelector("[data-ice-chart]"), data.iceSummary.monthly || []);
  renderIceCard();
  initMap();

  function format(value, digits) {
    const number = Number(value);
    return Number.isFinite(number) ? number.toFixed(digits) : "—";
  }

  function renderIceChart(target, rows) {
    if (!target || !rows.length) return;
    const w = 900, h = 330, left = 55, top = 25, plotW = 815, plotH = 245;
    const valid = rows.filter((row) => row.classified_fraction !== null);
    const points = (key) => valid.map((row) => {
      const x = left + ((row.month - 1) / 11) * plotW;
      const y = top + (1 - Number(row[key])) * plotH;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    }).join(" ");
    const months = rows.map((row) => `<text x="${left + ((row.month - 1) / 11) * plotW}" y="${top + plotH + 28}" text-anchor="middle">${row.month}</text>`).join("");
    const sceneCounts = rows.map((row) => `${row.month_name || row.month}: ${row.scene_count ?? 0}`).join(" · ");
    target.innerHTML = `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Monthly classified ice fraction and coarse reference">
      <g stroke="#24465b" stroke-width="1"><line x1="${left}" y1="${top}" x2="${left}" y2="${top + plotH}"/><line x1="${left}" y1="${top + plotH}" x2="${left + plotW}" y2="${top + plotH}"/><line x1="${left}" y1="${top + plotH/2}" x2="${left + plotW}" y2="${top + plotH/2}" stroke-dasharray="5 6"/></g>
      <polyline points="${points("coarse_reference_fraction")}" fill="none" stroke="#9cb5c2" stroke-width="3" stroke-dasharray="7 6"/>
      <polyline points="${points("classified_fraction")}" fill="none" stroke="#7bdff2" stroke-width="4"/>
      <g fill="#9cb5c2" font-family="system-ui" font-size="13">${months}<text x="12" y="${top + 5}">100%</text><text x="22" y="${top + plotH/2 + 5}">50%</text><text x="32" y="${top + plotH + 5}">0%</text></g>
      <g font-family="system-ui" font-size="14"><text x="${left}" y="318" fill="#7bdff2">— Sentinel-1 threshold classification</text><text x="340" y="318" fill="#9cb5c2">- - coarse reference</text></g>
    </svg><p class="note">Compatible Sentinel-1 scenes by month: ${sceneCounts}.</p>`;
  }

  function initMap() {
    const target = document.querySelector("[data-map-layer]");
    if (!target || typeof window.maplibregl === "undefined") return;
    const selected = target.getAttribute("data-map-layer");
    const center = data.config.aoi.center;
    // OpenFreeMap needs no key. Its dark style is built from OpenStreetMap data.
    const style = "https://tiles.openfreemap.org/styles/dark";
    const map = new maplibregl.Map({ container: target, style, center, zoom: data.config.site.map_zoom, attributionControl: { compact: true }, cooperativeGestures: true });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    try { (window.AtlasMaps = window.AtlasMaps || []).push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); } catch (e) { /* tools are optional */ }
    // style.load, not load: the layers must not wait for every basemap tile
    map.on("style.load", () => {
      addSource(map, "aoi", data.aoi);
      map.addLayer({ id: "aoi-fill", type: "fill", source: "aoi", paint: { "fill-color": "#83f3c7", "fill-opacity": 0.045 } });
      map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#83f3c7", "line-width": 2, "line-dasharray": [3, 2] } });
      if (selected === "all" || selected === "change") addChange(map);
      if (selected === "all" || selected === "ice") addIce(map);
      if (selected === "all" || selected === "vessels") addVessels(map);
      fitAoi(map, data.config.aoi.bbox);
      const shell = target.closest(".map-shell");
      if (shell) { layerBar(map, shell); if (selected === "all" || selected === "ice") timeBar(map, shell); }
    });
  }



  /* The polarisation, mode and threshold behind the ice layer, read from the published summary. */
  function renderIceCard() {
    const host = document.getElementById("ice-method-card");
    if (!host) return;
    const sum = data.iceSummary || {}, ice = (data.config && data.config.ice) || {}, acq = sum.acquisition || {};
    const live = (data.manifest && data.manifest.mode) === "live";
    const pol = acq.polarization || ice.polarization || "unknown";
    const thr = typeof sum.threshold_db === "number" ? sum.threshold_db.toFixed(1) + " dB" : "not set";
    const status = ice.threshold_status === "validated" ? "Calibrated for this study area" : "Not yet calibrated for this study area";
    const sens = typeof ice.sensitivity_db === "number" ? "±" + ice.sensitivity_db.toFixed(1) + " dB" : "n/a";
    const row = (k, v) => '<div class="kpi"><div class="label">' + k + '</div><div class="value" style="font-size:1.1rem">' + v + "</div></div>";
    host.innerHTML = '<h3>What this layer is using</h3><div class="kpis four">' +
      row("Polarisation", pol) + row("Instrument mode", acq.instrument_mode || ice.instrument_mode || "unknown") +
      row("Threshold", thr) + row("Sensitivity bracket", sens) + "</div>" +
      '<p class="panel-foot">' + status + ". " + (live ? "Values come from a provider-backed run." : "These are demonstration values, not a calibrated classification.") + "</p>";
  }

  /* ---- layer manager and time scrubber ---------------------------------------------------------- */
  const GROUPS = [
    ["aoi", "Study area", ["aoi-fill", "aoi-line"]],
    ["change", "Change candidates", ["change-fill", "change-line"]],
    ["ice", "Sea ice", ["ice-fill", "ice-line"]],
    ["vessels", "Vessel events", ["gaps-line", "gaps-point", "sar-point"]]
  ];
  const OPACITY = { fill: ["fill-opacity"], line: ["line-opacity"], circle: ["circle-opacity", "circle-stroke-opacity"] };
  function layerBar(map, shell) {
    const bar = document.createElement("div");
    bar.className = "layer-bar"; bar.setAttribute("role", "group"); bar.setAttribute("aria-label", "Map layers");
    GROUPS.filter((g) => g[2].every((id) => map.getLayer(id))).forEach(([key, label, ids]) => {
      const base = {};
      ids.forEach((id) => OPACITY[map.getLayer(id).type].forEach((prop) => { const v = map.getPaintProperty(id, prop); base[id + prop] = typeof v === "number" ? v : 1; }));
      const wrap = document.createElement("label");
      wrap.className = "layer-ctl";
      wrap.innerHTML = '<input type="checkbox" checked aria-label="Show ' + label + '" /><span>' + label + '</span><input type="range" min="0" max="100" value="100" aria-label="' + label + ' opacity" />';
      const [box, , range] = wrap.children;
      box.addEventListener("change", () => ids.forEach((id) => map.setLayoutProperty(id, "visibility", box.checked ? "visible" : "none")));
      range.addEventListener("input", () => ids.forEach((id) => OPACITY[map.getLayer(id).type].forEach((prop) => map.setPaintProperty(id, prop, base[id + prop] * range.value / 100))));
      bar.appendChild(wrap);
    });
    if (bar.children.length > 1) shell.appendChild(bar);
  }
  function timeBar(map, shell) {
    if (!map.getLayer("ice-fill")) return;
    const periods = [...new Set(data.ice.features.map((f) => f.properties.period))].sort();
    if (periods.length < 2) return;
    const bar = document.createElement("div");
    bar.className = "time-bar";
    bar.innerHTML = '<button type="button" class="play" aria-label="Play months">▶</button><input type="range" min="0" max="' + periods.length + '" value="' + periods.length + '" aria-label="Snapshot month" /><output aria-live="polite">All months</output>';
    const [play, range, out] = bar.children;
    function apply() {
      const i = Number(range.value), all = i >= periods.length;
      const filter = all ? null : ["==", ["get", "period"], periods[i]];
      ["ice-fill", "ice-line"].forEach((id) => map.setFilter(id, filter));
      out.textContent = all ? "All months" : periods[i];
    }
    range.addEventListener("input", apply);
    let timer = null;
    play.addEventListener("click", () => {
      if (timer) { clearInterval(timer); timer = null; play.textContent = "▶"; return; }
      play.textContent = "❚❚"; range.value = 0; apply();
      timer = setInterval(() => {
        range.value = Number(range.value) + 1; apply();
        if (Number(range.value) >= periods.length) { clearInterval(timer); timer = null; play.textContent = "▶"; }
      }, 1100);
    });
    shell.appendChild(bar);
  }

  function addSource(map, id, geojson) { if (!map.getSource(id)) map.addSource(id, { type: "geojson", data: geojson }); }
  function addChange(map) {
    addSource(map, "change", data.change);
    map.addLayer({ id: "change-fill", type: "fill", source: "change", paint: { "fill-color": "#ffb454", "fill-opacity": .55 } });
    map.addLayer({ id: "change-line", type: "line", source: "change", paint: { "line-color": "#ffe0ad", "line-width": 1.5 } });
    popup(map, "change-fill", ["candidate_id", "interpretation", "change_magnitude"]);
  }
  function addIce(map) {
    addSource(map, "ice", data.ice);
    map.addLayer({ id: "ice-fill", type: "fill", source: "ice", paint: { "fill-color": "#7bdff2", "fill-opacity": .24 } });
    map.addLayer({ id: "ice-line", type: "line", source: "ice", paint: { "line-color": "#b9f3ff", "line-width": 1.2 } });
    popup(map, "ice-fill", ["period", "threshold_db", "instrument_mode", "polarization"]);
  }
  function addVessels(map) {
    addSource(map, "gaps", data.gaps); addSource(map, "sar", data.sar);
    map.addLayer({ id: "gaps-line", type: "line", source: "gaps", paint: { "line-color": "#ff6b7a", "line-width": 3, "line-dasharray": [2, 1] } });
    map.addLayer({ id: "gaps-point", type: "circle", source: "gaps", filter: ["==", ["geometry-type"], "Point"], paint: { "circle-color": "#ff6b7a", "circle-radius": 6, "circle-stroke-color": "#fff", "circle-stroke-width": 1 } });
    map.addLayer({ id: "sar-point", type: "circle", source: "sar", paint: { "circle-color": "#ffb454", "circle-radius": ["interpolate", ["linear"], ["coalesce", ["get", "detections"], 1], 1, 5, 5, 11], "circle-stroke-color": "#071521", "circle-stroke-width": 2 } });
    popup(map, "gaps-line", ["event_id", "event_type", "duration_hours", "interpretation"]);
    popup(map, "gaps-point", ["event_id", "event_type", "duration_hours", "interpretation"]);
    popup(map, "sar-point", ["cell_id", "date", "detections", "interpretation"]);
  }
  function popup(map, layer, keys) {
    map.on("click", layer, (event) => {
      const props = event.features && event.features[0] ? event.features[0].properties : {};
      const box = document.createElement("div");
      keys.forEach((key) => {
        if (props[key] === undefined || props[key] === null) return;
        const row = document.createElement("p");
        const strong = document.createElement("strong"); strong.textContent = key.replaceAll("_", " ") + ": ";
        row.append(strong, document.createTextNode(String(props[key]))); box.appendChild(row);
      });
      new maplibregl.Popup().setLngLat(event.lngLat).setDOMContent(box).addTo(map);
    });
    map.on("mouseenter", layer, () => { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", layer, () => { map.getCanvas().style.cursor = ""; });
  }
  function fitAoi(map, bbox) { map.fitBounds([[bbox[0], bbox[1]], [bbox[2], bbox[3]]], { padding: 45, duration: 0 }); }
})();

