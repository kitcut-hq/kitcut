# Shorts as the whole business: market research and go-to-market

**Written** 2026-09-01, from a research session. **Status:** research + recommendation.
Nothing here is built. This document answers one question that
`docs/product-strategy.md` §6 dismissed in a single line — *"a shorts web SaaS:
entrant #40, rejected"* — and asks whether the rejection survives a different
premise: **not a web SaaS. A local-first, privacy-first, prompt-driven shorts
tool with a non-linear workflow and real control over the result.**

Read `docs/product-strategy.md` first; this is a focused re-examination of one
branch of it, not a replacement. Where the two disagree, the disagreement is
marked.

---

## The one-page version

The rejection survives, but not for the reason it was written. Shorts is not a
bad market because it is crowded; it is a bad *primary* market because **the four
things we would position on are each either not a purchase driver, already free,
or already shipped by the incumbent.**

- **Local-first** is real, but the version creators feel is not privacy — it is
  the **upload tax** (a 6-hour VOD is 10–15 GB and 15–30 minutes of uplink before
  any tool starts). That is a convenience argument, and it only wins on machines
  strong enough that local compute is not *slower* than a cloud GPU. Which is the
  same beachhead the multicam thesis already picked.
- **Privacy-first** is a purchase driver for studios, health, legal and
  pre-release corporate footage — buyers who do not shop for a $19/mo clip app —
  and is worth roughly nothing to the volume segment (creators). Every "creators
  worry about upload privacy" search returns surveillance-analytics vendors,
  not creator complaints. That absence is the finding.
- **Non-linear workflow** is the strongest of the four and the only one nobody
  sells. But it has to be made concrete or it is a slogan: *the deliverable is an
  editable decision record, not an mp4; change one boundary and one clip
  re-renders in seconds; hand the decision list to a real NLE.* Recut sells
  exactly this posture (find the cuts, **export the timeline, do not own the
  edit**) for $99–129 one-time and has for years.
- **More control** is a real, documented complaint about Opus Clip — and "control"
  is what every competitor's marketing already claims. It only converts money when
  sold to somebody **accountable for the output** (an agency owing a client two
  revision rounds), not to a creator who will just try the next free tool.
- **Prompting the app is not differentiation at all.** Opus ships ClipAnything
  (plain-language "find every time we mention pricing") plus Agent Opus; Descript
  ships Underlord as a conversational sidebar. Being able to ask for clips in
  words was the 2024 wedge. It closed.

And the floor under the price is now zero with our own slogan on it:
**OpenShorts** — MIT, 3.8k stars, 998 forks, self-host free, ships an **MCP
server so Claude/ChatGPT/Cursor can drive it**, cloud from $12/mo — plus
**AutoClip**, MIT, "open-source, local-first AI video clipper… fully offline with
Whisper + Ollama, only transcript text ever leaves the machine." Above that floor
sit free bundles: YouTube's own *Edit into a Short*, CapCut desktop (3-hour /
10 GB inputs, subject tracking, 20+ caption languages, free), Descript, Adobe.
Above *those* sit two funded incumbents at roughly $10M and $8M ARR.

**Recommendation: do not make shorts the business. Keep it as the free wedge
exactly as `product-strategy.md` planned — but spend the effort on the three
things that make the wedge convert into the paid product, all of which are also
what "control" and "non-linear" actually mean in a buyable form:**

1. **Timeline export** (FCPXML / EDL / OTIO) from the clip plan — already a
   frame-exact cut list, so it is serialization, not research.
2. **The manifest as the product surface** — the durable, diffable, re-runnable
   decision record, with per-clip incremental re-render (already true in
   `cut-clips.py`; nobody has been told).
3. **An MCP server** in front of the scripts, so the tool is agent-native
   everywhere rather than Claude-Code-only. OpenShorts shipping one at 3.8k stars
   says this is table stakes within a year, not a differentiator.

If shorts-only is pursued anyway against this recommendation, §7 gives the honest
version: one ICP (clip factories — agencies and podcast networks), $49–99 per
seat per month, sold direct, never through the paid-acquisition war. Realistic
ceiling ~$250–500k ARR. §10 is the two-week test that would prove or kill it
before any building.

