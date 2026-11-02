// GET /api/recent?days=7  (Authorization: Bearer WRITE_TOKEN)
// The scout reads what is already on the page, so it never sends the same story twice.
import { isRoutine, loadState, send } from "./_lib.js";

export default async function handler(req, res) {
  if (!isRoutine(req)) return send(res, 401, { error: "wrong or missing token" });
  const days = Math.min(Number(new URL(req.url, "http://x").searchParams.get("days")) || 7, 30);
  const since = Date.now() - days * 86400000;
  const { runs } = await loadState();
  const topics = [];
  for (const run of runs) {
    if (new Date(run.run_at || run.received_at).getTime() < since) continue;
    for (const i of run.ideas || []) {
      topics.push({ run_at: run.run_at || run.received_at, topic: i.topic, question: i.question || null,
        hn: (i.hn || []).map((h) => h.url), skipped: !!i.skipped, picked: (i.picks || []).map((p) => p.state) });
    }
  }
  send(res, 200, { days, topics });
}
