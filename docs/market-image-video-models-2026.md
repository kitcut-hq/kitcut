# Ranking image and video models with our own tests: coverage, demand, tests, cost

Researched 2026-10-25. Companion to `docs/market-llm-leaderboards-2026.md`, which covers
llm-stats.com and benchlm.ai (the two LLM leaderboards). Sources: the two sites' own pages and
sitemaps; OpenSEO (DataForSEO, US) for search demand and results pages; Claude's vision
documentation; this repo's own bake-offs and the `video-h3` skill; and web research on the
evaluation literature and on model APIs and prices (sections marked as such). Findings first,
then a design and a priced pilot.

## The short answer

1. **The two LLM leaderboards barely cover image and video models.**
   - benchlm.ai lists none.
   - llm-stats.com has ~123 media model pages, but they are shells. The five opened (Seedance
     2.5, Kling v3, GPT Image 2.5 Sunburst, Veo 3.1, FLUX 3 Video) had no benchmark row, no
     price and no speed data.
   - Its image and video rankings come from its own arena: 11,311 votes over 10 image models
     and 1,450 votes over 13 video models. New votes are now closed.
2. **The searches a ranking site can win are ~3x the LLM equivalents, easier, and worth more a
   click. The results pages are weak.**
   - Like for like: "best ai image generator" 33,100 a month (difficulty 18) plus "best ai video
     generator" 22,200 (difficulty 27, $13.19 a click) is ~55,000. "llm leaderboard" 8,100
     (difficulty 56), "best ai model" 4,400 and "ai ranking" 4,400 make ~17,000.
   - The headline terms ("ai image generator" 823,000, "ai video generator" 246,000) are people
     looking for a tool to use right now. A ranking site captures little of that.
   - Google's top ten for the two "best" searches has no leaderboard in it: listicles (several
     from 2024), API resellers' own blogs (fal.ai, WaveSpeed), Reddit and YouTube.
3. **Reliable automatic tests exist for images, not yet for video motion.** Checklists of yes/no
   questions answered by a strong vision model agree with human labels ~94% (GenEval 2). For
   video, frontier judges correlate only 0.18-0.26 with people (averaged over all dimensions;
   0.17-0.20 on physics alone). Details below.
