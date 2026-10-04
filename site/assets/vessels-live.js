/* Live vessel positions (AIS-reported) on the Live page. Positions are anonymous: no names, MMSI, call signs
 * or destinations are kept or shown, and military, law-enforcement and search-and-rescue vessels are dropped.
 * This is context, not a tracking service, and a missing dot is not a missing vessel.
 *
 * Sources:
 *   - Digitraffic (Fintraffic, open data, CC BY 4.0): live AIS from Finnish receivers over the Baltic Sea and
 *     the Gulf of Bothnia, up to about 66 N. Needs no key and runs straight from the browser.
 *   - The optional AIS relay in /ais-relay (AISStream), for the Arctic proper. It needs a key kept on a server,
 *     so it is only used when `aisRelayUrl` is set in site-config.js.
 */
(function () {
  "use strict";
  var cfg = Object.assign({}, (typeof window !== "undefined" && window.ATLAS_SITE) || {});
  // On localhost only, ?ais=http://127.0.0.1:8787/ points the page at a relay running on this machine.
  if (typeof location !== "undefined" && /^(localhost|127\.0\.0\.1)$/.test(location.hostname)) {
    var override = new URLSearchParams(location.search).get("ais");
    if (override && /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?\//.test(override)) cfg.aisRelayUrl = override;
  }
  var DIGI_LOC = "https://meri.digitraffic.fi/api/ais/v1/locations";
  var DIGI_VES = "https://meri.digitraffic.fi/api/ais/v1/vessels";
  var CLASSES = {
    cargo: ["Cargo", "#7bdff2"], tanker: ["Tanker", "#ffb454"], passenger: ["Passenger", "#c8a2ff"], fishing: ["Fishing", "#83f3c7"],
    service: ["Tug and service", "#9cb5c2"], pleasure: ["Pleasure and sailing", "#f4e285"], other: ["Other", "#e8f2f5"], unknown: ["Type not reported", "#6f8796"]
  };

  /* Lakes and inland waters in and near the Arctic: [name, country, south, west, north, east, who hears it]. */
  var LAKES = [
    ["Lake Saimaa", "Finland", 60.8, 27.0, 62.4, 30.0, "Finnish receivers (Digitraffic)"],
    ["Lake Päijänne", "Finland", 61.0, 25.0, 62.5, 26.5, "Finnish receivers (Digitraffic)"],
    ["Lake Oulujärvi", "Finland", 64.1, 27.0, 64.6, 28.3, "Finnish receivers (Digitraffic)"],
    ["Lake Pielinen", "Finland", 63.0, 28.5, 63.7, 29.8, "Finnish receivers (Digitraffic)"],
    ["Lake Kemijärvi", "Finland", 66.4, 27.2, 66.8, 27.9, "AIS relay only"],
    ["Lake Inari", "Finland", 68.8, 27.0, 69.3, 28.5, "AIS relay only"],
    ["Torneträsk", "Sweden", 68.2, 18.5, 68.5, 20.3, "AIS relay only"],
    ["Hornavan", "Sweden", 65.9, 17.2, 66.3, 18.2, "AIS relay only"],
    ["Storuman", "Sweden", 64.9, 16.5, 65.3, 17.8, "AIS relay only"],
    ["Lake Ladoga", "Russia", 60.2, 29.9, 61.8, 32.9, "Finnish receivers (Digitraffic) and AIS relay"],
    ["Lake Onega", "Russia", 60.8, 34.0, 62.9, 36.5, "AIS relay only"],
    ["Lake Beloye", "Russia", 59.8, 37.0, 60.5, 38.3, "AIS relay only"],
    ["Lake Vygozero", "Russia", 63.0, 34.0, 63.8, 35.5, "AIS relay only"],
    ["Lake Topozero", "Russia", 65.4, 32.0, 65.9, 33.5, "AIS relay only"],
    ["Lake Imandra", "Russia", 67.3, 32.2, 67.7, 33.5, "AIS relay only"],
    ["Lake Lovozero", "Russia", 67.7, 34.9, 68.2, 35.9, "AIS relay only"],
    ["Lake Pyasino", "Russia", 69.3, 87.0, 69.9, 89.5, "AIS relay only"],
    ["Taymyr Lake", "Russia", 74.0, 99.0, 75.5, 102.5, "AIS relay only"],
    ["Lake Mývatn", "Iceland", 65.5, -17.2, 65.7, -16.8, "AIS relay only"],
    ["Lagarfljót", "Iceland", 65.0, -14.6, 65.4, -14.2, "AIS relay only"],
    ["Þingvallavatn", "Iceland", 64.1, -21.2, 64.3, -20.9, "AIS relay only"],
    ["Great Slave Lake", "Canada", 60.8, -117.5, 62.9, -108.5, "AIS relay only"],
    ["Great Bear Lake", "Canada", 65.0, -125.5, 67.5, -118.0, "AIS relay only"],
    ["Lake Athabasca", "Canada", 59.0, -110.5, 59.7, -105.0, "AIS relay only"],
    ["Dubawnt Lake", "Canada", 62.5, -102.5, 63.8, -100.5, "AIS relay only"],
    ["Baker Lake", "Canada", 64.0, -97.0, 64.5, -95.5, "AIS relay only"],
    ["Kluane Lake", "Canada (Yukon)", 61.0, -139.0, 61.5, -138.0, "AIS relay only"],
    ["Atlin Lake", "Canada", 59.4, -133.9, 59.9, -133.3, "AIS relay only"],
    ["Lake Hazen", "Canada (Nunavut)", 81.8, -71.5, 81.95, -69.5, "AIS relay only"],
    ["Teshekpuk Lake", "United States (Alaska)", 70.4, -154.0, 70.8, -152.5, "AIS relay only"],
    ["Iliamna Lake", "United States (Alaska)", 59.3, -155.5, 59.9, -154.0, "AIS relay only"]
  ];

  /* AIS ship-type code to a public class. null means "do not publish". Mirrors ais-relay/logic.mjs. */
  function classify(code) {
    var c = Number(code);
    if (!isFinite(c) || c <= 0) return "unknown";
    if (c === 35 || c === 55 || c === 51) return null;
    if (c === 30) return "fishing";
    if (c === 31 || c === 32 || c === 52 || c === 53 || c === 50 || (c >= 33 && c <= 34)) return "service";
    if (c === 36 || c === 37) return "pleasure";
    if (c >= 60 && c <= 69) return "passenger";
    if (c >= 70 && c <= 79) return "cargo";
    if (c >= 80 && c <= 89) return "tanker";
    return "other";
  }
  /* Digitraffic locations (GeoJSON) and a map of MMSI to ship type become anonymous records. */
  function fromDigitraffic(locations, types, now) {
    var out = [];
    (locations.features || []).forEach(function (f) {
      var p = f.properties || {}, c = f.geometry && f.geometry.coordinates;
      if (!c || !isFinite(c[0]) || !isFinite(c[1]) || Math.abs(c[1]) > 90 || Math.abs(c[0]) > 180) return;
      var cls = classify(types[p.mmsi]);
      if (cls === null) return;
      var seen = p.timestampExternal || now;
      out.push({ lat: Math.round(c[1] * 1000) / 1000, lon: Math.round(c[0] * 1000) / 1000, sog: p.sog === undefined || p.sog >= 102.3 ? null : Math.round(p.sog * 10) / 10,
        cog: p.cog === undefined || p.cog >= 360 ? null : Math.round(p.cog), cls: cls, age_s: Math.max(0, Math.round((now - seen) / 1000)), src: "digitraffic" });
    });
    return out;
  }
  if (typeof module !== "undefined" && module.exports) module.exports = { classify: classify, fromDigitraffic: fromDigitraffic, LAKES: LAKES };
  if (typeof document === "undefined") return;

  function $(s) { return document.querySelector(s); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function mins(s) { return s < 90 ? Math.round(s) + " s" : Math.round(s / 60) + " min"; }
  function hhmm(d) { return String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0") + " UTC"; }
  function getJson(url, ms) {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms || 30000) : null;
    return fetch(url, ctl ? { signal: ctl.signal } : undefined).then(function (r) { if (timer) clearTimeout(timer); if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); });
  }

  var map = null, ready = false, hidden = {}, bySource = { digitraffic: [], relay: [] }, state = { digitraffic: "…", relay: cfg.aisRelayUrl ? "…" : "not connected" };
  var types = null, typesAt = 0;
  var presence = null, presenceOn = true;   // 30-day AIS presence from Global Fishing Watch (anonymous cells)

  function presenceGeojson() {
    var rows = presence ? presence.data : [];
    return { type: "FeatureCollection", features: rows.map(function (r) {
      return { type: "Feature", properties: { vessels: r[2], hours: r[3], cls: JSON.stringify(r[4]) }, geometry: { type: "Point", coordinates: [r[1], r[0]] } };
    }) };
  }
  function addPresence() {
    if (!map || !ready || !presence || map.getSource("presence")) return;
    map.addSource("presence", { type: "geojson", data: presenceGeojson() });
    map.addLayer({ id: "presence-dots", type: "circle", source: "presence",
      layout: { visibility: presenceOn ? "visible" : "none" },
      paint: {
        "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, ["interpolate", ["linear"], ["get", "vessels"], 1, 1.4, 20, 3.2, 100, 5], 6, ["interpolate", ["linear"], ["get", "vessels"], 1, 4, 20, 9, 100, 15]],
        "circle-color": ["interpolate", ["linear"], ["get", "vessels"], 1, "#35607a", 5, "#7bdff2", 20, "#ffd479", 60, "#ff9b54", 150, "#ff5d6c"],
        "circle-opacity": 0.55, "circle-stroke-width": 0 } }, map.getLayer("ais-dots") ? "ais-dots" : undefined);
    map.on("click", "presence-dots", function (e) {
      var f = e.features[0].properties, parts = [], cls = {};
      try { cls = JSON.parse(f.cls); } catch (err) { cls = {}; }
      Object.keys(cls).forEach(function (k) { parts.push((CLASSES[k] ? CLASSES[k][0] : k) + " " + cls[k]); });
      new maplibregl.Popup({ offset: 8 }).setLngLat(e.lngLat).setHTML("<strong>" + esc(f.vessels) + " vessel" + (Number(f.vessels) === 1 ? "" : "s") + "</strong> in this 0.2° cell<br>" + esc(Math.round(f.hours)) + " vessel-hours · " +
        esc(presence.date_start) + " to " + esc(presence.date_end) + "<br>" + esc(parts.join(", ")) + "<br><em>Anonymous AIS presence, Global Fishing Watch. Not live.</em>").addTo(map);
    });
    map.on("mouseenter", "presence-dots", function () { map.getCanvas().style.cursor = "pointer"; });
    map.on("mouseleave", "presence-dots", function () { map.getCanvas().style.cursor = ""; });
  }
  function loadPresence() {
    if (presence) return Promise.resolve();
    var note = $("#presence-note");
    return getJson("data/live/gfw_presence.json", 60000).then(function (d) {
      presence = d;
      if (note) note.textContent = d.date_start + " to " + d.date_end + ", " + d.cells.toLocaleString("en-US") + " cells. " + d.license + ".";
      addPresence();
    }).catch(function () { if (note) note.textContent = "The shipping-presence file could not be loaded."; });
  }

  function all() { return bySource.digitraffic.concat(bySource.relay); }
  function geojson() {
    return { type: "FeatureCollection", features: all().filter(function (v) { return !hidden[v.cls]; }).map(function (v) {
      return { type: "Feature", properties: { cls: v.cls, sog: v.sog, cog: v.cog, age_s: v.age_s, src: v.src }, geometry: { type: "Point", coordinates: [v.lon, v.lat] } };
    }) };
  }
  function draw() { if (map && ready && map.getSource("ais")) map.getSource("ais").setData(geojson()); }
  function legend() {
    var counts = {};
    all().forEach(function (v) { counts[v.cls] = (counts[v.cls] || 0) + 1; });
    $("#ais-legend").innerHTML = Object.keys(CLASSES).filter(function (k) { return counts[k]; }).map(function (k) {
      return '<label class="layer-ctl"><input type="checkbox" data-cls="' + k + '"' + (hidden[k] ? "" : " checked") + ' /><span class="dot-swatch" style="background:' + CLASSES[k][1] + '"></span><span>' +
        CLASSES[k][0] + " (" + counts[k] + ")</span></label>";
    }).join("");
  }
  function status() {
    var n = all().length, e = $("#ais-status");
    e.textContent = n + " positions shown. Baltic and Gulf of Bothnia (Digitraffic): " + state.digitraffic + ". Arctic relay: " + state.relay + ". Updated " + hhmm(new Date()) + ".";
    e.className = "form-status " + (n ? "ok" : "warn");
    var north = all().filter(function (v) { return v.lat >= 60; }).length, nEl = $("#ais-north");
    if (nEl) nEl.textContent = north.toLocaleString("en-US");
    var tEl = $("#ais-total"); if (tEl) tEl.textContent = n.toLocaleString("en-US");
  }
  function lakes() {
    var host = $("#ais-lakes");
    if (!host) return;
    var list = all();
    var counted = LAKES.map(function (l, i) { return { l: l, i: i, n: list.filter(function (v) { return v.lat >= l[2] && v.lat <= l[4] && v.lon >= l[3] && v.lon <= l[5]; }).length }; });
    counted.sort(function (a, b) { return b.n - a.n || a.i - b.i; });
    host.innerHTML = counted.map(function (c) {
      var l = c.l, i = c.i, n = c.n;
      var relayOnly = /relay only/i.test(l[6]) && !cfg.aisRelayUrl;
      return "<tr><td>" + esc(l[0]) + "<br><span class=\"muted\">" + esc(l[1]) + "</span></td><td>" + (relayOnly ? "<span class=\"muted\">no feed connected</span>" : n) +
        "</td><td class=\"muted\">" + esc(l[6]) + "</td><td><button type=\"button\" data-lake=\"" + i + "\">Zoom</button></td></tr>";
    }).join("");
  }
  function refresh() { legend(); draw(); status(); lakes(); }

  function loadDigitraffic() {
    var needTypes = !types || Date.now() - typesAt > 15 * 60 * 1000;
    var vessels = needTypes ? getJson(DIGI_VES, 45000).then(function (list) {
      var m = {}; list.forEach(function (v) { m[v.mmsi] = v.shipType; }); types = m; typesAt = Date.now();
    }).catch(function () { types = types || {}; }) : Promise.resolve();
    return vessels.then(function () { return getJson(DIGI_LOC, 30000); }).then(function (loc) {
      bySource.digitraffic = fromDigitraffic(loc, types, Date.now());
      state.digitraffic = bySource.digitraffic.length + " vessels";
    }).catch(function () { state.digitraffic = "did not answer"; });
  }
  function loadRelay() {
    if (!cfg.aisRelayUrl) return Promise.resolve();
    return getJson(cfg.aisRelayUrl, 30000).then(function (d) {
      bySource.relay = (d.vessels || []).map(function (v) { v.src = "relay"; return v; });
      state.relay = bySource.relay.length + " vessels";
    }).catch(function () { state.relay = "did not answer"; });
  }
  function tick() { Promise.all([loadDigitraffic().then(refresh), loadRelay().then(refresh)]).then(refresh); }

  function init() {
    if (!$("#ais-panel")) return;
    if (typeof maplibregl === "undefined") { $("#ais-status").textContent = "The map library did not load."; return; }
    map = new maplibregl.Map({ container: "ais-map", style: "https://tiles.openfreemap.org/styles/dark", center: cfg.aisRelayUrl ? [-20, 68] : [22, 62.5], zoom: cfg.aisRelayUrl ? 1.7 : 4.2,
      attributionControl: { compact: true }, cooperativeGestures: true });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    try { (window.AtlasMaps = window.AtlasMaps || []).push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); } catch (e) { /* optional */ }
    if (typeof ResizeObserver === "function") new ResizeObserver(function () { map.resize(); }).observe($("#ais-map"));
    map.on("style.load", function () {
      map.addSource("ais", { type: "geojson", data: geojson() });
      var colour = ["match", ["get", "cls"]]; Object.keys(CLASSES).forEach(function (k) { colour.push(k, CLASSES[k][1]); }); colour.push("#e8f2f5");
      map.addLayer({ id: "ais-dots", type: "circle", source: "ais", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 1, 2.5, 6, 5], "circle-color": colour, "circle-stroke-color": "#06121b", "circle-stroke-width": 1, "circle-opacity": 0.92 } });
      map.on("click", "ais-dots", function (e) {
        var p = e.features[0].properties, c = CLASSES[p.cls] || CLASSES.unknown;
        new maplibregl.Popup({ offset: 8 }).setLngLat(e.lngLat).setHTML("<strong>" + esc(c[0]) + "</strong><br>" + (p.sog !== "null" && p.sog !== null ? "Speed " + esc(p.sog) + " kn" : "Speed not reported") +
          (p.cog !== "null" && p.cog !== null ? " · course " + esc(p.cog) + "°" : "") + "<br>Position " + mins(Number(p.age_s)) + " old<br><em>No name or identifier is published.</em>").addTo(map);
      });
      map.on("mouseenter", "ais-dots", function () { map.getCanvas().style.cursor = "pointer"; });
      map.on("mouseleave", "ais-dots", function () { map.getCanvas().style.cursor = ""; });
      ready = true; draw();
      if (presenceOn) loadPresence();
    });
    var box = $("#presence-on");
    if (box) box.addEventListener("change", function () {
      presenceOn = box.checked;
      if (presenceOn && !presence) { loadPresence(); return; }
      if (map && map.getLayer("presence-dots")) map.setLayoutProperty("presence-dots", "visibility", presenceOn ? "visible" : "none");
    });
    var lt = $("#ais-lakes");
    if (lt) lt.addEventListener("click", function (e) {
      var b = e.target.closest && e.target.closest("button[data-lake]");
      if (!b) return;
      var l = LAKES[Number(b.getAttribute("data-lake"))];
      map.fitBounds([[l[3], l[2]], [l[5], l[4]]], { padding: 30, maxZoom: 9, duration: 700 });
      $("#ais-map").scrollIntoView({ block: "center", behavior: "smooth" });
    });
    $("#ais-legend").addEventListener("change", function (e) { var k = e.target.getAttribute("data-cls"); if (k) { hidden[k] = !e.target.checked; draw(); } });
    tick(); setInterval(tick, 60 * 1000);
  }
  document.addEventListener("DOMContentLoaded", init);
})();
