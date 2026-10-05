---
name: film-to-template
description: Turn a finished kitcut.ai film into a kitcut.ai template (an example others remake from one sentence), or make a new template from scratch by first making its source film -- find the film (by its id or its maker's email), pull it, move its facts into content.json, prove it draws the same, stress it with other content, write the two specs, publish it on the studio and the site, and prove with graded test films that a stranger's sentence makes a good video from it. Use when asked to make a template, to turn a film (or someone's films) into templates, to add a template for an occasion or a search keyword, to rename or reposition a template, or to check that a template still makes good films.
---

# A film into a template

A template is a finished film others remake: a person types one sentence (and may attach
pictures), and Claude remakes the film for it (`studio/templates.py`). Making one used to take an
afternoon across two repos. `studio/template_from_film.py` turns it into one command per stage. This
skill covers the parts a script can't decide.

```powershell
python studio/template_from_film.py find <email>                              # their films
python studio/template_from_film.py pull <film-id> --slug <slug>              # -> projects/<slug>
python studio/template_from_film.py prove --slug <slug>                       # same pixels
python studio/template_from_film.py alt   --slug <slug> --content content.alt.json
python studio/template_from_film.py check --slug <slug>                       # no sample in code
python studio/template_from_film.py spec  --slug <slug> --site ../sketch-studio
python studio/template_from_film.py make  --slug <slug> --push --publish      # studio
python studio/template_from_film.py site  --slug <slug> --site ../sketch-studio --publish
python studio/template_from_film.py test  --slug <slug> --prompt "<a sentence>" [--attach f]
```

Every stage takes `--plan`. Work in a worktree of each repo (peers share the main checkouts). The
studio has to run the release that knows what the template needs: if you changed anything under
`studio/`, ship it (`ops.sh ship`) before `make --push`.

## 1. Choose the film (or make it)

- **From someone's films.** Run `find <email>` and look at each candidate's
  `outputs/review/sheet.png` after `ops.sh pull`.
  - Take the one its maker kept: done, charged, liked.
  - Never take one whose narration was never recorded. `pull` refuses such a film: its picture
    was timed to nothing. On 2026-09-30, 52k5en was such a film.
- **A new template from scratch.** Make its source film first, in the owner's account (`scripts/film.mjs make --as alex@botmakers.net
  ...` in sketch-studio, with the real logos attached).
  - Write the prompt for a template: the facts in one object at the top of film.js; long values fitted; counts that vary must lay out.
  - The studio's brief asks every film for that since 2026-10-02 (`const FACTS`).
  - Use a **real** event or product by a **well-known name**, found on its own page, and its real logos from its brand page. Never invent a fact.
  - Judge the film by eye, using 10 frames from `outputs/film.mp4`, before building on it.

- **Several at once, overnight.** `studio/overnight_templates.py` (on the VM, from a jobs file; `--plan` first) makes the source films, a draft template of each and test films while nobody watches. It judges nothing: the next morning look at every film, rewrite each spec from its film, check 1:1 and 9:16 stills before offering those frames, and make the next version before publishing.

## 2. Pull and prove

- **pull** copies the film into `projects/<slug>/`: code, cast, engine, its own fonts, narration and sound, and the pictures it draws.
  - The film's closing brand is left out: the studio adds it per plan.
  - Attached pictures are renamed `upload1` → `sample1`, so a remake's own upload1 is never mistaken for the sample's.
  - If film.js keeps its facts in one object (`FACTS`, `EVENT`...; `--facts NAME` for another name), that object becomes `content.json`. That is the whole refactor.
  - Otherwise `pull` writes `temp/refactor-brief.md`: hand it to an agent (the birthday invitations needed this; about 17 minutes each).
- **prove** has to say *same*: within 2 levels at every moment. If it doesn't, the template is not the film.

## 3. Stress it, then read it by eye

Write `content.alt.json` and look at the sheet `alt` draws. Use other content that pushes every limit:
- a long name (`Anastasiya-Marie`, `Austin Rust & Systems Programming Meetup`);
- a two-digit age;
- one host and three;
- a missing optional field (no time, no address, no photo);
- fewer beats.

Fix what breaks in film.js (fit, re-split, move up), then **prove again**. `check` must find none of the sample's words in film.js or cast/: the studio stops every remake on a leftover.

## 4. Name it, and write the specs

- **Name the job people search for, never the sample.**
  - "LA Tech Week ride" named one event and went stale; it became "Group ride and run invitation".
  - Check volumes with Google Keyword Planner (the google-ads MCP `discover_keywords`).
  - Search phrases can name what the film does; brand names stay out of the title.
  - `docs/market-templates-2026.md` has the measured niches.
- **The studio spec** (`config/templates/<slug>.json`): `spec` fills it from the film. A person writes:
  - `description`: the film scene by scene.
  - `example`: what a stranger would type; no made-up URLs.
  - `brief`: the clock (which scene runs when, hung on which narration line), every content field and its limit, where to find the facts, what never to invent, and how pictures become the film's own (`template_pictures(logo=…)`, `logos=[…]` for co-hosts, `people=[…]`, `qr=`).
  - `generic`: words every film may keep (matched without case). Fill it from the sample's real content, after the film exists: every label a film of this kind says ("Register", "Kitchen", "Bedrooms"). It saves each remake a turn; a remake no longer fails without it, because Claude lists such words in content.json's `"_own"` (2026-10-03: four test films failed on those three words, with specs written before the films existed).
  - `watch`: content paths of short words such as a child's name.
  - `identity`: asking for the sample's own event turns the leftovers check off.
  - `narration` / `sound` come from the film: `"sound": "files"` keeps its score and cues, and moves the cues with a re-recorded narration.
- **The site spec** (`specs/templates/<slug>.json` in sketch-studio). `site` runs `templates.mjs check` first. The rules:
  - an H1 ending "video template";
  - a summary of up to 300 characters;
  - a description of 300-500 words;
  - 5-6 FAQs;
  - credits always "about N";
  - a category from `lib/templates.js` CATEGORIES (add one, with its SEO words, when none fits).
  - Facts only: the template's own numbers and the site's.

## 5. Publish, then prove it makes good films

`make --push --publish` builds the version, draws its preview and makes it live on the studio. `site --publish` puts its page up. Then the quality gate, which is why this is not done yet:

- **`test` twice:**
  - one sentence with nothing attached, its own example;
  - a real case: a real event's link, or a sentence with pictures.
- Each film is made on the VM and graded blind by `bakeoff`'s grader:
  - **professional ≥ 4**: how well made it looks;
  - **fidelity ≥ 4**: how closely it keeps the template, side by side with the source film.
- **Then look at both sheets yourself.** The grader is mild. Check that:
  - every fact is the person's;
  - nothing of the sample is left;
  - nothing overflows;
  - the logos read.
- **A FAIL is the template's fault, not the test's.** Fix the brief or the code, make a new version (`make` again: v2), and test again.

## 6. What stays private, and what to tell the user

- **Public repo.** The kitcut repo is public: commit the code, the cast, the README and the spec, never the sample's content or photos. Third-party logos, a real person's face, a private party's address and date stay in the local project.
- **A real child.** The site's preview is the source film itself. When it shows a real child or a private address, say so and offer a made-up sample.
- **The report.** Report the template's page, the two test films' links and grades, and anything under the bar. Open with the push/deploy status block (CLAUDE.md).

Related: `studio/README.md` "Templates", `docs/reference.md` "A narrated template", the
`video-sketch` skill (the films themselves), the `studio-vm` skill (ship, template push/publish).

## 7. A new template by remaking one, then polishing by hand (2026-10-05)

The fastest route to a new template at the bar of an existing one: ask the studio to remake that
template with "replace every scene" and a beat sheet. The first cut comes back in about ten minutes
with its facts already in `content.json`, sound written in code and the 3D and cut-out pieces working.

```powershell
node --env-file=../sketch-studio/.env scripts/film.mjs make --as <owner> --template conference-speaker-promo `
    --prompt-file beat-sheet.md --frame 1:1 --unlisted --studio-env ../kitcut/.env      # in the site repo
python studio/template_from_film.py pull <film-id> --slug <slug>      # takes a film whose facts are in a data file
```

- **Open the style books before the beat sheet.** Screenshot the event's own site and its social card,
  and read the logo page of each brand's standards. Put what they say, and their key art as a picture,
  in the prompt. "The event's own look" is not enough: the first Featured sponsor film struck a logo
  into a metal coin, and its owner called it cringe; both brands' rules forbade it.
- **A third party's logo sits flat and still on a solid panel in an approved colour, with clear space.**
  Never on metal or a gradient, never rotated, embossed or swept by a shine. The motion belongs to
  panels and type.
- **A budget stop is not the end:** `ops.sh resume <id> --minutes 20` finishes a first cut that stopped
  with `error_max_budget_usd`.
- **Polish locally, three frames:** copies of `sketch.json` with a `frame` key and their own `slug`
  (`sketch-wide.json`, `sketch-sq.json`, `sketch-tall.json`). Check every transition with stills at
  0.1 s steps (each frame is a pure function of t), stress the content, then `check`.
- **Put the master back under the same id:** `ops.sh replace <film-id> projects/<slug>` (with the pulled
  film's `events.jsonl` in the folder), then copy `content.json` and `inputs/` to the film's folder on
  the VM: `replace` does not take them.
- **A film for every frame on the page:** render the other frames, stage each as a folder
  (`sketch.json` = that frame's manifest, `outputs/` = its files) and import it link-only with
  `studio/import_film.py --unlisted --vm kitcut-studio-1`; then `templates.mjs update <slug>
  --square-film <id> --tall-film <id>` (and `--wide-film` when the template's first frame is square).
- **Show the owner a new look before its page goes public.** The link-only film is the preview.