4. **Claude Opus 5.5 can verify a large share automatically, as one component.**
   - It reads images only; video has to go in as frames.
   - It costs ~$12-15 per 1,000 images judged with the Batch API, and ~$23-26 per 1,000 clips
     judged from 16-24 frames.
   - Anthropic sells no image or video generator ("Claude is an image understanding model
     only"), so it has no house model to favour, unlike a GPT or Gemini judge.
   - It must be backed by checks that need no judge (OCR, face embeddings, ffprobe, motion
     measures, speech recognition), and calibrated against a small human-labelled set before
     anything is published.

## How the two LLM leaderboards cover image and video (measured)

| | llm-stats.com | benchlm.ai |
|---|---|---|
| image/video/audio model pages (sitemap names matching media model families) | ~123 of 584, image, video and audio together | 58 of 993, **all voice** (TTS, transcription); no image or video generation model |
| data on those pages | none on the five opened: 0 benchmark rows, no price, no speed | voice benchmark pages (53) and media price lists; no quality measurement of its own |
| ranking | own arena: image 11,311 votes / 10 models; video 1,450 votes / 13 models ("Kling v3 leads... arena score of 1934") | none |
| freshness | arenas closed to new votes ("moving to Playground") | no image/video pages to be fresh |
| last 30 days' image and video launches listed | 0 of 5 (FLUX 3 Image, FLUX 3 Image Klein, Krea 3, Qwen-Image-2.1-Turbo, Kandinsky 6.0 Video) | 0 of 5 |
| visible errors | LLM template text on image models ("Best-in-class multimodal reasoning... Pro variant pricing approaches Opus territory" on Gemini 3.1 Flash Image); video models priced "per M tokens" (Kling v3 "Input $0.17 / M tokens") | n/a |

llm-stats.com's thumbnail guide says it plainly: "The ranking measures general text-to-image
preference, not YouTube click-through rate."

## Search demand and who ranks today (OpenSEO, US)

| search | monthly volume | difficulty (0-100) | CPC |
|---|---|---|---|
| ai image generator | 823,000 | 69 | $3.16 |
| nano banana | 450,000 | 78 | $3.80 |
| sora 2 | 368,000 | 49 | $5.11 |
| ai video generator | 246,000 | 65 | $6.64 |
| midjourney | 246,000 | 56 | $3.14 |
| ai image editor | 201,000 | 65 | $4.44 |
| kling ai | 135,000 | 37 | $6.96 |
| seedance 2.0 | 90,500 | 45 | $11.25 |
| ai voice generator | 74,000 | 55 | $4.02 |
| veo 3 | 49,500 | 55 | $6.69 |
| runway ai | 40,500 | 28 | $10.75 |
| image to video ai | 40,500 | 40 | $4.44 |
| best ai image generator | 33,100 | **18** | $6.62 |
| hailuo ai | 33,100 | 25 | $4.03 |
| best ai video generator | 22,200 | **27** | **$13.19** |
| runway gen 4 | 4,400 | 18 | $20.47 |
| leaderboard terms ("text to video leaderboard", "image generation leaderboard", "video arena") | 70 / 90 / 210 | - | - |
| model-vs-model ("veo 3 vs sora 2", "sora vs veo", "kling vs veo") | 260 / 210 / 40 | 4-6 | - |

People search the model's name and "best X generator"; almost nobody types "leaderboard" or
"A vs B". A site here wins on per-model pages and per-job "best" pages, not on a leaderboard page.

**The top ten today:**
- "best ai video generator": an agency blog dated 2025, WaveSpeed's blog (a reseller ranking
  itself first), Curious Refuge (2024), fal.ai's learn page (a reseller), Reddit, and a YouTube
  test video. Plus a video carousel and forums.
- "best ai image generator": experte.com, Android Authority (2024), Reddit, a tools blog,
  YouTube, Android Police (2024), Mashable (2025).

None of the arena leaderboards appears, and none of the results shows measured tests with the
outputs side by side.

## What this repo already measures

- **Image models on real briefs.** `docs/reference.md`:
  - the same character brief through seven image models, measured for face-edit drift
    (0.2-3.5%), price ($0.019-0.136 a picture) and time (one at 57 s a picture); one model was
    unusable because it takes no reference;
  - `scripts/paint-compare.py` painted 72 pictures on 8 models for $1.78.
- **Voices.** The ElevenLabs bake-off scored Whisper accuracy and speaker similarity (NeMo
  TitaNet). `scripts/stt-compare.py` weighs speech-to-text engines on word error rate, names
  spelled right and speed.
- **Video.**
  - `scripts/short-stillness.py` measures how much of a picture stands still.
  - `scripts/compare-videos.py` scores frame against frame.
  - `studio/review.py` reads a finished film a frame a second for glitches. On 2026-10-07 it
    caught "a cat through her carrier's wall, a body flipped through a sliver, a hand hanging
    in the air".
- **A video model running here.** MiniMax H3 (open weights) on kc-local's RTX 3070 through
  Wan2GP. It takes about 1.1-1.3 GPU-minutes per second of film at 1344x768, electricity only
  (`.claude/skills/video-h3/SKILL.md`).
  - The skill's 17 rules are a defect list from a real episode: a boy turning into another boy
    at 480p, "a stranger wearing Dad's shorts", light words changing a face's colour, invented
    places, a car's dust not tracked from shot to shot.
  - Those are exactly what a creator needs a test to catch. The skill also says "no structural
    test can see" them, which is where a judge earns its place.