---

## 1. The market, in numbers

| fact | figure | source / confidence |
|---|---|---|
| OpusClip users / output | 10M+ users, 172M clips | vendor-reported; **medium** |
| OpusClip revenue | ~$10.3M est. ARR (2025) | Latka estimate; **low-medium** |
| OpusClip funding | $30M announced round; ~$50M total incl. SoftBank Vision Fund 2 at ~$215M valuation; one tracker says $79.25M total | trackers disagree; **low-medium** |
| Submagic | ~$8M ARR (mid-2025), **bootstrapped**, ~13 people, 4M+ users | Latka; **low-medium** |
| Entry pricing | Opus $15–19/mo · Submagic $14–60/mo · Vizard $29 · Klap $29 · Quso $24–40 | vendor pages via comparisons, verified Jul 2026; **medium** |
| Effective unit price | **$0.03–0.10 per source minute** | comparison sites; **medium** |
| Category size | AI video generation+editing $3.67B (2026) → $24.89B (2036), 21.4% CAGR; classical video-editing software $3.75B → $4.99B by 2031 | analyst reports; **low** (scope varies wildly) |
| Clipping *agencies* | retainers $1,250–$25,000/mo, most B2B $3–8k/mo for 16–40 clips; per-clip $5–800; one agency bills $0.003/qualified view | agency pricing guides; **medium** |
| Twitch reality | 6-hour VOD = 10–15 GB; 15–30 min to download before editing; manual clipping ≈ 45 min per 30-second clip | tool blogs; **medium** |
| Self-host penalty | OpenShorts: ~50 s on their cloud GPU vs **5–8 min self-hosted** for the same job | vendor README; **medium** |

**The number that matters most is the one nobody publishes: the category is
small.** Two visible leaders at ~$10M and ~$8M ARR, and a long tail of dozens of
$29/mo tools. Call the whole clipping-SaaS category $50–100M ARR in 2026 — less
than a rounding error against the "AI video" TAM headlines, split forty ways,
with the leader carrying tens of millions of venture dollars to spend on
acquisition. Any plan that quotes the $3.67B TAM as its opportunity is quoting
the wrong number; the addressable line item is "what people pay for clipping,"
and that is two orders of magnitude smaller.

## 2. The commodity floor — this is the decisive finding

The proposed positioning already exists, free, with the same words:

- **OpenShorts** (MIT, 3.8k★, 998 forks): "turns long videos into viral 9:16
  shorts with AI moment detection, face tracking, subtitles and dubbing. Self-host
  free with Docker, or use the cloud with GPU speed from $12/mo. **MCP server and
  API for AI agents.**" Runs fully local against Ollama/LM Studio/vLLM. It states
  the trade honestly: self-hosting "costs you a machine, your own API keys and the
  time to keep it running."
- **AutoClip** (MIT, 102★): "Open-source, **local-first** AI video clipper…
  **fully offline** with Whisper + Ollama, or bring your own API key… **only
  transcript text is ever sent to a provider — never video or audio.**"
- **AI-Youtube-Shorts-Generator**: explicit "open-source alternative to Opus Clip,
  Vidyo.ai, Klap & SubMagic… free, no watermarks, no per-clip credits."

This does not mean the market is closed. It means **"local + private + no
credits" is no longer a *reason to pay*.** It is now the free tier's pitch, and
our version of it would be technically better and commercially indistinguishable.
Whatever we charge for has to be something an MIT repo with 3.8k stars does not
already do.

The free floor is thicker still because the platforms bundle:

- **YouTube itself** — *Edit into a Short* inside Creator Studio, free, for the
  simplest case (own public long-form, up to 60 s).
- **CapCut desktop** — free, offline-capable, 3-hour / 10 GB inputs, AI long-to-
  shorts, auto subject tracking, 20+ caption languages. This is also the *local*
  competitor most creators already have installed, and it is ByteDance-funded.
