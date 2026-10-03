# Decisions

## AOI 1: Cambridge Bay (decided 2026-10-02)

Kept as the primary study area. It has shore installations for the surface-change layer, seasonal sea ice for the ice layer and some vessel traffic.

Known cost: the whole area is within 50 nautical miles of shore. The study box is about 43.9 km by 44.5 km and contains the hamlet of Cambridge Bay, so no point in it is more than 19.0 nautical miles from shore (upper bound; the real maximum is smaller). This is measured, not assumed: `arctic_passage_atlas/distance.py`. It is not a coastline-based maximum; that would need a coastline dataset. The provider documents that gap events starting that close to shore are not reliable indicators of intentional disabling, and that its SAR product leaves out much of the Arctic. The vessel layer is therefore reported as events with no inferred cause, and an empty SAR layer is read as "no usable data", not "no vessels". See the provider caveats in `METHODOLOGY.md`.

Not claimed: that gap events here are caused by receiver geometry or satellite pass timing. Those are plausible but untested.

An offshore passage segment is the candidate for the second study area, where the provider's 50 nautical mile condition can be met. Its location is not chosen.

## Still open

- Year pair for the change layer, subject to checking scene availability.
- Licence for derived data (see `DATA_LICENSE.md`).
- Domain: GitHub Pages default URL until the second study area is done.

## Route calculator and contact page (decided 3 October 2026)

- The route calculator finds the shortest open-water path on a generalised coastline (Natural Earth 1:10M, public domain). It is labelled a planning estimate and says what it does not model: ice, depth, tides, charts, vessel class and regulations. It calls the result "shortest", never "best" or "safe", because the shortest path can run through a different passage with heavier ice.
- The contact page composes an email in the visitor's mail program. There is no server, so nothing is stored. Contact details are read from `site/assets/site-config.js` and left empty until the maintainer sets them; the form switches itself off while the address is empty.
- Out of scope, stated on the page: navigation or ice routing, tracking specific vessels, and commercial products built on Global Fishing Watch data.
- No service level, response time, price or client list is stated, because none exists.
