// GET /api/pending  (Authorization: Bearer WRITE_TOKEN)
// The owner's picks still waiting for the maker, each with the text it should act on.
import { isRoutine, pendingPicks, send } from "./_lib.js";

export default async function handler(req, res) {
  if (!isRoutine(req)) return send(res, 401, { error: "wrong or missing token" });
  send(res, 200, { pending: await pendingPicks() });
}
