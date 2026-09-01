# books-giveaway -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-31
- 19:05 project created

### Stage 1: assembling the raw session into one film

**The ask.** Ten raw recordings of buying eight children's books for people who
commented under a Threads post, driven by Claude in the browser. Cut the dead
air, fast-forward where nothing is happening, show each of the eight books,
and blur the card number, CVV and phone numbers. Voice-over comes in stage 2.

**The finding that shaped everything: there is no audio.** Six of the seven
Windows captures are digitally silent (`mean_volume: -91.0 dB` AND
`max_volume: -91.0 dB` -- zero samples, not room tone). The seventh has ambient
noise at -56 dB and faster-whisper returned **0 words** from four minutes of
it. So `screencast-cut.py` cannot be used: every silence threshold it has
degenerates. Three new scripts exist because of this -- `screen-activity.py`,
`screen-cut.py`, `scan-pii.py`, tested by `check-screen.py`. See
"A screencast with no soundtrack at all" in the README.

**Where the footage came from.** Seven Windows Game Bar captures in
`~/Videos` (Windows also writes a byte-identical copy to
`Videos/Screen Recordings/` -- verified with `sha1sum` on the first 5 MB, they
are not two takes; `Recording 2026-08-31 105144.mp4` and `115632.mp4` are also
the same file). Two Android **screen recordings** from the phone's `Movies/`
folder -- NOT `DCIM/Camera`, which is where I looked first and wasted a pass.
One handheld camera clip from `DCIM/Camera`.

Ordering them needed care: Windows names a capture for when it *stopped*,
Android for when it *started*, and `PXL_20260831_181726168.mp4` is stamped in
**UTC** (18:17Z = 11:17 local), so it belongs between `desktop-110556` and
`desktop-112123` rather than at the end where a filename sort puts it. Also,
`Shell.Application` sorts MTP listings as strings, so `9/9/2025` sorted above
`8/31/2026` and the newest phone video looked eleven months old.

**The three-way cut.** Whole-frame activity says 80% of this footage is dead,
but it cannot tell the interesting 20% from the boring 20%. Measuring `main`
(browser, x < 0.748) and `panel` (the Claude side panel) separately gives the
distinction the edit needs: keep where the browser moves, speed up where only
the panel streams, drop where nothing does. The panel divider is at
**x = 0.748**, found by taking the strongest long vertical edge in the right
half at six timestamps per file and using the mode -- a single timestamp gave
three different answers because dialogs were on screen.

`hold` (dilating the activity track) is what makes it watchable: without it,
1094 segments and a film flickering between speeds several times a second;
with it, 579.

**Length.** Only 3:17 of 47:14 is truly dead, because the thinking spinner
means something is nearly always moving. `speed` 6x -> 12x only moved the film
25:27 -> 23:36, because 21:45 was held at 1x. `--target 8:00` was chosen by
the user from a priced menu; it solves to work 3.18x / waiting 19.07x.

**Privacy.** Asked for "phone number, card and CVV". The footage also carries
recipients' full names, phones and Nova Poshta addresses, their emails, the
user's own email, a 132,420.45 UAH balance and transaction history. Asked, and
the answer was **"everything above, but keep the city name"** -- so cities stay
readable in the checkout selector and the Claude summaries while the recipient
records are covered.

Two things `scan-pii.py` got wrong at first and now has tests for: a Threads
thread id (`.../t/2239405853520443/`) **passes Luhn** and would have pixelated
the address bar through the whole DM section; and OCR of mangled Cyrillic
produced `pMEAHyrOCbAo@gorokhovsky.FoTOBMio...`, which matched a loose email
pattern and would have covered the post text.

Two things it could not do at all, handled by hand in the manifest:

- **The phone bank clips.** `screen-20260831-083709` (monobank -- *not*
  Privat24, despite the ask) returned **zero hits** while showing two full
  PANs, three balances and a transaction list. The digits sit on a dark
  stylised card face in a display font and the model did not read them. Rects
  measured by hand off a fraction grid.
- **Cyrillic names.** This OCR cannot read them, so the recipient name above a
  detected phone and the branch address below it are invisible to it. The
  desktop rects are therefore grown by 0.075/0.055 of the frame around each
  readable field, to cover the record it belongs to.

The store's own support numbers (`+38 068 668-35-95`, `+380737161131`) are in
every page header and footer. They are real hits and nobody's private data, so
they are filtered out rather than smeared across the top of half the film.
- 20:40 screen-cut scripts/screen-cut.py -> projects/books-giveaway/temp/rendertest.mp4 (--manifest projects/books-giveaway/temp/rendertest.json --target 0:45) -- 1:30.0 of sources -> 0:45.9
- 20:53 screen-cut scripts/screen-cut.py -> projects/books-giveaway/temp/rendertest.mp4 (--manifest projects/books-giveaway/temp/rendertest.json --target 0:45) -- 1:30.0 of sources -> 0:45.9

