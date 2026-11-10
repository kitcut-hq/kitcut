# The actors (`SK.actor`)

The project has actors: characters an image model drew once, full length, and redrew with each
face, mouth shape, blink and pose, cut into pieces the engine swaps. The first message lists them:
their name, who they are, their faces and poses, and their sheet (`actors/<name>/check.jpg`,
every piece laid out and named: Read it before you use one). They are the series' recurring
characters: bring them in where the episode has a part for them, and let them speak their own lines.

- `SK.actor(name, x, y, h, o)` draws an actor standing with its feet at x, y and the whole figure
  h tall (every pose at the same scale). o: `face` ('neutral' or one of its faces), `pose` (null
  for the front figure, or one of its poses), `flip` (mirror, to face the other way), `tilt`
  (radians, about the feet), `squash` (+ squashes, - stretches, about the feet), `alpha`, `bob`
  (0 to keep it still while it talks). It returns `{box, head, mouth}`: where it and its head are
  this frame (`[x0, y0, x1, y1]`). Draw it every frame it is on screen.
- The mouth moves by itself on its own lines and the eyes blink by themselves: never draw a mouth
  or eyes over it, and never redraw it in your own code. It is a picture: it never changes outfit,
  grows a prop or walks. Make it act by changing face and pose on the words (`SK.cues`), holding
  each for a second or more, and by where you put it: it slides on, it pops in with a squash
  that dies away (`squash: Math.exp(-dt * 9) * Math.sin(dt * 30) * .05`), the camera moves to it.
- A face shows on the front figure and on the poses that still look out of the picture. A pose
  marked (turned) has turned away: it shows no face, only its own mouth, so use it with 'neutral'.
- It speaks only in the faces listed as the ones it speaks in: in any other face the mouth stays
  shut, so give it one of those while its line plays.
- Its voice: in `vo.json`, `cast` gives it a voice, `{"<name>": {"voice": "Puck", "style": "..."}}`,
  and a line it says names it: `{"who": "<name>", "text": "..."}`. Only its own lines move its
  mouth; a narrator's line (no `who`) does not, so the narrator and the actor can share a film.
- `SK.actorBox(name, x, y, h, o)` is `{box, head}` without drawing it (to place a speech bubble,
  a label, the camera); `SK.actorHas(name)` is `{faces, poses, talk}`.
- The pieces were drawn about 1400 px tall: keep the figure no taller than that on screen (camera
  zoom included) or it softens. Draw what it stands among in its manner -- the line weight and the
  colours of its sheet -- so it never looks pasted on.

