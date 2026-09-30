# The people (`SK.head`)

The person added people to this film: photos of real people, each drawn by the studio as a
character in a chosen style (a crayon drawing, a paper cut-out, a felt puppet...), with mouth
shapes and a blink of its own. The first message lists them: their id (`p1`...), their name when
given, the style, and anything to know. They are the film's speakers: each says their own lines.

- `SK.head(id, x, y, h, o)` draws a person with the middle of their face at x, y and the face h
  tall (the picture is their head and shoulders, about 2.5 h tall); it returns `{x, y, h, open}`.
  o: `alpha`, `flip` (mirror), `tilt` (radians), `shadow` (true), `nod` (1: a small nod on their
  words; 0 for none). The mouth moves by itself on their own lines and the eyes blink by
  themselves: never draw a mouth or eyes over them. Draw a person every frame they are on screen;
  they enter, move and scale like any picture (inside `SK.at`, `SK.alpha`, or a layer).
- `SK.headBox(id, x, y, h)` is the box `[x0, y0, x1, y1]` that person fills when drawn so; this
  helper fits one into a box:

```js
function fit(id, cx, cy, w, h, o = {}) { // a person, as big as fits a w x h box centred on cx, cy
  const b = SK.headBox(id, 0, 0, 100), s = Math.min(w / (b[2] - b[0]), h / (b[3] - b[1]));
  const bb = SK.headBox(id, 0, 0, 100 * s);
  return SK.head(id, cx - (bb[0] + bb[2]) / 2, cy - (bb[1] + bb[3]) / 2, 100 * s, o);
}
```

- In `vo.json`, `cast` gives each person a voice, `{"p1": {"voice": "Puck", "style": "..."}}`
  (Read their photo in `inputs/` to cast it), and a line says who speaks it:
  `{"who": "p1", "text": "..."}`. A line without `who` is a narrator in the film's own `voice`.
  Only the person speaking moves their mouth, so several can share the frame.
- `SK.speaker(t)` is the id speaking at t (or `''`); `SK.talk(id, t).on` whether one is.
- The picture tools wait until the people are drawn (a minute or so). A person the studio could
  not draw is named in the tool's answer: show their photo instead with `SK.image('<id>', ...)`.