**The near-miss worth remembering.** The first phone rule required the `+38`
country code. A composite proof frame from `desktop-105144` showed a Claude
panel summary reading

> (Київ, відділення 57, 0939589090, Стрельченко Марія — «Іздрик: Ліниві і
> ніжні», 430 грн)

in the clear -- city, branch, phone and full name -- because the national `0XX`
form never matched. Widening the rule and re-scanning took `desktop-110556`
from **0 regions to 7** and `desktop-105144` from 5 to 18. A recording that had
reported clean was not clean. `check-screen.py` now holds that exact string.

Two habits came out of it and are in the README:

- `--sheet` composites **every rect active at that instant**, not one per
  frame. The one-at-a-time proof had shown a card panel "covered" while a full
  IBAN two rects away sat in the clear.
- Scan the **render**, not only the sources. It is eight minutes at 1080p, so
  the pass costs minutes and checks the artefact that actually gets published.

Hand-measured rects live in `blur_extra` on the source so regenerating the
scanned ones cannot drop the rects that exist *because* the OCR missed
something. `desktop-104945` has one: scan-pii never reported the IBAN printed
there in full, even though its rule matches that string.
- 21:36 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:14.4 of sources -> 8:00.4
- 21:48 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00 --where 2:10 --where 2:36 --where 0:28 --where 7:12 --where 3:22) -- 47:14.4 of sources -> 8:00.4
- 22:05 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 45:38.3 of sources -> 7:42.0
- 22:22 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 45:38.3 of sources -> 7:42.0
- 22:26 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 45:38.3 of sources -> 7:42.0
- 22:27 publish scripts/yt-upload.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (projects/books-giveaway/outputs/books-giveaway.mp4 --title Купую книжки підписникам з Threads — чорновий монтаж (без озвучки) --description-file projects/books-giveaway/description.txt --channel @inst) https://youtu.be/gkSgIQKfgMc -- uploaded Купую книжки підписникам з Threads — чорновий монтаж (без озвучки)

### Stage 1 delivered

`outputs/books-giveaway.mp4`, 7:42, 1920x1080, 30 fps, **no audio track at
all** -- the voice-over is stage 2 and a silent AAC track would only invite a
later pass to mix onto nothing. Uploaded private to @instafill_ai as
https://youtu.be/gkSgIQKfgMc.

**What the user relaxed after seeing frames**, and it is worth keeping: the
Nova Poshta branch line, the masked PAN (`**** 4699`) and the whole LiqPay page
are all fine to show. Twelve rects came back out. Recipient names, phones,
emails and the Claude panel stay covered.

**Two sources are `skip: true`**, not deleted -- `desktop-104945` and
`desktop-105144`, both carrying the full PAN (the second one in a Notepad
WINDOW TITLE). 18 s of planning footage between them; the "I made a card"
beat is already told by the two phone clips. The reason lives on the source
entry so nobody re-adds them blindly.

**The verification lesson, which cost the most time here.** A scan at one frame
every two seconds came back with six findings, three of which looked stale on
inspection -- so it read as "essentially clean". Re-scanning the same ranges at
2 fps with `--skip-static 0` found the PAN in a window title that no rect was
near. **Sparse sampling had simply never landed on those frames.** The gate is
now: render, scan the RENDER at 1 fps with skipping off (462 frames, ~25 min),
and only then upload. That pass ended with 8 findings, of which 6 were OCR
variants of the store's own support number.

**Four ffmpeg traps, all new, all in the README:**

- A 579-segment graph is **87 KB** and Windows caps a command line at 32767, so
  it dies as `WinError 206: The filename or extension is too long` -- which
  names entirely the wrong thing. Use `-filter_complex_script`.
- `concat` with ten FILE inputs makes ffmpeg demux all ten concurrently and
  buffer the nine it is not consuming: 2.8 GB RSS and output frozen at 25 MB.
  Render per source, join with the concat DEMUXER and `-c copy`.
- Pixelate rects cost **35 s per 10 s of video at 18 rects**; drawbox costs 2 s.
  Each pixelate rect is its own split/crop/scale/scale/overlay and runs every
  frame whether its `enable` window is open or not. Boxes are also the safer
  redaction. Pixelate is kept for ONE big rect (the Claude panel), where the
  look is worth it and the cost is a single chain.
