# up-interview-2 -- edit journal
AI notes for future sessions. Scripts append the `- HH:MM` event lines;
after each editing session, append a short prose note: what was asked,
which knob changed, why, and anything the next session should not rediscover.

## 2026-08-27
- 20:06 project created

Brought in to test the framework on content it had never seen: 25 fps (not
23.976), an hour long, a different editor, 1080p in AV1/VP9. It failed at the
first step, and the failure is why this project is kept.

shot-detect finds the cuts but cannot tell the ANGLES apart, and says so: worst
distance within an angle exceeds the closest distance between two, meaning a
shot resembles a different camera more than it resembles its own. The angle
count never settles across the threshold sweep either.

The cause is visible the moment you look at --sheets. Four people at one table
against a plain black backdrop, so every camera has the SAME background -- and
reading the room behind the speaker is exactly how this method identifies an
angle. On the a16z films each camera had a gold disc, a lamp, a bookshelf; here
there is nothing. Burned-in lower-third name cards compound it: while a name is
up, that camera fingerprints as a new angle.

Three rescues were measured, not guessed, and all three failed: plain, top-60%
mask (drops the name cards and the table), and top-60% plus contrast
normalisation. Best margin 0.47x, where anything usable is well above 1.0.
Masking does help the name-card pairs specifically (0.158 -> 0.062) but the
underlying angles still do not separate.

Do not tune thresholds at this. The signal is absent, not buried. Making these
work needs angle identity from WHO is in frame and how they are framed -- face
or person embeddings -- which is a different method, not a parameter. Until
then shot-detect refuses to write a shot list here, which is what stops
split-cameras from building one hour-long tape per phantom angle.
- 22:39 shot-detect scripts/shot-detect.py (--src projects/up-interview-2/sources/original.mp4 --sheets) -- 506 shots, 10 angles, 505 cuts from projects/up-interview-2/sources/original.mp4

SECOND VISIT -- the negative result above is obsolete. This film produced the
cast rule.

Person-identity detection (see up-interview-1's journal for why it exists) took
this from 61 phantom angles to 36 -- better, but still refused. The reason is
specific to this show: roughly a third of it is ARCHIVAL INSERT material, and
archive footage has faces in it. Queen's "Mustapha", Joy Division's
"Transmission", vinyl-record transition animations, picture-in-picture
composites. Face identity happily clustered Freddie Mercury as a camera.

The rule that fixed it: a camera in a shoot films the people in THAT shoot. Any
angle showing nobody who holds 3% or more of the film goes to the shared xtra
bin, however often the editor returns to it. That took 36 -> 10 and the guard
passes (within 0.594, between 0.752).

A rarity rule was tried first -- bin anything used once for under 2% of the film
-- and dropped, because on up-interview-1 it binned a legitimate wide the editor
happened to use once. Rare is not the same as inserted; being nobody from the
cast is.

NOT round-tripped, on purpose. A show whose inserts are a third of the runtime
stretches the fixture idea past where it means anything: an insert is not a
camera that was rolling through the shoot, so "rebuild the tape it came from" has
no answer. The xtra bin gives inserts one pseudo-tape, which is self-consistent
and would round-trip, but it is not a camera and nobody should read it as one.
The three real cameras here (host, guest, wide) are ~85% of the film and would
round-trip fine if that were ever wanted.
