# comic-grok

Helper scripts for the owner's comic→panels workflow: turn each raw comic page
into clean 9:16 vertical panels (via Grok on the web, driven by the browser
automation tools) plus the page's text, ready for a self-hosted video model to
animate. These are small stdlib/Pillow utilities — **not** part of the video
pipeline under `scripts/`, so they skip the `_env` bootstrap and `check-script`
conventions on purpose.

The full procedure (how to drive Grok efficiently without screenshotting each
page, the lazy-load scroll step, ad detection, the one-download-per-chat rule,
the Disney-name refusals on Gemini/Flow) lives in the agent memory
`comic-to-flow-process`.

## Output layout

```
<root>/page-NN/
  scene-01.jpg scene-02.jpg ...   one 9:16 panel per scene, reading order
  scene-NN_old.jpg                backup kept when a panel was recomposed
  text.txt                        the page's script (captions/dialogue/SFX)
  page.json                       {page, kind, panel_count, scenes, has_text,
                                   needs_redraw, caption_only, note}
<root>/_skipped/page-NN/          ad/cover pictures set aside (text.txt kept)
```

## Scripts

Run each with `-I` (downloads are untrusted; `-I` ignores a planted module
beside them):

```bash
# split a downloaded .bundle into scene-NN.jpg
python -I tools/comic-grok/unbundle.py goofy-page-05.bundle "<root>/page-05"

# (re)write page.json for every page — edit the ADS/COVER/REDO/... tables first
python -I tools/comic-grok/pagejson.py "<root>"

# one contact sheet of the whole book (needs Pillow)
python -I tools/comic-grok/sheet.py "<root>" goofy-contact-sheet.jpg
```

The in-browser grabber that produces a `.bundle` (collect the message bubble
with the most `/generated/` images, `fetch` each with credentials, concat as
`IMG <len>\n<bytes>`, anchor-download) is run through the browser tools, not
from here — see the memory for the exact snippet.
