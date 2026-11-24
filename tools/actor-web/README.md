# actor-web

An actor pack's pictures drawn in a model's own web app (Gemini) in a browser already signed in,
instead of through OpenRouter: `actor-pack.py --external <dir>` lists each missing picture, the
page draws it, and the next `actor-pack.py --external <dir>` run takes it and gates it like any
other (drift, retakes). Made 2026-11-19 for the Warriors cats, when OpenRouter's credit ran out.
Gemini's edits gated at 0.2-0.3 % drift (GPT Image 2.6: 0.0-0.1 %).

Not part of the `scripts/` pipeline (a page script and a stdlib server), so it skips `_env` and
check-script on purpose.

## Use

```bash
python scripts/actor-pack.py --spec <spec> --external <dir>          # lists <dir>/jobs.json, refs/
python3 -I tools/actor-web/receiver.py <dir>                           # leave running (port 8899)
```

In the Gemini tab (gemini.google.com/app), with the Claude browser extension's javascript tool:
paste the whole of `gemini.js` (the page's Trusted Types forbid eval, so it cannot load itself),
then

```js
await AW.setup();            // opens the receiver popup
await AW.load([...done]);    // queues jobs.json, skipping keys already in out/
AW.start();  AW.status();
```

Then run `actor-pack.py --external <dir>` again: it gates what came back and lists the next round
(a mouth waits for its face; a turned pose's mouths for the pose).

## Traps (all met on the first run)

- **The picture's address.** The page shows a preview from `.../gg-dl/<id>=s1024-rw?...`; `=d-I`
  answers with the original's address as text, twice (`rd-gg-dl ...=s0-d-I`), then the picture.
  Gemini draws about 842x1264; its own "Download full size" saves the same picture enlarged 2x into
  the Downloads folder, so the button is never pressed.
- **Resource timings fill up** at 250 entries and stop recording: `setResourceTimingBufferSize`.
- **"New chat" on an empty chat keeps the last draft** (attachments and text): the runner clears
  the composer before each job.
- **Uploads are refused** after about ten in three minutes: a red mark on the attachment and Send
  `aria-disabled`. The runner waits 12 s between jobs and 2 minutes after a refusal.
- **Slow spells.** After ~25 pictures Gemini took 3-5 minutes a picture, with chats that did not
  open; each job has a 5-minute limit and three tries.
- A picture drawn for a prompt that has since changed is set aside (`out/<key>_stale.*`) by
  actor-pack.py and the job listed again.
