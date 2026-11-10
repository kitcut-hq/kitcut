# Tech meetup announcement -- the template's code

kitcut.ai's tech-meetup-announcement template (studio/templates.py; its spec and brief:
`../tech-meetup-announcement.json`).

- `film.js` -- the film, 30 s on a 112 bpm clock in six scenes (open, name, who, offer, facts, end);
  every word, colour and logo comes from `SK.DATA.content`. Its score and cues are files
  (`"sound": "files"`), kept from the film.
- The look is the hosts' own, measured off livekit.io and modal.com: a black page, Inter in light
  weights, IBM Plex Mono labels, hairline rules, one accent word a line, a dot-matrix date.

v3 (2026-10-02) is kitcut.ai film studio-20261002-181257-gpnrli, made for AI Agents Speakeasy
(LiveKit x Modal, LA Tech Week 2026). It was pulled with `studio/template_from_film.py pull`: the
film kept its facts in one `const FACTS` at the top of film.js, which became content.json, and the
template draws the film pixel for pixel. After that proof, the dotted x between logos was given air.
It was stressed with a long one-host name and a three-host demo night. v1-2 were an art-deco
speakeasy, withdrawn: a one-event theme had become every remake's costume.

The sample content and the hosts' logos are third-party and stay in the local project,
`projects/tech-meetup-announcement/`. A version is made from that project:

    python studio/template_from_film.py make --slug tech-meetup-announcement --push --publish
