# Review pass 1 — the user's own commentary

Source: `~/Videos/Recording 2026-08-31 174737.mp4` (3:47, spoken Ukrainian),
recorded 17:47 against the 8:00 render. The film's own timecode is visible in
the player's bottom-left corner, which is what maps each remark to a frame:
read it there, then `screen-cut.py --where <film time>` gives the source and
the source timecode.

| said at | film | source @ source time | the remark | disposition |
|---|---|---|---|---|
| 0:25 | 0:04 | `screen-…083709` @ 0:12.7 | "there is a blur here, though it makes no sense" | **false positive** — my hand rect `top-bar amount` spans 4–49 s and lands on the card-type picker, which has no amount |
| 0:45 | 0:17 | `screen-…083827` @ 0:05.5 | "I'm not against showing these balances — but the next frames remove them anyway. Strange." | **stop blurring balances**; the inconsistency is the complaint |
| 1:10 | 0:21 | `screen-…083827` @ 0:18.3 | "we hid literally everything, nothing is shown — including my selfie at the bottom. Too much." | full-width bands must go; blur the PAN/IBAN rows only |
| 1:35 | 0:31 | `screen-…083827` @ 0:50.0 | "I wanted to show how I created the card — that it didn't exist and I had to add it" | the card-creation story must survive the redaction |
| 2:02 | 1:46 | `desktop-104620` @ 3:24.0 | "this person's phone number, shown right in the chat, and we don't even try to hide it" | tracker miss |
| 2:24 | 2:07 | `desktop-105144` @ 0:14.3 | "this screen shows many phone numbers — they must be hidden" | the spreadsheet |
| 2:32 | 2:10 | `desktop-105144` @ 0:28.5 | "the card number, expiry and CVV are shown — hide all of it" | the Notepad |
| 3:16 | 2:22 | `desktop-110556` @ 1:14.6 | "this person's phone is not hidden, right in the chat" | tracker miss |
| 3:26 | 3:17 | `desktop-112123` @ 2:16.6 | "same problem, this person's phone number" | tracker miss |
| 3:39 | 3:33 | `desktop-112123` @ 4:05.4 | "same problem, phone right in the chat" | tracker miss |

Closing remark, and the one that matters most:

> "…одна і та сама проблема повторюється постійно. Нам треба знайти спосіб, як
> ми будемо ефективно затирати ці телефони."

That is the same failure the acceptance gate independently found — **183 hits,
28 distinct secrets, mostly recipient phones in DMs and checkout forms** — and
its cause was the frame-timestamp bug (`docs/retro-books-giveaway.md`, and the
`fps` filter entry in the README gotchas). Templates were cut up to four
seconds away from the frame that carried the text, so most of them matched
nothing. Fixed; recall on the source that exposed it went 46% → 92%.

## What changes because of this review

1. **`balance` is no longer a blurred kind.** Explicit: showing the account
   balances is acceptable. This also removes most of the over-blur.
2. **No full-width bands on the phone clips.** They hid the selfie and the
   card-creation story, which is the thing the clip exists to show.
3. **Tracking is re-enabled on the phone clips.** It was turned off when its
   recall there measured 14% — but that measurement was taken with the
   timestamp bug in place, so it was measuring the bug. Re-measure with
   `--recall` and only fall back to hand rects where the number says so.
4. **The monobank hand rects are narrowed** to the two card faces that
   actually carry a PAN.
