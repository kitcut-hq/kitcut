// POST /api/status  body: { pick_id, sig, state, note, title, film, youtube }
// The maker run reports on its own pick with the per-pick signature it was handed.
// state: researching | dropped | making | published | done | failed
import { readBody, saveEvent, send, sigOk } from "./_lib.js";

const STATES = new Set(["researching", "dropped", "making", "published", "done", "failed"]);

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "POST only" });
  const b = await readBody(req).catch(() => null);
  if (!b || !b.pick_id || !sigOk(b.pick_id, b.sig)) return send(res, 401, { error: "bad pick_id or sig" });
  if (!STATES.has(b.state)) return send(res, 400, { error: `state must be one of ${[...STATES].join(", ")}` });
  const clip = (v, n) => (v ? String(v).slice(0, n) : undefined);
  await saveEvent({
    type: "status",
    pick_id: b.pick_id,
    state: b.state,
    note: clip(b.note, 1500),
    title: clip(b.title, 200),
    film: clip(b.film, 500),
    youtube: clip(b.youtube, 500),
  });
  send(res, 200, { ok: true });
}
