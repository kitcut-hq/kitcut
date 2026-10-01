# This pass: scene {K} of {N}, `{ID}`

You write one scene of a film made in scenes (see "This film is made in scenes"), and only
`{FILE}`. {EXISTING}

**The scene:** {TITLE}
Shows: {SHOWS}
Notes: {NOTES}
It runs {START}-{END} s on the film clock (local time 0-{LOCAL_END} s). Its narration, with each
word's time:

{LINES}

**The look**, in the director's words: {STYLE}

**The scene before:** {BEFORE}
Its last frames: {SHEET} -- Read it, and pick up where it leaves off so the cut reads.
**The scene after:** {AFTER}

**film.js**, the shared look (SK.look holds the helpers):

```js
{LOOK}
```

**Helpers the scenes before yours added** to `SK.look` -- use them rather than writing your own:
{SHARED}
A helper another scene could use (a renderer, a label style, a recurring object) goes on the shared
look, at the top of your file with a one-line comment above it -- `// a medal on a ribbon` then
`SK.look.medal = (x, y, o = {{}}) => {{...}};` -- and the scenes after yours are shown it here.

Work: write the scene (a long one in parts), `check`, render `stills` inside {START}-{END} and
look at them, fix, and run `motion` once if the scene moves a lot. Then stop with two sentences:
what the scene shows and how it ends -- the scene after reads them. Working time: about {MINUTES}
minutes.
