# The maker: make the idea the owner picked

Started by the owner's pick on the ideas page (`web/`, Vercel project `hn-ideas`): the page fires
this routine's API trigger, and the pick arrives in the `<routine-fire-payload>` block as JSON:

```json
{
  "what": "The owner picked this idea and angle on their ideas page. Make it.",
  "pick_id": "uuid",
  "publish": true,
  "owner_note": "anything the owner typed, or null",
  "angle": {"id": "a1", "format": "recreation", "title": "...", "why": "..."},
  "idea": {"topic": "...", "kind": "...", "stakes": "...", "searches": "...", "supply": "...",
           "hn": [...], "sources": [...], "angles": [...]},
  "status_url": "https://.../api/status",
  "status_sig": "hex"
}
```

The routine's prompt opts in to acting on this block. Make **exactly that** idea with **that** angle
(the owner may have written their own, `angle.id: "own"`), and nothing else. No payload, or not this
shape: stop and say so.

Read `ROUTINE.md` first: its angle, recreation and title rules, and its steps 6b to 9, which this
run follows for the one pick.

## Report to the page as you go

The page shows the pick's state. POST at every step (the signature lets this run report on its own
pick and nothing else):

```bash
curl -sS -X POST "$STATUS_URL" -H "content-type: application/json" \
  -d '{"pick_id":"<pick_id>","sig":"<status_sig>","state":"researching","note":"..."}'
```

| state | when | send too |
|---|---|---|
| `researching` | at the start | `note`: the angle in a line |
| `dropped` | the evidence does not hold (step 6b says NO, or a number the film rests on cannot be backed) | `note`: why, in one or two plain sentences |
| `making` | `make_film` started | `film`: the film's link; `title` |
| `published` | live on YouTube | `film`, `youtube`: the video's link |
| `done` | finished, and the pick said not to publish | `film` |
| `failed` | the studio could not make it (after one remake for the studio's own reasons) | `note` |

## Steps

1. **`researching`.** Then the quick check (ROUTINE.md 6b) on the picked angle: does the evidence
   actually settle it? A NO is `dropped` with the reason; the owner would rather know than get a
   weak film. A better angle that the evidence supports may replace it only when the owner's angle
   cannot be made at all; say so in the note.
2. **Research and write** the three documents (ROUTINE.md 7), **60 to 120 seconds**, as long as
   the evidence needs; a `recreation` is a timeline with the time on screen at every step.
   `check_research` until clean, `check_sources` on every row.
3. **Make** (ROUTINE.md 8): `make_film` in project `p-mlgnibpqat`, 9:16, collage, the idea starting
   with the title (and `FORMAT: recreation, timestamps on screen` for a recreation). Then
   **`making`** with the film's link. Follow it with `get_film` until done. A film whose status is
   `cancelled` was stopped by a person: never make it again, and report `failed` with that note.
4. **Publish** when `publish` is true (ROUTINE.md 9: public on the KitCut channel, the title the
   question, never a news summary), then **`published`** with the YouTube link. When `publish` is
   false: **`done`** with the film's link.

## Report

End with: the pick (topic and angle), the state it ended in, the film's link, the YouTube link if
published, the script's words, the fact sheet's key rows, and anything a person should look at.
