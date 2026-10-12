#!/usr/bin/env node
// The lock on ssh.kitcut.ai, the address a Claude cloud session reaches the studio VM through
// (studio/deploy/README.md, "SSH for Claude cloud sessions"). It is one Cloudflare firewall rule
// on the zone: a request for that host that does not carry the secret header is blocked at
// Cloudflare, before it ever reaches the VM. Behind it sshd still takes keys only.
//
//   node --env-file=<file with CLOUDFLARE_API_TOKEN> studio/deploy/ssh-lock.mjs --check
//   node --env-file=<...> studio/deploy/ssh-lock.mjs --out <private dir>
//   node --env-file=<...> studio/deploy/ssh-lock.mjs --probe --out <private dir>
//
// --check reads the rule and changes nothing. --out makes it (or puts it back as it should be):
// the secret is generated here, written to <private dir>/gate.env and never printed; an existing
// gate.env is reused, so running it again keeps every session's setup script valid. --probe asks
// the address twice, without the header and with it, and fails unless the first is blocked and
// the second is not: run it after the tunnel is up and BEFORE the tunnel points at sshd
// (ssh-tunnel.sh closed, then up).
//
// Why a firewall rule and not Cloudflare Access with a service token: Access needs a token with
// Zero Trust permissions, and ours answers 403 there. The rule needs only "Zone WAF: Edit".
import { randomBytes } from "node:crypto";
import { existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";

const HOST = process.env.KITCUT_SSH_HOST || "ssh.kitcut.ai";
const ZONE = HOST.split(".").slice(-2).join(".");
const HEADER = "x-kitcut-gate";
const LABEL = `KitCut: ${HOST} only with the gate header (studio/deploy/ssh-lock.mjs)`;
const PHASE = "http_request_firewall_custom";
const args = process.argv.slice(2);
const flag = (name) => args.includes(name);
const outDir = flag("--out") ? args[args.indexOf("--out") + 1] : null;
const token = process.env.CLOUDFLARE_API_TOKEN;
const api = "https://api.cloudflare.com/client/v4";

const die = (msg) => {
  console.error(`ssh-lock: ${msg}`);
  process.exit(1);
};
if (!token) die("CLOUDFLARE_API_TOKEN is not set (start with node --env-file=...)");
if (!flag("--check") && !outDir) die("say --check, or --out <private dir> where the secret is kept");

async function call(method, path, body) {
  const r = await fetch(api + path, {
    method,
    headers: { Authorization: `Bearer ${token}`, "Content-Type": "application/json" },
    body: body ? JSON.stringify(body) : undefined,
  });
  const b = await r.json().catch(() => ({}));
  if (b.success !== true) {
    const why = (b.errors || []).map((e) => `${e.code} ${e.message}`).join("; ");
    die(`${method} ${path.replace(/[0-9a-f]{32}/g, "<id>")}: ${r.status} ${why || "no reason given"}`);
  }
  return b.result;
}

const gateFile = outDir ? join(outDir, "gate.env") : null;
function secret({ make }) {
  if (existsSync(gateFile)) {
    const m = readFileSync(gateFile, "utf8").match(/^KITCUT_SSH_GATE=(\S+)$/m);
    if (m) return m[1];
  }
  if (!make) die(`${gateFile} holds no secret: make the lock first (--out without --probe)`);
  const s = randomBytes(32).toString("base64url");
  mkdirSync(outDir, { recursive: true });
  writeFileSync(
    gateFile,
    `# The secret ${HOST} asks for, in the request header "${HEADER}" (studio/deploy/ssh-lock.mjs).\n` +
      `# Cloudflare blocks every request for that host without it.\nKITCUT_SSH_GATE=${s}\n`,
    { mode: 0o600 },
  );
  return s;
}
const expression = (s) =>
  `(http.host eq "${HOST}" and not any(http.request.headers["${HEADER}"][*] eq "${s}"))`;

if (flag("--probe")) {
  const s = secret({ make: false });
  const ask = async (headers) => (await fetch(`https://${HOST}/`, { headers, redirect: "manual" })).status;
  const without = await ask({});
  const withIt = await ask({ [HEADER]: s });
  console.log(`without the header: ${without}   with it: ${withIt}`);
  const ok = without === 403 && withIt !== 403;
  console.log(ok ? "locked: only the header gets through" : "NOT locked as expected");
  process.exit(ok ? 0 : 1);
}

const zone = (await call("GET", `/zones?name=${ZONE}`))[0] || die(`zone ${ZONE} is not visible to this token`);
const rulesets = await call("GET", `/zones/${zone.id}/rulesets`);
let entry = rulesets.find((r) => r.phase === PHASE && r.kind === "zone");
let rules = entry ? (await call("GET", `/zones/${zone.id}/rulesets/${entry.id}`)).rules || [] : [];
let ours = rules.find((r) => r.description === LABEL);

if (!flag("--check")) {
  const want = { description: LABEL, expression: expression(secret({ make: true })), action: "block", enabled: true };
  if (!entry) {
    entry = await call("PUT", `/zones/${zone.id}/rulesets/phases/${PHASE}/entrypoint`, { rules: [want] });
    console.log("made the rule (the zone had no firewall rules)");
  } else if (!ours) {
    // first in the list: an earlier rule that skips or allows must not get to decide for this host
    await call("POST", `/zones/${zone.id}/rulesets/${entry.id}/rules`, { ...want, position: { index: 1 } });
    console.log("made the rule, first in the list");
  } else if (ours.expression !== want.expression || ours.action !== "block" || ours.enabled === false) {
    await call("PATCH", `/zones/${zone.id}/rulesets/${entry.id}/rules/${ours.id}`, want);
    console.log("put the rule back as it should be");
  }
  rules = (await call("GET", `/zones/${zone.id}/rulesets/${entry.id}`)).rules || [];
  ours = rules.find((r) => r.description === LABEL);
}

// what is there now, read back (descriptions and actions only: our expression holds the secret)
const at = ours ? rules.indexOf(ours) + 1 : 0;
console.log(`firewall rules on ${ZONE}: ${rules.length}`);
for (const [i, r] of rules.entries()) {
  if (r !== ours) console.log(`  ${i + 1}. [${r.action}${r.enabled === false ? ", off" : ""}] ${r.description || "(no name)"}`);
}
const good = ours && ours.action === "block" && ours.enabled !== false;
const ahead = ours ? rules.slice(0, at - 1).filter((r) => r.action !== "block" && r.enabled !== false) : [];
console.log(`the lock: ${ours ? `rule ${at} of ${rules.length}, ${ours.action}, ${ours.enabled === false ? "OFF" : "on"}` : "none"}`);
if (ahead.length) console.log(`RULES AHEAD OF IT that do not block (check they cannot let ${HOST} through): ${ahead.length}`);
console.log(good ? "locked at Cloudflare: the host answers only the gate header" : "NOT locked");
process.exit(good || flag("--check") ? 0 : 1);
