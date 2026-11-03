// Shared by the API routes: auth, the append-only store, the merged state.
//
// Storage is a public Vercel Blob store used append-only: every write is a NEW file with a random
// suffix (runs/<time>-<rand>.json, events/<time>-<rand>.json), never an overwrite, so a CDN-cached
// read can never be stale. The state is all runs (newest first) with every event folded onto its
// idea. Nothing here is secret; the page and every action need the key.

import { createHmac, timingSafeEqual } from "node:crypto";
import { list, put } from "@vercel/blob";

const MAX_RUNS = 60; // about a month at two runs a day

export function send(res, status, body) {
  res.statusCode = status;
  res.setHeader("content-type", "application/json; charset=utf-8");
  res.setHeader("cache-control", "no-store");
  res.end(JSON.stringify(body));
}

function same(a, b) {
  const x = Buffer.from(String(a || ""));
  const y = Buffer.from(String(b || ""));
  return x.length > 0 && x.length === y.length && timingSafeEqual(x, y);
}

/** The owner's page key: header x-ideas-key. */
export function isOwner(req) {
  return same(req.headers["x-ideas-key"], process.env.IDEAS_KEY);
}

/** The routine's write token: Authorization: Bearer <WRITE_TOKEN>. */
export function isRoutine(req) {
  const h = String(req.headers.authorization || "");
  return same(h.replace(/^Bearer\s+/i, ""), process.env.WRITE_TOKEN);
}

/** A per-pick signature, so the maker run can report on its own pick and nothing else. */
export function pickSig(pickId) {
  return createHmac("sha256", process.env.WRITE_TOKEN || "").update(String(pickId)).digest("hex");
}

export function sigOk(pickId, sig) {
  return same(sig, pickSig(pickId));
}

export async function readBody(req) {
  if (req.body && typeof req.body === "object") return req.body;
  const chunks = [];
  for await (const c of req) chunks.push(c);
  const raw = Buffer.concat(chunks).toString("utf8");
  return raw ? JSON.parse(raw) : {};
}

function stamp() {
  return new Date().toISOString().replace(/[:.]/g, "-");
}

export async function saveRun(run) {
  const body = JSON.stringify(run);
  await put(`runs/${stamp()}.json`, body, {
    access: "public",
    contentType: "application/json",
    addRandomSuffix: true,
  });
}

export async function saveEvent(ev) {
  const body = JSON.stringify({ ...ev, at: new Date().toISOString() });
  await put(`events/${stamp()}.json`, body, {
    access: "public",
    contentType: "application/json",
    addRandomSuffix: true,
  });
}

async function listAll(prefix) {
  const out = [];
  let cursor;
  do {
    const page = await list({ prefix, cursor, limit: 1000 });
    out.push(...page.blobs);
    cursor = page.hasMore ? page.cursor : undefined;
  } while (cursor);
  return out.sort((a, b) => (a.pathname < b.pathname ? 1 : -1)); // newest first
}

async function fetchJson(blob) {
  const r = await fetch(blob.url, { cache: "no-store" });
  return r.ok ? r.json() : null;
}

/** All runs, newest first, each idea carrying its picks and their latest status. */
export async function loadState() {
  const [runBlobs, eventBlobs] = await Promise.all([listAll("runs/"), listAll("events/")]);
  const runs = (await Promise.all(runBlobs.slice(0, MAX_RUNS).map(fetchJson))).filter(Boolean);
  const events = (await Promise.all(eventBlobs.map(fetchJson))).filter(Boolean);
  events.sort((a, b) => (a.at < b.at ? -1 : 1)); // oldest first, so later events win

  const picks = {};
  const skips = {};
  for (const ev of events) {
    if (ev.type === "skip") { skips[`${ev.run_id}|${ev.idea_id}`] = ev.skip; continue; }
    const p = (picks[ev.pick_id] ||= { pick_id: ev.pick_id, history: [] });
    if (ev.type === "picked") Object.assign(p, ev.pick, { state: "picked", picked_at: ev.at });
    if (ev.type === "fired") Object.assign(p, { state: "started", session: ev.session || null });
    if (ev.type === "queued") Object.assign(p, { state: "queued", text: ev.text });
    if (ev.type === "fire_failed") Object.assign(p, { state: "failed", note: ev.note });
    if (ev.type === "status") {
      for (const k of ["state", "note", "film", "youtube", "title"]) if (ev[k]) p[k] = ev[k];
    }
    p.history.push({ at: ev.at, type: ev.type, state: ev.state || null, note: ev.note || null });
    p.updated_at = ev.at;
  }
  // A pick that never reached the maker because it was not connected yet is not a pick.
  for (const [id, p] of Object.entries(picks)) {
    if (p.state === "failed" && /not set yet|not connected/.test(p.note || "")) delete picks[id];
  }
  for (const run of runs) {
    for (const idea of run.ideas || []) {
      idea.picks = Object.values(picks).filter((p) => p.run_id === run.run_id && p.idea_id === idea.id);
      idea.skipped = skips[`${run.run_id}|${idea.id}`] === true;
    }
  }
  for (const p of Object.values(picks)) delete p.text; // the queue's payload is for the maker only
  return { runs, maker_connected: true };
}

/** Picks waiting for the maker: their latest state is still "queued". */
export async function pendingPicks() {
  const eventBlobs = await listAll("events/");
  const events = (await Promise.all(eventBlobs.map(fetchJson))).filter(Boolean);
  events.sort((a, b) => (a.at < b.at ? -1 : 1));
  const last = {};
  for (const ev of events) {
    if (ev.type === "skip") continue;
    last[ev.pick_id] = ev.type === "status" ? { state: ev.state } : ev.type === "queued" ? { state: "queued", text: ev.text, at: ev.at } : { state: ev.type };
  }
  return Object.entries(last).filter(([, v]) => v.state === "queued").map(([pick_id, v]) => ({ pick_id, queued_at: v.at, text: v.text }));
}

export async function findIdea(runId, ideaId) {
  const { runs } = await loadState();
  const run = runs.find((r) => r.run_id === runId);
  const idea = run && (run.ideas || []).find((i) => i.id === ideaId);
  return idea ? { run, idea } : null;
}
