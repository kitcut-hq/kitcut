#!/usr/bin/env node
// The lock on the studio's GitHub hook, studio.kitcut.ai/hooks/github (server.py github_hook,
// studio/deploy/README.md "A push to GitHub ships itself"). One Cloudflare firewall rule on the
// zone: a request for any /hooks/ path of that host from an address outside GitHub's published
// webhook ranges (api.github.com/meta, "hooks") is blocked at Cloudflare and never reaches the
// machine. Behind it the server still checks GitHub's signature on every request, and what gets
// through only tells the machine to look at GitHub now.
//
//   node --env-file=<file with CLOUDFLARE_API_TOKEN> studio/deploy/hook-lock.mjs --check
//   node --env-file=<...> studio/deploy/hook-lock.mjs           make it, or put it back
//
// --check reads the rule and GitHub's ranges and changes nothing; it says when GitHub has changed
// its ranges since the rule was made (GitHub says it rarely does; until the rule is made again
// such a hook is blocked, and the 15-minute poll still ships the push). The rule matches
// "/hooks" anywhere in the path, in any case, so no spelling of it slips past.
const HOST = process.env.KITCUT_STUDIO_HOST || "studio.kitcut.ai";
const ZONE = HOST.split(".").slice(-2).join(".");
const LABEL = `KitCut: ${HOST}/hooks/ only from GitHub's hook addresses (studio/deploy/hook-lock.mjs)`;
const PHASE = "http_request_firewall_custom";
const check = process.argv.includes("--check");
const token = process.env.CLOUDFLARE_API_TOKEN;
const api = "https://api.cloudflare.com/client/v4";

const die = (msg) => {
  console.error(`hook-lock: ${msg}`);
  process.exit(1);
};
if (!token) die("CLOUDFLARE_API_TOKEN is not set (start with node --env-file=...)");

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

// GitHub's webhook source addresses, IPv4 and IPv6, as published
const meta = await (await fetch("https://api.github.com/meta", { headers: { "User-Agent": "kitcut-hook-lock" } })).json();
const ranges = [...(meta.hooks || [])].sort();
if (!ranges.length) die("api.github.com/meta lists no hook ranges");
const expression =
  `(http.host eq "${HOST}" and lower(http.request.uri.path) contains "/hooks"` +
  ` and not ip.src in {${ranges.join(" ")}})`;

const zone = (await call("GET", `/zones?name=${ZONE}`))[0] || die(`zone ${ZONE} is not visible to this token`);
const rulesets = await call("GET", `/zones/${zone.id}/rulesets`);
let entry = rulesets.find((r) => r.phase === PHASE && r.kind === "zone");
let rules = entry ? (await call("GET", `/zones/${zone.id}/rulesets/${entry.id}`)).rules || [] : [];
let ours = rules.find((r) => r.description === LABEL);

if (!check) {
  const want = { description: LABEL, expression, action: "block", enabled: true };
  if (!entry) {
    entry = await call("PUT", `/zones/${zone.id}/rulesets/phases/${PHASE}/entrypoint`, { rules: [want] });
    console.log("made the rule (the zone had no firewall rules)");
  } else if (!ours) {
    // first in the list: an earlier rule that skips or allows must not decide for this path
    await call("POST", `/zones/${zone.id}/rulesets/${entry.id}/rules`, { ...want, position: { index: 1 } });
    console.log("made the rule, first in the list");
  } else if (ours.expression !== expression || ours.action !== "block" || ours.enabled === false) {
    await call("PATCH", `/zones/${zone.id}/rulesets/${entry.id}/rules/${ours.id}`, want);
    console.log("put the rule back as it should be (GitHub's ranges as published today)");
  } else {
    console.log("the rule is as it should be");
  }
  rules = (await call("GET", `/zones/${zone.id}/rulesets/${entry.id}`)).rules || [];
  ours = rules.find((r) => r.description === LABEL);
}

const at = ours ? rules.indexOf(ours) + 1 : 0;
console.log(`GitHub's hook ranges: ${ranges.length} (${ranges.join(", ")})`);
console.log(`firewall rules on ${ZONE}: ${rules.length}`);
const ahead = ours ? rules.slice(0, at - 1).filter((r) => r.action !== "block" && r.enabled !== false) : [];
if (ahead.length) console.log(`RULES AHEAD OF IT that do not block (check they cannot let ${HOST}/hooks through): ${ahead.length}`);
const good = ours && ours.action === "block" && ours.enabled !== false;
const current = good && ours.expression === expression;
console.log(
  !ours ? "the lock: none" :
  `the lock: rule ${at} of ${rules.length}, ${ours.action}, ${ours.enabled === false ? "OFF" : "on"}` +
    (current ? ", GitHub's ranges as published today" : ", STALE: GitHub's ranges changed -- run without --check"),
);
process.exit(good && current ? 0 : 1);
