# bpo-realtor -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-23
- 11:33 project created

## 2026-09-23

### Session note -- project opened, materials inventoried, nothing shot yet

**The ask.** Oleksandr: several people at a demo said they had seen the BPO
video, so the channel needs more of them. One of them can be the same form on
the same data under a different angle -- "how real estate agents can use AI to
automate paperwork" -- but the quality has to go up and something new has to be
tried. Plus a short out of each main video, an external voice-over (no lip
sync), and HIPAA / Boyd Group cases when their inputs arrive.

**The form is measurably what the old video claimed.** `BPO_TEMPLATE_Standard`
has **534 AcroForm fields** over 3 pages (455 text, 78 button, 1 choice, read
with pypdf). The "500+ fields" line in `neaCnEawvbk` was accurate, so it can be
said again without hedging.

**The dataset tells a story, which the old chapter list did not exploit.**
The subject at 946 Alderwick St is Pending at **$151,800** in "Major Rehab
Needed" condition, and every one of the six comparables sits between **$389,500
and $442,000**. There is a renovation budget in the scope of work. So the video
is not "watch a form get filled" -- it is "here is a $150k house in a $400k
street, and the BPO is the document that has to justify the number".

**pypdf was added to the venv** to read the form and the data. It is not in
`requirements.txt` yet; add it there before anything depends on it.

**The assets are committed, deliberately breaking the gitignore convention.**
`neaCnEawvbk` kept its manifests and lost its sources, which is exactly why
this session could not simply re-cut the old film. 490 KB of synthetic PDFs is
a cheap insurance premium. Nothing in them is real.

**Recording has not started and the arrangement is not settled.** The proposal
on the table is to record SILENT -- clicks only, no talking -- and write the
narration afterwards as an ElevenLabs voice-over. That removes the accented,
halting live take that made `flatten-pdf` need a voice-over anyway, and it
makes the recording itself far easier: no retakes for stumbles.

### Session note -- sources arrived, inventoried

Five files, not six: takes 3 and 4 were recorded as one Cursorful file,
`take3-upload-take4-fill.mp4` (200 s). Not a problem -- the takes are split by
content, not by file; the boundary is the Submit click. Take 5 is named
`take5-results.mp4` (plan said `result`); names are not load-bearing.

**Screen size changed mid-session:** take1/take2 are 1920x1064, take3-4/take5
are 1920x968 (all 60 fps, no audio track). The cut has to pad or scale onto one
canvas -- do not assume one size.

**The phone did not run continuously.** `phone.mp4` is 5:49, 1920x1080 30 fps,
creation_time 13:55:59Z; the screen takes are stamped 13:18Z..14:01Z. By the
stamps (not yet proven by sync) it covers only the ~4 minutes before take 5 and
take 5 itself -- i.e. cutaway #2 (result) exists, cutaway #1 (Submit, take 3)
does not. Framing is good: hands + mouse, laptop screen at the bottom edge and
unreadable. The last frames of take3-4 are black (recorder tail) -- trim.

### Session note -- every take read frame by frame (sheets in temp/inspect/)

**The one real duplicate: Download -> open PDF is recorded twice.** End of
take3-4 (3:06-3:20, with a black frame at 3:15) and start of take 5
(0:04-0:12). Keep take 5's -- it runs straight on into the walkthrough.
take3-4 2:49-3:01 is 12 s of "File is loading" after the fill: cut.

**Fill timing, measured (take3-4 source time):** Submit clicked 0:58.1;
"Filling out form" screen 1:01.3; progress bar sits near 0 % to ~1:25, stalls
~24 % 1:48-2:20; "processed in 1 minute and 28 seconds" text appears 2:48.5;
filled form visible 3:01.8. Click-to-result on screen = **110 s**, the app
says **88 s** -- no visible event at 2:48.5-88 s, so the app's number is a
server-side interval. A counter must not sit next to that text disagreeing
without a decision about which clock it shows.

**Content problems no cut fixes:**
- take 3 0:41-0:59: yellow banner "You've attached 8 source files ... a large
  number of documents increases the chance of errors" -- on screen through Submit.
- take 5 0:46-0:52: section VII MARKET VALUE, AS IS / REPAIRED estimated value
  are EMPTY. The bottom line of the BPO is blank; do not end the film on it.
- takes 1-2 show the browser chrome: address bar C:/Users/<user>/Downloads/...,
  and eight tabs titled "untitled" in take 2. Crop the chrome.