- **Descript Underlord** — conversational clip generation inside the editor
  creators already pay for.

## 3. Scoring the four pillars honestly

### Local-first — real, but rename it

The privacy framing is the weak half. The strong half is physics: **the file is
already on the disk.** A 6-hour VOD is 10–15 GB; the upload is 15–30 minutes
before a cloud tool begins, and it repeats on every re-do. Local also means no
per-minute meter, no 1080p-gated tier, no clip expiry (a documented Opus
complaint), and no 4K downscale.

The counter-evidence must be stated: **local is slower where the machine is
weak** — OpenShorts' own numbers are 50 s cloud vs 5–8 min self-hosted — and a
large share of creators edit on laptops. So local-first only wins for people with
a real rig and huge source files. That is: streamers, podcast studios, editors,
agencies. **It is the same audience `product-strategy.md` §2 already chose**,
which is a point in favour of that document, not this one.

### Privacy-first — right, wrong buyer

Where footage is legally constrained the demand is genuine and documented:
studios increasingly require on-prem or local processing for pre-release content
under NDA; healthcare video under HIPAA is cleanest when nothing leaves the
covered entity; GDPR cross-border questions disappear when raw video never moves.
Our own devrel/pre-release-demo case is the same shape.

Two problems for a shorts business:

1. **Those buyers do not buy clip apps.** They buy a security review, an invoice,
   a site licence and a name to call. That is a 3–9 month enterprise motion for a
   product whose category price is $19/mo.
2. **In the creator segment privacy is not a felt pain at all.** It does not
   appear in the complaint literature; what appears is quality, control, credits
   and expiry. Selling privacy there is selling a vitamin to someone with a
   headache.

**Keep privacy as a trust *qualifier* — "footage never leaves your machine,
here is the proof" — never as the lede.** It removes an objection; it does not
create a purchase.

### Non-linear workflow — the one genuinely unclaimed position

Every SaaS in this category is linear: upload → the AI decides → you get ten
ranked candidates → light edits in a web editor → export mp4. Re-deciding means
re-running and re-spending, and the reasoning is gone.

This repo is already the other thing, and has been by accident:

- The edit is a **manifest** — a diffable JSON of quoted-speech boundaries
  (`start_text` / `end_before_text`), not timecodes, so it survives a re-cut of
  the source.
- `--list` **prices the decision before any encode**.
- `cut-clips.py` **skips existing outputs**, so changing one entry re-renders one
  clip.
- Every output writes a **sidecar** recording exact boundaries and encoder
  settings; `project.json` records what is burned onto which render and which key
  controls it.

That is a non-linear editing model with an audit trail, and none of it is
marketed because none of it was built to be sold. Made explicit it becomes three
sellable claims: **"nothing renders unproven," "change one line, rebuild one
clip," "the edit is a file you own — including as a timeline in your NLE."**

**Precedent that this is monetizable:** Recut ($99–129 one-time, Mac+Windows)
finds the cuts and **exports XML to Premiere / Resolve / FCP / ScreenFlow /
CapCut** rather than owning the edit. AutoPod does the equivalent inside Premiere
on subscription. Both make money from professionals precisely by *handing the
timeline back*.

### More control — real complaint, but qualify the buyer

Documented: Opus Clip's built-in editor "frustrates users who need to do anything
beyond the AI's defaults," with the one-click promise collapsing on custom
branding and fine-grained captions; independent testing frames it as *"where the
AI wins and the 40% you'll discard"*; third-party reports on the claimed 80–90%
time saving are mixed, with cleanup sometimes cancelling the benefit.

But control is what everyone's landing page already promises, and creators
respond to disappointment by switching to the next free tool, not by paying more.
**Control converts to revenue only for someone who owes a deliverable**: an
agency with two contracted revision rounds per clip, an editor whose name is on
it, a brand team that cannot ship an off-brand caption. Same conclusion as the
other three pillars — the positioning is fine, the *creator* segment is not.

### Prompting — closed

