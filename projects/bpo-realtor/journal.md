# bpo-realtor -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-09-23
- 11:33 project created

## 2026-09-23

### Session note -- project opened, materials inventoried, nothing shot yet

**The ask.** Oleksandr: several people at a demo said they had seen the BPO
video, so the channel needs more of them. One of them can be the same form on
the same data under a different angle -- "how real estate agents can use AI to
automate paperwork" -- but the quality has to go up and something new has to be
tried. Plus a short out of each main video, an external voice-over (no lip
sync), and HIPAA / Boyd Group cases when their inputs arrive.

**The form is measurably what the old video claimed.** `BPO_TEMPLATE_Standard`
has **534 AcroForm fields** over 3 pages (455 text, 78 button, 1 choice, read
with pypdf). The "500+ fields" line in `neaCnEawvbk` was accurate, so it can be
said again without hedging.

**The dataset tells a story, which the old chapter list did not exploit.**
The subject at 946 Alderwick St is Pending at **$151,800** in "Major Rehab
Needed" condition, and every one of the six comparables sits between **$389,500
and $442,000**. There is a renovation budget in the scope of work. So the video
is not "watch a form get filled" -- it is "here is a $150k house in a $400k
street, and the BPO is the document that has to justify the number".

**pypdf was added to the venv** to read the form and the data. It is not in
`requirements.txt` yet; add it there before anything depends on it.

**The assets are committed, deliberately breaking the gitignore convention.**
`neaCnEawvbk` kept its manifests and lost its sources, which is exactly why
this session could not simply re-cut the old film. 490 KB of synthetic PDFs is
a cheap insurance premium. Nothing in them is real.

**Recording has not started and the arrangement is not settled.** The proposal
on the table is to record SILENT -- clicks only, no talking -- and write the
narration afterwards as an ElevenLabs voice-over. That removes the accented,
halting live take that made `flatten-pdf` need a voice-over anyway, and it
makes the recording itself far easier: no retakes for stumbles.
