# bpo-realtor — recording plan

For the person holding the mouse.

Three things decide everything below, so they come first:

1. **You do not speak.** Every word is written afterwards and spoken by
   ElevenLabs. Silence on the recording is correct, not a mistake.
2. **Two cameras.** The screen (Cursorful) and a phone on a stand filming the
   desk and your hands. The phone runs continuously and is never touched.
3. **No face.** A written voice-over over a filmed face is a lip-sync problem
   by construction, and the phone is pointed at your hands, not at you.

---

## Part 0 — why there is a second camera at all

A second angle used for decoration is worse than no second angle. This one has
a job: it shows that a person is doing this, and it gives the cut somewhere to
breathe at the two moments that matter.

**The hand is the subject of this shot, not the screen.** The screen already
exists in the recording, sharp and clean. Filming it a second time only adds
moire, reflections, and an exposure that reads the bright screen and leaves
the hands in shadow. So the laptop display enters the top of the frame at an
angle and is **cut off and unreadable**; hands and keyboard own the rest.

    +----------------------------------+
    |   \  edge of the screen, angled,  |  <- top third: screen,
    |    \ cropped by the frame         |     cropped, not readable
    |-----\--------------------------   |
    |      keyboard                    |  <- bottom two thirds:
    |         [hand] on trackpad/mouse |     hands and keyboard
    +----------------------------------+

Cutaways are **2-3 seconds each**, in two places: the moment of **Submit**, and
the moment the finished report appears. A product demo that spends half its
runtime on a hand is a lifestyle advert.

> An earlier version of this plan put a **printed copy of the form** on the
> desk and filmed a hand turning its three pages. That is a better shot and it
> is kept here for whenever a printer is available -- "534 fields on screen,
> three sheets of paper in a hand" is the whole argument in one image. It was
> dropped only because there was no printer. Blank A4 as a stand-in was
> considered and refused: blank paper is not this form, and a viewer reads the
> difference as staging.

## Part 1 — what the previous BPO video got wrong

Not editing mistakes — **recording** mistakes, which no cut repairs. From the
published `neaCnEawvbk`:

| at | on screen | why it hurts |
|---|---|---|
| 0:52 | bookmarks bar reading `hipa.ai`, `crowd links`, two Gmail threads | private working context on a public product video |
| 2:56 | five tabs titled `(anonymous)` | looks like a debugging session |
| 6:20 | the webcam bubble sits **on top of the adjustment grid** | it covers the one thing the video exists to show |

Cursorful removes the first two by framing the browser window. The third is
solved by not filming a face.

---

## Part 2 — set up (20 minutes, once)

### The screen

- **Cursorful export at 1080p.** The reference recording `sARFB1XnQKk` is
  1280x720, and that is not enough here: the vertical short keeps only a
  middle band of the frame, and 720p falls apart inside it.
- Browser **zoom 125 %** (`Ctrl` `+` twice). The form's labels must stay
  readable after the vertical crop.
- A **clean Chrome profile**: no extensions bar, no bookmarks
  (`Ctrl+Shift+B`), signed into Instafill and nothing else.
- Tabs: open the ones take 2 needs **before** recording starts, so no tab is
  ever created on camera.

### Windows

- `Win+N` → **Do not disturb ON**.
- Quit Telegram, Slack, mail.

### The phone

- **Landscape, 1080p, 30 fps.** Landscape because the film is 16:9 and a
  vertical insert can only be pillarboxed or cropped. 1080p because the shot
  lives for two seconds. 30 fps to match the screen recording.
- **To the side of the laptop, about 45 degrees, 50-70 cm away**, a little
  above desk height -- the view of somebody sitting beside you watching your
  hands.
- **Propped against something solid** -- books, a mug, a box. Not hand-held:
  a shake is obvious in a two-second insert.
- Frame it as in Part 0: hands and keyboard fill the bottom two thirds, the
  screen only clips in at the top.
- **Lock focus and exposure on the hands.** On iPhone, press and hold on the
  hands until `AE/AF LOCK` appears. Without it autofocus hunts every time a
  hand moves.
- **Light from the front.** A window behind the laptop turns the hands into a
  silhouette.
