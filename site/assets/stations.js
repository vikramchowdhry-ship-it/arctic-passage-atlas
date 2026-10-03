/* Weather around the Arctic and the world, on one map and one table. Everything is fetched in the visitor's
 * browser from public services:
 *   - observed: Environment Canada SWOB stations north of 60 N, and U.S. National Weather Service stations
 *     in northern Alaska (real station reports, newest only)
 *   - model: Open-Meteo current-conditions analysis at ports and Arctic-rim places that have no open station
 *     feed here. These are gridded model values at a point, not a station, and are drawn hollow.
 * Nothing is stored or sent anywhere else.
 */
(function () {
  "use strict";

  var ECCC = "https://api.weather.gc.ca/collections/swob-realtime/items?f=json&limit=500&bbox=-141,60,-52,84&sortby=-date_tm-value" +
    "&properties=stn_nam-value,date_tm-value,air_temp,avg_wnd_spd_10m_pst10mts,avg_wnd_dir_10m_pst10mts,stn_pres";
  var NWS = "https://api.weather.gov/stations/";
  var OPEN_METEO = "https://api.open-meteo.com/v1/forecast";
  var BASE = (document.currentScript && document.currentScript.src.replace(/assets\/stations\.js.*$/, "")) || "";
  var MAX_AGE_H = 4;   // observations older than this are treated as not reporting

  var ALASKA = [
    ["PABR", "Utqiagvik"], ["PASC", "Deadhorse"], ["PABA", "Barter Island"], ["PAQT", "Nuiqsut"], ["PAWI", "Wiseman"],
    ["PAOT", "Kotzebue"], ["PAIK", "Kiana"], ["PASH", "Shishmaref"], ["PAPO", "Point Hope"], ["PAOM", "Nome"],
    ["PAGM", "Gambell"], ["PABT", "Bettles"], ["PAFA", "Fairbanks"]
  ];
  // Arctic-rim places without an open station feed in this page.
  var RIM = [
    ["Longyearbyen", "Norway (Svalbard)", 15.65, 78.22], ["Ny-Ålesund", "Norway (Svalbard)", 11.93, 78.92],
    ["Hammerfest", "Norway", 23.68, 70.66], ["Kirkenes", "Norway", 30.05, 69.73], ["Bodø", "Norway", 14.4, 67.28],
    ["Arkhangelsk", "Russia", 40.5, 64.55], ["Dikson", "Russia", 80.5, 73.5], ["Tiksi", "Russia", 128.87, 71.63],
    ["Pevek", "Russia", 170.27, 69.7], ["Anadyr", "Russia", 177.5, 64.73], ["Tórshavn", "Faroe Islands", -6.77, 62.01],
    ["Akureyri", "Iceland", -18.1, 65.68], ["Ittoqqortoormiit", "Greenland", -21.95, 70.48], ["Ilulissat", "Greenland", -51.1, 69.22],
    ["Qaanaaq", "Greenland", -69.36, 77.47], ["Alert", "Canada (Nunavut)", -62.3, 82.5], ["Eureka", "Canada (Nunavut)", -85.9, 80.0]
  ];

  function $(s) { return document.querySelector(s); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function num(v, d) { return v === null || v === undefined || isNaN(Number(v)) ? "—" : Number(v).toFixed(d); }
  function hhmm(d) { return pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + " UTC"; }
  function fetchJson(url, ms) {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms || 20000) : null;
    return fetch(url, ctl ? { signal: ctl.signal } : undefined).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  function retry(url) { return fetchJson(url).catch(function () { return new Promise(function (r) { setTimeout(r, 1500); }).then(function () { return fetchJson(url); }); }); }

  var records = [], map = null, markers = [], mapReady = false, view = { region: "arctic", observed: true, model: true };
  var status = { eccc: "…", nws: "…", model: "…" };

  /* ---- sources -------------------------------------------------------------------------------- */
  function loadEccc() {
    return fetchJson(ECCC, 30000).then(function (d) {
      var seen = {}, out = [];
      (d.features || []).forEach(function (f) {
        var p = f.properties, name = p["stn_nam-value"];
        if (!name || seen[name] || !f.geometry) return;
        seen[name] = 1;
        var t = new Date(p["date_tm-value"]);
        if ((Date.now() - t.getTime()) / 3600000 > MAX_AGE_H) return;
        out.push({ name: name.replace(/\b\w+/g, function (w) { return w.length > 2 ? w[0] + w.slice(1).toLowerCase() : w; }), country: "Canada", lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1],
          temp: p.air_temp, wind: p.avg_wnd_spd_10m_pst10mts, dir: p.avg_wnd_dir_10m_pst10mts, press: p.stn_pres, time: t, kind: "observed", source: "Environment and Climate Change Canada (SWOB)" });
      });
      records = records.concat(out); status.eccc = out.length + " stations";
    }).catch(function () { status.eccc = "unavailable"; });
  }
  function loadNws() {
    return Promise.all(ALASKA.map(function (s) {
      return fetchJson(NWS + s[0] + "/observations/latest", 20000).then(function (j) {
        var p = j.properties, t = new Date(p.timestamp);
        if (isNaN(t) || (Date.now() - t.getTime()) / 3600000 > MAX_AGE_H || p.temperature.value === null) return null;
        return { name: s[1], country: "United States (Alaska)", lon: j.geometry.coordinates[0], lat: j.geometry.coordinates[1], temp: p.temperature.value,
          wind: p.windSpeed.value, dir: p.windDirection.value, press: p.barometricPressure.value === null ? null : p.barometricPressure.value / 100, time: t, kind: "observed",
          source: "U.S. National Weather Service (" + s[0] + ")" };
      }).catch(function () { return null; });
    })).then(function (list) {
      var ok = list.filter(Boolean); records = records.concat(ok); status.nws = ok.length + " stations";
    });
  }
  function loadModel() {
    return fetchJson(BASE + "data/route/ports.json").catch(function () { return { ports: [] }; }).then(function (d) {
      var pts = d.ports.map(function (p) { return { name: p.name, country: p.country, lon: p.lon, lat: p.lat }; })
        .concat(RIM.map(function (r) { return { name: r[0], country: r[1], lon: r[2], lat: r[3] }; }));
      var batches = [];
      for (var i = 0; i < pts.length; i += 40) batches.push(pts.slice(i, i + 40));
      return Promise.all(batches.map(function (b) {
        var url = OPEN_METEO + "?latitude=" + b.map(function (p) { return p.lat.toFixed(2); }).join(",") + "&longitude=" + b.map(function (p) { return p.lon.toFixed(2); }).join(",") +
          "&current=temperature_2m,wind_speed_10m,wind_direction_10m,pressure_msl&wind_speed_unit=kmh&timezone=GMT";
        return retry(url).then(function (res) {
          [].concat(res).forEach(function (r, k) {
            var c = r.current, p = b[k];
            if (!c) return;
            records.push({ name: p.name, country: p.country, lon: p.lon, lat: p.lat, temp: c.temperature_2m, wind: c.wind_speed_10m, dir: c.wind_direction_10m,
              press: c.pressure_msl, time: new Date(c.time + ":00Z"), kind: "model", source: "Open-Meteo model analysis at this point (not a station)" });
          });
        }).catch(function () { /* this batch is left out */ });
      }));
    }).then(function () { status.model = records.filter(function (r) { return r.kind === "model"; }).length + " points"; });
  }

  /* ---- rendering ------------------------------------------------------------------------------ */
  function colour(t) {
    if (t === null || t === undefined || isNaN(t)) return "#9cb5c2";
    var k = Math.max(0, Math.min(1, (t + 30) / 60));               // -30 C blue to +30 C red
    return "hsl(" + Math.round(210 - 210 * k) + ",85%," + (k > 0.5 ? 58 : 62) + "%)";
  }
  function visible() {
    return records.filter(function (r) {
      if (r.kind === "observed" && !view.observed) return false;
      if (r.kind === "model" && !view.model) return false;
      return view.region === "world" || r.lat >= 60;
    }).sort(function (a, b) { return b.lat - a.lat; });
  }
  function popupHtml(r) {
    return "<strong>" + esc(r.name) + "</strong><br>" + esc(r.country) + "<br>" + num(r.temp, 1) + " °C · " + num(r.wind, 0) + " km/h" + (r.dir !== null && r.dir !== undefined ? " from " + Math.round(r.dir) + "°" : "") +
      "<br>" + (r.press ? num(r.press, 0) + " hPa · " : "") + hhmm(r.time) + "<br><em>" + esc(r.source) + "</em>";
  }
  function render() {
    var list = visible();
    $("#stn-count").textContent = list.length + " places";
    $("#stn-body").innerHTML = list.length ? list.map(function (r) {
      return "<tr><td>" + esc(r.name) + "<br><span class=\"muted\">" + esc(r.country) + "</span></td><td><span class=\"badge " + (r.kind === "observed" ? "ok" : "") + "\">" + (r.kind === "observed" ? "station" : "model") + "</span></td>" +
        "<td>" + num(r.temp, 1) + " °C</td><td>" + num(r.wind, 0) + " km/h" + (r.dir !== null && r.dir !== undefined ? " <span class=\"muted\">" + Math.round(r.dir) + "°</span>" : "") + "</td><td>" + (r.press ? num(r.press, 0) + " hPa" : "—") +
        "</td><td>" + hhmm(r.time) + "</td></tr>";
    }).join("") : "<tr><td colspan=\"6\">Nothing to show with these filters, or the services did not answer.</td></tr>";
    $("#stn-status").textContent = "Canada: " + status.eccc + " · Alaska: " + status.nws + " · model points: " + status.model + ".";
    drawMap(list);
  }
  function drawMap(list) {
    if (!map || !mapReady) return;
    markers.forEach(function (m) { m.remove(); }); markers = [];
    list.forEach(function (r) {
      var el = document.createElement("div");
      el.className = "stn " + r.kind; el.style.setProperty("--c", colour(r.temp));
      el.setAttribute("role", "img"); el.setAttribute("aria-label", r.name + " " + num(r.temp, 0) + " degrees Celsius, " + (r.kind === "observed" ? "station" : "model"));
      markers.push(new maplibregl.Marker({ element: el }).setLngLat([r.lon, r.lat]).setPopup(new maplibregl.Popup({ offset: 10, maxWidth: "260px" }).setHTML(popupHtml(r))).addTo(map));
    });
    if (list.length) {
      var b = list.reduce(function (acc, r) { return acc.extend([r.lon, r.lat]); }, new maplibregl.LngLatBounds([list[0].lon, list[0].lat], [list[0].lon, list[0].lat]));
      map.fitBounds(b, { padding: 40, maxZoom: view.region === "arctic" ? 3.6 : 3, duration: 500 });
    }
  }
  function initMap() {
    var el = $("#stn-map");
    if (!el || typeof maplibregl === "undefined") return;
    map = new maplibregl.Map({ container: el, style: "https://tiles.openfreemap.org/styles/dark", center: [-60, 70], zoom: 1.8, attributionControl: { compact: true }, cooperativeGestures: true });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    try { (window.AtlasMaps = window.AtlasMaps || []).push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); } catch (e) { /* optional */ }
    if (typeof ResizeObserver === "function") new ResizeObserver(function () { map.resize(); }).observe(el);
    map.on("style.load", function () { mapReady = true; render(); });
  }

  function exportCsv() {
    var X = window.AtlasExport; if (!X) return;
    var rows = visible().map(function (r) { return { name: r.name, country: r.country, kind: r.kind, lat: r.lat.toFixed(3), lon: r.lon.toFixed(3), temperature_c: r.temp, wind_kmh: r.wind, wind_from_deg: r.dir, pressure_hpa: r.press, time_utc: r.time.toISOString(), source: r.source }; });
    X.download("arctic-passage-atlas-weather-" + new Date().toISOString().slice(0, 10) + ".csv", X.toCsv(rows), "text/csv;charset=utf-8");
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("#stn-map")) return;
    initMap();
    document.querySelectorAll("[name=stn-region]").forEach(function (r) { r.addEventListener("change", function () { view.region = r.value; render(); }); });
    $("#stn-observed").addEventListener("change", function () { view.observed = this.checked; render(); });
    $("#stn-model").addEventListener("change", function () { view.model = this.checked; render(); });
    $("#stn-csv").addEventListener("click", exportCsv);
    function load() {
      records = []; status = { eccc: "…", nws: "…", model: "…" };
      Promise.all([loadEccc().then(render), loadNws().then(render), loadModel().then(render)]).then(function () {
        $("#stn-updated").textContent = "Loaded " + hhmm(new Date()) + ".";
        render();
      });
    }
    load();
    setInterval(load, 15 * 60 * 1000);
  });
})();
