# bpo-realtor — recording plan

For the person holding the mouse. **You do not speak.** Every word of this
video is written afterwards and spoken by ElevenLabs, so the recording carries
picture only. That is deliberate: it removes retakes for stumbles, and it
removes the lip-sync problem a written voice-over over a face would create.

Five short takes, not one long one. A fumble then costs one take, not the day.

---

## Part 0 — what the previous video got wrong

Read this first; it is the whole reason for the checklist below. Frames pulled
from the published `neaCnEawvbk` (1920x1080, 9:14):

| at | what is on screen | why it hurts |
|---|---|---|
| 0:52 | bookmarks bar reading `hipa.ai`, `crowd links`, `Re: Do you assembl…` (two Gmail threads) | private working context on a public product video |
| 2:56 | five browser tabs titled `(anonymous)` | looks like a debugging session, not a product |
| 6:20 | the webcam bubble sits **on top of the adjustment grid** | it covers the exact thing the video exists to show |
| throughout | taskbar, system clock, notification area | nothing to do with the product |

None of these are editing mistakes. They are **recording** mistakes, and no
amount of cutting afterwards fixes the first two.

---

## Part 1 — prepare the machine (15 minutes, once)

**Screen**
- Display resolution **1920x1080**. If the laptop panel is larger, set it to
  1920x1080 for the recording — a downscaled 4K screencast reads soft, and the
  vertical short cut out of it reads worse.
- Nothing on the desktop wallpaper worth reading.

**Browser — use a clean profile**
- Chrome → profile icon → **Add** → a new profile with no name, no sync, no
  extensions. This is faster and safer than tidying the working profile, and
  the working profile stays untouched.
- Hide the bookmarks bar: **Ctrl+Shift+B**.
- Exactly **one tab** open. Close everything else.
- **Zoom to 125 %** (Ctrl and `+` twice). This is not cosmetic: the vertical
  short only keeps a middle band of the screen, and at 100 % the form's
  labels are unreadable there.

**Windows**
- Notifications off: **Win+N** → Do not disturb ON. One Slack toast mid-take
  and the take is gone.
- Quit Telegram, Slack, mail, anything that can pop.
- Clock and taskbar can stay; the edit crops them.

**Webcam: OFF.** Not minimised — off. There is no face in this video.

---

## Part 2 — the recorder

Use the **Windows 11 Snipping Tool**, which records video and needs no install:

1. **Win+Shift+S**
2. In the little toolbar at the top, switch from the camera icon to the
   **video camera icon**.
3. Drag a rectangle over the **whole screen** (or click the full-screen
   option).
4. **Start** → a 3-second countdown → record.
5. **Stop** → Save → into `projects/bpo-realtor/sources/`.

> **Do not use the Xbox Game Bar here.** It refuses to record File Explorer and
> the desktop — and take 2 is File Explorer. It was fine for `books-giveaway`
> because that was browser-only.

Name the files exactly:

```
take1-form.mp4
take2-documents.mp4
take3-upload.mp4
take4-fill.mp4
take5-result.mp4
```

Audio does not matter — record it or don't, it is discarded.

---

## Part 3 — how to move

Four rules, and they matter more than anything else here:

1. **Move the mouse slowly.** A cursor that snaps across the screen cannot be
   followed at 1080p, and cannot be followed at all in a vertical crop.
2. **Pause two full seconds** before and after every click that matters. Those
   pauses are where the cuts land and where the voice-over breathes. Count them
   out; two seconds feels much longer than it is.
3. **Never talk. Never apologise to the screen.**
4. **If you fumble:** stop, hold still for three seconds, then redo the action
   from its start. The still moment is what lets the edit remove the fumble
   cleanly. Do not restart the take.

---

## Part 4 — the five takes

Everything lives in `projects/bpo-realtor/assets/forms/`. Copy that folder's
nine PDFs somewhere ordinary first — `Downloads` is fine and is what the old
video used.

### Take 1 — the form itself (~45 s)

The beat: *534 fields, and none of them get typed.*

1. Open `BPO_TEMPLATE_Standard.pdf` in the browser. Hold **3 s**.
2. Scroll page 1 slowly, top to bottom, about **8 s**.
3. Same for page 2. When the **COMPETITIVE CLOSED SALES** grid is fully in
   frame, **stop and hold 3 s**. That grid is the image the whole video is
   built around.
4. Same for page 3. Hold **2 s** at the end.
5. Stop recording.

### Take 2 — the documents (~25 s)

The beat: *these are papers the agent already has.*

1. File Explorer, open on the folder with the nine PDFs. **Details** view,
   sorted by name, so the file names are readable. Hold **3 s**.
2. Double-click `cantrell_sold1.pdf`. Let it open. Hold **5 s** — long enough
   for a viewer to see it is a real listing sheet with a price on it.
3. Close it. Back to the folder. Hold **2 s**.
4. Stop recording.

### Take 3 — handing them over (~50 s)

The beat: *upload, don't type.*

1. Instafill, signed in, on **Forms**. Hold **2 s**.
2. Upload `BPO_TEMPLATE_Standard.pdf`. Wait for it to finish processing.
   **Hold 4 s** on whatever it says about the form — if a field count appears
   anywhere on screen, hold on it.
3. Start filling the form out.
4. Add the **eight** `cantrell_*.pdf` documents. Select all eight at once
   rather than one at a time. Hold **4 s** once they are all listed.
5. Submit. Hold **3 s**.
6. Stop recording.

### Take 4 — the fill (~however long it takes)

1. Start recording **before** you submit if that is easier; overlap is fine.
2. **Hands off the mouse entirely.** Do not scroll, do not move the cursor.
3. Let it run to completion. Hold **3 s** after it finishes.
4. Stop recording.

The edit speeds this up. A still cursor is what makes that look deliberate
instead of broken.

### Take 5 — the result (~70 s)

The beat, and the most important one in the video: *the numbers are in the
right cells, and you can check.*

1. The filled form, open. Hold **3 s**.
2. Scroll to **III. COMPETITIVE CLOSED SALES**. Frame the grid so the SUBJECT
   column and all three COMPARABLE columns are visible. Hold **5 s**.
3. Now the verification shot. Open `cantrell_sold1.pdf` in a second window,
   side by side with the filled form. Move the cursor to the **sale price** on
   the listing sheet, hold **3 s**, then move it to **the same number** in the
   grid and hold **3 s**. Slowly. This single move is the most persuasive
   thing in the video — it is the difference between "it filled something in"
   and "it filled in the right thing".
4. Close the second window. Scroll to **IV. COMPETITIVE LISTINGS** (the active
   ones). Hold **4 s**.
5. Click **Download PDF**. Hold **3 s** on the downloaded file.
6. Stop recording.

---

## Part 5 — what you do NOT have to care about

- **Length.** Take as long as you like; dead air is removed automatically.
- **Mistakes.** Hold still for three seconds and redo. That is all.
- **Order between takes.** They are assembled from this list, not from
  timestamps.
- **The wording.** There is none — the script is written to the picture
  afterwards, so nothing in the recording can contradict it.
- **Sound.** Discarded.

When the five files are in `projects/bpo-realtor/sources/`, say so. Nothing
else is needed from you until there is a cut to watch.
