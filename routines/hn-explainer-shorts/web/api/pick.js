// POST /api/pick  (header x-ideas-key)
// body: { run_id, idea_id, angle_id | custom_angle, publish (default true), note }
// Records the pick, then fires the maker routine (its API trigger) with the pick as text.
import { randomUUID } from "node:crypto";
import { findIdea, isOwner, pickSig, readBody, saveEvent, send } from "./_lib.js";

const BETA = "experimental-cc-routine-2026-04-01";

export default async function handler(req, res) {
  if (req.method !== "POST") return send(res, 405, { error: "POST only" });
  if (!isOwner(req)) return send(res, 401, { error: "wrong or missing key" });
  const body = await readBody(req).catch(() => null);
  if (!body) return send(res, 400, { error: "body is not JSON" });

  const found = await findIdea(body.run_id, body.idea_id);
  if (!found) return send(res, 404, { error: "no such idea" });
  const { idea } = found;
  const custom = String(body.custom_angle || "").trim();
  const angle = custom
    ? { id: "own", title: custom, format: "owner's own angle", question: custom }
    : (idea.angles || []).find((a) => a.id === body.angle_id);
  if (!angle) return send(res, 400, { error: "pick an angle or write one" });

  const pickId = randomUUID();
  const publish = body.publish !== false;
  const pick = {
    run_id: body.run_id,
    idea_id: idea.id,
    angle_id: angle.id,
    angle_title: angle.title,
    topic: idea.topic,
    publish,
    owner_note: String(body.note || "").slice(0, 2000),
  };
  await saveEvent({ type: "picked", pick_id: pickId, pick });

  const origin = `https://${req.headers["x-forwarded-host"] || req.headers.host}`;
  const text = JSON.stringify(
    {
      what: "The owner picked this idea and angle on their ideas page. Make it.",
      pick_id: pickId,
      publish,
      owner_note: pick.owner_note || null,
      angle,
      idea: { ...idea, picks: undefined },
      status_url: `${origin}/api/status`,
      status_sig: pickSig(pickId),
    },
    null,
    1,
  );

  // Without an API-trigger token the pick waits in the queue; the maker routine collects it
  // (every hour, or at once when started by hand) through kc-local's hn-ideas-pending.
  if (!process.env.FIRE_URL || !process.env.FIRE_TOKEN) {
    await saveEvent({ type: "queued", pick_id: pickId, text });
    return send(res, 200, { ok: true, pick_id: pickId, queued: true });
  }
  try {
    const r = await fetch(process.env.FIRE_URL, {
      method: "POST",
      headers: {
        authorization: `Bearer ${process.env.FIRE_TOKEN}`,
        "anthropic-beta": BETA,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
      },
      body: JSON.stringify({ text }),
    });
    const out = await r.json().catch(() => ({}));
    if (!r.ok) {
      const note = `routine answered ${r.status}: ${JSON.stringify(out).slice(0, 300)}`;
      await saveEvent({ type: "fire_failed", pick_id: pickId, note });
      return send(res, 502, { error: note, pick_id: pickId });
    }
    const session = out.claude_code_session_url || out.session_url || out.url || null;
    await saveEvent({ type: "fired", pick_id: pickId, session });
    send(res, 200, { ok: true, pick_id: pickId, session });
  } catch (e) {
    await saveEvent({ type: "fire_failed", pick_id: pickId, note: String(e.message || e) });
    send(res, 502, { error: String(e.message || e), pick_id: pickId });
  }
}
