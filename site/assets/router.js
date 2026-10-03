/* Shortest open-water path on a longitude/latitude grid.
 *
 * Input is a grid of water/land cells (see arctic_passage_atlas/route_grid.py). The search is A* over
 * eight neighbours with real ground distances, no corner-cutting through land, an optional margin from
 * the coast, and line-of-sight smoothing. Ice, depth, tides, charts and regulations are not modelled, so
 * the result is a shortest-water estimate and never a recommendation to navigate.
 */
(function (root) {
  "use strict";

  var KM_PER_DEG = 111.195;

  // Search buffers are large on a world grid, so all routers of the same size share one set.
  var SCRATCH = {};
  function scratch(n) {
    if (!SCRATCH[n]) SCRATCH[n] = { g: new Float32Array(n), p: new Int32Array(n), d: new Uint8Array(n) };
    return SCRATCH[n];
  }

  function createRouter(grid) {
    var rows = grid.rows, cols = grid.cols, west = grid.bbox[0], north = grid.bbox[3];
    var dlon = grid.dlon, dlat = grid.dlat, water = grid.water, wrap = !!grid.wrap;
    var N = rows * cols;
    var rowCos = new Float64Array(rows);
    for (var r = 0; r < rows; r++) rowCos[r] = Math.cos(((north - (r + 0.5) * dlat) * Math.PI) / 180);
    var masks = { 0: water };
    var DR = [-1, -1, -1, 0, 0, 1, 1, 1], DC = [-1, 0, 1, -1, 1, -1, 0, 1];

    function lonOf(c) { return west + (c + 0.5) * dlon; }
    function latOf(r) { return north - (r + 0.5) * dlat; }
    function cellOf(lon, lat) {
      return { r: Math.floor((north - lat) / dlat), c: Math.floor((lon - west) / dlon) };
    }
    // On a world grid the columns wrap at the antimeridian, so a ship can sail across 180 degrees.
    function wc(c) { return wrap ? ((c % cols) + cols) % cols : c; }
    function inside(r, c) { return r >= 0 && r < rows && (wrap || (c >= 0 && c < cols)); }
    function dcols(c1, c2) { var d = Math.abs(c2 - c1); return wrap && d > cols / 2 ? cols - d : d; }

    /* Water cells at least `margin` cells from any land (square neighbourhood). */
    function maskFor(margin) {
      if (masks[margin]) return masks[margin];
      var tmp = new Uint8Array(N), out = new Uint8Array(N), r, c, k, i;
      for (r = 0; r < rows; r++) {
        for (c = 0; c < cols; c++) {
          var ok = 1;
          for (k = -margin; k <= margin && ok; k++) {
            var cc = c + k;
            if (!wrap && (cc < 0 || cc >= cols)) { ok = 0; continue; }
            if (!water[r * cols + wc(cc)]) ok = 0;
          }
          tmp[r * cols + c] = ok;
        }
      }
      for (c = 0; c < cols; c++) {
        for (r = 0; r < rows; r++) {
          var good = 1;
          for (k = -margin; k <= margin && good; k++) {
            var rr = r + k;
            if (rr < 0 || rr >= rows || !tmp[rr * cols + c]) good = 0;
          }
          out[r * cols + c] = good;
        }
      }
      // cells on the grid edge are kept if they are water, so a route may leave the area
      for (i = 0; i < N; i++) if (water[i] && !out[i] && margin === 0) out[i] = 1;
      masks[margin] = out;
      return out;
    }

    var MIN_SEA_CELLS = 2000;  // anything smaller is an enclosed pocket, not a place a route can start
    var compCache = {};
    function components(margin) {
      if (compCache[margin]) return compCache[margin];
      var m = maskFor(margin), comp = new Int32Array(N), sizes = [0], stack = new Int32Array(N), id = 0;
      for (var i = 0; i < N; i++) {
        if (!m[i] || comp[i]) continue;
        id++; var sp = 0, count = 0; stack[sp++] = i; comp[i] = id;
        while (sp > 0) {
          var u = stack[--sp]; count++;
          var ur = (u / cols) | 0, uc = u - ur * cols;
          for (var k = 0; k < 8; k++) {
            var vr = ur + DR[k], vc = wc(uc + DC[k]);
            if (vr < 0 || vr >= rows || vc < 0 || vc >= cols) continue;
            var v = vr * cols + vc;
            if (!m[v] || comp[v]) continue;
            if (DR[k] !== 0 && DC[k] !== 0 && (!m[ur * cols + vc] || !m[vr * cols + uc])) continue;
            comp[v] = id; stack[sp++] = v;
          }
        }
        sizes.push(count);
      }
      compCache[margin] = { comp: comp, sizes: sizes };
      return compCache[margin];
    }

    function groundKm(r1, c1, r2, c2) {
      var cosm = (rowCos[r1] + rowCos[r2]) / 2;
      var dx = dcols(c1, c2) * dlon * KM_PER_DEG * cosm, dy = (r2 - r1) * dlat * KM_PER_DEG;
      return Math.sqrt(dx * dx + dy * dy);
    }

    /* nearest cell that is open water for this margin, within maxKm; null if none */
    function snap(lon, lat, margin, maxKm) {
      var m = maskFor(margin), cc = components(margin), p = cellOf(lon, lat), best = null, bestD = Infinity;
      var reach = Math.ceil(maxKm / (dlat * KM_PER_DEG)) + 1;
      for (var dr = -reach; dr <= reach; dr++) {
        for (var dc = -reach * 3; dc <= reach * 3; dc++) {
          var r = p.r + dr, c = wc(p.c + dc);
          if (!inside(r, c) || !m[r * cols + c] || cc.sizes[cc.comp[r * cols + c]] < MIN_SEA_CELLS) continue;
          var d = groundKm(p.r, wc(p.c), r, c);
          if (d < bestD && d <= maxKm) { bestD = d; best = { r: r, c: c, km: d }; }
        }
      }
      return best;
    }

    /* binary heap of (node, key) pairs */
    function Heap() {
      this.n = 0; this.cap = 1 << 16; this.node = new Int32Array(this.cap); this.key = new Float32Array(this.cap);
    }
    Heap.prototype.push = function (node, key) {
      if (this.n === this.cap) {
        this.cap *= 2;
        var nn = new Int32Array(this.cap); nn.set(this.node); this.node = nn;
        var nk = new Float32Array(this.cap); nk.set(this.key); this.key = nk;
      }
      var i = this.n++;
      while (i > 0) {
        var p = (i - 1) >> 1;
        if (this.key[p] <= key) break;
        this.node[i] = this.node[p]; this.key[i] = this.key[p]; i = p;
      }
      this.node[i] = node; this.key[i] = key;
    };
    Heap.prototype.pop = function () {
      var top = this.node[0], n = --this.n;
      if (n > 0) {
        var node = this.node[n], key = this.key[n], i = 0;
        for (;;) {
          var l = 2 * i + 1;
          if (l >= n) break;
          if (l + 1 < n && this.key[l + 1] < this.key[l]) l++;
          if (this.key[l] >= key) break;
          this.node[i] = this.node[l]; this.key[i] = this.key[l]; i = l;
        }
        this.node[i] = node; this.key[i] = key;
      }
      return top;
    };

    function astar(start, goal, m) {
      var buf = scratch(N), g = buf.g.fill(Infinity), parent = buf.p.fill(-1), done = buf.d.fill(0);
      var heap = new Heap(), s = start.r * cols + start.c, t = goal.r * cols + goal.c, expanded = 0;
      function h(r, c) {
        var cosm = (rowCos[r] + rowCos[goal.r]) / 2;
        var dx = dcols(goal.c, c) * dlon * KM_PER_DEG * cosm, dy = (goal.r - r) * dlat * KM_PER_DEG;
        return 0.995 * Math.sqrt(dx * dx + dy * dy);
      }
      g[s] = 0; heap.push(s, h(start.r, start.c));
      while (heap.n > 0) {
        var u = heap.pop();
        if (done[u]) continue;
        done[u] = 1; expanded++;
        if (u === t) break;
        var ur = (u / cols) | 0, uc = u - ur * cols;
        for (var k = 0; k < 8; k++) {
          var vr = ur + DR[k], vc = wc(uc + DC[k]);
          if (vr < 0 || vr >= rows || vc < 0 || vc >= cols) continue;
          var v = vr * cols + vc;
          if (!m[v] || done[v]) continue;
          if (DR[k] !== 0 && DC[k] !== 0 && (!m[ur * cols + vc] || !m[vr * cols + uc])) continue; // no corner cutting
          var ng = g[u] + groundKm(ur, uc, vr, vc);
          if (ng < g[v]) { g[v] = ng; parent[v] = u; heap.push(v, ng + h(vr, vc)); }
        }
      }
      if (!done[t]) return { path: null, expanded: expanded };
      var path = [];
      for (var x = t; x !== -1; x = parent[x]) path.push({ r: (x / cols) | 0, c: x % cols });
      path.reverse();
      return { path: path, expanded: expanded };
    }

    function clear(a, b, m) {
      var r0 = a.r, c0 = a.c, r1 = b.r, c1 = b.c;
      if (wrap) { if (c1 - c0 > cols / 2) c1 -= cols; else if (c0 - c1 > cols / 2) c1 += cols; }   // go the short way round
      var dr = Math.abs(r1 - r0), dc = Math.abs(c1 - c0), sr = r0 < r1 ? 1 : -1, sc = c0 < c1 ? 1 : -1, err = dc - dr;
      while (true) {
        if (!m[r0 * cols + wc(c0)]) return false;
        if (r0 === r1 && c0 === c1) return true;
        var e2 = 2 * err, pr = r0, pc = c0;
        if (e2 > -dr) { err -= dr; c0 += sc; }
        if (e2 < dc) { err += dc; r0 += sr; }
        if (r0 !== pr && c0 !== pc && (!m[pr * cols + wc(c0)] || !m[r0 * cols + wc(pc)])) return false;
      }
    }

    function smooth(path, m) {
      var out = [path[0]], i = 0;
      while (i < path.length - 1) {
        var j = path.length - 1;
        while (j > i + 1 && !clear(path[i], path[j], m)) j--;
        out.push(path[j]); i = j;
      }
      return out;
    }

    function haversineKm(a, b) {
      var rad = Math.PI / 180, dLat = (b[1] - a[1]) * rad, dLon = (b[0] - a[0]) * rad;
      var q = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(a[1] * rad) * Math.cos(b[1] * rad) * Math.sin(dLon / 2) * Math.sin(dLon / 2);
      return 2 * 6371.0088 * Math.asin(Math.min(1, Math.sqrt(q)));
    }

    /* Shortest water path between two lon/lat points. Ports sit on land, so each end is snapped to the
     * nearest open water within maxSnapKm; the (short) link from the port is included in the length. */
    /* Copy of the margin mask with the water around both ports opened, so a route can leave a harbour or
     * a strait that is narrower than the margin but still keeps off the coast in open water. */
    function openEnds(mask, a, b, radius) {
      var out = Uint8Array.from(mask);
      [a, b].forEach(function (p) {
        for (var dr = -radius; dr <= radius; dr++) {
          for (var dc = -radius; dc <= radius; dc++) {
            var r = p.r + dr, c = wc(p.c + dc);
            if (r >= 0 && r < rows && c >= 0 && c < cols && water[r * cols + c]) out[r * cols + c] = 1;
          }
        }
      });
      return out;
    }

    function route(from, to, margin, maxSnapKm) {
      var maxKm = maxSnapKm || 40, usedMargin = margin, m = maskFor(0), result = null, a, b;
      if (margin > 0) {
        a = snap(from[0], from[1], 0, maxKm); b = snap(to[0], to[1], 0, maxKm);
        if (a && b) {
          m = openEnds(maskFor(margin), a, b, 3 * margin + 3);
          result = astar(a, b, m);
        }
        if (!result || !result.path) { usedMargin = 0; result = null; }
      }
      if (usedMargin === 0) {
        m = maskFor(0);
        a = snap(from[0], from[1], 0, maxKm); b = snap(to[0], to[1], 0, maxKm);
        if (!a || !b) return { error: "A port is more than " + maxKm + " km from open water on this grid." };
        result = astar(a, b, m);
      }
      if (!result.path) return { error: "No open-water connection on this grid.", expanded: result.expanded };
      var cells = smooth(result.path, m);
      var coords = [[from[0], from[1]]].concat(cells.map(function (p) { return [lonOf(p.c), latOf(p.r)]; }), [[to[0], to[1]]]);
      if (wrap) {   // keep longitudes continuous (e.g. 179, 181) so the line crosses 180 instead of spanning the globe
        for (var q = 1; q < coords.length; q++) {
          while (coords[q][0] - coords[q - 1][0] > 180) coords[q][0] -= 360;
          while (coords[q][0] - coords[q - 1][0] < -180) coords[q][0] += 360;
        }
      }
      var km = 0;
      for (var i = 1; i < coords.length; i++) km += haversineKm(coords[i - 1], coords[i]);
      return { coords: coords, km: km, margin: usedMargin, marginRequested: margin, expanded: result.expanded, snapKm: [a.km, b.km] };
    }

    return { route: route, snap: snap, cellOf: cellOf, maskFor: maskFor, haversineKm: haversineKm, lonOf: lonOf, latOf: latOf, rows: rows, cols: cols };
  }

  /* point `km` along a polyline of lon/lat coordinates */
  function pointAlong(coords, km, haversineKm) {
    var left = km;
    for (var i = 1; i < coords.length; i++) {
      var seg = haversineKm(coords[i - 1], coords[i]);
      if (left <= seg || i === coords.length - 1) {
        var f = seg === 0 ? 0 : Math.min(1, left / seg);
        return [coords[i - 1][0] + (coords[i][0] - coords[i - 1][0]) * f, coords[i - 1][1] + (coords[i][1] - coords[i - 1][1]) * f];
      }
      left -= seg;
    }
    return coords[coords.length - 1];
  }

  var api = { createRouter: createRouter, pointAlong: pointAlong };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  root.AtlasRouter = api;
})(typeof window !== "undefined" ? window : globalThis);