- **Local measuring tools:**
  - RapidOCR (onnxruntime) from the redaction pipeline;
  - the YuNet face detector (`models/face/`) from the multicam work; its SFace identity model
    has download commands in the `video-multicam-switch` skill but is not on this machine;
  - OpenCV for optical flow;
  - faster-whisper;
  - matting models.

## Claude Opus 5.5 as the judge: what it can and cannot do

From Claude's vision documentation (fetched 2026-10-25) and the Claude API reference bundled
with Claude Code:

**What it can take:**
- **Input:** JPEG, PNG, GIF, WebP. **No video input**, and an animated GIF counts as its first
  frame only.
- Up to 600 images per API request; above 20, each image must be 2,000 px or less on both
  sides.
- 10 MB per image and 32 MB per request (the Files API avoids resending).

**What it costs:**
- **Image tokens:** `ceil(width/28) x ceil(height/28)`, capped at 2,576 px on the long edge and
  4,784 tokens. 1024x1024 is 1,369 tokens; 1920x1080 is 2,691.
- **Price:** $4 per million input tokens and $20 per million output; cache reads $0.20; the
  Batch API halves both.
- Structured output (`output_config.format`) returns a fixed JSON verdict per check.

**What the docs say it cannot do:**
- counting is "approximate... especially with large numbers of small objects";
- spatial and coordinate answers are approximate;
- it "cannot determine whether an image is AI-generated";
- it will not name people.

**Neutrality.** It "cannot generate, produce, edit... images", so there is no Anthropic model
on the board for it to favour.

**Judge cost** (computed with the rule above; ~1,500 cached rubric tokens, 500-800 fresh text
tokens, 800-1,200 output tokens including thinking; heavier thinking roughly doubles it):

| judged item | image tokens | $ each | $ per 1,000 | $ per 1,000, Batch API |
|---|---|---|---|---|
| one 1024x1024 image, 10-question checklist | 1,369 | 0.024 | 23.78 | 11.89 |
| one 1920x1080 image, 10-question checklist | 2,691 | 0.029 | 29.06 | 14.53 |
| a pair, A vs B (pairwise) | 2,738 | 0.032 | 31.65 | 15.83 |
| an edit: source + result | 2,738 | 0.032 | 31.65 | 15.83 |
| a video clip: 16 frames at 640x360 + one reference | 6,153 | 0.052 | 52.11 | 26.06 |
| a video clip: 24 frames at 448x252 + one reference | 4,825 | 0.047 | 46.80 | 23.40 |

Judging costs cents. Generation is the bill (API section below).

## Who already ranks image and video models, and do reliable tests exist?

Web research, 2026-10-25. Arena pages returned HTTP 403, so Arena was read through its official
dataset.