**Waste to cut:** take1 0:00-0:08 hold (keep ~2 s), 0:21-0:27 zoomed-out page 2,
0:31-0:41 page-3 hold; take2 0:00-0:11 on cantrell_tax; take3 0:16-0:24
upload spinner, 0:44-0:58 cursor hovering over Submit. Screen-activity's
"still" runs mislabel the fill as still (141.8 s): the progress bar moves
below the threshold -- do not let the cut drop it.
- 14:53 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor-review1.mp4 (--manifest projects/bpo-realtor/edit.json)

### Session note -- review cut 1, and the counter

**Ask:** cut the waste, keep the best of each repeated action, speed up the fill
and put a professional elapsed counter in a corner that stays correct at speed.
User said "добре" to the 1:50 (click-to-result) clock, the recommendation.

**New tool, `scripts/edl-cut.py` + `edit.json`.** screen-cut.py's motion
classifier cannot make editorial choices and called the fill "still". The EDL
is data with a `_why` per range. The counter maps every film frame back to
source time, so it reads 0:52 at film 1:33 (3.3 s + 4.9 s x 10) and stops on
1:50 at the frame the result message appears (source 168.88; Submit 58.00).
Card style: config/overlays/elapsed-counter.json, bottom-right in the lavender
margin under the window (it covers nothing of the app there).

**What review1 shows (2:24):** blank form -> 8 documents -> upload -> Submit ->
fill at 10x under the counter -> "Form filled 1:50" -> form appears ->
download (take 5's copy; take3's is the duplicate) -> comps grid -> $392,000
check -> section VI. Ends before section VII (empty estimated values).
Chrome in takes 1-2 painted in its own colours (tab strip, path, 'untitled').
The app's "processed in 1 minute and 28 seconds" is blurred.

**Open, for the next session:** phone cutaways not in yet (phone covers only
take 5 -- sync it with sync-tracks.py before using it); the yellow 8-files
warning is still visible 1:02-1:28 film; take 5 enters on Cursorful's zoom,
off-centre (as recorded); no voice-over. Pacing is 1x everywhere except the
spinner and the fill -- the voice-over will decide the rest.
- 15:41 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor-review2.mp4 (--manifest projects/bpo-realtor/edit.json)
- 15:45 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor-review2.mp4 (--manifest projects/bpo-realtor/edit.json)

### Session note -- review 2: zoom-proof paint, zooms, phone

**Ask:** remove the stripes where the video zooms; add zooms where an accent
helps; add the phone; propose texts; explain how shorts come out of this.

**The stripes were the fixed paint rects inside Cursorful's own zoom** (take2
23.1-26.2, the $392,000 zoom): the chrome slid away, the rects stayed on the
page, the path showed beside them. edl-cut.py now tests every used frame (a
paint rect at rest is mostly its own colour) and tracks the chrome through the
moved runs with ORB + RANSAC, frame to frame. Verified on the render at
36.2-39.0: clean. Nearest-neighbour upscale of the follow clip, or the rects
get a dark outline.

**Phone:** upside down with no rotation tag -> `rotate: 180`. NOT synced:
creation_time seed +264 s; sync-tracks correlation z=3.2 (+275.65); click
matching gives three equal offsets; screen brightness via the phone z=13 at
+276.77 but the event spacing disagrees ~1.5x. Used as B-roll only: a hand at
the keyboard before Instafill (phone 119-121.5), a click on Submit (272.0-
273.6), a click covering take5's dark PDF-loading flash (269.1-270.6).

**Zooms:** the headline (2x), the documents + Submit (1.95x, framed below the
yellow 8-files banner, fully in before it appears), Submit after the cutaway at
1.6x (at 1.95x the counter card covered Submit), a slow push onto the filled
fields at the reveal (2.4x). Bug found and fixed: a zoom ending on a cut
reached across the phone cutaway and magnified it.

**Texts:** voiceover.md -- timed script, titles, description, chapters,
thumbnail, three short concepts. Not yet approved. The full-film voice-over is
still the missing capability (dub-clips --script is per clip).
- 16:08 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/previews/endcard-window.mp4 (--manifest projects/bpo-realtor/temp/endcard-window.json)
- 16:09 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/previews/endcard-plain.mp4 (--manifest projects/bpo-realtor/temp/endcard-plain.json)
- 16:10 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/previews/endcard-chips.mp4 (--manifest projects/bpo-realtor/temp/endcard-chips.json)

### Session note -- end-card, caption and music options (nothing chosen yet)

**Ask:** an end screen in the video's backdrop colour with checkboxes ticking
in one by one; maybe captions; maybe background music; show options.

