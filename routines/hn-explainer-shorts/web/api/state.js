// GET /api/state  (header x-ideas-key)  ->  { runs: [...] } newest first, picks folded in.
import { isOwner, loadState, send } from "./_lib.js";

export default async function handler(req, res) {
  if (req.method !== "GET") return send(res, 405, { error: "GET only" });
  if (!isOwner(req)) return send(res, 401, { error: "wrong or missing key" });
  try {
    send(res, 200, await loadState());
  } catch (e) {
    send(res, 500, { error: String(e.message || e) });
  }
}
