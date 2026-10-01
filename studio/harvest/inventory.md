# Inventory brief: what does each film's code draw, and what is re-invented?

Context. kitcut.ai's studio makes animated films. For every film, Claude (Opus) writes JavaScript
(`film.js`, sometimes `scenes/*.js` and `cast/*.js`) on top of a shared engine:
`sketch/engine.js` (SK.*: ink/wash/hatch strokes, shapes S.line/ell/arc/poly/rrect/path, SK.txt text,
SK.card, SK.check, SK.spark/heart/puff/sparkle/dashes, SK.sky/band/stars, SK.kf keyframes, easing E.*,
pop/clamp/lerp/inv/mix, SK.w(line, word) voice-word timing, SK.image pictures), `sketch/props.js`
(SK.P.*: faces, ticket, person + poses, plane, laptop, table, floor, lightbulb, rocket, padlock, coin,
stamp, pokeHand, browser, thoughtBubble, confetti, kid + poses, phone, window, house, siren, drone,
missile, stopwatch, debris, tree, bush, cloud, sun, moon, mountain, building) and, for the collage
look, `sketch/collage.js` -- and `sketch/kit.js`, the pieces already lifted out of earlier films. Read the header comments of those files in `sketch/`
first (top ~60 lines of each, plus grep for `SK\.[A-Za-z]+ =` / `P\.[a-z]+ =` / `L\.[a-z]+ =`) so you
know what already exists.

Claude spends ~24 h of generation across ~90 films in 3 days, mostly deciding and writing this
code. We want to find the pieces Claude keeps building from scratch, so they can become tested,
parameterised library components it calls in one line instead.

## Your job

For EACH film folder in your batch, read all of its code (`film.js`, `scenes/*.js`, `cast/*.js`;
`studio.json` has the prompt, look and length). List every distinct visual/motion component or
helper the film builds. Skip trivial one-liners and the film's story-specific choreography.

For each component record:

- `film`: the folder name (studio-YYYYMMDD-HHMMSS-xxxxxx)
- `cat`: one of the categories below (add a new `cat` only if nothing fits)
- `what`: a GENERIC name for the component, the way a library would name it
  (e.g. "outlined title text", "phone with chat messages", "bar chart growing", "logo on a plate",
  "number counter ticking up", "map with route and pins") -- not the film's own function name
- `fn`: the film's own function/const name(s), if any
- `desc`: <= 25 words: what it draws and how it animates
- `built_with`: which existing SK./SK.P./collage helpers it uses, or "hand-rolled"
- `exists`: the existing library equivalent if there is one (e.g. "SK.P.phone", "SK.card"), else ""
- `why_not_existing`: if an equivalent exists but the film did not use it, the likely reason
  (needed a feature it lacks / different look / unknown) -- short
- `chars`: approximate characters of code it took
- `reuse`: 0 = only makes sense in this film; 1 = reusable with parameters; 2 = generic boilerplate
  every film needs (math/easing/colour/layout/text utilities)
- `params`: for reuse>=1, the parameters a library version would need (short list)

Categories:
text (titles, outlined/two-tone text, kinetic type, captions, tags/chips/pills, lower thirds,
quote cards, counters, checklists), ui (phone/laptop/browser/app screens, chat bubbles,
notifications, forms, terminal/code, cursor/taps), dataviz (bar/line/pie charts, meters/progress,
timelines, tables, maps/routes/pins, flow diagrams, comparisons, icon grids), brand (logo plates,
wordmarks, end cards/CTA, title cards, handle/URL stamps, palette from brand colours, watermark),
fx (glow, burst/impact, whip/swoosh, transitions/wipes, camera moves/parallax, particles, shake,
spotlight, ripples), scenery (sky/sea/ground, buildings, vehicles, nature, weather), objects
(money/coins, documents/paper stacks, parcels, clocks, calendars, tools, food...), characters
(people/kids/animals, faces/expressions, lip-sync mouths, poses/walks), structure (scene switching,
chapter tracker, keyframe/timing helpers, VO word-cue helpers, layout grids/safe areas,
easing/math/colour utilities, image/picture placement).

## Output

Write ONE JSON file: `<pull>/inventory/batch-<N>.out.json`, an object:

```json
{"films": [{"film": "...", "look": "...", "length": "...", "prompt": "<first 120 chars>",
            "summary": "<one line: what the film is>", "components": [ {...}, ... ]}],
 "notes": "<anything striking across your batch: repeated patterns, things the engine lacks,
           boilerplate every film carries -- up to 15 bullet lines>"}
```

Be thorough and concrete; `chars` estimates may be rough. Do not modify any file other than your
output. Finish by replying with a 5-line summary of your batch.
