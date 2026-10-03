/* Worldwide / Arctic tabs on the route page. The hash (#arctic, #world) selects a tab so it can be linked. */
(function () {
  "use strict";
  function init() {
    var tabs = [].slice.call(document.querySelectorAll('[role="tab"]'));
    if (!tabs.length) return;
    function select(id, focus) {
      tabs.forEach(function (t) {
        var on = t.id === id;
        t.setAttribute("aria-selected", String(on));
        t.tabIndex = on ? 0 : -1;
        document.getElementById(t.getAttribute("aria-controls")).hidden = !on;
        if (on && focus) t.focus();
      });
      var name = id.replace("tab-", "");
      document.dispatchEvent(new Event(name + "-shown"));
      if (history.replaceState) history.replaceState(null, "", "#" + name);
    }
    tabs.forEach(function (t, i) {
      t.addEventListener("click", function () { select(t.id); });
      t.addEventListener("keydown", function (e) {
        var k = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
        if (k) { e.preventDefault(); select(tabs[(i + k + tabs.length) % tabs.length].id, true); }
      });
    });
    if (location.hash === "#arctic") select("tab-arctic");
  }
  document.addEventListener("DOMContentLoaded", init);
})();
