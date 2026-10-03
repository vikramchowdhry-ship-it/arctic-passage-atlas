/* Route calculator for the Northwest Passage corridor. Everything here runs in the visitor's browser:
 *   - a shortest open-water search on a land/water grid (assets/router.js, data/route/water.png)
 *   - sailing time, arrival times and sun position along the path
 *   - live station observations (Environment Canada SWOB) and hourly forecasts (citypage weather)
 * Ice, depth, tides, charts and regulations are not modelled; the result is a planning estimate and
 * never a recommendation to navigate.
 */
(function () {
  "use strict";

  var SWOB = "https://api.weather.gc.ca/collections/swob-realtime/items";
  var CITY = "https://api.weather.gc.ca/collections/citypageweather-realtime/items";
  var KM_PER_NM = 1.852;
  var BASE = (document.currentScript && document.currentScript.src.replace(/assets\/route\.js.*$/, "")) || "";

  // West to east. `station` is the exact SWOB station name; `city` is the citypage forecast name.
  var STOPS = [
    { id: "tuk", label: "Tuktoyaktuk", station: "TUKTOYAKTUK", city: "Tuktoyaktuk", note: "Beaufort Sea", pos: [-133.021, 69.436] },
    { id: "cb", label: "Cambridge Bay", station: "CAMBRIDGE BAY GSN", city: "Cambridge Bay", note: "Dease Strait", pos: [-105.116, 69.107] },
    { id: "gjoa", label: "Gjoa Haven", station: "Gjoa Haven", city: "Gjoa Haven", note: "Rae Strait", pos: [-95.85, 68.636] },
    { id: "res", label: "Resolute", station: "RESOLUTE CS", city: "Resolute", note: "Barrow Strait", pos: [-94.968, 74.706] },
    { id: "arc", label: "Arctic Bay", station: "ARCTIC BAY CS", city: "Arctic Bay", note: "Admiralty Inlet", pos: [-85.012, 72.993] },
    { id: "pond", label: "Pond Inlet", station: "POND INLET CLIMATE", city: "Pond Inlet", note: "Eclipse Sound", pos: [-77.957, 72.693] },
    { id: "clyde", label: "Clyde River", station: "Clyde River", city: "Clyde River", note: "Baffin Island", pos: [-68.517, 70.486] }
  ];
  var CARD = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
  var MARGINS = [
    { cells: 0, name: "Shortest water path", km: "no coastal margin" },
    { cells: 1, name: "About 2 km off the coast", km: "2 km margin" },
    { cells: 3, name: "About 6 km off the coast", km: "6 km margin" }
  ];

  function $(sel) { return document.querySelector(sel); }
  function pad(n) { return String(n).padStart(2, "0"); }
  function rad(d) { return (d * Math.PI) / 180; }
  function deg(r) { return (r * 180) / Math.PI; }
  function utc(d) { return d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate()) + " " + pad(d.getUTCHours()) + ":" + pad(d.getUTCMinutes()) + " UTC"; }
  function hm(ms) { var m = Math.max(0, Math.round(ms / 60000)); return pad(Math.floor(m / 60)) + ":" + pad(m % 60); }
  function dur(ms) { var h = ms / 3600000; return h >= 48 ? (h / 24).toFixed(1) + " days" : hm(ms) + " h"; }
  function esc(s) { return String(s).replace(/[&<>"]/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]; }); }
  function dig(o, path) { for (var i = 0; i < path.length && o !== undefined && o !== null; i++) o = o[path[i]]; return o === undefined ? null : o; }
  function fix(v, n) { return v === null || v === undefined || isNaN(Number(v)) ? "n/a" : Number(v).toFixed(n); }
  function cardinal(d) { return d === null || d === undefined ? "" : " " + CARD[Math.round(d / 22.5) % 16]; }

  /* ---- sun ---------------------------------------------------------------------------------- */
  function solar(date) {
    var start = Date.UTC(date.getUTCFullYear(), 0, 0);
    var n = (date.getTime() - start) / 86400000;
    var g = (2 * Math.PI / 365) * (n - 1);
    var eqt = 229.18 * (0.000075 + 0.001868 * Math.cos(g) - 0.032077 * Math.sin(g) - 0.014615 * Math.cos(2 * g) - 0.040849 * Math.sin(2 * g));
    var decl = 0.006918 - 0.399912 * Math.cos(g) + 0.070257 * Math.sin(g) - 0.006758 * Math.cos(2 * g) + 0.000907 * Math.sin(2 * g) - 0.002697 * Math.cos(3 * g) + 0.00148 * Math.sin(3 * g);
    return { eqt: eqt, decl: decl };
  }
  /* Sun elevation in degrees (NOAA method, no refraction correction). */
  function elevation(lat, lon, date) {
    var s = solar(date);
    var minutes = date.getUTCHours() * 60 + date.getUTCMinutes() + date.getUTCSeconds() / 60;
    var ha = rad(((minutes + s.eqt + 4 * lon) / 4) - 180);
    var sinE = Math.sin(rad(lat)) * Math.sin(s.decl) + Math.cos(rad(lat)) * Math.cos(s.decl) * Math.cos(ha);
    return deg(Math.asin(Math.max(-1, Math.min(1, sinE))));
  }
  function daylightMs(lat, lon, date) {
    var s = solar(date);
    var cosH = (Math.cos(rad(90.833)) / (Math.cos(rad(lat)) * Math.cos(s.decl))) - Math.tan(rad(lat)) * Math.tan(s.decl);
    if (cosH > 1) return 0;
    if (cosH < -1) return 24 * 3600000;
    return (2 * deg(Math.acos(cosH)) / 15) * 3600000;
  }
  function sunState(el) { return el > -0.833 ? "Day" : el > -6 ? "Civil twilight" : el > -12 ? "Nautical twilight" : "Night"; }
  window.AtlasSun = { elevation: elevation, daylightMs: daylightMs, sunState: sunState };

  /* ---- data --------------------------------------------------------------------------------- */
  function fetchJson(url, ms) {
    var ctl = typeof AbortController === "function" ? new AbortController() : null;
    var timer = ctl ? setTimeout(function () { ctl.abort(); }, ms || 15000) : null;
    return fetch(url, ctl ? { signal: ctl.signal } : undefined).then(function (r) {
      if (timer) clearTimeout(timer);
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  var live = {}, forecast = {}, router = null, grid = null, ice = null, iceMeta = null, iceRouters = {};

  function loadObs(stop) {
    var q = "?f=json&limit=1&sortby=-date_tm-value&properties=date_tm-value,air_temp,avg_wnd_spd_10m_pst10mts,avg_wnd_dir_10m_pst10mts&stn_nam-value=" + encodeURIComponent(stop.station);
    return fetchJson(SWOB + q).then(function (d) {
      var f = d.features && d.features[0];
      if (!f) throw new Error("none");
      var p = f.properties;
      live[stop.id] = { lon: f.geometry.coordinates[0], lat: f.geometry.coordinates[1], temp: p.air_temp, wind: p.avg_wnd_spd_10m_pst10mts, dir: p.avg_wnd_dir_10m_pst10mts, time: new Date(p["date_tm-value"]) };
    }).catch(function () { live[stop.id] = { error: true }; });
  }

  function loadForecast(stop) {
    return fetchJson(CITY + "?f=json&lang=en&limit=10&q=" + encodeURIComponent(stop.city), 25000).then(function (d) {
      var hit = (d.features || []).filter(function (f) {
        var n = dig(f, ["properties", "name", "en"]);
        return n && n.toLowerCase() === stop.city.toLowerCase();
      })[0];
      var hours = hit && dig(hit, ["properties", "hourlyForecastGroup", "hourlyForecasts"]);
      if (!hours || !hours.length) throw new Error("no hourly forecast");
      forecast[stop.id] = hours.map(function (h) {
        return { t: new Date(h.timestamp), temp: dig(h, ["temperature", "value", "en"]), wind: dig(h, ["wind", "speed", "value", "en"]),
          dir: dig(h, ["wind", "direction", "windDirFull", "en"]), cond: dig(h, ["condition", "en"]) };
      });
    }).catch(function () { forecast[stop.id] = null; });
  }

  function loadGrid() {
    return fetchJson(BASE + "data/route/water.json").then(function (meta) {
      return new Promise(function (resolve, reject) {
        var img = new Image();
        img.onload = function () {
          var cv = document.createElement("canvas"); cv.width = meta.cols; cv.height = meta.rows;
          var ctx = cv.getContext("2d", { willReadFrequently: true }); ctx.drawImage(img, 0, 0);
          var px = ctx.getImageData(0, 0, meta.cols, meta.rows).data, water = new Uint8Array(meta.cols * meta.rows);
          for (var i = 0; i < water.length; i++) water[i] = px[i * 4] > 127 ? 1 : 0;
          grid = { rows: meta.rows, cols: meta.cols, bbox: meta.bbox, dlon: meta.dlon, dlat: meta.dlat, water: water };
          router = AtlasRouter.createRouter(grid);
          resolve(meta);
        };
        img.onerror = reject;
        img.src = BASE + "data/route/water.png";
      });
    });
  }

  /* Sea-ice concentration (NSIDC, percent) on the same grid. If it cannot be loaded the ice option does nothing. */
  function loadIce() {
    return fetchJson(BASE + "data/route/ice_grid.json").then(function (m) {
      iceMeta = m;
      return new Promise(function (resolve) {
        var img = new Image();
        img.onload = function () {
          if (!grid || img.width !== grid.cols || img.height !== grid.rows) { resolve(); return; }
          var cv = document.createElement("canvas"); cv.width = img.width; cv.height = img.height;
          var ctx = cv.getContext("2d", { willReadFrequently: true }); ctx.drawImage(img, 0, 0);
          var px = ctx.getImageData(0, 0, img.width, img.height).data;
          ice = new Uint8Array(grid.cols * grid.rows);
          for (var i = 0; i < ice.length; i++) ice[i] = px[i * 4];
          var note = $("[data-r='ice-date']"); if (note) note.textContent = "Sea ice: NSIDC analysis of " + m.date + ".";
          resolve();
        };
        img.onerror = function () { resolve(); };
        img.src = BASE + "data/route/ice_arctic.png";
      });
    }).catch(function () { ice = null; });
  }
  function routerFor(threshold) {
    var t = parseFloat(threshold);
    if (!(t > 0) || !ice || !grid) return router;
    if (!iceRouters[t]) {
      var w = Uint8Array.from(grid.water);
      for (var i = 0; i < w.length; i++) if (ice[i] >= t) w[i] = 0;
      iceRouters[t] = AtlasRouter.createRouter({ rows: grid.rows, cols: grid.cols, bbox: grid.bbox, dlon: grid.dlon, dlat: grid.dlat, water: w });
    }
    return iceRouters[t];
  }

  /* ---- calculation --------------------------------------------------------------------------- */
  function inputs() {
    var a = STOPS.findIndex(function (s) { return s.id === $("#r-from").value; });
    var b = STOPS.findIndex(function (s) { return s.id === $("#r-to").value; });
    var step = a <= b ? 1 : -1, ports = [];
    for (var i = a; i !== b + step; i += step) ports.push(STOPS[i]);
    var departIso = $("#r-depart").value + ":00Z", depart = new Date(departIso);
    return {
      ports: ports, calls: $("#r-via").checked, from: STOPS[a], to: STOPS[b],
      speed: Math.max(1, parseFloat($("#r-speed").value) || 8), dwell: Math.max(0, parseFloat($("#r-dwell").value) || 0),
      depart: isNaN(depart) ? new Date() : depart, ice: ($("#r-ice") || { value: "0" }).value
    };
  }

  function planFor(inp, margin) {
    var stops = inp.calls ? inp.ports : [inp.from, inp.to];
    var coords = [], km = 0, used = margin, legs = [];
    for (var i = 1; i < stops.length; i++) {
      var r = routerFor(inp.ice).route(stops[i - 1].pos, stops[i].pos, margin);
      if (r.error) return { error: stops[i - 1].label + " to " + stops[i].label + ": " + r.error };
      if (r.margin < used) used = r.margin;
      coords = coords.concat(coords.length ? r.coords.slice(1) : r.coords);
      km += r.km; legs.push({ from: stops[i - 1], to: stops[i], km: r.km });
    }
    return { coords: coords, km: km, legs: legs, stops: stops, marginUsed: used };
  }

  function timeline(inp, plan) {
    // Clock model: sailing time is distance / speed; each port call between legs adds `dwell` hours.
    var speedKmH = inp.speed * KM_PER_NM, t0 = inp.depart.getTime();
    var bounds = [], cum = 0;                       // cumulative km at the end of each leg
    plan.legs.forEach(function (leg) { cum += leg.km; bounds.push(cum); });
    function clockAt(km) {                          // wall-clock ms when the ship has covered `km`
      var stops = 0;
      for (var i = 0; i < bounds.length - 1; i++) if (km > bounds[i] + 1e-9) stops++;
      return t0 + (km / speedKmH) * 3600000 + stops * inp.dwell * 3600000;
    }
    var arrivals = [{ stop: plan.stops[0], at: new Date(t0), leg: 0 }];
    plan.legs.forEach(function (leg, i) {
      arrivals.push({ stop: leg.to, at: new Date(clockAt(bounds[i])), leg: leg.km, legMs: (leg.km / speedKmH) * 3600000, cumKm: bounds[i] });
    });
    var total = bounds.length ? bounds[bounds.length - 1] : 0, ms = (total / speedKmH) * 3600000;
    var hours = Math.ceil(ms / 3600000), samples = [], sunUp = 0, civil = 0, dark = 0;
    for (var h = 0; h <= hours; h++) {
      var km = Math.min(total, h * speedKmH), when = new Date(clockAt(km));
      var pos = AtlasRouter.pointAlong(plan.coords, km, router.haversineKm), el = elevation(pos[1], pos[0], when);
      samples.push({ h: h, when: when, pos: pos, el: el, km: km });
      if (h < hours) { if (el > -0.833) sunUp++; else if (el > -6) civil++; else dark++; }
    }
    return { arrivals: arrivals, ms: ms, samples: samples, sunUp: sunUp, civil: civil, dark: dark, hours: hours, final: arrivals[arrivals.length - 1].at };
  }

  function nearestStop(pos) {
    var best = STOPS[0], bd = Infinity;
    STOPS.forEach(function (s) { var d = router.haversineKm(pos, s.pos); if (d < bd) { bd = d; best = s; } });
    return { stop: best, km: bd };
  }

  /* ---- rendering ----------------------------------------------------------------------------- */
  var map, mapReady = false, markers = [], lastPlans = [];

  function obsText(L) {
    if (!L || L.error) return "unavailable";
    return fix(L.temp, 1) + " °C · " + fix(L.wind, 0) + " km/h" + cardinal(L.dir === null ? null : Number(L.dir));
  }
  function forecastAt(stop, when) {
    var f = forecast[stop.id];
    if (!f) return "not available";
    var ahead = (when.getTime() - Date.now()) / 3600000;
    if (ahead < -1) return "in the past";
    var best = f[0];
    f.forEach(function (h) { if (Math.abs(h.t - when) < Math.abs(best.t - when)) best = h; });
    if (Math.abs(best.t - when) > 90 * 60000) return "beyond forecast (next " + f.length + " h only)";
    return fix(best.temp, 0) + " °C · " + fix(best.wind, 0) + " km/h" + (best.dir ? " " + esc(best.dir) : "") + (best.cond ? " · " + esc(best.cond) : "");
  }

  function render() {
    if (!router) return;
    var inp = inputs();
    if (inp.from.id === inp.to.id) { $("#route-body").innerHTML = "<tr><td colspan='6'>Choose two different places.</td></tr>"; return; }
    var plans = MARGINS.map(function (m) { var p = planFor(inp, m.cells); p.cfg = m; return p; });
    var good = plans.filter(function (p) { return !p.error; });
    if (!good.length) {
      var hint = parseFloat(inp.ice) > 0 && ice ? " Sea ice at " + inp.ice + "% or more may be blocking the passage in the " + (iceMeta ? iceMeta.date : "latest") + " analysis. Try a higher threshold or ignore sea ice." : "";
      $("#route-body").innerHTML = "<tr><td colspan='6'>" + esc(plans[0].error || "No route") + esc(hint) + "</td></tr>"; return;
    }
    var shortest = good.reduce(function (a, b) { return b.km < a.km ? b : a; });
    var chosen = shortest;
    var tl = timeline(inp, chosen);
    lastPlans = good;

    $("[data-r='total-nm']").textContent = (chosen.km / KM_PER_NM).toFixed(0);
    $("[data-r='total-km']").textContent = chosen.km.toFixed(0);
    $("[data-r='total-time']").textContent = dur(tl.ms);
    $("[data-r='arrival']").textContent = utc(tl.final);
    $("[data-r='daylight']").textContent = tl.hours ? Math.round((tl.sunUp / tl.hours) * 100) + "% sun up" : "n/a";
    $("[data-r='daylight-foot']").textContent = tl.sunUp + " h sun up, " + tl.civil + " h twilight, " + tl.dark + " h dark";
    var straight = router.haversineKm(inp.from.pos, inp.to.pos);
    $("[data-r='detour']").textContent = (chosen.km / straight).toFixed(2) + "×";

    // alternatives
    $("#alt-body").innerHTML = good.map(function (p) {
      var ms = (p.km / (inp.speed * KM_PER_NM)) * 3600000, extra = p.km - shortest.km;
      var note = p.marginUsed < p.cfg.cells ? "margin not possible, fell back to " + (p.marginUsed === 0 ? "none" : "a smaller one") : p.cfg.km;
      return "<tr" + (p === chosen ? ' class="chosen"' : "") + "><td>" + esc(p.cfg.name) + (p === shortest ? " <span class=\"badge ok\">shortest</span>" : "") +
        "</td><td>" + (p.km / KM_PER_NM).toFixed(0) + " nm</td><td>" + dur(ms) + "</td><td>" + (extra < 0.5 ? "—" : "+" + (extra / KM_PER_NM).toFixed(0) + " nm") + "</td><td>" + esc(note) + "</td></tr>";
    }).join("");

    // ports
    $("#route-body").innerHTML = tl.arrivals.map(function (a, i) {
      var L = live[a.stop.id], lat = L && !L.error ? L.lat : a.stop.pos[1], lon = L && !L.error ? L.lon : a.stop.pos[0];
      var dl = daylightMs(lat, lon, a.at), dayText = dl === 0 ? "Polar night" : dl >= 24 * 3600000 ? "Midnight sun" : hm(dl) + " h";
      var el = elevation(lat, lon, a.at);
      return "<tr><td>" + esc(a.stop.label) + "<br><span class=\"muted\">" + esc(a.stop.note) + "</span></td>" +
        "<td>" + (i === 0 ? "Departure" : (a.leg / KM_PER_NM).toFixed(0) + " nm<br><span class=\"muted\">" + dur(a.legMs) + "</span>") + "</td>" +
        "<td>" + utc(a.at) + "<br><span class=\"muted\">" + sunState(el) + " on arrival</span></td><td>" + dayText + "</td>" +
        "<td>" + obsText(L) + "</td><td>" + forecastAt(a.stop, a.at) + "</td></tr>";
    }).join("");

    // checkpoints every 12 h of sailing
    var cps = tl.samples.filter(function (s) { return s.h % 12 === 0 && s.h > 0 && s.h < tl.hours; });
    $("#cp-body").innerHTML = cps.length ? cps.map(function (s) {
      var n = nearestStop(s.pos), L = live[n.stop.id];
      return "<tr><td>+" + s.h + " h<br><span class=\"muted\">" + utc(s.when) + "</span></td><td>" + Math.abs(s.pos[1]).toFixed(2) + "°" + (s.pos[1] >= 0 ? "N" : "S") + " " +
        Math.abs(s.pos[0]).toFixed(2) + "°" + (s.pos[0] >= 0 ? "E" : "W") + "<br><span class=\"muted\">" + (s.km / KM_PER_NM).toFixed(0) + " nm from start</span></td><td>" +
        sunState(s.el) + "<br><span class=\"muted\">sun " + s.el.toFixed(1) + "°</span></td><td>" + esc(n.stop.label) + " <span class=\"muted\">(" + (n.km / KM_PER_NM).toFixed(0) + " nm)</span><br>" + obsText(L) + "</td></tr>";
    }).join("") : "<tr><td colspan='4'>The voyage is shorter than 12 hours.</td></tr>";

    var warns = [];
    if (tl.dark + tl.civil > 0 && tl.hours && (tl.dark / tl.hours) > 0.4) warns.push("More than 40% of the voyage is in darkness.");
    tl.arrivals.forEach(function (a) {
      var L = live[a.stop.id], lat = L && !L.error ? L.lat : a.stop.pos[1], lon = L && !L.error ? L.lon : a.stop.pos[0];
      if (daylightMs(lat, lon, a.at) === 0) warns.push(a.stop.label + ": polar night on the arrival day (no sunrise).");
    });
    var maxLat = chosen.coords.reduce(function (m, c) { return Math.max(m, c[1]); }, -90);
    if (!inp.calls && maxLat > 73.3 && inp.from.pos[1] < 71 && inp.to.pos[1] < 73.5) {
      warns.push("The shortest path runs north through Parry Channel (up to " + maxLat.toFixed(1) + "\u00b0N). That is a different passage from the southern route past Cambridge Bay and Gjoa Haven, and it can hold heavier ice. Tick \u201cCall at every port in between\u201d to force the southern route. Shortest is not the same as best.");
    }
    if (parseFloat(inp.ice) > 0 && ice && iceMeta) {
      warns.push("Sea ice: cells at " + inp.ice + "% concentration or more are avoided, using the NSIDC analysis of " + iceMeta.date + ". It is one past day, not a forecast, and 25 km cells miss thin ice, narrow channels and melt-season ice. Consult an official ice chart before relying on any ice-avoiding path.");
    }
    $("#route-notes").innerHTML = warns.map(function (w) { return "<li>" + esc(w) + "</li>"; }).join("");
    drawMap(good, chosen, tl);
  }

  function drawMap(plans, chosen, tl) {
    if (!map || !mapReady) return;
    ["alt1", "alt2", "main"].forEach(function (id) {
      var src = map.getSource(id);
      if (!src) return;
      var plan = id === "main" ? chosen : plans.filter(function (p) { return p !== chosen; })[id === "alt1" ? 0 : 1];
      src.setData({ type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: plan ? plan.coords : [] } });
    });
    markers.forEach(function (m) { m.remove(); });
    markers = [];
    tl.arrivals.forEach(function (a, i) {
      var el = document.createElement("div"); el.className = "stop-pin"; el.textContent = i + 1; el.title = a.stop.label;
      markers.push(new maplibregl.Marker({ element: el }).setLngLat(a.stop.pos).setPopup(new maplibregl.Popup({ offset: 14 }).setText(a.stop.label + " — " + utc(a.at))).addTo(map));
    });
    tl.samples.filter(function (s) { return s.h % 12 === 0 && s.h > 0 && s.h < tl.hours; }).forEach(function (s) {
      var el = document.createElement("div"); el.className = "cp-dot"; el.title = "+" + s.h + " h";
      markers.push(new maplibregl.Marker({ element: el }).setLngLat(s.pos).setPopup(new maplibregl.Popup({ offset: 8 }).setText("+" + s.h + " h · " + utc(s.when) + " · " + sunState(s.el))).addTo(map));
    });
    var b = chosen.coords.reduce(function (acc, c) { return acc.extend(c); }, new maplibregl.LngLatBounds(chosen.coords[0], chosen.coords[0]));
    map.fitBounds(b, { padding: 60, maxZoom: 7, duration: 500 });
  }

  function initMap() {
    var el = $("#route-map");
    if (!el || typeof maplibregl === "undefined") return;
    var d = new Date(Date.now() - 86400000), day = d.getUTCFullYear() + "-" + pad(d.getUTCMonth() + 1) + "-" + pad(d.getUTCDate());
    map = new maplibregl.Map({ cooperativeGestures: true,
      container: el,
      style: { version: 8,
        sources: { gibs: { type: "raster", tileSize: 256, maxzoom: 9, attribution: "Imagery: NASA GIBS / ESDIS",
          tiles: ["https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_SNPP_CorrectedReflectance_TrueColor/default/" + day + "/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg"] } },
        layers: [{ id: "bg", type: "background", paint: { "background-color": "#081925" } }, { id: "gibs", type: "raster", source: "gibs" }] },
      center: [-105, 70], zoom: 3.4, attributionControl: { compact: true }
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    try { (window.AtlasMaps = window.AtlasMaps || []).push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); } catch (e) { /* tools are optional */ }
    if (typeof ResizeObserver === "function") new ResizeObserver(function () { map.resize(); }).observe(el);
    // "style.load" fires once the style is usable; "load" waits for every imagery tile and can take a while.
    map.on("style.load", function () {
      mapReady = true;
      var empty = { type: "Feature", properties: {}, geometry: { type: "LineString", coordinates: [] } };
      ["alt2", "alt1", "main"].forEach(function (id) {
        map.addSource(id, { type: "geojson", data: empty });
        map.addLayer({ id: id + "-line", type: "line", source: id, layout: { "line-join": "round", "line-cap": "round" },
          paint: id === "main" ? { "line-color": "#ffb454", "line-width": 3.4 } : { "line-color": "#7bdff2", "line-width": 2, "line-dasharray": [2, 2], "line-opacity": 0.85 } });
      });
      render();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    var from = $("#r-from"), to = $("#r-to");
    STOPS.forEach(function (s) { [from, to].forEach(function (sel) { var o = document.createElement("option"); o.value = s.id; o.textContent = s.label; sel.appendChild(o); }); });
    from.value = "tuk"; to.value = "pond";
    var now = new Date(); now.setUTCMinutes(0, 0, 0);
    $("#r-depart").value = now.getUTCFullYear() + "-" + pad(now.getUTCMonth() + 1) + "-" + pad(now.getUTCDate()) + "T" + pad(now.getUTCHours()) + ":00";
    ["r-from", "r-to", "r-speed", "r-dwell", "r-depart", "r-via", "r-ice"].forEach(function (id) { $("#" + id).addEventListener("input", render); });
    $("#r-swap").addEventListener("click", function () { var a = from.value; from.value = to.value; to.value = a; render(); });
    // The corridor map and its data load the first time the Arctic tab is opened. A map created inside a
    // hidden tab never becomes ready, and the worldwide tab does not need these requests.
    var started = false;
    function start() {
      if (started) return;
      started = true;
      initMap();
      var obsAll = function () { return Promise.all(STOPS.map(loadObs)).then(function () {
        var ok = STOPS.filter(function (s) { return live[s.id] && !live[s.id].error; }).length;
        $("[data-r='stations']").textContent = ok + " of " + STOPS.length + " stations reporting";
        var newest = STOPS.map(function (s) { return live[s.id] && live[s.id].time; }).filter(Boolean).sort(function (a, b) { return b - a; })[0];
        $("[data-r='updated']").textContent = newest ? "Latest observation " + utc(newest) + "." : "";
      }); };
      var pending = false;
      function schedule() { if (pending) return; pending = true; setTimeout(function () { pending = false; render(); }, 60); }
      loadGrid().then(loadIce).then(schedule).catch(function () { $("[data-r='stations']").textContent = "The routing grid could not be loaded."; });
      obsAll().then(schedule);
      var loaded = 0;
      STOPS.forEach(function (s) {
        loadForecast(s).then(function () {
          loaded++;
          var nf = STOPS.filter(function (x) { return forecast[x.id]; }).length;
          $("[data-r='forecasts']").textContent = loaded < STOPS.length ? "Loading forecasts (" + loaded + " of " + STOPS.length + ")…" : nf + " of " + STOPS.length + " forecasts loaded.";
          schedule();
        });
      });
      setInterval(function () { obsAll().then(render); }, 10 * 60 * 1000);
      setInterval(function () { Promise.all(STOPS.map(loadForecast)).then(render); }, 60 * 60 * 1000);
    }
    document.addEventListener("arctic-shown", function () { start(); if (map) { map.resize(); } render(); });
  });
})();
