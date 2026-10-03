/* Live conditions: three third-party feeds, none of them project results.
 *   1. Environment Canada station observations (fetched by the browser; falls back to a dated snapshot).
 *   2. NASA GIBS imagery tiles (fetched by the browser from NASA).
 *   3. NSIDC pan-Arctic sea-ice extent (a snapshot refreshed on a schedule by `live-feeds`).
 * Every value is shown with its observation time, and anything old is flagged as stale.
 */
(function () {
  "use strict";

  var STATION_URL = "https://api.weather.gc.ca/collections/swob-realtime/items";
  var STATION_NAME = "CAMBRIDGE BAY GSN";
  var STATION_STALE_MIN = 180;
  var ICE_STALE_HOURS = 60;
  var AOI = { west: -105.65, south: 68.95, east: -104.55, north: 69.35 };
  var BASE = (document.currentScript && document.currentScript.src.replace(/assets\/live\.js.*$/, "")) || "";

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); }
  function setAll(key, text) { $all('[data-live="' + key + '"]').forEach(function (el) { el.textContent = text; }); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function hhmm(d) { return pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + " UTC"; }
  function ago(ms) {
    var m = Math.max(0, Math.round(ms / 60000));
    if (m < 2) return "just now";
    if (m < 120) return m + " min ago";
    var h = Math.round(m / 60);
    return h < 48 ? h + " h ago" : Math.round(h / 24) + " d ago";
  }
  var CARDINALS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  function cardinal(deg) { return CARDINALS[Math.round(deg / 22.5) % 16]; }
  function num(field, digits) {
    if (!field || field.value === null || field.value === undefined || isNaN(Number(field.value))) return null;
    return Number(field.value).toFixed(digits === undefined ? 1 : digits);
  }
  function unit(field, fallback) {
    var u = field && field.unit;
    return u && u.indexOf("�") === -1 ? u : fallback;
  }

  /* ---- 1. station -------------------------------------------------------------------------- */
  function fromSwob(feature) {
    var p = feature.properties;
    function f(k) { return p[k] === undefined || p[k] === null ? null : { value: p[k], unit: p[k + "-uom"] }; }
    return {
      station: p["stn_nam-value"], observed_at: p["date_tm-value"], air_temperature: f("air_temp"),
      relative_humidity: f("rel_hum"), station_pressure: f("stn_pres"),
      wind_speed_10m_10min: f("avg_wnd_spd_10m_pst10mts"), wind_direction_10m_10min: f("avg_wnd_dir_10m_pst10mts")
    };
  }

  function fetchJson(url, ms) {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms || 9000) : null;
    return fetch(url, ctl ? { signal: ctl.signal } : undefined).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  function renderStation(obs, source) {
    var t = num(obs.air_temperature), ws = num(obs.wind_speed_10m_10min), rh = num(obs.relative_humidity, 0);
    var p = num(obs.station_pressure), dir = obs.wind_direction_10m_10min && obs.wind_direction_10m_10min.value;
    setAll("temp", t === null ? "n/a" : t);
    setAll("temp-unit", unit(obs.air_temperature, "°C"));
    setAll("wind", ws === null ? "n/a" : ws);
    setAll("wind-unit", unit(obs.wind_speed_10m_10min, "km/h"));
    setAll("winddir", dir === null || dir === undefined ? "" : "from " + cardinal(Number(dir)) + " (" + Math.round(dir) + "°)");
    setAll("rh", rh === null ? "n/a" : rh);
    setAll("pressure", p === null ? "n/a" : p);
    var when = new Date(obs.observed_at);
    var ageMin = (Date.now() - when.getTime()) / 60000;
    var stale = !(ageMin >= 0) || ageMin > STATION_STALE_MIN;
    var label = (isNaN(when) ? "time unknown" : hhmm(when) + " · " + ago(Date.now() - when.getTime()));
    setAll("obs-time", label);
    $all('[data-live="obs-time"]').forEach(function (el) { el.setAttribute("data-live-obs-iso", obs.observed_at); });
    setAll("station-name", obs.station || STATION_NAME);
    setAll("station-source", source === "live" ? "Live request to Environment Canada" : "Saved snapshot (live request failed)");
    $all("[data-live-dot]").forEach(function (el) {
      el.className = "dot " + (source === "live" && !stale ? "live" : "stale");
    });
    setAll("status-text", source === "live" && !stale ? "Station reporting" : "Station data may be stale");
  }

  function loadStation() {
    var q = "?f=json&limit=1&sortby=-date_tm-value&stn_nam-value=" + encodeURIComponent(STATION_NAME);
    return fetchJson(STATION_URL + q).then(function (data) {
      if (!data.features || !data.features.length) throw new Error("no observations");
      renderStation(fromSwob(data.features[0]), "live");
    }).catch(function () {
      return fetchJson(BASE + "data/live/station_snapshot.json").then(function (snap) { renderStation(snap, "snapshot"); })
        .catch(function () { setAll("status-text", "Station feed unavailable"); });
    });
  }


  /* ---- chart hover readout ------------------------------------------------------------------ */
  function attachTip(host, svg, W, H, L, R, T, B, lookup) {
    var tip = document.createElement("div");
    tip.className = "chart-tip"; tip.hidden = true; host.style.position = "relative"; host.appendChild(tip);
    var rule = document.createElementNS("http://www.w3.org/2000/svg", "line");
    rule.setAttribute("y1", T); rule.setAttribute("y2", H - B); rule.setAttribute("stroke", "#e8f2f5");
    rule.setAttribute("stroke-opacity", ".35"); rule.setAttribute("visibility", "hidden"); svg.appendChild(rule);
    function move(ev) {
      var box = svg.getBoundingClientRect();
      var px = ((ev.clientX - box.left) / box.width) * W;
      var frac = Math.min(1, Math.max(0, (px - L) / (W - L - R)));
      var info = lookup(frac);
      if (!info) { tip.hidden = true; rule.setAttribute("visibility", "hidden"); return; }
      var x = L + frac * (W - L - R);
      rule.setAttribute("x1", x); rule.setAttribute("x2", x); rule.setAttribute("visibility", "visible");
      tip.innerHTML = info; tip.hidden = false;
      var left = (x / W) * box.width + 12;
      tip.style.left = Math.min(left, box.width - tip.offsetWidth - 4) + "px";
    }
    svg.addEventListener("pointermove", move);
    svg.addEventListener("pointerleave", function () { tip.hidden = true; rule.setAttribute("visibility", "hidden"); });
  }

  /* ---- 24-hour station history ---------------------------------------------------------------- */
  function loadHistory() {
    var host = $("#station-chart");
    if (!host) return Promise.resolve();
    var q = "?f=json&limit=1500&sortby=-date_tm-value&properties=date_tm-value,air_temp,avg_wnd_spd_10m_pst10mts&stn_nam-value=" +
      encodeURIComponent(STATION_NAME);
    return fetchJson(STATION_URL + q, 15000).then(function (data) {
      var rows = (data.features || []).map(function (f) {
        return { t: new Date(f.properties["date_tm-value"]).getTime(), temp: f.properties.air_temp, wind: f.properties.avg_wnd_spd_10m_pst10mts };
      }).filter(function (r) { return !isNaN(r.t); }).reverse();
      // one point per 10 minutes keeps the chart light without hiding the shape
      var pts = rows.filter(function (r, i) { return i % 10 === 0; });
      if (pts.length < 6) throw new Error("not enough history");
      var W = 900, H = 300, L = 52, R = 52, T = 14, B = 34;
      var t0 = pts[0].t, t1 = pts[pts.length - 1].t;
      var temps = pts.map(function (r) { return r.temp; }).filter(function (v) { return v !== null; });
      var winds = pts.map(function (r) { return r.wind; }).filter(function (v) { return v !== null; });
      var tMin = Math.floor(Math.min.apply(null, temps) - 1), tMax = Math.ceil(Math.max.apply(null, temps) + 1);
      var wMax = Math.ceil(Math.max.apply(null, winds) / 10) * 10 || 10;
      var x = function (t) { return L + ((t - t0) / (t1 - t0)) * (W - L - R); };
      var yT = function (v) { return T + (1 - (v - tMin) / (tMax - tMin)) * (H - T - B); };
      var yW = function (v) { return T + (1 - v / wMax) * (H - T - B); };
      function path(key, y) {
        var d = "", pen = false;
        pts.forEach(function (r) {
          var v = r[key];
          if (v === null || v === undefined) { pen = false; return; }
          d += (pen ? "L" : "M") + x(r.t).toFixed(1) + " " + y(v).toFixed(1); pen = true;
        });
        return d;
      }
      var g = "";
      for (var i = 0; i <= 4; i++) {
        var yy = T + (i / 4) * (H - T - B);
        g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + yy + '" y2="' + yy + '" stroke="#24465b"/>';
        g += '<text x="' + (L - 8) + '" y="' + (yy + 4) + '" fill="#7bdff2" font-size="12" text-anchor="end">' + (tMax - (i / 4) * (tMax - tMin)).toFixed(0) + "</text>";
        g += '<text x="' + (W - R + 8) + '" y="' + (yy + 4) + '" fill="#ffb454" font-size="12">' + (wMax - (i / 4) * wMax).toFixed(0) + "</text>";
      }
      for (var h = 0; h <= 24; h += 6) {
        var tt = t1 - (24 - h) * 3600000;
        var d = new Date(tt);
        g += '<text x="' + x(tt) + '" y="' + (H - 12) + '" fill="#9cb5c2" font-size="12" text-anchor="middle">' + pad(d.getUTCHours()) + ":00</text>";
      }
      g += '<text x="14" y="' + (T + 6) + '" fill="#7bdff2" font-size="11" transform="rotate(-90 14 ' + (T + 6) + ')" text-anchor="end">air temperature \u00b0C</text>';
      g += '<text x="' + (W - 12) + '" y="' + (T + 6) + '" fill="#ffb454" font-size="11" transform="rotate(90 ' + (W - 12) + " " + (T + 6) + ')">wind km/h</text>';
      g += '<path d="' + path("wind", yW) + '" fill="none" stroke="#ffb454" stroke-width="1.8" opacity=".9"/>';
      g += '<path d="' + path("temp", yT) + '" fill="none" stroke="#7bdff2" stroke-width="2.6" stroke-linejoin="round"/>';
      host.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-labelledby="st-t st-d" xmlns="http://www.w3.org/2000/svg">' +
        '<title id="st-t">Cambridge Bay air temperature and wind, last 24 hours</title>' +
        '<desc id="st-d">Temperature ranged from ' + Math.min.apply(null, temps) + " to " + Math.max.apply(null, temps) +
        " degrees Celsius; wind up to " + Math.max.apply(null, winds) + " kilometres per hour.</desc>" + g + "</svg>";
      attachTip(host, host.querySelector("svg"), W, H, L, R, T, B, function (frac) {
        var tm = t0 + frac * (t1 - t0), best = pts[0];
        pts.forEach(function (r) { if (Math.abs(r.t - tm) < Math.abs(best.t - tm)) best = r; });
        return "<b>" + hhmm(new Date(best.t)) + "</b><br>" + (best.temp === null ? "n/a" : best.temp.toFixed(1)) + " \u00b0C \u00b7 " +
          (best.wind === null ? "n/a" : best.wind.toFixed(1)) + " km/h";
      });
      setAll("history-range", "Last 24 hours, one point every 10 minutes, to " + hhmm(new Date(t1)));
    }).catch(function () {
      host.innerHTML = '<p class="chart-note" style="padding:1rem">The 24-hour history could not be loaded.</p>';
    });
  }

  /* ---- 3. sea-ice extent chart -------------------------------------------------------------- */
  var MONTH_START = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function pathFor(values, x, y) {
    var d = "", pen = false;
    values.forEach(function (v, i) {
      if (v === null || v === undefined) { pen = false; return; }
      d += (pen ? "L" : "M") + x(i).toFixed(1) + " " + y(v).toFixed(1);
      pen = true;
    });
    return d;
  }

  function drawChart(host, s) {
    var W = 900, H = 380, L = 54, R = 18, T = 16, B = 38, y0 = 2, y1 = 18;
    var x = function (i) { return L + (i / 365) * (W - L - R); };
    var y = function (v) { return T + (1 - (v - y0) / (y1 - y0)) * (H - T - B); };
    var g = "";
    for (var v = y0; v <= y1; v += 4) {
      g += '<line x1="' + L + '" x2="' + (W - R) + '" y1="' + y(v) + '" y2="' + y(v) + '" stroke="#24465b" stroke-width="1"/>' +
        '<text x="' + (L - 8) + '" y="' + (y(v) + 4) + '" fill="#9cb5c2" font-size="12" text-anchor="end">' + v + "</text>";
    }
    MONTH_START.forEach(function (start, i) {
      g += '<text x="' + (x(start) + 3) + '" y="' + (H - 14) + '" fill="#9cb5c2" font-size="12">' + MONTHS[i] + "</text>";
    });
    g += '<text x="14" y="' + (T + 8) + '" fill="#9cb5c2" font-size="11" transform="rotate(-90 14 ' + (T + 8) + ')" text-anchor="end">million km²</text>';
    var ser = s.series;
    g += '<path d="' + pathFor(ser.baseline_mean, x, y) + '" fill="none" stroke="#9cb5c2" stroke-width="2"/>';
    if (ser.record_low_year) g += '<path d="' + pathFor(ser.record_low_year.values, x, y) + '" fill="none" stroke="#ff6b7a" stroke-width="2" stroke-dasharray="5 4"/>';
    g += '<path d="' + pathFor(ser.previous_year.values, x, y) + '" fill="none" stroke="#a79bff" stroke-width="2"/>';
    g += '<path d="' + pathFor(ser.this_year.values, x, y) + '" fill="none" stroke="#7bdff2" stroke-width="3.2" stroke-linejoin="round"/>';
    var last = -1;
    ser.this_year.values.forEach(function (val, i) { if (val !== null) last = i; });
    if (last >= 0) {
      var lv = ser.this_year.values[last];
      g += '<line x1="' + x(last) + '" x2="' + x(last) + '" y1="' + T + '" y2="' + (H - B) + '" stroke="#7bdff2" stroke-dasharray="2 4" opacity=".6"/>' +
        '<circle cx="' + x(last) + '" cy="' + y(lv) + '" r="5" fill="#7bdff2" stroke="#06121b" stroke-width="2"/>';
    }
    var title = "Pan-Arctic sea-ice extent through the year";
    var desc = s.this_year_label + ": " + s.latest_extent_million_km2.toFixed(3) + " million km² on " + s.latest_date +
      ", compared with the " + s.baseline_period + " average for that date of " + (s.baseline_mean_same_day || "n/a") + ".";
    host.innerHTML = '<svg viewBox="0 0 ' + W + " " + H + '" role="img" aria-labelledby="ice-t ice-d" xmlns="http://www.w3.org/2000/svg">' +
      '<title id="ice-t">' + title + '</title><desc id="ice-d">' + desc + "</desc>" + g + "</svg>";
    attachTip(host, host.querySelector("svg"), W, H, L, R, T, B, function (frac) {
      var i = Math.round(frac * 365), cal = new Date(Date.UTC(2000, 0, 1 + i));
      function f(v) { return v === null || v === undefined ? "n/a" : v.toFixed(2); }
      return "<b>" + cal.getUTCDate() + " " + MONTHS[cal.getUTCMonth()] + "</b><br>" +
        '<span style="color:#7bdff2">' + s.this_year_label + ": " + f(ser.this_year.values[i]) + "</span><br>" +
        '<span style="color:#a79bff">' + ser.previous_year.year + ": " + f(ser.previous_year.values[i]) + "</span><br>" +
        (ser.record_low_year ? '<span style="color:#ff6b7a">' + ser.record_low_year.year + ": " + f(ser.record_low_year.values[i]) + "</span><br>" : "") +
        '<span style="color:#9cb5c2">mean: ' + f(ser.baseline_mean[i]) + "</span>";
    });
  }

  function loadIce() {
    var host = $("#ice-chart");
    var hasKpi = $("[data-ice]");
    if (!host && !hasKpi) return Promise.resolve();
    return fetchJson(BASE + "data/live/nsidc_extent.json", 12000).then(function (s) {
      s.this_year_label = String(s.series.this_year.year);
      var rank = s.rank_from_lowest + " of " + (s.same_day_years_compared + 1);
      var diff = s.baseline_mean_same_day ? s.latest_extent_million_km2 - s.baseline_mean_same_day : null;
      $all('[data-ice="extent"]').forEach(function (el) { el.textContent = s.latest_extent_million_km2.toFixed(2); });
      $all('[data-ice="date"]').forEach(function (el) { el.textContent = s.latest_date; });
      $all('[data-ice="rank"]').forEach(function (el) { el.textContent = rank; });
      $all('[data-ice="vs-baseline"]').forEach(function (el) {
        el.textContent = diff === null ? "n/a" : (diff >= 0 ? "+" : "−") + Math.abs(diff).toFixed(2);
      });
      $all('[data-ice="baseline"]').forEach(function (el) { el.textContent = s.baseline_period; });
      $all('[data-ice="record"]').forEach(function (el) {
        el.textContent = s.lowest_on_record_same_day ? s.lowest_on_record_same_day.extent.toFixed(2) + " (" + s.lowest_on_record_same_day.year + ")" : "n/a";
      });
      var ageH = (Date.now() - new Date(s.retrieved_at).getTime()) / 3600000;
      $all('[data-ice="retrieved"]').forEach(function (el) {
        el.textContent = "Snapshot taken " + s.retrieved_at.replace("T", " ").replace(/\+00:00$/, " UTC") + (ageH > ICE_STALE_HOURS ? " — older than expected" : "");
      });
      if (host) drawChart(host, s);
    }).catch(function () {
      if (host) host.innerHTML = '<p class="chart-note" style="padding:1rem">The sea-ice snapshot could not be loaded.</p>';
    });
  }

  /* ---- 2. NASA GIBS map ---------------------------------------------------------------------- */
  var GIBS_LAYERS = {
    MODIS_Terra_CorrectedReflectance_TrueColor: "MODIS Terra true colour",
    MODIS_Aqua_CorrectedReflectance_TrueColor: "MODIS Aqua true colour",
    VIIRS_SNPP_CorrectedReflectance_TrueColor: "VIIRS Suomi NPP true colour"
  };
  function tileUrl(layer, date) {
    return "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/" + layer + "/default/" + date +
      "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg";
  }
  function isoDay(d) { return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()); }

  function initMap() {
    var el = $("#live-map");
    if (!el || typeof maplibregl === "undefined") return;
    var dateInput = $("#map-date"), layerSel = $("#map-layer");
    var yesterday = new Date(Date.now() - 86400000);
    dateInput.max = isoDay(new Date());
    dateInput.value = isoDay(yesterday);
    Object.keys(GIBS_LAYERS).forEach(function (k) {
      var o = document.createElement("option"); o.value = k; o.textContent = GIBS_LAYERS[k]; layerSel.appendChild(o);
    });
    var map = new maplibregl.Map({ cooperativeGestures: true,
      container: el,
      style: {
        version: 8,
        sources: { gibs: { type: "raster", tiles: [tileUrl(layerSel.value, dateInput.value)], tileSize: 256, maxzoom: 9,
          attribution: "Imagery: NASA GIBS / ESDIS (MODIS, VIIRS)" } },
        layers: [
          { id: "bg", type: "background", paint: { "background-color": "#081925" } },
          { id: "gibs", type: "raster", source: "gibs" }
        ]
      },
      center: [-105.1, 69.15], zoom: 6, minZoom: 3, maxZoom: 11, attributionControl: { compact: true }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    // MapLibre sizes its canvas once at creation; follow the container so layout changes never leave it small.
    try { (window.AtlasMaps = window.AtlasMaps || []).push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); } catch (e) { /* tools are optional */ }
    if (typeof ResizeObserver === "function") new ResizeObserver(function () { map.resize(); }).observe(el);
    window.addEventListener("load", function () { map.resize(); });
    map.on("load", function () {
      map.addSource("aoi", { type: "geojson", data: { type: "Feature", properties: {}, geometry: { type: "Polygon", coordinates: [[
        [AOI.west, AOI.south], [AOI.east, AOI.south], [AOI.east, AOI.north], [AOI.west, AOI.north], [AOI.west, AOI.south]]] } } });
      map.addLayer({ id: "aoi-line", type: "line", source: "aoi", paint: { "line-color": "#ffb454", "line-width": 2.2 } });
    });
    function refresh() {
      var src = map.getSource("gibs");
      if (src && src.setTiles) src.setTiles([tileUrl(layerSel.value, dateInput.value)]);
      setAll("map-caption", GIBS_LAYERS[layerSel.value] + " · " + dateInput.value + " (UTC day)");
    }
    function shift(days) {
      var d = new Date(dateInput.value + "T00:00:00Z"); d.setUTCDate(d.getUTCDate() + days);
      if (isoDay(d) > dateInput.max) return;
      dateInput.value = isoDay(d); refresh();
    }
    dateInput.addEventListener("change", refresh);
    layerSel.addEventListener("change", refresh);
    $("#map-prev").addEventListener("click", function () { shift(-1); });
    $("#map-next").addEventListener("click", function () { shift(1); });
    $("#map-today").addEventListener("click", function () { dateInput.value = isoDay(new Date()); refresh(); });
    refresh();
    compare(map, el, layerSel, dateInput);
  }

  /* Before/after curtain: a second map of the same view with another date sits over the first and is clipped. */
  function compare(map, el, layerSel, dateInput) {
    var on = $("#cmp-on"), box = $("#live-map-b"), line = $("#cmp-line"), slider = $("#cmp-slider"), sliderWrap = $("#cmp-slider-wrap");
    var dateB = $("#cmp-date"), dateWrap = $("#cmp-date-wrap"), map2 = null;
    if (!on || !box) return;
    function clip() {
      var x = Number(slider.value);
      box.style.clipPath = "inset(0 0 0 " + x + "%)";
      line.style.left = x + "%";
    }
    function sync() { if (map2) map2.jumpTo({ center: map.getCenter(), zoom: map.getZoom(), bearing: map.getBearing(), pitch: map.getPitch() }); }
    function caption() {
      var cap = $('[data-live="map-caption"]');
      if (cap) cap.textContent = on.checked ? "Left " + dateInput.value + " · right " + dateB.value + " · " + GIBS_LAYERS[layerSel.value] + " (UTC days)" : GIBS_LAYERS[layerSel.value] + " · " + dateInput.value + " (UTC day)";
    }
    function refreshB() {
      if (!map2) return;
      var src = map2.getSource("gibs");
      if (src && src.setTiles) src.setTiles([tileUrl(layerSel.value, dateB.value)]);
      caption();
    }
    function enable() {
      var d = new Date(dateInput.value + "T00:00:00Z"); d.setUTCFullYear(d.getUTCFullYear() - 1);
      if (!dateB.value) dateB.value = isoDay(d);
      dateB.max = isoDay(new Date());
      [box, line, sliderWrap, dateWrap].forEach(function (n) { n.hidden = false; });
      if (!map2) {
        map2 = new maplibregl.Map({
          container: box, interactive: false, attributionControl: false,
          style: { version: 8, sources: { gibs: { type: "raster", tiles: [tileUrl(layerSel.value, dateB.value)], tileSize: 256, maxzoom: 9 } },
            layers: [{ id: "bg", type: "background", paint: { "background-color": "#081925" } }, { id: "gibs", type: "raster", source: "gibs" }] },
          center: map.getCenter(), zoom: map.getZoom(), minZoom: 3, maxZoom: 11
        });
        map.on("move", sync);
      } else { map2.resize(); refreshB(); }
      sync(); clip(); caption();
    }
    function disable() { [box, line, sliderWrap, dateWrap].forEach(function (n) { n.hidden = true; }); caption(); }
    on.addEventListener("change", function () { if (on.checked) enable(); else disable(); });
    slider.addEventListener("input", clip);
    dateB.addEventListener("change", refreshB);
    layerSel.addEventListener("change", refreshB);
    dateInput.addEventListener("change", caption);
    if (typeof ResizeObserver === "function") new ResizeObserver(function () { if (map2) map2.resize(); }).observe(el);
  }

  document.addEventListener("DOMContentLoaded", function () {
    if ($("[data-live]")) { loadStation(); setInterval(loadStation, 5 * 60 * 1000); }
    loadIce();
    loadHistory();
    setInterval(loadHistory, 15 * 60 * 1000);
    initMap();
    // Seconds until the next station request, so the page visibly stays alive, and keep "x min ago" honest.
    var next = Date.now() + 5 * 60 * 1000;
    setInterval(function () {
      if (Date.now() >= next) next = Date.now() + 5 * 60 * 1000;
      var left = Math.max(0, Math.round((next - Date.now()) / 1000));
      setAll("countdown", Math.floor(left / 60) + ":" + pad(left % 60));
      var ts = $("[data-live-obs-iso]");
      if (ts) {
        var w = new Date(ts.getAttribute("data-live-obs-iso"));
        setAll("obs-time", hhmm(w) + " · " + ago(Date.now() - w.getTime()));
      }
    }, 1000);
  });
})();
