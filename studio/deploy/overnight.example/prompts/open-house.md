A 30-second open house invitation for a real home: the film an agent or a builder posts the week before so people come on the day.

The event: Lennar's grand opening of the Driftwood model home at Pepperwood in Stuart, Florida, Saturday, October 17, 12 to 4 PM. Its page: https://www.lennar.com/new-homes/florida/palm-beach/event/pepperwood-model-go . Read that page and Lennar's Pepperwood community page for the address, the home's facts (bedrooms, bathrooms, square feet, price from) and its photos.

Beats:
1. "OPEN HOUSE" (here: "Model grand opening") with the day and the hours, on a yard sign that swings in, in the host's colours.
2. The home's best exterior photo in a frame with a slow push in, and the address written under it. Use the host's own published photo; if none can be fetched, draw the house simply.
3. The key facts tick in one by one: bedrooms, bathrooms, square feet, price. Only those published.
4. Up to three more photos flick through (kitchen, living room, outside), each with a one- or two-word label.
5. A pin drops on a simple drawn street map with the street's name.
6. The end card: the day and hours again, the address, who to contact (the host's sales line or agent, only if published) and the host's logo.

How to make it (this film will become a template others remake for their own event):
- Use only facts published on the pages above or on the host's own pages. Never invent a date, time, address, price, name or number; a fact you cannot find is left out and the layout still holds.
- Use the host's real logo and its own colours and type (fetch them from its site). Draw nothing generic where the real thing exists. No mascots, no jokes, no theme costume: clean, brand-led, typographic motion design of the kind a good in-house designer would post.
- Keep every fact, colour and picture name in one `const FACTS = {...}` object at the top of film.js, and nothing of them in the code below it.
- Fit long values (shrink, then wrap); lists lay out for 1 to 4 items; an optional item that is missing leaves no hole.
- Lay everything out from the frame's width and height, not fixed pixels, so the same code holds in 16:9, 1:1 and 9:16.
- Narration: short, warm, plain. Say the day and time the way a person would. Never read a URL aloud.
- Readable on a phone: nothing important smaller than a caption.