Opus **ClipAnything** takes plain-language prompts across visual, audio and
sentiment cues ("find every time we mention pricing"); **Agent Opus** automates
end-to-end; Descript's **Underlord** is a chat sidebar over the timeline.
"Prompt the app to make shorts" is 2026 table stakes. Our version is better in
kind (a general agent that can also *write new tooling* mid-session, against a
scripts SDK) — but that superiority is invisible on a landing page and is
indistinguishable from theirs in a 30-second trial.

## 4. What is left that is actually ours

Filtering everything above, four assets survive contact with this market — and
only the first two are shorts-related:

1. **The decision record + incremental re-render** (§3, non-linear). Unclaimed.
2. **Boundaries as quoted speech.** "End before he says *'the next thing'*" is a
   better interface than a scrubber *and* a better prompt target, and it degrades
   gracefully — a re-transcribed source still resolves.
3. **The verification discipline** — `--list`, `--frame`, duration assertions, the
   review sheet before render, the render-gate that reads the render. In a
   category whose top complaint is "40% of output is discardable," *proving the
   output before spending the encode* is the only credible answer.
4. **The benchmark** — frame-scored reproduction of professionally edited films.
   Nobody in the clipping category has anything like it. It is worth more as
   marketing for the multicam product than for shorts.

## 5. Who would pay, scored

| ICP | pain we solve | pays? | verdict |
|---|---|---|---|
| **Solo creators / podcasters** | none we uniquely solve; $19/mo is not their problem | $15–30/mo, churny | **No.** The volume segment, the free floor, the acquisition war. |
| **Streamers (Twitch/Kick)** | genuine: 10–15 GB VODs, 15–30 min uploads, per-minute meters on 8-hour sources | $20–50/mo | **Maybe.** Best fit for the *upload-tax* argument; served by Eklipse/ClipMe already; price-sensitive. |
| **Clip factories — agencies, podcast networks, social teams** | volume, brand consistency, contracted revisions, per-seat SaaS cost, client footage under NDA | retainers $3–8k/mo today; tooling budget is a rounding error inside it | **Yes — the only credible one.** Accountable for output, owns rigs, buys tools as a habit, findable and countable. |
| **Regulated / pre-release (studio, health, legal, enterprise comms)** | footage legally cannot leave | $2–10k/yr site licence | **Later.** Real budget, wrong sales motion for a first product; reachable via the agencies who serve them. |

The clip-factory read matches `product-strategy.md` §2's editor thesis rather
than contradicting it — same people, same rigs, same buying habit. Which is the
tell: **shorts is a feature of that product, not a competitor to it.**

## 6. So: keep shorts as the wedge, and sharpen it

The build list that follows is small because most of it exists. It is worth doing
whether or not shorts is ever the business, because every item also serves the
paid multicam/editor SKU.

1. **Timeline export** — `clip-plan → FCPXML / EDL / OTIO`. Frame-exact cut lists
   already exist; this is serialization. It is `product-strategy.md` build-list
   item 11, and this research raises its priority: it *is* the "control" pitch,
   it is what Recut and AutoPod monetize, and it defuses the replacement reflex.
2. **`--plan` output as a human artifact** — the review sheet pattern from
   pipeline 7 applied to shorts: candidate clips, boundaries as quoted speech,
   duration, why chosen, one contact-sheet frame each, *before* any encode.
   This is the answer to "40% of the output is discardable."
3. **MCP server** over `transcript-outline` / `auto-reframe` / `cut-clips` so any
   agent — Claude Desktop, Cursor, ChatGPT — can drive it, not only Claude Code
   in this folder. OpenShorts shipping one at 3.8k stars makes this table stakes.
4. **Batch + brand kit** for the clip-factory ICP: one manifest, N episodes, a
   committed brand config (caption preset, handle badge, card brand) so a whole
   client renders consistently and re-renders on a brand change.
5. **`--no-network` proof mode** — a flag that refuses any outbound call and
   prints what it did *not* do, for the NDA conversation. Cheap; it converts the
   privacy claim from a promise into a receipt.

