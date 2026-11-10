// POST /api/runs  (Authorization: Bearer WRITE_TOKEN)  body: one scout run (see ROUTINE.md).
// The scout routine calls this once per run; the page shows the run at the top.
import { isRoutine, readBody, saveRun, send } from "./_lib.js";

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "POST only" });
  if (!isRoutine(req)) return send(res, 401, { error: "wrong or missing token" });
  let run;
  try {
    run = await readBody(req);
  } catch {
    return send(res, 400, { error: "body is not JSON" });
  }
  if (!Array.isArray(run.ideas) || run.ideas.length === 0) {
    return send(res, 400, { error: "ideas[] is required" });
  }
  for (const [i, idea] of run.ideas.entries()) {
    if (!idea.topic || !Array.isArray(idea.angles) || idea.angles.length === 0) {
      return send(res, 400, { error: `ideas[${i}] needs topic and angles[]` });
    }
    idea.id ||= `i${i + 1}`;
    idea.angles.forEach((a, j) => (a.id ||= `a${j + 1}`));
  }
  run.run_id ||= new Date().toISOString();
  run.received_at = new Date().toISOString();
  try {
    await saveRun(run);
  } catch (e) {
    return send(res, 500, { error: String(e.message || e) });
  }
  send(res, 200, { ok: true, run_id: run.run_id, ideas: run.ideas.length });
}
