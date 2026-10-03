/* Worldwide route planner. Everything runs in the visitor's browser:
 *   - shortest open-water path on a 0.1 degree world grid (assets/router.js, data/route/world.png)
 *   - sailing time, arrival times and sun position along the path
 *   - model forecasts for wind, waves and temperature at the time the ship would be at each waypoint
 *     (Open-Meteo forecast and marine APIs, no key)
 * Ice, depth, tides, currents, traffic separation, piracy areas and regulations are not modelled. The result
 * is a planning estimate and never a recommendation to navigate.
 */
(function () {
  "use strict";

  var KM_PER_NM = 1.852;
  var FORECAST = "https://api.open-meteo.com/v1/forecast";
  var MARINE = "https://marine-api.open-meteo.com/v1/marine";
  var BASE = (document.currentScript && document.currentScript.src.replace(/assets\/world\.js.*$/, "")) || "";
  var Sun = window.AtlasSun;

  function $(sel) { return document.querySelector(sel); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function utc(d) { return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) + " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + " UTC"; }
  function dur(ms) { var h = ms / 3600000; if (h >= 48) return (h / 24).toFixed(1) + " days"; var m = Math.round(ms / 60000); return pad(Math.floor(m / 60)) + ":" + pad(m % 60) + " h"; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function fix(v, n) { return v === null || v === undefined || isNaN(Number(v)) ? "n/a" : Number(v).toFixed(n); }
  function nm(km) { return Math.round(km / KM_PER_NM).toLocaleString("en-US"); }
  function normLon(l) { return ((l + 540) % 360) - 180; }
  function place(pos) {
    var lat = pos[1], lon = normLon(pos[0]);
    return Math.abs(lat).toFixed(1) + "°" + (lat >= 0 ? "N" : "S") + " " + Math.abs(lon).toFixed(1) + "°" + (lon >= 0 ? "E" : "W");
  }
  // The free forecast service sometimes answers 503 when busy, so try again once after a short wait.
  function fetchRetry(url) {
    return fetchJson(url).catch(function () {
      return new Promise(function (resolve) { setTimeout(resolve, 1800); }).then(function () { return fetchJson(url); });
    });
  }
  function fetchJson(url, ms) {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms || 20000) : null;
    return fetch(url, ctl ? { signal: ctl.signal } : undefined).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }

  /* ---- state ---------------------------------------------------------------------------------- */
  var meta = null, water = null, ports = [], byId = {}, routers = {}, order = [];
  var map = null, mapReady = false, markers = [];
  var options = [], chosen = 0, runId = 0, weatherCache = {};
  var lastExport = null, lastWx = {};
  var ice = null, iceMeta = null;   // NSIDC concentration in percent on the same grid, or null if unavailable

  /* Zones where ice normally makes a route unrealistic for ordinary ships. Approximate boxes, not ice charts. */
  function polarBlocked(lat, lon) {
    if (lat <= -60 || lat >= 80) return true;
    return lat >= 66 && (lon >= 55 || lon <= -30);
  }

  function routerFor(opt) {
    var key = "i" + opt.ice + (opt.suez ? "S" : "s") + (opt.panama ? "C" : "c");
    if (routers[key]) return routers[key];
    var copy = Uint8Array.from(water), rows = meta.rows, cols = meta.cols, dlon = meta.dlon, dlat = meta.dlat, north = meta.bbox[3], west = meta.bbox[0];
    function box(b) {
      var r0 = Math.max(0, Math.floor((north - b[3]) / dlat)), r1 = Math.min(rows - 1, Math.floor((north - b[1]) / dlat));
      var c0 = Math.floor((b[0] - west) / dlon), c1 = Math.floor((b[2] - west) / dlon);
      for (var r = r0; r <= r1; r++) for (var c = c0; c <= c1; c++) copy[r * cols + c] = 0;
    }
    if (!opt.suez) box(meta.closable_boxes.suez);
    if (!opt.panama) box(meta.closable_boxes.panama);
    var threshold = parseFloat(opt.ice);
    if (threshold > 0 || opt.ice === "polar") {
      for (var r = 0; r < rows; r++) {
        var lat = north - (r + 0.5) * dlat;
        if (ice && opt.ice !== "polar") {
          // real concentration where the data covers the cell; the Southern Ocean is not covered, so keep out of it
          for (var c = 0; c < cols; c++) { if (ice[r * cols + c] >= threshold || lat <= -60) copy[r * cols + c] = 0; }
        } else {
          if (lat < 66 && lat > -60) continue;
          for (var c2 = 0; c2 < cols; c2++) if (polarBlocked(lat, west + (c2 + 0.5) * dlon)) copy[r * cols + c2] = 0;
        }
      }
    }
    routers[key] = AtlasRouter.createRouter({ rows: rows, cols: cols, bbox: meta.bbox, dlon: dlon, dlat: dlat, wrap: true, water: copy });
    order.push(key);
    while (order.length > 3) delete routers[order.shift()];   // keep memory bounded
    return routers[key];
  }

  /* ---- loading -------------------------------------------------------------------------------- */
  function loadGrid() {
    return Promise.all([fetchJson(BASE + "data/route/world.json"), fetchJson(BASE + "data/route/ports.json")]).then(function (res) {
      meta = res[0]; ports = res[1].ports; ports.forEach(function (p) { byId[p.id] = p; });
      return new Promise(function (resolve, reject) {
        var img = new Image();
        img.onload = function () {
          var cv = document.createElement("canvas"); cv.width = meta.cols; cv.height = meta.rows;
          var ctx = cv.getContext("2d", { willReadFrequently: true }); ctx.drawImage(img, 0, 0);
          var px = ctx.getImageData(0, 0, meta.cols, meta.rows).data;
          water = new Uint8Array(meta.cols * meta.rows);
          for (var i = 0; i < water.length; i++) water[i] = px[i * 4] > 127 ? 1 : 0;
          resolve();
        };
        img.onerror = reject;
        img.src = BASE + "data/route/world.png";
      });
    });
  }

  function loadIce() {
    return fetchJson(BASE + "data/route/ice_grid.json").then(function (m) {
      iceMeta = m;
      return new Promise(function (resolve, reject) {
        var img = new Image();
        img.onload = function () {
          var cv = document.createElement("canvas"); cv.width = img.width; cv.height = img.height;
          var ctx = cv.getContext("2d", { willReadFrequently: true }); ctx.drawImage(img, 0, 0);
          var px = ctx.getImageData(0, 0, img.width, img.height).data;
          if (img.width !== meta.cols || img.height !== meta.rows) { reject(new Error("ice grid size")); return; }
          ice = new Uint8Array(meta.cols * meta.rows);
          for (var i = 0; i < ice.length; i++) ice[i] = px[i * 4];
          resolve();
        };
        img.onerror = reject;
        img.src = BASE + "data/route/ice_world.png";
      });
    }).catch(function () { ice = null; });
  }

  function fillPorts() {
    var groups = {};
    ports.forEach(function (p) { (groups[p.region] = groups[p.region] || []).push(p); });
    ["#w-from", "#w-to"].forEach(function (sel) {
      var el = $(sel); el.innerHTML = "";
      Object.keys(groups).forEach(function (g) {
        var og = document.createElement("optgroup"); og.label = g;
        groups[g].forEach(function (p) { var o = document.createElement("option"); o.value = p.id; o.textContent = p.name + ", " + p.country; og.appendChild(o); });
        el.appendChild(og);
      });
    });
    var q = new URLSearchParams(location.search);
    $("#w-from").value = byId[q.get("from")] ? q.get("from") : "rtm";
    $("#w-to").value = byId[q.get("to")] ? q.get("to") : "sin";
  }

  /* ---- calculation ---------------------------------------------------------------------------- */
  function inputs() {
    var depart = new Date($("#w-depart").value + ":00Z");
    return {
      from: byId[$("#w-from").value], to: byId[$("#w-to").value],
      speed: Math.max(1, Math.min(40, parseFloat($("#w-speed").value) || 14)),
      depart: isNaN(depart) ? new Date() : depart,
      ice: $("#w-ice").value, suez: $("#w-suez").checked, panama: $("#w-panama").checked
    };
  }

  function passes(coords, box) {
    for (var i = 0; i < coords.length; i++) {
      var lon = normLon(coords[i][0]), lat = coords[i][1];
      if (lon >= box[0] && lon <= box[2] && lat >= box[1] && lat <= box[3]) return true;
    }
    return false;
  }

  function solve(inp, name, over, margin) {
    var opt = { ice: inp.ice, suez: inp.suez, panama: inp.panama };
    Object.keys(over || {}).forEach(function (k) { opt[k] = over[k]; });
    var r = routerFor(opt).route([inp.from.lon, inp.from.lat], [inp.to.lon, inp.to.lat], margin || 0, 150);
    r.name = name; r.margin = r.error ? 0 : r.margin; r.requested = margin || 0;
    return r;
  }

  function timeline(inp, r) {
    var kmh = inp.speed * KM_PER_NM, t0 = inp.depart.getTime(), total = r.km, ms = (total / kmh) * 3600000;
    var count = Math.max(3, Math.min(9, Math.round(total / KM_PER_NM / 700) + 2)), pts = [];
    for (var i = 0; i < count; i++) {
      var km = (total * i) / (count - 1), pos = AtlasRouter.pointAlong(r.coords, km, haversine);
      pts.push({ i: i, km: km, pos: pos, at: new Date(t0 + (km / kmh) * 3600000) });
    }
    var hours = Math.ceil(ms / 3600000), up = 0, civil = 0, dark = 0;
    var step = Math.max(1, Math.floor(hours / 400));
    var n = 0;
    for (var h = 0; h < hours; h += step) {
      var km2 = Math.min(total, h * kmh), p = AtlasRouter.pointAlong(r.coords, km2, haversine), el = Sun.elevation(p[1], normLon(p[0]), new Date(t0 + h * 3600000));
      n++; if (el > -0.833) up++; else if (el > -6) civil++; else dark++;
    }
    pts.forEach(function (p) { p.el = Sun.elevation(p.pos[1], normLon(p.pos[0]), p.at); });
    return { ms: ms, pts: pts, final: new Date(t0 + ms), up: up / (n || 1), civil: civil / (n || 1), dark: dark / (n || 1) };
  }
  function haversine(a, b) {
    var rad = Math.PI / 180, dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
    var q = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
    return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(q)));
  }

  /* ---- weather -------------------------------------------------------------------------------- */
  function loadWeather(pts) {
    var lat = pts.map(function (p) { return p.pos[1].toFixed(2); }).join(","), lon = pts.map(function (p) { return normLon(p.pos[0]).toFixed(2); }).join(",");
    var key = lat + "|" + lon;
    if (weatherCache[key] && Date.now() - weatherCache[key].at < 30 * 60000) return Promise.resolve(weatherCache[key].data);
    var common = "&latitude=" + lat + "&longitude=" + lon + "&timezone=GMT&forecast_days=16";
    var f = fetchRetry(FORECAST + "?hourly=temperature_2m,wind_speed_10m,wind_gusts_10m,wind_direction_10m&wind_speed_unit=kn" + common);
    var m = fetchRetry(MARINE + "?hourly=wave_height,wave_period,wave_direction" + common).catch(function () { return null; });
    return Promise.all([f, m]).then(function (res) {
      var data = { f: [].concat(res[0]), m: res[1] ? [].concat(res[1]) : null };
      weatherCache[key] = { at: Date.now(), data: data };
      return data;
    });
  }
  function at(series, when) {
    if (!series || !series.hourly || !series.hourly.time) return null;
    var t0 = Date.parse(series.hourly.time[0] + ":00Z"), i = Math.round((when.getTime() - t0) / 3600000);
    if (i < 0 || i >= series.hourly.time.length) return { out: true };
    var o = { out: false }; Object.keys(series.hourly).forEach(function (k) { o[k] = series.hourly[k][i]; });
    return o;
  }
  function band(wave, gust) {
    var w = wave === null || wave === undefined ? 0 : wave, g = gust === null || gust === undefined ? 0 : gust;
    if (w >= 4 || g >= 48) return { n: 3, label: "Severe", cls: "bad" };
    if (w >= 2.5 || g >= 34) return { n: 2, label: "Rough", cls: "warn" };
    if (w >= 1.25 || g >= 22) return { n: 1, label: "Moderate", cls: "" };
    return { n: 0, label: "Calm", cls: "ok" };
  }
  var CARD = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  function card(d) { return d === null || d === undefined ? "" : " " + CARD[Math.round(d / 22.5) % 16]; }

  function renderConditions(inp, tl, runToken) {
    var body = $("#w-cond");
    body.innerHTML = tl.pts.map(function (p) {
      return "<tr><td>" + (p.i === 0 ? "Start" : p.i === tl.pts.length - 1 ? "Arrival" : "Waypoint " + p.i) + "<br><span class=\"muted\">" + nm(p.km) + " nm</span></td><td>" + place(p.pos) + "</td><td>" + utc(p.at) + "<br><span class=\"muted\">" + Sun.sunState(p.el) + "</span></td><td colspan=\"4\" class=\"muted\">Loading forecast…</td></tr>";
    }).join("");
    $("#w-weather-status").textContent = "Loading forecasts for " + tl.pts.length + " points…";
    loadWeather(tl.pts).then(function (data) {
      if (runToken !== runId) return;
      var worst = { n: -1 }, beyond = 0;
      body.innerHTML = tl.pts.map(function (p, k) {
        var f = at(data.f[k], p.at), m = data.m ? at(data.m[k], p.at) : null;
        var head = "<td>" + (p.i === 0 ? "Start" : p.i === tl.pts.length - 1 ? "Arrival" : "Waypoint " + p.i) + "<br><span class=\"muted\">" + nm(p.km) + " nm</span></td><td>" + place(p.pos) + "</td><td>" + utc(p.at) + "<br><span class=\"muted\">" + Sun.sunState(p.el) + "</span></td>";
        if (!f || f.out) { beyond++; return "<tr>" + head + "<td colspan=\"4\" class=\"muted\">Beyond the 16-day forecast. Nothing is shown rather than guessing.</td></tr>"; }
        var wave = m && !m.out ? m.wave_height : null, b = band(wave, f.wind_gusts_10m);
        lastWx[k] = { wind_kn: f.wind_speed_10m, gust_kn: f.wind_gusts_10m, wind_from_deg: f.wind_direction_10m, wave_m: wave, wave_period_s: m && !m.out ? m.wave_period : null, air_c: f.temperature_2m, sea_state: b.label };
        if (b.n > worst.n) worst = { n: b.n, p: p, b: b };
        var vis = f.visibility === null || f.visibility === undefined ? "" : (f.visibility < 2000 ? " · <b>visibility " + (f.visibility / 1000).toFixed(1) + " km</b>" : "");
        return "<tr>" + head + "<td>" + fix(f.wind_speed_10m, 0) + " kn" + card(f.wind_direction_10m) + "<br><span class=\"muted\">gusts " + fix(f.wind_gusts_10m, 0) + " kn" + vis + "</span></td>" +
          "<td>" + (wave === null || wave === undefined ? "<span class=\"muted\">n/a</span>" : fix(wave, 1) + " m<br><span class=\"muted\">period " + fix(m.wave_period, 0) + " s</span>") + "</td>" +
          "<td>" + fix(f.temperature_2m, 0) + " °C</td><td><span class=\"badge " + b.cls + "\">" + b.label + "</span></td></tr>";
      }).join("");
      var s = $("#w-weather-status");
      s.textContent = beyond === tl.pts.length ? "The voyage starts beyond the 16-day forecast, so no conditions are shown." :
        (worst.n >= 2 ? "Heaviest forecast conditions: " + worst.b.label.toLowerCase() + " near " + place(worst.p.pos) + " around " + utc(worst.p.at) + ". " : "No rough conditions in the forecast at these points. ") +
        (beyond ? beyond + " point(s) fall beyond the forecast and are left blank. " : "") + "Model forecast, retrieved " + utc(new Date()) + ".";
    }).catch(function () {
      if (runToken !== runId) return;
      body.querySelectorAll("td.muted[colspan]").forEach(function (td) { td.textContent = "Forecast service unavailable. Try again shortly."; });
      $("#w-weather-status").textContent = "The forecast service could not be reached.";
    });
  }

  /* ---- rendering ------------------------------------------------------------------------------ */
  function render() {
    if (!water) return;
    var inp = inputs(), token = ++runId;
    if (!inp.from || !inp.to || inp.from.id === inp.to.id) { $("#w-alt").innerHTML = "<tr><td colspan=\"5\">Choose two different ports.</td></tr>"; return; }
    $("#w-busy").hidden = false;
    // first paint quickly with the shortest route, then add the alternatives
    setTimeout(function () {
      if (token !== runId) return;
      var base = solve(inp, "Shortest path with your settings", {}, 0);
      $("#w-busy").hidden = true;
      if (base.error) { options = []; $("#w-alt").innerHTML = "<tr><td colspan=\"5\">" + esc(base.error) + (parseFloat(inp.ice) > 0 ? " Sea ice may be closing the route or a port. Try a higher ice threshold, or choose “Ignore sea ice”." : "") + "</td></tr>"; clearResults(); return; }
      options = [base]; chosen = 0;
      show(inp, token);
      setTimeout(function () { alternatives(inp, token, base); }, 30);
    }, 20);
  }

  function alternatives(inp, token, base) {
    if (token !== runId) return;
    var extra = [];
    var off = solve(inp, "Keep about 20 km off the coast", {}, 2);
    if (!off.error) {
      off.note = off.margin >= 2 ? (off.km > base.km * 1.15 ? "narrow canals and straits do not fit inside the margin, so this goes the long way round" : "") : "not possible all the way, so it uses the shortest path";
      extra.push(off);
    }
    var topLat = base.coords.reduce(function (m, c) { return Math.max(m, c[1]); }, -90);
    if (topLat > 66) { var dry = solve(inp, "Without Arctic waters", { ice: "polar" }, 0); extra.push(dry); }
    if (inp.suez && passes(base.coords, meta.closable_boxes.suez)) extra.push(solve(inp, "Without the Suez Canal", { suez: false }, 0));
    if (inp.panama && passes(base.coords, meta.closable_boxes.panama)) extra.push(solve(inp, "Without the Panama Canal", { panama: false }, 0));
    if (token !== runId) return;
    options = [base].concat(extra.filter(function (o) { return !(o.error === undefined && o.margin < 2 && o.requested === 2); }));
    show(inp, token, true);
  }

  function clearResults() {
    ["w-nm", "w-km", "w-time", "w-arrival", "w-light"].forEach(function (id) { var e = document.getElementById(id); if (e) e.textContent = "—"; });
    $("#w-cond").innerHTML = "<tr><td colspan=\"7\">No route.</td></tr>";
    if (map && mapReady) ["w-main", "w-alt1", "w-alt2", "w-alt3"].forEach(function (id) { var s = map.getSource(id); if (s) s.setData(line([])); });
  }

  function show(inp, token, keepWeather) {
    var r = options[chosen], tl = timeline(inp, r);
    lastExport = { inp: inp, r: r, tl: tl };
    briefing(inp, r, tl);
    var straight = haversine([inp.from.lon, inp.from.lat], [inp.to.lon, inp.to.lat]);
    $("#w-nm").textContent = nm(r.km);
    $("#w-km").textContent = Math.round(r.km).toLocaleString("en-US") + " km · " + (r.km / straight).toFixed(2) + "× the great-circle line";
    $("#w-time").textContent = dur(tl.ms);
    $("#w-arrival").textContent = utc(tl.final);
    $("#w-light").textContent = Math.round(tl.up * 100) + "% daylight";
    $("#w-light-foot").textContent = Math.round(tl.civil * 100) + "% twilight, " + Math.round(tl.dark * 100) + "% dark";
    var shortest = options.reduce(function (a, b) { return b.km < a.km ? b : a; });
    $("#w-alt").innerHTML = options.map(function (o, i) {
      var extraKm = o.km - shortest.km, ms = (o.km / (inp.speed * KM_PER_NM)) * 3600000;
      var err = o.error ? esc(o.error) : "";
      return "<tr tabindex=\"0\" data-i=\"" + i + "\" class=\"pick" + (i === chosen ? " chosen" : "") + "\"><td>" + esc(o.name) + (i === 0 ? " <span class=\"badge ok\">shortest</span>" : "") + (o.note ? "<br><span class=\"muted\">" + esc(o.note) + "</span>" : "") + "</td>" +
        (o.error ? "<td colspan=\"4\">" + err + "</td>" : "<td>" + nm(o.km) + " nm</td><td>" + dur(ms) + "</td><td>" + (extraKm < 1 ? "—" : "+" + nm(extraKm) + " nm") + "</td><td>" + (i === chosen ? "shown" : "show on map") + "</td>") + "</tr>";
    }).join("");
    notes(inp, r, tl);
    draw(inp, tl);
    var key = inputsKey(inp, r);
    if ($("#w-cond").dataset.run !== key) {
      $("#w-cond").dataset.run = key;
      lastWx = {};
      renderConditions(inp, tl, token);
    }
  }
  function inputsKey(inp, r) { return [inp.from.id, inp.to.id, inp.speed, inp.depart.getTime(), inp.ice, inp.suez, inp.panama, r.name, Math.round(r.km)].join("|"); }


  /* ---- export and briefing -------------------------------------------------------------------- */
  function iceRule(inp) {
    var t = parseFloat(inp.ice);
    if (inp.ice === "polar") return "Arctic waters excluded";
    if (!(t > 0)) return "sea ice ignored";
    return "avoid ice at " + t + "% or more" + (iceMeta ? " (NSIDC analysis " + iceMeta.date + ")" : "");
  }
  /* Split a line where it crosses the antimeridian, as GeoJSON requires, and keep longitudes in -180..180. */
  function splitAtAntimeridian(coords) {
    var parts = [[]], prev = null;
    coords.forEach(function (c) {
      var lon = normLon(c[0]), lat = c[1];
      if (prev && Math.abs(lon - prev[0]) > 180) {
        var east = prev[0] > 0, lonA = east ? 180 : -180, lonB = -lonA;
        var d = (lon + (east ? 360 : -360)) - prev[0], f = d === 0 ? 0 : (lonA - prev[0]) / d, latX = prev[1] + (lat - prev[1]) * f;
        parts[parts.length - 1].push([lonA, latX]);
        parts.push([[lonB, latX]]);
      }
      parts[parts.length - 1].push([lon, lat]); prev = [lon, lat];
    });
    return parts.filter(function (x) { return x.length > 1; });
  }
  function routeData() {
    if (!lastExport) return null;
    var e = lastExport, inp = e.inp, r = e.r, tl = e.tl;
    var meta = {
      from: inp.from.name + ", " + inp.from.country, to: inp.to.name + ", " + inp.to.country, option: r.name,
      speed_kn: inp.speed, departure_utc: inp.depart.toISOString(), arrival_utc: tl.final.toISOString(),
      distance_nm: Math.round(r.km / KM_PER_NM), distance_km: Math.round(r.km), time_under_way_days: +(tl.ms / 86400000).toFixed(2),
      sea_ice_rule: iceRule(inp), suez_allowed: inp.suez, panama_allowed: inp.panama, generated_utc: new Date().toISOString(),
      notice: "Planning estimate, not for navigation. Shortest open-water path on a 0.1 degree grid. Ice, depth, currents, traffic separation, canal rules and regulations are not modelled."
    };
    var points = tl.pts.map(function (p, k) {
      var wx = lastWx[k] || {}, o = {
        point: p.i === 0 ? "start" : p.i === tl.pts.length - 1 ? "arrival" : "waypoint " + p.i, time_utc: p.at.toISOString(),
        nm_from_start: Math.round(p.km / KM_PER_NM), lat: +p.pos[1].toFixed(4), lon: +normLon(p.pos[0]).toFixed(4), sun: Sun.sunState(p.el)
      };
      Object.keys(wx).forEach(function (key) { o[key] = wx[key]; });
      return o;
    });
    return { meta: meta, points: points, parts: splitAtAntimeridian(r.coords) };
  }
  function exportRoute(fmt) {
    var d = routeData();
    if (!d) return;
    var X = window.AtlasExport, base = "route-" + lastExport.inp.from.id + "-" + lastExport.inp.to.id;
    if (fmt === "geojson") {
      var fc = { type: "FeatureCollection", features: [{ type: "Feature", properties: d.meta, geometry: { type: "MultiLineString", coordinates: d.parts } }].concat(d.points.map(function (o) {
        return { type: "Feature", properties: o, geometry: { type: "Point", coordinates: [o.lon, o.lat] } };
      })) };
      X.download(base + ".geojson", JSON.stringify(fc, null, 1), "application/geo+json");
    } else if (fmt === "kml") {
      var feats = [{ type: "Feature", properties: d.meta, geometry: { type: "LineString", coordinates: d.parts.reduce(function (a, b) { return a.concat(b); }, []) } }].concat(d.points.map(function (o) {
        return { type: "Feature", properties: o, geometry: { type: "Point", coordinates: [o.lon, o.lat] } };
      }));
      X.download(base + ".kml", X.toKml(feats, d.meta.from + " to " + d.meta.to, d.meta.notice, function (f, i) { return i === 0 ? "Route: " + d.meta.option : d.points[i - 1].point + " " + d.points[i - 1].time_utc.slice(0, 10); }), "application/vnd.google-earth.kml+xml");
    } else {
      X.download(base + ".csv", X.toCsv(d.points), "text/csv;charset=utf-8");
    }
  }
  function briefing(inp, r, tl) {
    var el = $("#w-print-head");
    if (!el) return;
    el.innerHTML = "<h2>Route briefing: " + esc(inp.from.name) + " to " + esc(inp.to.name) + "</h2>" +
      "<p>" + nm(r.km) + " nm (" + Math.round(r.km).toLocaleString("en-US") + " km), " + dur(tl.ms) + " at " + inp.speed + " kn. Departs " + utc(inp.depart) + ", arrives " + utc(tl.final) + ". Option: " + esc(r.name) + ". Sea ice: " + esc(iceRule(inp)) + ".</p>" +
      "<p><strong>Planning estimate, not for navigation.</strong> Shortest open-water path on a coarse grid. Ice, depth, currents, traffic separation, canal rules and regulations are not modelled. Forecasts: Open-Meteo. Generated " + utc(new Date()) + " by Arctic Passage Atlas.</p>";
  }

  function notes(inp, r, tl) {
    var w = [];
    var maxLat = r.coords.reduce(function (m, c) { return Math.max(m, Math.abs(c[1])); }, 0);
    var thr = parseFloat(inp.ice);
    if (thr > 0 && ice && iceMeta) {
      var age = Math.round((inp.depart.getTime() - Date.parse(iceMeta.date + "T00:00:00Z")) / 86400000);
      w.push("Sea ice: cells with " + thr + "% concentration or more are avoided, using the NSIDC analysis of " + iceMeta.date + ". Ice is not forecast: " +
        (age > 7 ? "your departure is " + age + " days after this analysis, so conditions in polar waters can be very different." : "it changes daily and the situation at your arrival will differ.") +
        " The data are 25 km passive-microwave cells that miss thin ice and understate concentration in summer melt. Open water here does not make a polar passage navigable or permitted.");
      if (maxLat > 66) w.push("This route enters Arctic waters (up to " + maxLat.toFixed(0) + "° latitude). Check the Canadian Ice Service or the relevant national ice service, and the rules for transit, before relying on it.");
    } else if (thr > 0) {
      w.push("The ice data could not be loaded, so approximate polar zones are excluded instead of real sea ice. Arctic shortcuts are not offered.");
    } else if (maxLat > 66) {
      w.push("Sea ice is ignored and this path enters polar waters (up to " + maxLat.toFixed(0) + "° latitude). Ice usually blocks ordinary ships there for much of the year, so the distance saved may not be usable.");
    }
    if (thr > 0) w.push("The Southern Hemisphere has no ice data here, so the Southern Ocean is kept out of the search.");
    if (tl.dark > 0.4) w.push("More than 40% of the voyage is in darkness.");
    if (r.snapKm && (r.snapKm[0] > 25 || r.snapKm[1] > 25)) w.push("A port is more than 25 km from open water on this coarse grid, so the first or last part of the line is a straight link.");
    w.push("Canals, locks, pilotage, traffic separation schemes, piracy areas, sanctions and port restrictions are not modelled. Real routing also depends on weather forecasts, ice charts and company policy.");
    $("#w-notes").innerHTML = w.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("");
  }

  function line(coords) { return { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: coords } }; }

  function draw(inp, tl) {
    if (!map || !mapReady) return;
    var others = options.filter(function (o, i) { return i !== chosen && !o.error; });
    map.getSource("w-main").setData(line(options[chosen].coords));
    ["w-alt1", "w-alt2", "w-alt3"].forEach(function (id, i) { map.getSource(id).setData(line(others[i] ? others[i].coords : [])); });
    markers.forEach(function (m) { m.remove(); }); markers = [];
    tl.pts.forEach(function (p) {
      var end = p.i === 0 || p.i === tl.pts.length - 1, el = document.createElement("div");
      el.className = end ? "stop-pin" : "cp-dot"; if (end) el.textContent = p.i === 0 ? "A" : "B";
      var label = (p.i === 0 ? inp.from.name : p.i === tl.pts.length - 1 ? inp.to.name : "Waypoint " + p.i) + " — " + utc(p.at);
      markers.push(new maplibregl.Marker({ element: el }).setLngLat([p.pos[0], p.pos[1]]).setPopup(new maplibregl.Popup({ offset: 12 }).setText(label)).addTo(map));
    });
    var c = options[chosen].coords, b = c.reduce(function (acc, x) { return acc.extend(x); }, new maplibregl.LngLatBounds(c[0], c[0]));
    map.fitBounds(b, { padding: 50, maxZoom: 6, duration: 600 });
  }

  function initMap() {
    var el = $("#w-map");
    if (!el || typeof maplibregl === "undefined") return;
    map = new maplibregl.Map({ container: el, style: "https://tiles.openfreemap.org/styles/dark", center: [10, 25], zoom: 1.4, attributionControl: { compact: true }, cooperativeGestures: true, preserveDrawingBuffer: true });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    try { (window.AtlasMaps = window.AtlasMaps || []).push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); } catch (e) { /* tools are optional */ }
    if (typeof ResizeObserver === "function") new ResizeObserver(function () { map.resize(); }).observe(el);
    map.on("style.load", function () {
      ["w-alt3", "w-alt2", "w-alt1", "w-main"].forEach(function (id) {
        map.addSource(id, { type: "geojson", data: line([]) });
        map.addLayer({ id: id + "-line", type: "line", source: id, layout: { "line-join": "round", "line-cap": "round" },
          paint: id === "w-main" ? { "line-color": "#ffb454", "line-width": 3.6 } : { "line-color": "#7bdff2", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.9 } });
      });
      mapReady = true; render();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!$("#w-from")) return;
    var now = new Date(); now.setUTCMinutes(0, 0, 0);
    $("#w-depart").value = now.getUTCFullYear() + "-" + pad(now.getUTCMonth() + 1) + "-" + pad(now.getUTCDate()) + "T" + pad(now.getUTCHours()) + ":00";
    initMap();
    loadGrid().then(loadIce).then(function () {
      fillPorts();
      if (iceMeta) $("#w-ice-date").textContent = "Sea ice: NSIDC analysis of " + iceMeta.date + ".";
      ["w-from", "w-to", "w-speed", "w-depart", "w-ice", "w-suez", "w-panama"].forEach(function (id) { $("#" + id).addEventListener("change", render); });
      $("#w-speed").addEventListener("input", function () { clearTimeout(this._t); this._t = setTimeout(render, 350); });
      document.querySelectorAll("[data-preset]").forEach(function (b) {
        b.addEventListener("click", function () {
          var ids = b.getAttribute("data-preset").split(">");
          $("#w-from").value = ids[0]; $("#w-to").value = ids[1]; render();
        });
      });
      $("#w-swap").addEventListener("click", function () { var a = $("#w-from").value; $("#w-from").value = $("#w-to").value; $("#w-to").value = a; render(); });
      document.querySelectorAll("[data-route-export]").forEach(function (b) {
        b.addEventListener("click", function () { exportRoute(b.getAttribute("data-route-export")); });
      });
      var pr = $("#w-print"); if (pr) pr.addEventListener("click", function () { window.print(); });
      $("#w-alt").addEventListener("click", pick);
      $("#w-alt").addEventListener("keydown", function (e) { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(e); } });
      render();
    }).catch(function () { $("#w-busy").hidden = false; $("#w-busy").textContent = "The routing grid could not be loaded. Check your connection and reload."; });
  });
  function pick(e) {
    var tr = e.target.closest && e.target.closest("tr[data-i]");
    if (!tr) return;
    var i = parseInt(tr.getAttribute("data-i"), 10);
    if (i === chosen || !options[i] || options[i].error) return;
    chosen = i; show(inputs(), runId, false);
  }
  document.addEventListener("world-shown", function () { if (map) { map.resize(); } render(); });
})();