- `_progress.begin()` RETURNS the path ffmpeg must be given as `-progress`.
  Declaring the job and not wiring it leaves the status line reading an empty
  file and reporting "stalled" for the entire encode.

**Proxies.** `make-proxies.py` transcodes each source once at the canvas fit
size: 12 GB -> 332 MB, SSIM 0.9999 against source. Safe because every rect in
this pipeline is a FRACTION of the frame, so proxy and original are
interchangeable and there is no "apply it to the big one" step. It is what made
five re-renders affordable. **Do not** proxy for `scan-pii.py` -- OCR is
resolution-bound.

**Not done, and the next session should decide it:** the eight books are not
pinned to beats. At 3.18x the pages stay readable because each is on screen
15-40 s, but nothing guarantees it. `hold_1x` windows on the source are the
lever; `--target` deliberately does not scale them.
- 22:34 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 45:38.3 of sources -> 7:42.0
- 22:34 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 45:38.3 of sources -> 7:42.0
- 23:07 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:14.4 of sources -> 8:00.4
- 23:08 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:14.4 of sources -> 8:00.4
- 23:10 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:14.4 of sources -> 8:00.4

### The redaction pivot: track the pixels, not the clock

The user called out both the look and the architecture in one message: black
boxes instead of blur, wiped screens instead of covered fields, and "it seems
we start from nothing each frame -- isn't this a standard task?" It is. The
standard name is **tracked redaction**, and the standard algorithm is template
matching: capture the secret's own pixels once, find them per frame with NCC
(`cv2.matchTemplate`), blur exactly what matched. `track-blur.py` implements
it; a source's `track` key points screen-cut at the mask stream, and the frame
is blurred once and shown through the mask.

What the verification frames taught, in order:

- **Scale.** Privat24 draws the same account number at list/detail/form sizes
  and NCC only matches its own size -- templates are now searched at three
  scales, one variant kept per rendered height OCR saw.
- **Trust.** A 39x11 "UA39" patch cleared 0.90 NCC against a FACE. Templates
  under 48 px wide or 12 sigma contrast are refused at collection.
- **Where tracking honestly loses.** (1) Selected text: white-on-blue does not
  match a template captured black-on-white, so the PAN went sharp exactly
  while the user highlighted it. (2) The Alt-Tab switcher renders a window
  TITLE carrying the PAN at thumbnail scale. (3) A field OCR never hit has no
  template at all (the full IBAN on the card page). Those three cases carry
  hand rects in the manifest, with the reason on each.
- **Division of labour that stuck:** tracking for desktop browser footage
  (consistent rendering; 70% of frames carry boxes on the busiest source),
  hand time-gated rects for the two phone-bank clips (static screens, few
  fields, multiple render styles) and the handheld clip (photographed screen,
  NCC recall 14% -- per-hit time rects instead).

Cost model that makes it fast: unchanged frames are skipped outright (87-93%
of a desktop screencast), tracked instances re-found in a local window, full
sweeps only for lost templates at half scale. 47 minutes of footage tracks in
about six.

User decisions this pass: blur, never black boxes or pixelate mosaic; never
wipe a whole region or panel; the Claude chat stays readable except the
sensitive field itself; uploads go up UNLISTED (memory saved).
- 23:50 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:14.4 of sources -> 8:00.4

**Template pooling, the last structural fix.** The full PAN typed into the
Claude panel in `desktop-110556` rendered sharp: that recording's own OCR
never read it (tiny grey panel text at 4K), so its tracker had no template --
while `desktop-105144`'s scan had read the same digits in Notepad. Secrets
cross recordings; template pools must too. track-blur's `--pii` now takes all
same-geometry scans pooled, cutting each template's pixels from the file the
hit was found in. THR also dropped 0.88 -> 0.86: a near-miss blur is a few
pixels off (cosmetic), a near-miss rejection is a leak.

## 2026-09-01
- 00:24 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:14.4 of sources -> 8:00.4

### Post-mortem tooling, and the bug under everything

The retro is `docs/retro-books-giveaway.md`. Building the recall harness
(`track-blur.py --recall`) took an hour and paid for the whole day: the first
number it printed was **26.9%** on a source whose own OCR hits were the
templates. Three hypotheses fell (half-scale prefilter; template chosen by
height only; template chosen without width) and each moved it a few points.
Then a direct experiment -- cut the template from the frame OCR named, and
self-match it there -- gave std 0.0: the crop was blank. The OCR hit was
right; its TIMESTAMP was the sample slot, not the frame. ffmpeg's fps filter
emits, for the slot labelled 16 s, whichever input frame fell inside that
4-second slot, and scan-pii labelled it 16.0. Every template was cut up to
4 s away from the frame that carried the text. Recall 46% -> 92% from that
one fix; the 183-leak render is explained by it too.

