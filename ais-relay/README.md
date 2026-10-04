# AIS relay (optional)

Live vessel positions on the Live page need a server-side relay, because AISStream does not allow browser
connections and its API key must never be published. This folder is that relay, written for a free
Cloudflare Worker. Without it the website works as before and the vessel panel says it is not connected.

## What it publishes

Anonymous positions only: latitude and longitude rounded to about 100 m, speed, course, age and a broad class
(cargo, tanker, passenger, fishing, service, pleasure, other, unknown). It never sends MMSI, names, call signs,
IMO numbers or destinations, and it drops military, law-enforcement and search-and-rescue vessels.

AISStream is fed by community terrestrial receivers. Open ocean and much of the high Arctic have no coverage,
so the map shows where receivers hear ships, not all ships. A missing dot is not a missing vessel.

## Set up

1. Create a free AISStream account and an API key at <https://aisstream.io>. Read their current terms.
2. Create a free Cloudflare account and install Wrangler: `npm install -g wrangler`, then `wrangler login`.
3. In this folder, create `wrangler.toml` from `wrangler.example.toml` and set `ALLOWED_ORIGIN` to your website
   origin, which is `https://arcticpassageatlas.com`. (The older address `https://vikramchowdhry-ship-it.github.io` redirects to it.)
4. Store the key as a secret (it is not written to any file): `wrangler secret put AISSTREAM_API_KEY`.
5. Deploy: `wrangler deploy`. Wrangler prints the Worker URL.
6. Put that URL in `site/assets/site-config.js` as `aisRelayUrl`, then publish the site.

Tests for the anonymising logic run with the rest of the suite (`python -m pytest`).
