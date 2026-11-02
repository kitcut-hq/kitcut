// POST /api/skip  (header x-ideas-key)  body: { run_id, idea_id, skip: true | false }
// The owner skips (or brings back) a whole topic; the page greys it out and folds it.
import { isOwner, readBody, saveEvent, send } from "./_lib.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "POST only" });
  if (!isOwner(req)) return send(res, 401, { error: "wrong or missing key" });
  const b = await readBody(req).catch(() => null);
  if (!b || !b.run_id || !b.idea_id) return send(res, 400, { error: "run_id and idea_id are required" });
  await saveEvent({ type: "skip", pick_id: `skip:${b.run_id}:${b.idea_id}`, run_id: b.run_id, idea_id: b.idea_id, skip: b.skip !== false });
  send(res, 200, { ok: true });
}