`scan-pii` now samples with `select` and reads the real pts from `showinfo`
(the fps filter would REWRITE the timestamps onto its grid, which is the very
number that was wrong), and reading the frame before its time avoids the
stdout/stderr deadlock that hung the first version. The tracker tolerates the
old labels by probing the slot and taking the crop with the most structure,
so the existing scans did not need re-OCR -- but the pipeline re-OCRs anyway
because the rules file changed, and writes the per-frame cache this time.

New: `screencast-pipeline.py` (eleven stages, cached, one stop),
`import-footage.py`, `redaction-review.py`, `render-gate.py --patch`,
`screen-cut.py --smoke`, `screen-activity.py --find-panel`, the OCR cache.
Phone clips are `track: false` in the manifest: hand rects there.
- 04:30 redaction-review -- redaction look approved (8c9ce85e4859af6a)

### Review pass 1 applied; first full pipeline run

The user's review recording (`review-notes.md`) changed three decisions:
balances are shown (out of `blur_kinds`), no full-width bands on the phone
clips, and the phone clips are tracked again -- their 14% recall had been
measured with the timestamp bug in place. The measurement after the fix:

    desktop-104620   11/11  100%      desktop-112123  162/166  97.6%
    desktop-104945    6/6   100%      desktop-115024  182/189  96.3%
    desktop-110556    6/6   100%      screen-…083827    9/10   90.0%
    desktop-105144   25/27   92.6%    PXL (handheld)    6/7    85.7% -> one hand rect

407/422 = 96.4% overall. Recipient NAMES are deliberately not blurred: the
OCR cannot read Cyrillic, so the tool cannot promise them; the user approved
the look with that stated.

**The new bottleneck is tracking time**: OCR 27 min, tracking **82 min** with
5 parallel workers. Worse than the original 8-minute tracker, and for a known
reason: the full-resolution search added for small templates runs every
pooled template (~85 per source, x3 scales) on every change frame for every
lost template. The fix is a cost model, not a tune -- a permissive coarse
prefilter with full-res confirmation, sweeps bounded to the windows the OCR
cache says a secret is on screen (plus a slow patrol outside them), one
thread per worker process. Next task after this upload.

Also: never pipe a long run through `tail` into a log -- it kept only the
last 40 lines of the pipeline output, and the per-source recall table had to
be re-run to be read. The pipeline now writes its own log file.
- 04:37 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00) -- 47:13.4 of sources -> 7:60.0
- 04:46 screen-cut scripts/screen-cut.py -> projects/books-giveaway/outputs/books-giveaway-hot-draft.mp4 (--manifest projects/books-giveaway/screen.json --target 8:00 --hot --draft) -- 47:13.4 of sources -> 1:15.1

### Draft stage, the register, and the tracker's cost model

Two asks from the user this evening, both structural:

1. **A knowledge base of known issues and limitations** so mistakes are not
   repeated. `docs/known-issues.md` is the register -- id, status
   (`limitation` / `open` / `fixed`), stage, symptom, cause, fix -- seeded
   with seventeen entries from this project. The pipeline prints the open
   ones and the limitations for the stages it is about to run, so it is seen
   on every run; `check-screen.py` parses the header shape.
2. **Lightweight renders before the full one.** `screen-cut.py --draft`
   (half resolution, fast preset) and `--hot` / `--range` (film-time
   windows mapped back through the cut) are separate levers; the pipeline's
   new `draft` stage renders `--hot --draft` -- the riskiest minute at half
   resolution, 1:15 in 99 s here -- and stops for approval before the final.
   The 30 s smoke stays at final settings: its job is the graph and the
   encoder, which a draft cannot validate. Redaction is resolution-independent
   (fractions), so a draft is a valid review of the blur.

**The gate stalled** on the first full run: fourteen minutes with no
progress, for the same reason tracking took 82 minutes (KI-005). Fixing the
tracker's cost model on the 60-second test source, recall held at 92.6%
throughout:

    full-res search for small templates       131 s   3217 sweeps
    coarse-first (0.50 prefilter + confirm)    105 s   3217
    foreign templates on a slow patrol,
      scale variants only when warm            57 s   2577
    no sweeps on caret-blink frames, warm 1 s,
      foreign never on a page change            42 s   1299

The gate now searches at native scale only (the render is at proxy scale,
and a secret at another size is already its own template).