Explicitly **not** worth building for this market: virality scoring (unfalsifiable
and everyone has it), a web editor (deletes the differentiation, per §6 of the
strategy doc), social scheduling/publishing (Submagic, Quso and Opus own it and it
is pure integration maintenance).

**Legal note on "paste a YouTube link."** Opus-style link import is convenient and
is the shape users expect, but YouTube's ToS prohibits downloading, and
enforcement historically targets *services that facilitate it commercially*. The
safe shape, which local-first gives us for free: `yt-dlp` runs **on the user's
machine**, we never host a download endpoint, and the docs scope it to *their own
channel*. Never operate that step server-side, including in the phase-2 cloud.

## 7. If shorts-only is pursued anyway — the honest GTM

**ICP:** clip factories. Agencies, podcast networks, and in-house social teams
producing 40+ clips/month from long-form, on Windows/NVIDIA rigs, with clients
who ask for changes.

**Positioning line** (note that none of the four proposed pillars is the lede):

> *Every clip is a decision you can read, change and re-render — in seconds, on
> your own machine, without re-uploading 15 GB or re-spending a credit. Hand the
> result to your NLE or ship it finished.*

Privacy is the second bullet, not the first. Local is stated as speed and cost
before it is stated as privacy.

**Pricing.** Not $19/mo — that price implies the incumbent's product.
$49–99/seat/month or $499–999/year, with a perpetual fallback (cancel and keep
what you have; `product-strategy.md` §5 explains why local licensing cannot be
enforced and should not be attempted). A site licence at $2–10k/yr for the
regulated buyer, where the deliverable includes the `--no-network` receipt.
COGS ≈ 0: their GPU, their footage, their Claude subscription.

**Channels, ranked, with the reason:**

1. **Direct to agencies.** They are countable (retainer guides list them), they
   already spend $3–8k/mo on labour, and a tool that raises throughput at a fixed
   day rate is an obvious margin buy. Ten conversations beat ten thousand
   impressions here.
2. **Open-core distribution.** Ship the local core free and public — that is the
   only way to compete with a free floor rather than pretend it is not there — and
   sell the pro pack (timeline export, batch, brand kits, gotcha library, support,
   the update stream). GPL-economy precedent in §5 of the strategy doc.
3. **Craft receipts.** The benchmark write-up and the debug-overlay video — an
   editor that explains every cut on screen — are the only marketing this audience
   respects, and both already exist as capabilities.
4. **Agent-native marketplaces** — Claude Code plugin marketplace, MCP directories.
   Cheap category ownership while it is early; a channel, never a moat.
5. **Dogfooding channel.** Our own shorts, made by the tool, with the line saying
   so.

**The anti-channel, stated so nobody drifts into it:** the paid-acquisition war —
YouTube sponsorships, affiliate stacks, comparison-SEO farms. Opus raised tens of
millions to fund exactly that; the entire "best Opus Clip alternative" search
results page is that war. We cannot win it and should not fund a single month of
it.

**Bottom-up sizing, stated with its assumptions.** Assume ~2,000 identifiable
clipping/repurposing agencies and heavy in-house teams in the English-speaking
market (order-of-magnitude, from the density of agencies in the pricing guides —
this is the weakest number here). Win 10% over three years at 2 seats and
$800/seat/year → **~$250–500k ARR**. That is a good outcome for one or two
people and a bad one for anything venture-shaped. It is also roughly the same
revenue the editor SKU in `product-strategy.md` targets, with a worse story —
which is the argument for merging them rather than choosing.

## 8. What changes in `product-strategy.md` if this is adopted

Nothing structural. Three amendments:

- **§6 "rejected: a shorts web SaaS"** — keep the rejection, add the reason
  discovered here: the local/private/no-credits pitch is already free and MIT
  (OpenShorts, AutoClip), so the differentiation has to be the decision record
  and the timeline hand-off, not the deployment model.
- **§4 SKUs** — the free tier stays captions + shorts, and gains its real job:
  it is the **acquisition surface and the proof of the verification discipline**,
  not just a taste of the paid product. Add the review sheet to it.
