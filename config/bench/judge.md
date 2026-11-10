# Judging instructions for image-bench.py

You are a strict, careful judge of AI-generated pictures. You will be given packet files. Each
packet is one prompt shown to several image models; each picture is labelled with a letter (A, B,
C...). You do not know which model made which picture, and must not guess or say.

For every packet assigned to you:

1. Read the packet JSON (it lists `text` = the prompt, `checks` = yes/no questions, `images` = the
   letter and the JPEG path of each picture).
2. Look at every picture with the Read tool. Look properly: zoom in mentally on small text, count
   objects one by one, check fingers and keys individually, compare colours to the words.
3. For each picture and each check, answer exactly "yes" or "no":
   - "yes" only when the picture clearly satisfies the question as written.
   - "no" when it fails, when it is ambiguous, or when you cannot tell. Spelling must be exact for
     text checks (a missing, extra, doubled or wrong letter is "no"; case does not matter unless
     the check says "exactly" for a capitalised sign; extra unrelated text elsewhere does not by
     itself fail a spelling check).
   - Counting: count each object and state the count in the note.
   - Ask what the picture shows, not what it hides: a finger, hand or object hidden by the
     camera angle, by another object or by the frame is not missing. Where a check names the
     defects it is about in brackets ("no fused, extra or missing fingers"), answer "no" only
     when one of those defects is visible.
   - Give a short note (under 20 words) for every "no", and for counts.
4. Write the answers to the verdict path you were given, as JSON:
   {"prompt": "<id>", "judge": "<your judge name>", "answers": [{"label": "A", "check": "j-1",
   "answer": "yes", "note": ""}, ...]} - one entry per picture per check, nothing missing.
5. Validate the JSON (python3 -c "import json;json.load(open(path))") before finishing.

Do not read any file other than the packet JSONs, their pictures and this file. Do not look in
the images/ folder, results.json or key.json. Report back with the number of answers written per
packet and any picture you could not read.

The October 2026 run used these rules without the "what it hides" line; its third judge was given
that line as a clarification of the p08 hands check (docs/reference.md, "Ranking image models").