**End card:** new scripts/checklist-card.py (words: cards/checklist.json;
looks: config/cards/checklist/{window,plain,chips}.json). Previews in
outputs/previews/endcard-*.mp4 (the film's last 6 s + the card) and *.png.
Wired into edl-cut.py as an EDL entry {"card","style"} -- NOT yet in edit.json;
add it after the user picks a look. Lines are only what the film showed (no
hand-time claim, no market value).

**Captions:** need the voice-over audio first (words come from it, not from
ASR on a silent film). Previews used the draft script at 2.5 words/s, so the
group splits in outputs/previews/captions-compare.png are not real. Three
looks: instafill (existing, sits on the window edge), instafill-band-light,
instafill-band-dark (both in the lavender band under the window).

**Music:** proposed only -- nothing downloaded or generated.
- 16:29 render scripts/edl-cut.py -> projects/bpo-realtor/temp/picture.mp4 (--manifest projects/bpo-realtor/edit.json --out projects/bpo-realtor/temp/picture.mp4)
- 16:32 dub scripts/dub-clips.py -> projects/bpo-realtor/outputs/dub/bpo-realtor-film.vo.wav (--manifest projects/bpo-realtor/vo.json --only film --script projects/bpo-realtor/vo/film.json --tts elevenlabs --voice brian --tag vo --outdir projects/bpo-realtor/outputs/dub) -- sync 40.7%, elevenlabs/nPczCjzI2devNBz1zQrb
- 16:43 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor.mp4 (--manifest projects/bpo-realtor/edit.json)
- 16:47 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor.mp4 (--manifest projects/bpo-realtor/edit.json)

### Session note -- the film: end card, voice, captions (music pending)

**Chosen by the user:** end card A (`window`) with the Instafill logo in place
of the typed URL; captions C (`instafill-band-dark`); music 1 (YouTube Audio
Library); voice-over text as drafted.

**outputs/bpo-realtor.mp4** (2:35.2): the picture from review 2, the checklist
card at the end (logo: config/cards/brands/instafill-logo.png), the ElevenLabs
voice-over (brian, vo/film.json, every line `natural`), captions built from the
voice-over's own words with `display` putting numbers in written form
(534, $392,000, 1:50, instafill.ai). Mix at -13.9 LUFS integrated.

Verified by transcribing the voice back: every difference is number formatting,
except ElevenLabs said "in section three" for "and section three" (harmless).

**Music is the one open item.** The YouTube Audio Library needs the user's
Studio login. When the track is in `projects/bpo-realtor/audio/`, set
`audio.music` in edit.json and re-render: loop, fades and ducking are automatic.
Tooling gaps closed this session: dub-clips --script without a transcript;
edl-cut audio/captions/display; checklist-card logo.
- 17:05 render scripts/edl-cut.py -> projects/bpo-realtor/temp/picture.mp4 (--manifest projects/bpo-realtor/edit.json --out projects/bpo-realtor/temp/picture.mp4)
- 17:06 dub scripts/dub-clips.py -> projects/bpo-realtor/outputs/dub/bpo-realtor-film.vo.wav (--manifest projects/bpo-realtor/vo.json --only film --script projects/bpo-realtor/vo/film.json --tts elevenlabs --voice brian --tag vo --outdir projects/bpo-realtor/outputs/dub --force) -- sync 52.5%, elevenlabs/nPczCjzI2devNBz1zQrb
- 17:09 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor.mp4 (--manifest projects/bpo-realtor/edit.json)
- 17:12 render scripts/edl-cut.py -> projects/bpo-realtor/outputs/bpo-realtor.mp4 (--manifest projects/bpo-realtor/edit.json)

### Session note -- music in, voice retimed

User: the voice starts at the first second and then goes quiet for long
stretches; let the music play 2-3 s first. Music: "When You're Alone - Dyalla"
(YouTube Audio Library, audio/), bed at -18 dB, ducked under the voice.

Changes: take1 now opens at 3.0 (2.5 s of page 1 with music alone; voice at
2.80 s); take5 ends at 42.0 (3 s less dead tail before the end card). Silences
measured on the voice words: were 8.2/8.9/14.4/7.0/11.9 s, now max 7.9 s (the
zoom on the documents before Submit -- a picture beat). Four lines ADDED to the
approved script to fill them (section three; "maps every text box and
checkbox"; "tax record, scope of work, six listings"; "the clock in the corner
is real time, the video runs ten times faster"); others moved onto their
picture. Line 1 now uses its `tight` form. Tell the user about the additions.
