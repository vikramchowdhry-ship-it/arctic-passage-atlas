/* The AIS relay as a plain Node program, for running on your own machine.
 *
 *   AISSTREAM_API_KEY=<your key> node ais-relay/local.mjs
 *
 * It keeps one connection open to AISStream, remembers the latest position of each vessel for 20 minutes, and
 * answers http://127.0.0.1:8787/ with the same anonymous JSON as the Cloudflare Worker. The key is read from
 * the environment and is never written to a file. Then open the Live page with
 *   http://127.0.0.1:8000/live.html?ais=http://127.0.0.1:8787/
 */
import http from "node:http";
import { BOXES, MESSAGE_TYPES, reduce, summarise } from "./logic.mjs";

const key = process.env.AISSTREAM_API_KEY;
if (!key) { console.error("Set AISSTREAM_API_KEY first."); process.exit(1); }
const PORT = Number(process.env.PORT || 8787);
const KEEP_MS = 20 * 60 * 1000;

const positions = new Map();   // MMSI -> latest position message
const types = new Map();       // MMSI -> ship type
let connected = false, received = 0;

function connect() {
  const ws = new WebSocket("wss://stream.aisstream.io/v0/stream");
  ws.onopen = () => { connected = true; ws.send(JSON.stringify({ APIKey: key, BoundingBoxes: BOXES, FilterMessageTypes: MESSAGE_TYPES })); };
  ws.onmessage = async (e) => {
    try {
      const text = typeof e.data === "string" ? e.data : Buffer.from(await e.data.arrayBuffer()).toString("utf8");
      const m = JSON.parse(text);
      if (!m.MetaData) return;
      received++;
      const id = m.MetaData.MMSI;
      if (m.MessageType === "ShipStaticData") { const t = m.Message.ShipStaticData && m.Message.ShipStaticData.Type; if (t !== undefined) types.set(id, t); }
      else positions.set(id, { m, at: Date.now() });
    } catch (err) { /* skip a frame we cannot read */ }
  };
  ws.onclose = () => { connected = false; setTimeout(connect, 5000); };
  ws.onerror = () => { connected = false; };
}
connect();

http.createServer((req, res) => {
  const origin = req.headers.origin || "";
  const ok = /^http:\/\/(127\.0\.0\.1|localhost)(:\d+)?$/.test(origin);
  const headers = { "content-type": "application/json", "access-control-allow-origin": ok ? origin : "null", vary: "origin" };
  if (req.method === "OPTIONS") { res.writeHead(204, headers); res.end(); return; }
  const now = Date.now();
  for (const [id, p] of positions) if (now - p.at > KEEP_MS) positions.delete(id);
  const vessels = reduce([...positions.values()].map((p) => p.m), now, types);
  res.writeHead(200, headers);
  res.end(JSON.stringify({
    generated_at: new Date(now).toISOString(), window_s: KEEP_MS / 1000, source: "AISStream (community terrestrial AIS receivers)",
    coverage: "Arctic and approaches; terrestrial receivers only, so open ocean and much of the high Arctic have no coverage",
    connected, messages_received: received, counts: summarise(vessels), vessels,
    notice: "Positions only. No names, identifiers or destinations. Absence of a dot does not mean absence of a vessel.",
  }));
}).listen(PORT, "127.0.0.1", () => console.log(`AIS relay on http://127.0.0.1:${PORT}/`));
