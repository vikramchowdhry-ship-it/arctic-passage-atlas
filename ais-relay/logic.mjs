/* Pure logic for the AIS relay: turn raw AISStream messages into an anonymous list of positions.
 *
 * What leaves the relay: position (rounded to ~100 m), speed, course, an age in seconds and a broad ship class.
 * What never leaves it: MMSI, vessel name, call sign, IMO, destination, dimensions. Military, law-enforcement
 * and search-and-rescue vessels are dropped. This is context for a public page, not a tracking service.
 */

/* Search boxes as AISStream wants them: [[lat, lon], [lat, lon]] corners. Arctic and the approaches to it. */
export const BOXES = [
  [[62, -30], [82, 70]],      // Greenland Sea, Norwegian Sea, Barents Sea, Svalbard
  [[66, 70], [82, 160]],      // Kara, Laptev and East Siberian seas (Northern Sea Route)
  [[50, 160], [75, 180]],     // Bering Sea and Chukchi Sea, western side of the antimeridian
  [[50, -180], [75, -140]],   // Bering Sea, Chukchi Sea and Beaufort Sea, eastern side
  [[50, -140], [84, -50]],    // Canadian Arctic, Baffin Bay, Hudson Bay, Labrador Sea, Great Slave and Great Bear lakes
  [[59, 28], [63, 40]]        // Lake Ladoga and Lake Onega
];

export const MESSAGE_TYPES = ["PositionReport", "StandardClassBPositionReport", "ShipStaticData"];

/* AIS ship-type code to a public class. null means "do not publish". */
export function classify(code) {
  const c = Number(code);
  if (!Number.isFinite(c) || c <= 0) return "unknown";
  if (c === 35 || c === 55 || c === 51) return null;          // military, law enforcement, search and rescue
  if (c === 30) return "fishing";
  if (c === 31 || c === 32 || c === 52 || c === 53 || c === 50 || (c >= 33 && c <= 34)) return "service";
  if (c === 36 || c === 37) return "pleasure";
  if (c >= 60 && c <= 69) return "passenger";
  if (c >= 70 && c <= 79) return "cargo";
  if (c >= 80 && c <= 89) return "tanker";
  return "other";
}

const round3 = (v) => Math.round(v * 1000) / 1000;

/* messages: parsed AISStream objects collected over a short window. now: ms since the epoch. */
export function reduce(messages, now = Date.now(), known = new Map()) {
  const types = known;       // MMSI -> ship type code, from ShipStaticData; callers may keep this map between calls
  const last = new Map();    // MMSI -> latest position report
  for (const m of messages) {
    if (!m || !m.Message || !m.MetaData) continue;
    const id = m.MetaData.MMSI;
    if (id === undefined || id === null) continue;
    if (m.MessageType === "ShipStaticData") {
      const t = m.Message.ShipStaticData && m.Message.ShipStaticData.Type;
      if (t !== undefined) types.set(id, t);
      continue;
    }
    const body = m.Message.PositionReport || m.Message.StandardClassBPositionReport || m.Message.ExtendedClassBPositionReport;
    if (!body || body.Valid === false) continue;
    const lat = body.Latitude !== undefined ? body.Latitude : m.MetaData.Latitude;
    const lon = body.Longitude !== undefined ? body.Longitude : m.MetaData.Longitude;
    if (!Number.isFinite(lat) || !Number.isFinite(lon) || Math.abs(lat) > 90 || Math.abs(lon) > 180) continue;
    if (lat === 91 || lon === 181) continue;                  // AIS "not available" values
    const seen = m.MetaData.time_utc ? Date.parse(String(m.MetaData.time_utc).replace(" +0000 UTC", "Z").replace(" ", "T")) : now;
    last.set(id, { lat, lon, sog: body.Sog, cog: body.Cog, seen: Number.isFinite(seen) ? seen : now });
  }
  const out = [];
  for (const [id, p] of last) {
    const cls = classify(types.get(id));
    if (cls === null) continue;
    out.push({
      lat: round3(p.lat), lon: round3(p.lon),
      sog: p.sog === undefined || p.sog >= 102.3 ? null : Math.round(p.sog * 10) / 10,
      cog: p.cog === undefined || p.cog >= 360 ? null : Math.round(p.cog),
      cls, age_s: Math.max(0, Math.round((now - p.seen) / 1000)),
    });
  }
  return out;
}

export function summarise(list) {
  const counts = {};
  for (const v of list) counts[v.cls] = (counts[v.cls] || 0) + 1;
  return counts;
}