- Face out of frame.
- **Check with a 5-second test:** play it back, and if the text on the laptop
  screen is readable, there is too much screen in the shot -- move the phone.
- **Press record once, before take 1, and stop it only after take 5.** Do not
  start and stop it per take, and do not move it once it is rolling. One
  continuous file is what lets `sync-tracks.py` line the two cameras up by
  itself.

---

## Part 3 — how to move

More important than anything else in this file:

1. **Move the mouse slowly.** A cursor that snaps across the screen cannot be
   followed — and Cursorful's zoom follows the cursor, so a fast cursor makes
   the whole frame lurch.
2. **Pause two full seconds** before and after every click that matters. The
   cuts land in those pauses and the voice-over breathes there. Count them.
3. **Never talk.**
4. **If you fumble:** stop, hold still for three seconds, redo the action from
   its start. Do not restart the take. The still moment is what lets the fumble
   be removed cleanly.

---

## Part 4 — the five takes

Everything is in `projects/bpo-realtor/assets/forms/`. Save the recordings into
`projects/bpo-realtor/sources/` with exactly these names:

```
take1-form.mp4       take2-documents.mp4   take3-upload.mp4
take4-fill.mp4       take5-result.mp4
```

### Take 1 — the form (~45 s)

*534 fields, and nobody types them.*

1. `BPO_TEMPLATE_Standard.pdf` open in a browser tab. Hold **3 s**.
2. Scroll page 1 slowly, top to bottom — about **8 s**.
3. Page 2. When **III. COMPETITIVE CLOSED SALES** is fully in frame, **stop and
   hold 3 s**. That grid is the image the whole video is built around.
4. Page 3. Hold **2 s**.
5. Stop recording.

### Take 2 — the documents (~30 s)

*Papers the agent already has.*

All eight `cantrell_*.pdf` are already open in tabs — you opened them before
recording.

1. Click through the tabs slowly: `cantrell_tax`, `cantrell_scope`, then one
   sold and one active. **Hold 4 s on each.**
2. On `cantrell_sold1.pdf`, put the cursor on the **sale price** and hold
   **3 s**. Remember this number; take 5 comes back to it.

### Take 3 — handing them over (~50 s)

*Upload, don't type.*

1. Instafill, on **Forms**. Hold **2 s**.
2. Upload `BPO_TEMPLATE_Standard.pdf`. Wait for processing. If a field count
   appears anywhere, **hold 4 s** on it.
3. Start filling the form out, and add the **eight** documents — all eight at
   once, not one by one. Hold **4 s** when they are listed.
4. **Submit.** Hold **3 s**, and keep your hand resting where the phone can
   see it -- this is cutaway #1.

### Take 4 — the fill

1. **Hands off the mouse completely.** No scrolling, no cursor movement.
2. Let it run to the end. Hold **3 s** after it finishes.

The edit speeds this up; a motionless cursor is what makes that read as
deliberate rather than broken.

### Take 5 — the result (~70 s)

*The numbers are in the right cells — and you can check.*

1. The filled form. Hold **3 s** — hand visible to the phone again, cutaway
   #2.
2. Scroll to **III. COMPETITIVE CLOSED SALES**, framed so the SUBJECT column
   and all three COMPARABLE columns are visible. Hold **5 s**.
3. **The verification shot — the most persuasive ten seconds in the video.**
   Put `cantrell_sold1.pdf` beside the filled form. Move the cursor to the sale
   price on the listing sheet, hold **3 s**, then move it slowly to **the same
   number** in the grid and hold **3 s**. This is the difference between "it
   filled something in" and "it filled in the right thing".
4. Scroll to **IV. COMPETITIVE LISTINGS**. Hold **4 s**.
5. **Download PDF.** Hold **3 s** on the downloaded file.
6. Stop the screen recording, then stop the phone.

---

## Part 5 — what you do NOT have to care about

- **Length** — dead air is removed automatically.
- **Mistakes** — hold still three seconds, redo.
- **Order** — takes are assembled from this list, not from timestamps.
- **Sound** — discarded from both cameras.
- **Wording** — there is none; the script is written to the finished picture,
  so nothing you record can contradict it.

When the five screen files and the one phone file are in
`projects/bpo-realtor/sources/`, say so. Nothing else is needed from you until
there is a cut to watch.