**The rankers are preference arenas, not tests:**
- **Artificial Analysis** (https://artificialanalysis.ai/methodology/image,
  https://artificialanalysis.ai/methodology/video).
  - Blind pairwise votes fitted to an Elo scale. Voters are now "validated private evaluators"
    with hidden quality checks.
  - Prompts curated per use case. No automatic quality metric; only price and generation time
    are measured.
  - On 2026-10-25: text-to-image 106 models (leader GPT Image 2.5 Sunburst, 1222), image editing
    76, text-to-video with audio 30 (leader Wan 3.0, 1175), image-to-video with audio 23 (leader
    MiniMax H3, 1140 ±16).
  - A free API with attribution (1,000 requests a day). Website terms: personal, non-commercial,
    no competing site.
- **Arena** (formerly LMArena; https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset,
  CC BY 4.0).
  - Public crowd votes with Bradley-Terry ratings and 95% intervals.
  - Text-to-image 82 models (leader gpt-image-2.5-sunburst, 1425; data to 2026-10-07), image
    edit 60, text-to-video 48 and image-to-video 48 (leader minimax-h3; data to 2026-09-22).
  - It also published **Arena-T2I-Hard** (MIT): 310 hard real prompts broken into 13.9k yes/no
    checklist questions. That is the same method as our design.
- **Others:**
  - Design Arena (raised $7.9M in August 2026, sells human feedback to labs).
  - VBench (16 automatic dimensions; its leaderboard was last committed ~7 months ago).
  - K-Sort Arena.
  - Pixazo, a fully automatic board scored by learned rewards plus a VLM judge, 21 models.
  - Yupp, a crowd-voting platform, shut down in 2026.

**What makers publish at launch:**
- No shared benchmark tables like LLM launches.
- Arena ranks: Runway Gen-4.5 #1 on AA; Seedance and Seedream #1 on AA; MAI-Image-2 "#3 family
  on Arena".
- In-house human-preference studies with few numbers: Veo 3.1, Seedance 2.0 radar charts,
  FLUX 3 win rates with no protocol.
- Academic suites from open-weight labs: Qwen-Image reports GenEval, DPG, OneIG, CVTG-2K,
  LongText, GEdit.
- Nothing quantitative from MiniMax H3, even while it leads both image-to-video boards.

**Automatic image tests, and how far they agree with people:**
- **Decomposed checklists answered by a strong vision model are the most reliable method:**
  - GenEval 2 (Meta, December 2025): Soft-TIFA with a VLM reaches AUROC 94.5% against human
    labels; VQAScore run on GPT-4o reaches 91.2%. The best model passes only 35.8% of prompts,
    so it is far from solved (https://arxiv.org/html/2512.16853v1).
  - The original GenEval is saturated and was gamed by reinforcement learning (63% to 95%).
- Learned preference models:
  - HPSv3 (76.9% on its own test), PickScore, ImageReward.
  - All three are also used as training targets, so they get over-optimised.
- Text rendering is measured by OCR plus edit distance (CVTG-2K, LongText-Bench).
- Editing: GEdit-Bench (GPT-4.1 judge; scores vary ~0.1 between runs), ImgEdit, KRIS-Bench,
  EditReward.
- Subject consistency: in DreamBench++, a GPT-4o judge agrees with humans 79.6% on concept
  preservation and 93.2% on prompt following.

**Video is where automatic scoring is weak:**
- VBench ranked six current models with Spearman 0.60 against humans, not significant; most gaps
  between models are under 3 points.
- VBench-2.0 switched to trained anomaly detectors for anatomy because VLMs are unreliable there.
- Physics:
  - The hard subset of VideoPhy-2 tops out at 21.9%.
  - Its AutoEval correlates 0.42 with humans; Gemini-2.0-Flash correlates 0.185.
  - PhyGenEval reaches 0.81.
- Video-Bench (a GPT-4o judge) reaches Spearman 0.70-0.75 on static quality and alignment, but
  0.40 on temporal consistency and 0.51 on motion.
- On VideoScore-Bench-v2, frontier models correlate with humans at only 0.18-0.26, the average
  Pearson correlation over all its dimensions (Claude Sonnet 4: 0.23); on physics alone, 0.17-0.20.
- FVD is biased toward per-frame quality and can be gamed with motionless samples.

**Protocol the evidence supports** (and our design follows):
1. Atomic yes/no questions, scored per fact.
2. Pairwise forced choice in both orders for preference. GenArena: Spearman 0.86 with Arena when
   pairwise, 0.36 when each image is scored alone (measured on seven image-editing models).
3. A second judge.
4. Calibration against human labels, re-validated as generators improve.
5. Deterministic tools where VLMs fail: OCR for text, detectors for counts, specialist detectors
   for anatomy, optical flow for motion.

## A test design that can be checked automatically

**The principle.** Every prompt states facts that can be checked, so verifying means asking
"is it there?", not "is it beautiful?". Each check is answered by the cheapest reliable
verifier:
- a deterministic tool when one exists;
- Opus 5.5 with a yes/no checklist and a JSON verdict when the check needs eyes;
- a person only to calibrate the judge.

Taste (aesthetics) is the one thing no automatic method settles. Leave it to the arenas, or
score it pairwise and publish it separately, never inside the score.

**Image generation and editing:**

| check | example prompt fact | verifier | expected reliability |
|---|---|---|---|
| spec compliance | 16:9, ≥1920 px, no watermark | ffprobe/PIL; OCR for watermark text | deterministic |
| objects and attributes | "a woman in a green coat left of a man in a red scarf" | Opus: one yes/no question per atomic fact (the TIFA/DSG method) | high for presence, colour and simple relations |
| counts | "exactly three people at a table" | Opus, counts kept ≤5; a second judge or a detector on disagreement | medium (Claude's docs: counting is approximate) |
| text rendering | the exact words "GRAND OPENING", or a Ukrainian line | RapidOCR exact match and character error rate, Opus as second reader | deterministic for Latin; Cyrillic needs an OCR model that reads it |
| exclusions | "no people, no text" | Opus: "is there any person / any lettering?" | high |
| editing precision | "make only the mug green" | pixel/SSIM difference outside the edited region (no judge) + Opus "was the change made?" | deterministic + high |
| character consistency across a set | one character in four scenes | SFace face embeddings (human faces) + Opus comparing each to the reference | high on faces; Opus for drawn characters and clothes |
| reliability, speed, cost | - | API logs: refusals of benign prompts, failures, seconds, dollars | deterministic |

**Video** (the H3 defect list turned into checks):

| check | verifier | expected reliability |
|---|---|---|
| spec compliance: duration, fps, resolution, audio present | ffprobe | deterministic |
| it moves: frozen and merely drifting share | `short-stillness.py` | deterministic |
| identity holds: same face and clothes across the clip | SFace per sampled frame vs the reference (faces); Opus on a frame sheet ("which frames show a different person or outfit?") | high on faces; Opus good on clothes and colours |
| prompt facts present and absent | Opus checklist on 16-24 frames | high for content; it cannot see what happens between frames |
| camera instruction ("slow push-in", "pan left") | optical-flow direction and scale (OpenCV), Opus as tie-break | medium-high |
| temporal artifacts: flicker, morphing, limbs through walls | frame-difference spikes and per-frame embedding jumps flag candidates; Opus inspects the flagged frames | medium; the weakest automatic area |
| physics and cause-effect ("the glass falls and shatters") | Opus on before/after frames, low confidence, human-calibrated | low-medium; report separately |
| speech in the clip (models that make sound) | faster-whisper word error rate against the requested line | deterministic |
| reliability, speed, cost per second | API logs | deterministic |

**Making the judge trustworthy:**
1. **Calibrate before publishing.** Two people label a fixed set (for example 300 image checks
   and 100 clips). Report Opus's agreement per check type. A check under ~90% agreement is
   shown as "judged, low confidence" or left out of the score.
2. **Ask twice and route disagreement.** Run each check twice, plus a second judge where it is
   cheap. If they disagree, a person decides, and that label feeds the calibration set.
3. **Blind and vary.** Strip model names. Mask visible provider watermarks where the terms allow
   it, or record that they were visible. Make 2-4 samples per prompt so every score carries an
   interval.
4. **Keep part of the prompt set private.** Publish examples and all outputs of the public part.
   Keep ~30% hidden and rotate it, so nobody tunes to the test.
5. **Publish pass rates per ability, with intervals**, plus price and speed. Do not merge them
   into one number: a creator choosing a model for consistent characters needs that column, not
   an average.

**Example items** (illustrative; each line after the prompt is a check and its verifier):

- **I-1, composition and text.** *"A flat-lay photo of a wooden desk: exactly three red mugs in
  a row on the left, an open notebook on the right with the handwritten words 'Monday plan',
  morning light from the top."*
  - Opus: three mugs? red? on the left? notebook open, on the right? any person? (no
    person expected).
  - RapidOCR: character error rate of "Monday plan".
  - PIL: aspect ratio as requested.
- **I-2, editing precision.** A source photo plus *"Change only the jacket to bright yellow;
  keep the face, pose and background unchanged."*
  - Opus: jacket yellow? face and pose the same?
  - SSIM outside the jacket region must be ≥0.97. The region is the area Opus marks, checked by
    eye during calibration.
- **I-3, one character in four scenes.** A character sheet plus four scene prompts.
  - SFace similarity to the sheet (human faces).
  - Opus: same hair, outfit and colours in all four? Which differ?
- **V-1, identity and camera.** A reference photo plus *"She walks toward the camera along a
  beach at sunset; slow push-in; she wears the same red scarf throughout."*
  - ffprobe: duration and frame rate.
  - `short-stillness.py`: frozen share under 20%.
  - SFace per sampled frame against the photo.
  - Optical flow: the frame scales up (push-in).
  - Opus on a 16-frame sheet: scarf red in every frame? anyone else in frame?
- **V-2, state over time.** *"A dusty blue car is washed by a man with a hose; by the end it is
  clean and shiny."*
  - Opus on the first and last frames: dusty, then clean? car still blue? the same man
    throughout?
- **V-3, speech** (models that make sound). *"A presenter says: 'Welcome to KitCut, where films
  make themselves.'"*
  - faster-whisper word error rate against the line.
  - Lip sync is not judged automatically.

**How many launches a month need testing.** ai-tldr.dev's feed recorded, per 30 days, 2-5 image
models, 2-5 video models and 3-8 voice/music models notable enough to cover (last 90 days). A
monthly "new models" run is a handful of models, not the whole board.

## Is this a better focus than LLMs?

**Why the economics differ from the LLM boards:**
- An LLM leaderboard can be built without running anything: labs publish benchmark tables,
  and both LLM sites copy them (95% of llm-stats.com's rows, 42% of benchlm.ai's).
- Image and video makers publish far fewer comparable numbers (literature section below), so
  there is little to copy. The only way to rank them is to run them.
- That makes the entry price real money and the result original. Whoever runs the tests owns
  the numbers others quote: llm-stats.com built 5,122 referring domains by being the quoted
  source for LLM numbers.

**Why it fits this repo:**
1. **We buy these models anyway.** The studio picks image models, voices and now a video model
   (H3), and every pick so far was a bake-off on our own briefs. A public board is those
   bake-offs, kept up to date and published, so the tests pay for themselves inside the product.
2. **The output is pictures and video, which is what we make.**
   - A "best video model for consistent characters" page is stronger as the same prompt
     rendered by eight models side by side than as a table.
   - YouTube already takes places in those results pages ("I Tried Every 2026 AI Video
     Generator" sits in the top ten). The studio can make those comparison films from the test
     outputs.
3. **Our defect list is real.** The H3 rules and `studio/review.py`'s glitch catalogue come from
   shipping films, not from a benchmark paper.

**Business shape (from the numbers above, not tested):**
- Clicks are worth more than on LLM terms: $13.19 a click on "best ai video generator", $20.47
  on "runway gen 4", against $10.32 on "llm leaderboard". Affiliate and sponsorship pay
  accordingly.
- The API resellers (fal.ai, WaveSpeed) write these listicles themselves to sell access. They
  are both competitors for the results page and natural sponsors or data partners.
- The cautionary number from the LLM side: benchlm.ai turned ~1.1M monthly pageviews into
  $6,105 of revenue all-time by August 2026 (Stripe-verified). Traffic alone does not pay. The
  value has to come from what it does for KitCut (product choices, content, leads) or from
  selling the test data.

**Risks:**
- **Generation cost**, video above all (API section below).
- **Churn.** Several launches a month, each needing a run.
- **The judge's blind spot is motion.** Frames cannot show flicker or morphing between them.
- **Provider terms** (API section below).
- **Established preference arenas** for "which looks best" (literature section below).
