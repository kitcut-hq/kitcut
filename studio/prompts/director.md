# This pass: the director

This is a {LENGTH}-second film made in scenes (see "This film is made in scenes"). In this pass,
and only this:

1. Decide who the film is for and its mood (film.js's first line), its look, its voice and its
   music.
2. Write the narration in vo.json and record it (`voice`). A long film is a sequence of sections:
   let each end on a short pause.
3. Write film.js: the shared look only -- no scene in it, no draw.
4. Plan the scenes in scenes.json: 12-75 s each, every narration line in exactly one scene, in
   order. Say in `shows` what each scene shows, concretely enough that another animator can draw
   it from that alone; put in `notes` what must carry over (a character, a colour, an object).
5. Write scene 1, `scenes/01-<slug>.js`, as the pilot: it sets the look every later scene copies.
   `check`, render `stills` of it, look at them, fix.
6. Stop with one paragraph for the animators of the other scenes: the look in words (line weight,
   how the palette is used, where text sits, how things enter and leave) and the helpers in
   SK.look, with when to use each.

Do not write the other scenes, score.json or sfx.json: later passes do. Working time for this
pass: about {MINUTES} minutes.
