/* Home page: fills the quick-route selects from the same port list the planner uses. If the list cannot
 * be loaded the two default ports stay in place and the form still works. */
(function () {
  "use strict";
  document.addEventListener("DOMContentLoaded", function () {
    var from = document.getElementById("q-from"), to = document.getElementById("q-to");
    if (!from || !to) return;
    fetch("data/route/ports.json").then(function (r) { return r.json(); }).then(function (d) {
      var groups = {};
      d.ports.forEach(function (p) { (groups[p.region] = groups[p.region] || []).push(p); });
      [from, to].forEach(function (sel) {
        var keep = sel.value;
        sel.innerHTML = "";
        Object.keys(groups).forEach(function (g) {
          var og = document.createElement("optgroup"); og.label = g;
          groups[g].forEach(function (p) {
            var o = document.createElement("option"); o.value = p.id; o.textContent = p.name + ", " + p.country; og.appendChild(o);
          });
          sel.appendChild(og);
        });
        sel.value = keep;
      });
    }).catch(function () { /* keep the defaults */ });
  });
})();
