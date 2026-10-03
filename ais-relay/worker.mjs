/* Cloudflare Worker: a small server-side relay between AISStream and the Arctic Passage Atlas website.
 *
 * AISStream does not allow browser connections and its API key must stay on a server, so the website asks
 * this Worker for a snapshot instead. The Worker opens one short WebSocket to AISStream, collects position
 * reports for a few seconds, reduces them to an anonymous list (see logic.mjs) and caches the answer so any
 * number of visitors share one upstream connection. Free-tier limits are 3 connections per account.
 *
 * Secrets and settings (never commit these):
 *   AISSTREAM_API_KEY   secret, from your AISStream account
 *   ALLOWED_ORIGIN      variable, the website origin, for example https://<user>.github.io
 */
import { BOXES, MESSAGE_TYPES, reduce, summarise } from "./logic.mjs";

const COLLECT_MS = 9000;
const TYPES = new Map();   // MMSI -> ship type, kept while this Worker instance stays warm so classes fill in over time
const CACHE_SECONDS = 60;

function cors(env, extra = {}) {
  return { "access-control-allow-origin": env.ALLOWED_ORIGIN || "null", "vary": "origin", ...extra };
}

async function collect(env) {
  const upstream = await fetch("https://stream.aisstream.io/v0/stream", { headers: { Upgrade: "websocket" } });
  const ws = upstream.webSocket;
  if (!ws) throw new Error("AISStream did not accept the connection");
  ws.accept();
  const messages = [];
  const decoder = new TextDecoder();
  ws.addEventListener("message", (event) => {
    try {
      const text = typeof event.data === "string" ? event.data : decoder.decode(event.data);
      messages.push(JSON.parse(text));
    } catch (e) { /* skip a frame we cannot read */ }
  });
  ws.send(JSON.stringify({ APIKey: env.AISSTREAM_API_KEY, BoundingBoxes: BOXES, FilterMessageTypes: MESSAGE_TYPES }));
  await new Promise((resolve) => setTimeout(resolve, COLLECT_MS));
  try { ws.close(1000, "done"); } catch (e) { /* already closed */ }
  return messages;
}

export default {
  async fetch(request, env, ctx) {
    if (request.method === "OPTIONS") return new Response(null, { status: 204, headers: cors(env, { "access-control-allow-methods": "GET" }) });
    if (!env.AISSTREAM_API_KEY) return new Response(JSON.stringify({ error: "not configured" }), { status: 503, headers: cors(env, { "content-type": "application/json" }) });
    const cache = caches.default, key = new Request(new URL("/snapshot", request.url).toString());
    const hit = await cache.match(key);
    if (hit) return new Response(hit.body, { status: 200, headers: cors(env, { "content-type": "application/json", "cache-control": "public, max-age=" + CACHE_SECONDS }) });
    try {
      const now = Date.now(), messages = await collect(env), vessels = reduce(messages, now, TYPES);
      if (TYPES.size > 30000) TYPES.clear();
      const body = JSON.stringify({
        generated_at: new Date(now).toISOString(), window_s: COLLECT_MS / 1000, source: "AISStream (community terrestrial AIS receivers)",
        coverage: "Arctic and approaches; terrestrial receivers only, so open ocean and much of the high Arctic have no coverage",
        counts: summarise(vessels), vessels,
        notice: "Positions only. No names, identifiers or destinations. Absence of a dot does not mean absence of a vessel.",
      });
      ctx.waitUntil(cache.put(key, new Response(body, { headers: { "content-type": "application/json", "cache-control": "public, max-age=" + CACHE_SECONDS } })));
      return new Response(body, { status: 200, headers: cors(env, { "content-type": "application/json", "cache-control": "public, max-age=" + CACHE_SECONDS }) });
    } catch (e) {
      return new Response(JSON.stringify({ error: "upstream unavailable" }), { status: 502, headers: cors(env, { "content-type": "application/json" }) });
    }
  },
};