- **Build list** — promote item 11 (timeline export) to the top three, and add an
  MCP server as item 17.

## 9. Risks specific to this branch

- **Free floor rises.** OpenShorts and its peers improve weekly; anything we
  charge for that they can copy in a month is not pricing power. Only the gotcha
  library, the benchmark and the support stream resist that.
- **Platform bundling.** YouTube, CapCut, Descript and Adobe all ship shorts
  generation inside products creators already have. Feature-level competition
  here is a losing posture; workflow-level (decision record, NLE hand-off) is not.
- **Two-sided attention split.** Building the shorts business and the editor
  business are the same engineering but *different* marketing, sales and support
  motions. Doing both badly is the default failure.
- **The privacy pitch invites an enterprise sales motion we cannot staff.**
  Answer inbound; do not go build for it.
- **"Local" ages badly on weak machines.** If the ICP drifts toward laptop
  creators, the physics inverts and the pitch becomes false.

## 10. The test, before building anything

Two weeks, no code. Kill criteria stated up front so the result is falsifiable.

1. **Ten clip-factory conversations.** Screening: *do you pay for a clipping tool
   today, and what do you do when a client asks for a change to a clip you already
   delivered?* **Listen for:** re-uploading, re-spending credits, redoing captions,
   "we just cut it by hand in Premiere." **Kill if:** fewer than four describe
   re-work pain, or the tool bill is invisible to them.
2. **Price probe.** Offer a $499/yr founding licence with timeline export and
   batch, before either exists. **Kill if:** fewer than three of ten agencies will
   take a paid pilot at ≥$400/yr — the willingness-to-pay premium over the $19/mo
   anchor is the whole thesis.
3. **The receipt post.** Publish one artefact — the review sheet plus a clip whose
   every boundary is a quoted line, next to the same source through Opus — to
   r/editors, r/podcasting and the editing Discords. **Kill if:** the response is
   "so it's Opus Clip but I have to install Python."
4. **A discipline check on ourselves.** Run three of our own long videos through
   the existing shorts pipeline end to end and count what fraction of output is
   shippable without a hand pass. If our own discard rate is near the 40% the
   incumbents are criticised for, the differentiation is a claim we cannot make
   yet, and that is worth knowing before a landing page says it.

Green on 1+2 → build §6's five items and sell to agencies, with shorts as the
front door of the editor product rather than a separate company. Red on either →
`product-strategy.md` stands unchanged, and shorts stays the free wedge it was
always planned to be.

## Verify before relying

Revenue figures for OpusClip (~$10.3M) and Submagic (~$8M) are third-party
estimates (Latka), not filings; funding totals disagree across trackers ($30M
announced, ~$50M with SoftBank, $79.25M per one tracker). Pricing was verified by
comparison sites in July 2026 and moves often — re-check on vendor pages before
any of it goes on a deck. Star counts (OpenShorts 3.8k, AutoClip 102) are
2026-09-01 snapshots and are the fastest-moving numbers in this document. The
2,000-agency figure in §7 is an order-of-magnitude assumption, not a measurement,
and the sizing is only as good as it is. Category-size analyst figures vary by
5x depending on scope and should never be quoted as our addressable market.

**Sources:** OpusClip company profiles (Latka, Sacra, PitchBook, Tracxn) and
blog; Submagic profiles and pricing pages; Ssemble / ngram / Choppity comparison
round-ups (Jul 2026); GitHub — `mutonby/openshorts`, `artbyjazi/autoclip`,
`Anil-matcha/AI-Youtube-Shorts-Generator`; getrecut.com; screen.studio pricing
coverage; YouTube Help *Create Shorts from your videos*; capcut.com long-video-to-
shorts pages; descript.com/underlord; FORKOFF and Clipping Culture agency pricing
guides; Eklipse/ClipMe/Ssemble Twitch-VOD workflow guides; Meticulous Research and
Mordor Intelligence market reports; BIGVU *Opus Clip Tested 2026*; yt-dlp legal
explainers; on-prem video-AI compliance guides (Camlytics, SecureRedact,
iFactory).
