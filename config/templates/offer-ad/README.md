# The offer ad -- the template's code

A kitcut.ai template (studio/templates.py; its spec and brief: `../offer-ad.json`).

- `film.js` -- the film. Every word, picture and colour comes from `SK.DATA.content` (read as
  `FACTS`); nothing of any one offer is in the code.
- `content.sample.json` -- a made-up example of the facts (a software discount, no pictures). The
  real sample -- a bank card's 4X travel-points offer over a photo, with the card image and
  the bank's logo -- is third-party creative, so it stays in the local working project
  `projects/offer-ad/` (gitignored), whose `film.js` this is a copy of.

7 s, 60 fps, loops, 1080 x 1080 (and 1080 x 1920 from the same code; the layout also lays out 1920 x 1080, which the template does not offer until a sample photo suits it), one
looping ad with a light score and soft cues written by the film itself (`SK.film({sound})`).

The layout re-measures itself per frame: the product beside the words in square and wide frames,
above them in a vertical one (which also keeps clear of the app's top bar and bottom controls);
the figure fits its column, wrapping onto two lines when a long one ("2 months free") would
shrink to nothing; the subline wraps only when fitting would make it small. With a photo, the
words sit on a scrim that is *measured*: the photo is sampled under them and the veil is only as
strong as it takes for the text to reach 4.8:1 -- light words on a dark veil, or dark words on a
light one, whichever needs less. With no photo the brand's colour is the page (light or dark; the
words and logo variant follow it).

The clock never changes with the content: product in at .5 s, figure at .75, logo at 1, subline
word by word from 2, button at 3, everything out from 6; the picture breathes over the whole loop
so the end meets the start.

A version is made from the working project:

    python studio/templates.py make --folder projects/offer-ad --id t-offer-ad --spec config/templates/offer-ad.json

Checked with a made-up SaaS discount (no photo, a screenshot, a button and fine print), a long
figure over three lines, a bright and a dark stock picture with the words on the top and the
bottom edge, and a bare figure -- in all three frames.
