# This film is made in scenes (this section comes first where it differs from the ones above)

This film is too long to write as one film.js in one conversation, so it is made in passes, each
a conversation of its own, and your first message says which one you are:

- the **director** writes and records the narration (`vo.json`), writes `film.js` as the shared
  look, plans the scenes (`scenes.json`) and writes scene 1, the pilot;
- each **scene** is written by a conversation of its own, which may write only its own file,
  `scenes/NN-slug.js`;
- the **editor** looks at the whole film, fixes what breaks between scenes, and writes `score.json`
  and `sfx.json`.

Where the sections above speak of film.js's `draw`, of "How to work" and of keeping film.js under
200 lines, this is how it is instead:

- `film.js` -- the look every scene shares, and nothing else: the first line `// For: ...`, the
  style and the ground, the palette and fonts, the helpers every scene uses exported as
  `SK.look = {...}`, the camera, and `SK.film({duration: <the film's length>, camera})` with **no
  draw** -- the film draws its scenes. Keep it under about 300 lines: every scene reads it.
- `scenes.json` -- the plan: `{"scenes": [{"id": "01-orbit", "title": "...", "lines": [0, 4],
  "shows": "...", "notes": "..."}]}` -- ids numbered in order, each scene a stretch of narration
  lines [first, last], no gaps, no overlaps, every line in one scene, 12-75 s each once timed.
- `scenes/NN-slug.js` -- one scene:

```js
const L = SK.look; // the shared helpers from film.js
SK.scene({
  id: '03-first-failure', lines: [9, 14],
  draw(t, local, vis) { /* local: seconds since this scene began; t: the film clock, for SK.w cues */ },
  // camera: SK.camera([[0, [0, 0, 1]], [8, [400, 0, 1.2]]]),  // optional, on local time
  // out: 0.5,                                                 // optional: cross-fade into the next scene
});
```

  A scene starts 0.3 s before its first line is spoken (the first scene at 0) and lasts until
  the next one starts; during a cross-fade the next scene is drawn from just before its start
  (local < 0), so clamp. Draw it in its own space and time, cue it to its own words with `SK.w`,
  and rely on nothing another scene defines -- only film.js, the engine, the props and the cast.
- In a scene's pass, `stills` and `motion` look only at that scene's stretch of the film.
- End each pass with the short summary its first message asks for: the passes after you read it.
