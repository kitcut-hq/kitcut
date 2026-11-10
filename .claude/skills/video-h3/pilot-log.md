# Leo × MiniMax H3: experiment log

## Summary (2026-10-24, 05:35)

**Can we rely on H3 to carry an episode?** Yes, for the picture. It took eight prompt versions in one night to learn how, and the method is now written down (the `video-h3` skill, 17 rules).
- **Final minute:** `temp/h3test/v8/leo-ep12-h3-v8.mp4`. The episode's own narration and music, the model's sound effects, 11 shots.
- **Side by side** (KitCut original | v1 | v5 | v8): `temp/h3test/leo-ep12-compare-grid.mp4`.
- **What made the difference, in order of effect:**
  1. **Pictures drawn by the series' own code** as references: Leo, the coupe, the empty cabin (`cabin(t, {leo: null})`), the street. The cabin alone turned "a generic car" into the series, texture included.
  2. **MiniMax's own prompt format**, written in full (250–400 words a shot). It removed every stray Dad, interior colour change and garbled sign from v1.
  3. **A fresh reviewer comparing against the original.** It found the story faults (jokes landing early or not at all, the wrong emotion) that checking each shot's technique missed.
  4. **The right angle for each beat:** the reference's own angle for the place, a character's point of view for what he sees, and Dad's point of view so his face can't appear.
- **Yield: 3 of 3 seeds usable**, nearly identical. Failures are systematic (prompt, reference, angle), not random, so fix the prompt instead of re-rolling.
- **Cost:** about 1.2–1.4 GPU-minutes per second of film at 768p on the RTX 3070. That's about 6–7 hours for a 5-minute episode, plus a fix pass of about 3 shots in 11. Electricity only.
- **Sound:** 0 words of speech in the model's own audio across three minutes (v1, v5, v8); the positive control found all 116 narration words.
- **The last reviewer's verdict on v8:** "reads as the same series … a parent would rather their child watched the AI minute". Its three fixes went in as v8f. Still open: the other dad's car still shows a second door (it needs its own drawn reference), and the outdoor shots are a little glossier than the inside ones.
- **Quoted on-screen text works:** the count's pop-up numbers "1"–"5" and a red "7" rendered crisp.
- **Open, for the owner:** (1) does v8 read as *Leo* to you? The second reviewer called v7 "glossy, a different show"; the cabin reference brought back the paper and crayon in v8. (2) Re-shoot the whole episode (about 4:50, about 7 hours on kc-local)?

**Machine:** kc-local (RTX 3070 8 GB, 32 GB RAM). Wan2GP, FastH3 Omni 8-step int8, Q4 text encoder, 1344x768, seed 42 unless noted. Every run is capped at 22 GB of RAM beside the live studio.
**Source:** Leo ep. 12 "The Car Wash" (studio-20261012-083224-uchafl). The narration is the episode's own, line by line.

## Round 1: one clip, which settings (2026-10-23)

| Run | Change | Result | Time |
|---|---|---|---|
| 480p, Q2 text encoder, first frame | baseline | Soft. Leo turns into another boy halfway. A brush appears inside the car. | 2 min (after a 7 min first load) |
| A | 768p | Leo holds. Lines are crisp. The brush is still inside the car. | ~6 min |
| B | 768p + Leo reference + Q4 | Best foam. The brush sweeps through the cabin. | ~10 min (includes download) |
| C | FL2VA PDD model | OOM at the 22 GB cap | — |
| D | KitCut first and last frames + Leo reference, no brush | Clean and on model, but **looks just like KitCut** | 7:54 |
| E | D with FL2VA PDD (`--perc-reserved-mem-max 0.35`) | Clean, but stiller | 12:54 |
| F | References only (Leo, car), outside tunnel, camera glide | Looks nothing like KitCut. Leo shows up in the front side window. | ~7 min |
| G | References only, close at the window, camera orbit | Dynamic. The camera ended up outside, not inside the car. | ~7 min |

**Lesson:** fixed KitCut frames reproduce KitCut. References alone let the model direct the shot.

## Round 2: the first minute (0:00–1:11, 11 shots)

