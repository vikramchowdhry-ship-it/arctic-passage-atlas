/* Interface behaviour shared by every page: scroll reveals, mobile menu, count-up numbers and the
 * project-status board. Nothing here changes what the data says. All motion respects
 * prefers-reduced-motion. */
(function () {
  "use strict";
  var reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* mobile menu */
  function menu() {
    var nav = document.querySelector(".nav");
    var btn = document.querySelector(".nav-toggle");
    if (!nav || !btn) return;
    btn.addEventListener("click", function () {
      var open = nav.classList.toggle("open");
      btn.setAttribute("aria-expanded", String(open));
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape" && nav.classList.contains("open")) { nav.classList.remove("open"); btn.setAttribute("aria-expanded", "false"); btn.focus(); }
    });
  }

  /* header gains a shadow once the page scrolls */
  function headerShadow() {
    var h = document.querySelector(".site-header");
    if (!h) return;
    function on() { h.classList.toggle("scrolled", window.scrollY > 8); }
    on(); window.addEventListener("scroll", on, { passive: true });
  }

  /* reveal on scroll. Content must never stay hidden: anything already on screen is shown straight
   * away, and a timer reveals whatever is left if the observer never fires. */
  function reveal() {
    var els = [].slice.call(document.querySelectorAll(".section-head, .card, .panel, .pipeline, .video-frame, .map-shell, .table-wrap, .kpi"));
    if (reduce || !("IntersectionObserver" in window)) return;
    var below = els.filter(function (el) { return el.getBoundingClientRect().top > window.innerHeight; });
    below.forEach(function (el) { el.classList.add("reveal"); });
    var io = new IntersectionObserver(function (entries) {
      entries.forEach(function (en) {
        if (en.isIntersecting) { en.target.classList.add("in"); io.unobserve(en.target); }
      });
    }, { rootMargin: "0px 0px -8% 0px", threshold: 0.05 });
    below.forEach(function (el) { io.observe(el); });
    setTimeout(function () { below.forEach(function (el) { if (el.getBoundingClientRect().top < window.innerHeight * 1.5) el.classList.add("in"); }); }, 2500);
  }

  /* count-up for the headline numbers on the first view */
  function countUp(el) {
    var target = parseFloat(el.textContent);
    if (reduce || isNaN(target) || el.dataset.counted) return;
    el.dataset.counted = "1";
    var decimals = (el.textContent.split(".")[1] || "").length, t0 = performance.now(), dur = 900;
    function step(now) {
      var k = Math.min(1, (now - t0) / dur), e = 1 - Math.pow(1 - k, 3);
      el.textContent = (target * e).toFixed(decimals);
      if (k < 1) requestAnimationFrame(step); else el.textContent = target.toFixed(decimals);
    }
    requestAnimationFrame(step);
  }
  function watchNumbers() {
    var els = document.querySelectorAll("[data-stat], [data-ice='extent']");
    var mo = new MutationObserver(function (list) {
      list.forEach(function (m) { if (m.target.nodeType === 1) countUp(m.target); else if (m.target.parentElement) countUp(m.target.parentElement); });
    });
    els.forEach(function (el) { mo.observe(el, { childList: true, characterData: true, subtree: true }); });
  }

  /* project status board, built from the published configuration */
  function statusBoard() {
    var host = document.getElementById("project-status");
    var data = window.ATLAS_DATA;
    if (!host || !data) return;
    var cfg = data.config || {}, mode = (data.manifest && data.manifest.mode) || "unknown";
    var iceStatus = cfg.ice && cfg.ice.threshold_status, reviewStatus = cfg.change && cfg.change.manual_review_status;
    var rows = [
      ["Study area and configuration", "Configured", "ok", "Boundary, dates and dataset IDs are in one reviewed JSON file."],
      ["Live context feeds", "Operating", "ok", "Station weather, NASA imagery and NSIDC sea-ice extent on the Live page."],
      ["Analytical layers", mode === "live" ? "Provider-backed" : "Synthetic demonstration", mode === "live" ? "ok" : "warn",
        mode === "live" ? "Outputs were generated from provider data." : "Layer pages show labelled fixtures until a live run is published."],
      ["Sea-ice thresholds", iceStatus === "validated" ? "Validated" : "Pending calibration", iceStatus === "validated" ? "ok" : "warn",
        "Needs one Earth Engine inventory run, a chosen threshold per polarisation and a comparison with an independent source."],
      ["Change-candidate review", reviewStatus === "complete" ? "Complete" : "Pending review", reviewStatus === "complete" ? "ok" : "warn",
        "Candidates need visual and documentary checking before they are described as anything."],
      ["Vessel-event schema", "Pending one API call", "warn", "A real Global Fishing Watch response will replace the assumed field names."],
      ["Live publication gate", mode === "live" ? "Open" : "Closed", mode === "live" ? "ok" : "warn",
        "The pipeline refuses to publish a mixed demonstration and live site."]
    ];
    host.innerHTML = rows.map(function (r) {
      return '<div class="status-row"><div><strong>' + r[0] + '</strong><span>' + r[3] + '</span></div><span class="badge ' + r[2] + '">' + r[1] + "</span></div>";
    }).join("");
  }

  document.addEventListener("DOMContentLoaded", function () {
    menu(); headerShadow(); reveal(); watchNumbers(); statusBoard();
  });
})();
