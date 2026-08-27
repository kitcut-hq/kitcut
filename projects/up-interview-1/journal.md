# up-interview-1 -- edit journal
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