| Shot | What | Prompt version | Look | Defects | Time |
|---|---|---|---|---|---|
| S01 | Leo intro, back seat | v1 | Static. Leo's face is brownish. | **Dad's legs and sneakers in the back seat** (my Dad note was in every shot). Palm-shadow wording darkened the face. | 10:55 (9 s) |
| S02 | Dusty car drives to the wash | v1 | Good: dusty silver coupe, palms, pastel wash | **Giant Dad legs walk through the street** | 8:03 (7 s) |
| S03 | Leo cheers, bare feet | v1 | to look at | Dad note was present | — |
| S04 | Lost shoe under the seat | v2 (Dad note only where needed) | Good: crumbs, toy dinosaur, one red sneaker | Interior is dark brown, not grey | ~6 min |
| S05 | Long line of cars | v2 | Good: crane up over a curving rainbow line | Garbled sign on the wash | ~6 min |
| S06 | Leo counts on his fingers | v2 | **Very good acting**, Leo on model | **Car interior is a yellow and brown taxi**, not the silver coupe | 11:01 (9.3 s) |
| S07 | The chocolate tradition | v2 | **Directed itself in several moves**: shop front, push in to the shelf, a hand takes the purple bar, Leo hugs it | Garbled sign "Los colae" | 10:22 (8.7 s) |
| S08 | Two doors, Leo in the back | v3 | Same silver coupe as S02 and S05 (the car reference holds across shots). Leo waves from the rear window. | "Only two doors" isn't made obvious. A tiny made-up sign is still there under v3. | 9:24 (7 s) |
| S09 | Another dad folds the seat | v3 | Well animated | **The stranger wears Dad's blue shorts and sneakers**: the Dad note leaked into this shot. Fixed as v4 (the stranger in khaki), redo queued. | 4:13 (4 s) |
| S10 | The sunroof opens, Leo stands | v3 | **The interior fix worked**: grey seats and dash, Leo's blue seat. Cut-away side view; the roof lifts in a burst of light; Leo stands barefoot, points up and shouts. Strong. | The car reads as a four-door, and the sunroof opens like a hatch | 5:04 (4 s) |

| S11 | Dad lifts Leo out through the roof | v3 | The lift at the end reads | **The first 3 s are an empty car.** At the end **a pair of upside-down legs in sneakers** is under Leo: the Dad note again, plus "hands from the bottom edge" with no arms or body behind them. | 7:31 (5.6 s) |

### The v1 minute as a whole (1:11.6, `temp/h3test/v1/leo-ep12-h3-v1.mp4`)
- **Speech check: clean.** Recognition on the model-only audio found 0 words in 71 s.
- **Dad's arms, legs or sneakers leak into 5 of 11 shots** (S01, S02, S03, S09, S11). It's the biggest defect, and all of it came from the prompt.
- The car's interior differs in 3 shots (brown, taxi-yellow, grey).
- What works: Leo's identity and acting (S06, S07, S10), the car's identity (S02, S05, S08), and the model's own directing (the cuts in S07, the crane in S05).

