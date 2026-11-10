# Birthday party invitation -- the template's code

kitcut.ai's birthday-party-invitation template (studio/templates.py; its spec and brief:
`../birthday-party-invitation.json`). The first narrated template, and the first whose sound is files.

- `film.js` -- the film, 40 s of crayon on the blush ground: one wide slime world the camera slides through
  past five stops (the "?" blob that becomes the child's photo, the venue's storefront, the slime bar, the
  slime bucket, the invitation), on the narration's clock: eight lines, one per scene, every cue hung on a
  word with `SK.w`. Every fact of the party comes from `SK.DATA.content` -- the child's name, age and photo,
  the venue's name, sign, city and address, the date and time, the greeting, headline and stamp, the
  colours -- and every one of them is fitted to its place, so a long name is set smaller, never cut. The
  cues on the name, the venue and the city find those words in the narration by themselves.
- `cast/mascot.js` -- the venue's mascot (`SK.cast.mascot`), the star of the sample: it surfs the slime
  between the stops, kneads the slime, gets slimed and holds up the cake.
- `cast/kid.js` -- the birthday child drawn (`SK.cast.kid`), the other star (`"star": "kid"` in the content),
  with the age on the shirt. Same calling convention as the mascot, so the film swaps one for the other.

The sound is the sample's own files, not code: `score.json` (130 bpm) and `sfx.json` (cues in seconds on the
sample's narration), which the studio moves with their lines when a film records its own narration
(`"sound": "files"` in the spec). The narration is `vo.json` (`"narration": true`): a bubbly kids'-TV party
host, eight lines.

The sample is a real child's party -- a real name, a real venue, a real date, a photo of the child -- and this
repo is public, so the sample's content (`content.json`), its narration and word times, and the photo live
only with the working project, `projects/birthday-party-invitation/` (local), whose `film.js` and `cast/`
these are copies of. A version is made from that project:

    python studio/templates.py make --folder projects/birthday-party-invitation --id t-birthday-party-invitation --spec config/templates/birthday-party-invitation.json

v1 (2026-10-02): from kitcut.ai film studio-20260929-143101-qshcoy, its party moved out of the code into
`content.json`. Checked by rendering both ways: at 20 moments across the 40 s the refactored film is
pixel-identical to the original. Checked for generality with two made-up parties rendered over the
sample's narration: a 6-year-old with a 16-letter hyphenated name at a two-line-sign studio in another
city with the kid as the star, and a 10-year-old with no photo (the initial instead), a one-line sign, a
22-letter city, one address line, no time and a longer stamp.
