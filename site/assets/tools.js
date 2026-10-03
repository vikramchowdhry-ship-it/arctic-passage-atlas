/* Analyst tools shared by every page with a map:
 *   - a heads-up display with the cursor position (WGS 84 and EPSG:3413 polar stereographic) and the UTC time
 *   - a scale bar
 *   - download helpers (GeoJSON, KML, CSV) used by the layer pages and the route planner
 *   - a layer-page export bar built from the published layer data
 * Everything runs in the browser from data already on the page. Nothing is uploaded.
 */
(function () {
  "use strict";

  /* ---- download helpers ------------------------------------------------------------------------ */
  function download(filename, text, type) {
    var blob = new Blob([text], { type: type || "text/plain;charset=utf-8" });
    var a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = filename;
    document.body.appendChild(a); a.click();
    setTimeout(function () { URL.revokeObjectURL(a.href); a.remove(); }, 500);
  }
  function xml(s) { return String(s).replace(/[<>&"']/g, function (c) { return { "<": "&lt;", ">": "&gt;", "&": "&amp;", '"': "&quot;", "'": "&apos;" }[c]; }); }
  function csvCell(v) {
    var s = v === null || v === undefined ? "" : String(v);
    return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
  }
  function toCsv(rows, columns) {
    columns = columns || Object.keys(rows.reduce(function (acc, r) { Object.keys(r).forEach(function (k) { acc[k] = 1; }); return acc; }, {}));
    return [columns.map(csvCell).join(",")].concat(rows.map(function (r) { return columns.map(function (c) { return csvCell(r[c]); }).join(","); })).join("\r\n") + "\r\n";
  }
  function coordsKml(coords) { return coords.map(function (c) { return c[0].toFixed(5) + "," + c[1].toFixed(5) + ",0"; }).join(" "); }
  function geomKml(g) {
    if (g.type === "Point") return "<Point><coordinates>" + coordsKml([g.coordinates]) + "</coordinates></Point>";
    if (g.type === "LineString") return "<LineString><tessellate>1</tessellate><coordinates>" + coordsKml(g.coordinates) + "</coordinates></LineString>";
    if (g.type === "Polygon") return "<Polygon><outerBoundaryIs><LinearRing><coordinates>" + coordsKml(g.coordinates[0]) + "</coordinates></LinearRing></outerBoundaryIs></Polygon>";
    if (g.type === "MultiPolygon") return "<MultiGeometry>" + g.coordinates.map(function (p) { return geomKml({ type: "Polygon", coordinates: p }); }).join("") + "</MultiGeometry>";
    return "";
  }
  /* KML for Google Earth. `notice` is written into the document description so it travels with the file. */
  function toKml(features, name, notice, nameOf) {
    var body = features.map(function (f, i) {
      var p = f.properties || {};
      var rows = Object.keys(p).map(function (k) { return "<tr><td>" + xml(k.replace(/_/g, " ")) + "</td><td>" + xml(p[k]) + "</td></tr>"; }).join("");
      return "<Placemark><name>" + xml(nameOf ? nameOf(f, i) : (p.name || p.candidate_id || p.event_id || p.cell_id || p.period || "feature " + (i + 1))) + "</name>" +
        "<description><![CDATA[<table>" + rows.replace(/]]>/g, "") + "</table>]]></description>" + geomKml(f.geometry) + "</Placemark>";
    }).join("");
    return '<?xml version="1.0" encoding="UTF-8"?>\n<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>' + xml(name) + "</name><description>" + xml(notice || "") + "</description>" + body + "</Document></kml>\n";
  }
  window.AtlasExport = { download: download, toCsv: toCsv, toKml: toKml };

  /* ---- EPSG:3413 (WGS 84 NSIDC polar stereographic north), kilometres ---------------------------- */
  function epsg3413(lon, lat) {
    var a = 6378137, e = 0.0818191908426, rad = Math.PI / 180;
    function t(phi) { var s = Math.sin(phi); return Math.tan(Math.PI / 4 - phi / 2) / Math.pow((1 - e * s) / (1 + e * s), e / 2); }
    var phiC = 70 * rad, mC = Math.cos(phiC) / Math.sqrt(1 - e * e * Math.sin(phiC) * Math.sin(phiC));
    var rho = a * mC * t(Math.min(lat, 89.999999) * rad) / t(phiC), l = (lon + 45) * rad;
    return [rho * Math.sin(l) / 1000, -rho * Math.cos(l) / 1000];
  }
  window.AtlasExport.epsg3413 = epsg3413;
  function dms(v, pos, neg) { return Math.abs(v).toFixed(3) + "° " + (v >= 0 ? pos : neg); }
  function utcStamp() { var d = new Date(); return d.toISOString().slice(0, 16).replace("T", " ") + " UTC"; }

  /* ---- HUD and scale bar ----------------------------------------------------------------------- */
  function attach(map) {
    if (!map || map.__atlasHud) return;
    map.__atlasHud = true;
    var host = map.getContainer().parentElement;
    if (!host) return;
    var nautical = map.getContainer().classList.contains("tall");
    try { map.addControl(new maplibregl.ScaleControl({ unit: nautical ? "nautical" : "metric", maxWidth: 110 }), "bottom-left"); } catch (e) { /* older style not ready */ }
    var hud = document.createElement("div");
    hud.className = "map-hud"; hud.setAttribute("aria-hidden", "true");
    hud.innerHTML = '<span data-h="lat">LAT —</span><span data-h="lon">LON —</span><span data-h="xy">EPSG:3413 —</span><span data-h="t"></span>';
    host.appendChild(hud);
    var q = function (k) { return hud.querySelector('[data-h="' + k + '"]'); };
    function clock() { q("t").textContent = utcStamp(); }
    clock(); setInterval(clock, 15000);
    map.on("mousemove", function (e) {
      var lng = ((e.lngLat.lng + 540) % 360) - 180, lat = e.lngLat.lat, xy = epsg3413(lng, lat);
      q("lat").textContent = "LAT " + dms(lat, "N", "S");
      q("lon").textContent = "LON " + dms(lng, "E", "W");
      q("xy").textContent = "EPSG:3413 " + xy[0].toFixed(0) + ", " + xy[1].toFixed(0) + " km";
    });
  }
  window.AtlasMaps = window.AtlasMaps || [];
  window.AtlasMaps.forEach(attach);
  document.addEventListener("atlas-map", function (e) { attach(e.detail); });
  window.AtlasRegisterMap = function (map) { window.AtlasMaps.push(map); document.dispatchEvent(new CustomEvent("atlas-map", { detail: map })); };

  /* ---- layer export bar ------------------------------------------------------------------------ */
  var LAYERS = {
    change: { label: "Surface-change candidates", key: "change" },
    ice: { label: "Sea-ice snapshots", key: "ice" },
    gaps: { label: "AIS gap events", key: "gaps" },
    sar: { label: "SAR detection cells", key: "sar" }
  };
  function centroid(g) {
    var pts = g.type === "Point" ? [g.coordinates] : g.type === "LineString" ? g.coordinates : g.type === "Polygon" ? g.coordinates[0] : [];
    if (!pts.length) return ["", ""];
    var x = 0, y = 0; pts.forEach(function (p) { x += p[0]; y += p[1]; });
    return [(y / pts.length).toFixed(5), (x / pts.length).toFixed(5)];
  }
  function exportBar() {
    var data = window.ATLAS_DATA, target = document.querySelector("[data-map-layer]");
    if (!data || !target) return;
    var which = target.getAttribute("data-map-layer");
    var keys = which === "all" ? ["change", "ice", "gaps", "sar"] : which === "vessels" ? ["gaps", "sar"] : [which];
    var demo = (data.manifest && data.manifest.mode) !== "live";
    var notice = demo ? "SYNTHETIC DEMONSTRATION DATA. NOT OBSERVATIONS. Generated by Arctic Passage Atlas." : "Generated by Arctic Passage Atlas. Check the manifest and method page for limits.";
    var shell = target.closest(".map-shell");
    if (!shell) return;
    var bar = document.createElement("div");
    bar.className = "export-bar";
    bar.innerHTML = '<span class="export-title">Export</span>' +
      keys.map(function (k) {
        return '<span class="export-group"><span class="export-name">' + LAYERS[k].label + '</span>' +
          ["GeoJSON", "KML", "CSV"].map(function (f) { return '<button type="button" data-k="' + k + '" data-f="' + f + '">' + f + "</button>"; }).join("") + "</span>";
      }).join("") + '<button type="button" class="print-btn" data-print>Save PDF briefing</button>';
    shell.insertAdjacentElement("afterend", bar);
    bar.addEventListener("click", function (e) {
      var b = e.target.closest("button"); if (!b) return;
      if (b.hasAttribute("data-print")) { window.print(); return; }
      var k = b.getAttribute("data-k"), f = b.getAttribute("data-f"), fc = data[k], tag = (demo ? "demo-" : "") + k;
      if (!fc) return;
      var withNotice = { type: "FeatureCollection", name: tag, notice: notice, features: fc.features };
      if (f === "GeoJSON") window.AtlasExport.download("arctic-passage-atlas-" + tag + ".geojson", JSON.stringify(withNotice, null, 1), "application/geo+json");
      else if (f === "KML") window.AtlasExport.download("arctic-passage-atlas-" + tag + ".kml", toKml(fc.features, LAYERS[k].label + (demo ? " (synthetic)" : ""), notice), "application/vnd.google-earth.kml+xml");
      else {
        var rows = fc.features.map(function (ft) { var c = centroid(ft.geometry), r = { notice: demo ? "synthetic demonstration" : "" }; Object.keys(ft.properties).forEach(function (p) { r[p] = ft.properties[p]; }); r.geometry = ft.geometry.type; r.centroid_lat = c[0]; r.centroid_lon = c[1]; return r; });
        window.AtlasExport.download("arctic-passage-atlas-" + tag + ".csv", toCsv(rows), "text/csv;charset=utf-8");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", exportBar);
})();