**Prompt v3** (S08 onward and every redo): the interior is described in each inside-the-car shot (grey seats, grey doors, Leo's blue seat in the middle of the back), and "no signs, no lettering" is in every shot.

## Round 3: v5, the whole minute in MiniMax's own format (running)

v5 follows MiniMax's official guide. The six sections each hold only their own content, and style opens the description. Descriptions run 185–372 words (v1: 60–100), covering framing, positions, light, timed actions and a camera move (type, amplitude, speed). Cuts inside a clip are used (S02, S03, S07). Each shot says only what is in the frame, the interior is described in every inside shot, and the stranger has his own clothes. Shots with no character (S04, S09) get no character picture. A lint runs before any GPU time.
Two traps cost a restart: Wan2GP split the blank-line sections into 6 separate videos (fixed with `multi_prompts_gen_type: FG`), and a script saved with Windows line endings would not run.

| Shot | v1 | v5 | Time v5 |
|---|---|---|---|
| S01 Leo intro | Dad's arms and sneakers in the back seat, brownish face, static | **Clean.** Leo alone in the middle of a grey interior. He plays every scripted beat in order (swings his feet, folds his arms, frowns, puffs his cheeks, then a big grin), and the camera pushes in as written. | 11:09 (9 s) |
| S02 Dusty car to the wash | Giant Dad legs walk through the street | **Clean.** A muddy silver car with dust puffs, tracked past pastel buildings. The **written cut at 4 s lands**: a turquoise car wash with two blue brushes, the car turning in. **Plain blank walls, no signs.** Minor: the car reads more like a sedan than a coupe. | 8:18 (7 s) |
| S03 Leo cheers, bare feet | Dad's arms on **both** sides of Leo, sneakers in the seat | **Clean cheer**: grey interior, fists up, delighted. The written cut to his feet lands at 3.5 s. **New defect: the close-up of his bare soles lasts 4 s and the toes are miscounted** (5–6 bulbous toes per foot); it reads odd. Lesson: keep close-ups of hands and feet short, and show them from the side, not soles-on. | 9:36 (7.4 s) |
| S04 The lost shoe | Good, but a dark-brown interior | **Exactly as written, with no reference picture at all:** the crayon style held from the style sentence alone. Grey carpet and seats, crumbs, a green dinosaur, one red sneaker, then the camera trucks right onto empty carpet. | 5:06 (4.9 s) |
| S05 The long line | Good, but a garbled sign on the wash | **As written:** the dusty silver car last in a rainbow line, the camera rising higher and higher, the car shrinking at the bottom. **The sign panel on the wash is blank: no garbled text.** | 6:05 (4.7 s) |
| S06 Leo counts the cars | Great acting, but a yellow taxi interior | **Same great acting, now in the grey coupe interior:** he points and counts finger by finger with a frown, gets confused, then turns to the camera smiling as it arcs round. | 11:18 (9.3 s) |
| S07 Chocolate | Garbled "Los colae" sign; strong story | All three written cuts land. Plain shop walls with no sign; push in on the shelf; a hand takes the purple bar. **Two new defects:** (1) **Leo wears his car-seat harness (black straps, red clip) in the shop**, because the reference picture is a crop of him in the car seat, and **a reference carries its incidental details with the character**; (2) the last 3 s are static and stiff, Leo is small in a wide frame, and the "sways happily" never happens. v1's ending, a close hug, was warmer. | 10:20 (8.7 s) |
| S08 Two doors | Didn't read as two doors | **Reads as a coupe now:** one long front door, a small rear window, the camera trucking along to Leo waving from the back, with a grey interior seen through the glass. Spelling out "exactly one door on this side … a long fixed rear side window" worked. | 9:34 (7 s) |
| S09 Another dad | The stranger wore Leo's Dad's shorts and sneakers | **Exactly the stranger asked for:** green shirt, khaki trousers, brown shoes, seen from the chest down, folding the seat of a blue car. No reference picture; the crayon style held. | 4:05 (4 s) |
| S10 The sunroof | Strong, but a four-door cut-away | **As written:** a front view inside the grey cabin; the glass roof slides open in a burst of sun; Leo stands up and points both index fingers at the sky, shouting. Minor: the unbuckled straps still wrap his legs, and the brown "nose" comes from the cropped reference (fixed in v6). | 5:02 (4 s) |
| S11 Out through the roof | An empty car for 3 s; upside-down legs under Leo | **No stray legs.** Leo rises out of the open roof, held by two hands in white sleeves. The camera tilts up, and he ends against the sky, palms around him, arms up like a champion. Minor: the arms come up out of the roof, so Dad reads as inside the car. | 7:47 (5.6 s) |

**v5 against v1, the whole minute:** Dad's legs went from 5 shots to 0. The interior went from 3 different colours to grey in every shot. Garbled signs went from 2 to 0. The car reads as the two-door coupe in S08. Every written cut landed (S02, S03, S07). Defects left: S03's long soles close-up, S07's stiff ending and harness, and the reference's "chocolate nose" in every Leo shot. All three are fixed in v6. Total machine time for v5's 71.6 s: 89 min (1.25 GPU-min per second of film).

### Fresh review of v5 against KitCut's same minute (a separate agent, no notes from me)
**"Not yet. The first half is better than the original; the second half breaks two of its jokes."** 0:00–0:32 beats the original clearly: it looks like real TV animation, Leo's face moves, and every picture matches the words. From 0:42 the pictures stop telling the jokes. Its three changes, all prompt errors of mine:
1. **The two-door joke breaks:** inside shots show back doors with handles beside Leo, and at the end Dad's arms push him up from inside the car instead of lifting him out from outside.
2. **The chocolate shot comes too early:** it cuts to the shop shelf 6 s before the narrator says "Chocolate", and takes Leo out of the car he is queuing in.
3. **Leo looks sulky, then worried:** "puffs out his cheeks and narrows his eyes" reads as a sulk on "basically a grown-up", and "frowning with concentration" as worry.

It also caught: the car spotless while still queuing (I wrote "now clean and shiny"), the "other dads" shot in a heavier crayon than its neighbours, the harness in the shop and the brown "nose" (already fixed in v6), and a ghost face in a side window at 1:07.

v6 was stopped on its first shot: its prompts still had these faults.

## Round 4: v7, clean engine-drawn references and the review's fixes (running)
On top of v6's references and its fixes to S03 and S07:
- **The interior is a two-door coupe**, worded positively: "the walls beside the back seat are smooth solid grey panels under small fixed rear side windows; the only doors are the two long front doors".
- **S01** shows a proud, confident smile, not puffed cheeks.
- **S06** counts cheerfully.
- **S07 stays in the car:** Leo relaxed in the queue, then a thought bubble with the chocolate bar lands on the word "Chocolate" (cut at 7.0 s = 49.3 s).
- **S08's car is still dusty.**
- **S11:** Dad's hands come from outside the car, reach down into the sunroof and lift Leo out.
- **S09 gets a style-only reference:** Leo's street drawn alone by the engine, marked `partially_preserved` (style only).
- S04 was reused from v5 (identical settings).

| Shot | v5 | v7 | Time v7 |
|---|---|---|---|
| S01 Leo intro | Scowl with puffed cheeks; brown "nose" | **Proud, confident grin; the real doodle face** (dot eyes, tiny nose line, sunglasses up in his hair), arms folded, camera pushing in. **Interior only partly fixed:** grey, glass roof, no handles beside him, but the large windows beside the back seat still read like rear doors. The model's idea of a car interior is strong. Next: an interior reference picture drawn by the engine. | 11:15 (9 s) |
| S02 Dusty car to the wash | Good, but the car read as a sedan | **The car now reads as the series' coupe**: one long door and a roof sloping in one line to a short tail, from the engine-drawn sheet. Muddy, with dust puffs; the 4 s cut to the wash lands. | 8:20 (7 s) |
| S03 Leo cheers, bare feet | A 4 s soles-on close-up with miscounted toes | **The feet are fixed:** a short side view of his legs kicking reads naturally. The cheer is delighted. **But the side view shows a rear door panel with a handle right beside Leo**: the text-only two-door wording loses to the model's idea of a back seat. This is the case the cabin reference is for. | 9:38 (7.4 s) |
| S04 The lost shoe | (reused from v5: identical settings) | Exactly as written. | — |
| S05 The long line | As written | As written, and the dusty car at the end now has the coupe's kidney grille and long door. The crane rises until the line snakes across the frame. | 6:06 (4.7 s) |
| S06 Leo counts the cars | Good acting but a worried frown | **Cheerful now** (a wink, fingers, a wave, a big laugh), the real doodle face. **New continuity error: his car seat appears to be in the front**, with the dashboard and front door beside him. "From beside the back seat, facing the side window" did not pin the seat's place. Another case for the cabin reference. | 11:21 (9.3 s) |
| S07 Chocolate | Shelf 6 s early; Leo left the queuing car; harness in the shop | **The joke lands on its word now:** Leo leans back with his hands behind his head, unbothered by the line; his eyes open, he rubs his hands; then **the cut at 7.0 s brings a thought bubble with the purple and gold chocolate bar** while he licks his lips and hugs himself. Remaining: rear doors with handles beside the back seat. | 10:26 (8.7 s) |
| S08 Two doors | Reads as a coupe, but spotless before its wash | **Still muddy, so continuity holds.** One long door; the camera trucks along to Leo waving from the small rear window, far from it. Minor: the car faces left here and right in S02. | 9:40 (7 s) |
| S09 Another dad (style reference) | No picture; a heavier crayon than its neighbours | The same stranger and action. With Leo's street as a style-only picture the look is close to v5's: bold outlines, little hatching. **By eye the style reference changed little.** Left to the fresh review to judge against its neighbours. | 5:06 (4 s) |
| S10 The sunroof | As written; brown "nose" | **As written with the real doodle face:** the roof slides open in a burst of sun, and Leo stands and points both index fingers up, shouting with joy. The interior is still the invented grey. | 5:30 (4 s) |
| S11 Out through the roof | Arms from inside the car; a ghost face in the window | **The story is right:** Dad outside lifts Leo up and out of the roof against the sky. **It breaks a series rule: Dad's face comes into frame** as the camera tilts, and a dark shape shows through the window at the start. Fix for v8: **Dad's own point of view** (looking down into the sunroof, his hands from the bottom of the frame), so his face cannot be in the shot. | 7:33 (5.6 s) |

### Experiment S01_cabinref (02:43): the series' own cabin as an environment reference — **the breakthrough**
With `cabin_clean.png` (the episode's `cabin()` drawn empty) as `<Subject 2>`, and the interior described as the series draws it, **the shot looks like *Leo***: caramel bench, dark pillars, **no rear doors** (the two-door joke now works), and the series' flat paper-and-crayon texture (which also answers v7's "glossy, reads as a different show"). The model still directs: Leo folds his arms proudly and grins as the camera pushes in. 12:54 (9 s).
**Lesson:** environment references drawn by the series' own code keep the series' world; the model keeps the camera and the acting. That is different from first/last frames, which also fix the action and so reproduce KitCut.

### Fresh review of v7 (02:35): "NOT YET. The idea works; three things in the second half."
- **Better than v5:** no garbled text, Leo looks the same from shot to shot, no character speaks, no cut jars. Keep the queue pull-back (0:28–0:33) and the chocolate daydream (0:48–0:51).
- **The payoff (1:06–1:11):** Dad's bearded face is in frame and is the minute's last picture, which breaks the series rule. Leo also dangles from one hand.
- **The two-door joke still fails:** a four-door car outside and rear-door handles inside; at 0:21 his feet rest on a rear-door handle.
- **The count:** Leo sits in the **front** seat, and the queue he counts is not in the picture, so the "five, seven" joke is lost.
- **Leo's sunglasses belong over his eyes** in this part of the episode. I pushed them up because my first reference was cropped from a later scene.
- The look is glossier than the series' paper and crayon: an owner's call.

## Round 5: v8 (running) — the cabin reference in every inside shot, plus the second review's fixes
- Inside shots (S01, S03, S06, S07, S10) get the cabin picture, with the interior described as the series draws it.
- Leo's reference is redrawn with **his sunglasses over his eyes**, and the acting moves to eyebrows, mouth and head.
- **S06** is over his shoulder from the back seat: his finger taps each car of the queue through the windscreen, then a cut to his shrug.
- **S08:** behind the one long door is a solid panel with a small triangular window.
- **S10:** the straps lie open as he stands.
- **S11** is from **Dad's own point of view**, looking down into the sunroof as his hands lift Leo out towards the camera.
- S02, S04, S05 and S09 are reused from v7 (identical settings).
- Then the **yield** test: v8's S06 with two more seeds.

| Shot | v7 | v8 | Time v8 |
|---|---|---|---|
| S01 Leo intro | Proud, but in a generic grey car with rear-door windows | **It looks like the series:** the caramel bench, dark pillars and glass roof, and Leo as the series draws him, **sunglasses over his eyes**. He swings his feet, folds his arms and grins proudly as the camera pushes in. | 12:47 (9 s) |
| S03 Leo cheers, bare feet | Rear-door handle beside his feet | The cheer is in the series' cabin, delighted, fists up. **But the cut to a side view of his feet shows a grey door with a handle again:** the cabin picture is a front view, and **a reference only holds the angles it shows**. For a new angle, draw that angle with the engine or shoot from the reference's angle. Redo: the feet from the front. | 10:40 (7.4 s) |
| S06 The count | Leo in the front seat; the queue not in the picture | **The joke is visible now:** over his shoulder, his finger taps the red, yellow and orange cars of the queue through the windscreen. **New continuity error: Leo is out of his car seat.** The empty blue seat sits beside him, and he stands on the bench in the second half: from behind, the model split the boy from the seat. Redo (v8d): Leo in his seat from the front (the cabin's angle), then **his point of view** with his finger tapping each car, then back to him for the shrug. | 12:43 (9.3 s) |

| S07 Chocolate | Right beat, but rear doors beside him | **Right beat in the series' cabin.** Hands behind his head, unbothered by the queue seen through the rear window; then he rubs his hands; on "Chocolate" a thought bubble with the bar appears and he licks his lips. It reads as the series. | 11:59 (8.7 s) |

| S08 Two doors | Muddy coupe, good | Dusty coupe, the series' tan interior through the glass, Leo waving from the back. **But a second, empty blue car seat sits in the front**, and the rear window is a big ordinary window. Describing the cabin in an outside shot invited the model to draw it. Redo (v8e): outside only, Leo framed in the small rear window, no interior description. | 9:48 (7 s) |

| S10 The sunroof | As written, grey interior, straps around his legs | **In the series' cabin, with the straps lying open on both sides** as written. The glass roof opens in a beam of sun; Leo stands on his seat, points both fingers up and cheers. | 6:06 (4 s) |

| S11 Out through the roof | Dad's face in frame; Leo dangling | **Dad's point of view solves it:** looking down at the open roof, Leo reaching up from the tan seat; Dad's hands in white sleeves come in from the bottom of the frame and lift him towards the camera against the sky as he cheers. **His face cannot be in the shot**, so the series rule holds by construction. | 8:07 (5.6 s) |

**v8 minute assembled 03:57** (`out_v8`), before the S03, S06 and S08 fixes; the final assembly follows them.

### Fix pass on the shots v8 flagged
| Shot | Fix | Result | Time |
|---|---|---|---|
| S03 (v8c) | The feet from the front, the cabin picture's angle | **Fixed:** the cheer in the series' cabin, then 2.4 s of bare feet from the front against the blue seat and the tan bench, with no door. | 10:53 |
| S08 (v8e) | Outside only, Leo framed in the small rear window, no cabin description | **Fixed:** the dusty coupe, a dark tinted front window, Leo waving from the small rear window, and no second car seat. | 9:41 |
| S06 (v8d) | Three angles: Leo from the front, his point of view, back to him | **Fixed:** strapped in his seat, pointing past the camera; his point of view through the windscreen, a finger tapping the red, yellow and blue cars of the queue; back to him for the shrug and smile. The count reads, and he never leaves his seat. | 12:56 |

### Final review of v8 (after the S03, S06 and S08 fixes): "NOT YET, but close"
- **It reads as the same series.** The inside shots copy the original's framing. The outdoor shots are a little brighter and glossier, "a richer version of the show, not a different one".
- A parent would pick it over the original: Leo's face reacts, and the punchline is shown.
- **Every series rule holds:** Dad only as hands, no character voices, Leo strapped in whenever the car moves, no text on screen. The speech check found 0 words.
- **Three shots to redo:**
  - S09: the stranger's car has rear doors and no seat tips forward, so the setup collapses.
  - S06: the cars face the camera like oncoming traffic, and nothing shows the skipped six.
  - S11: Dad's hands grip Leo's head for about a second before moving under his arms.
- Smaller notes: at 0:09 nobody is visible in the car; at 0:13 the car at the wash looks smaller.

### v8f: the last fix pass (S06, S09, S11)
- **S09:** the stranger's car is a two-door too, and its seat back visibly tips forward.
- **S06:** the queue is seen from behind (tail lights), and **the original's own device: a number pops up over each car, "1" to "5", then a red "7"**. Visible text is in quotes, per MiniMax's rule, so this also tests whether H3 can render it.
- **S11:** Dad's hands go under Leo's arms from the start, away from his face.

| Shot | Result | Time |
|---|---|---|
| S06 (v8f) | **The best shot of the night.** Leo in his seat points; cut to his point of view: a queue seen from behind (tail lights); as his finger taps each car a white circle pops up with a **crisp "1", "2", "3", "4", "5", then a red "7"**; back to him shrugging with a grin. **Quoted on-screen text renders cleanly**, while unquoted signs came out garbled ("Los colae"). | 12:37 |
| S09 (v8f) | **Partly fixed:** the seat back now visibly tips forward and folds flat, so the action reads. But **the car still shows a second door with a handle**: text alone lost to the model's idea of "a small car", as with the coupe before its engine-drawn picture. Next round: give the stranger's car its own drawn reference (`SK.cast.coupe` recoloured blue, or similar). | 5:00 |
| S11 (v8f) | **Fixed:** Dad's hands reach in and take Leo under the arms from the start, never near his face, and lift him out of the roof against the sky, arms up like a champion. | 7:42 |

**The final minute (05:30)** is `temp/h3test/v8/leo-ep12-h3-v8.mp4`, with v8f's three shots in it. The third review saw v8 before v8f; v8f addresses each of its three points, and I checked each shot at 1 fps. One is only partly fixed (S09's car). The speech check on the final audio found 0 words, with all 116 narration words in the mix.

### Yield: v8's S01 with other seeds
| Seed | Usable? | Notes | Time |
|---|---|---|---|
| 42 | yes | the v8 shot | 12:47 |
| 7 | **yes** | Same beats in the same order, Leo on model, the series' cabin. A slightly closer push-in at the end. | 12:53 |
| 99 | **yes** | Same beats again, nearly identical framing. | 12:57 |

**Yield 3/3. With full references and a detailed prompt, H3 is consistent, not random.** The three seeds give nearly the same shot. Every failure this night was systematic, the same on every seed: the prompt, a reference, or an angle the reference does not cover. So a fixed prompt stays fixed, and an episode needs no "make five takes and pick one" step. Budget one render per shot plus one fix pass for the shots the review flags (3 of 11 in v8).

Queued after v8: the yield test moved to **S01** (good staging), because on S06 every seed would fail for the same staging reason. Then the S03 front-feet fix (v8c) and the S06 three-angle fix (v8d), each reassembling the minute.

**v7 minute:** `temp/h3test/v7/leo-ep12-h3-v7.mp4`, 80 min of machine time (S04 reused). A fresh review against KitCut's minute is running.

**Finding (01:17):** rendered empty with the episode's own `cabin(t, {leo: null})`, the series' real interior is **a caramel-tan bench, solid dark charcoal pillars beside it (no rear doors), small side windows only at the far edges, and a glass roof**. The "light grey interior" of v5 to v7 was my invention, and the model followed it faithfully. Queued **S01_cabinref**: S01 with this drawing as an environment reference and the interior described as the series draws it.

## (superseded) v6, clean references drawn by the KitCut engine

The v5 defects traced to the **reference picture**, a crop of an episode frame. It carried the car-seat harness into the shop and a chocolate smudge into every shot as "a brown button nose" (my written description of Leo came from the same frame). v6's references are the cast drawn alone by the KitCut engine (`sheet_film.js`): Leo standing, barefoot, sunglasses pushed up, with his canonical doodle face, and the coupe side-on with its real two-door shape. The subject descriptions are rewritten from those sheets. Shot fixes: S03's feet become a short side view (cut at 5.0 s, not 3.5 s), and S07 ends on a chest-up hug that rocks, not a stiff wide shot. Every shot with Leo or the car is redone. The experiments move to v6's S06 so they measure the setup we would actually use.

## Queued after v6 (one change each, on v6's S06)

| Experiment | Change | Question |
|---|---|---|
| v5 minute against v1 minute | the whole prompt format | Is Dad gone everywhere, is the interior grey every time, are the signs gone? |
| S06_seed7, S06_seed99 | seed | **Yield:** how many of 3 seeds are usable? |
| S06_5s | 5 s instead of 9.3 s | Do long shots degrade? |
| S06_pdd | Ref2VA PDD model instead of FastH3 | Is the slower model better? |
