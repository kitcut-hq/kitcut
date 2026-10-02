# Pool party invitation -- the template's code

kitcut.ai's pool-party-invitation template (studio/templates.py; its spec and brief: `../pool-party-invitation.json`).

- `film.js` -- the film, 30 s, drawn in crayon on the blush ground: a backyard pool seen side-on, the
  diving board, a cannonball, the floaties and the cake, then the invitation card rising out of the water.
  Every fact of one party -- the child's name, age and photo, the date, the time, an optional place and
  address, the film's words and its palette -- comes from `SK.DATA.content` (content.json); a long name,
  date or place is fitted, and a place line or two make the card close up its rows. Its header is the
  clock: which scene hangs on which narration line and word. The words that name the party are worked
  out from the content (`SAY`), the others are the narration's own.
- `cast/kid.js` -- the birthday child (`SK.cast.kid`), a front-facing doodle kid with the age on the tee;
  a remake redraws it from the person's photo (hair, skin, glasses, clothes) and keeps its size and poses.

The template is the first **narrated** one with its **sound as files**: the working project's `vo.json`
(six lines, a bubbly kids'-TV host) is seeded as the script Claude rewrites and records, its recorded word
times are the preview's clock, and `score.json` / `sfx.json` are kept as they are, the effects moved with
their lines once the new narration is recorded.

The sample is a real child's party, so its content (`content.json`), narration and photo stay out of this
repo, which is public; they live only in the working project, `projects/pool-party-invitation/` (local),
whose `film.js` and `cast/kid.js` these are copies of. A version is made from that project:

    python studio/templates.py make --folder projects/pool-party-invitation --id t-pool-party-invitation --spec config/templates/pool-party-invitation.json

v1 (2026-10-02): the kitcut.ai film studio-20260930-173158-pqxyhi with its party moved out of the code,
drawn pixel-identical to the original at 19 moments (the brand outro aside, which the studio adds per
plan). Checked with two made-up parties: a 7-year-old with a long hyphenated name, a weekday date, a
morning time and a two-line place (venue and street); and a 10-year-old (two digits on the tee and the big
number) with a long weekday and month and a place with no address.
