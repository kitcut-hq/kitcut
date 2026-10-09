"""One question to a model that is not Claude Code's: the text, pictures before it, a JSON object back.

The studio's small steps (the second reader, the share words, the episode log, the YouTube draft)
each ask one question with no tools (ytdraft.ask_json). On Claude that is a Claude Code process per
question, on the login's plan or the film's key. A model named with its provider ("openai/gpt-6-luna",
"google/gemini-3.8-flash", "anthropic/claude-haiku-5.5") is asked here instead, through OpenRouter
(OPENROUTER_API_KEY): one HTTP request, nothing of Claude's plan spent.

    ask_json(text, images, model, effort, system) -> (the parsed JSON object, cost in USD)

Which step may run on which model is a measurement, not a guess: studio/defects.py --part review
--model <id> scores a reader on the bench of known glitches, and docs/studio-speed.md ("Smaller
models for the small steps") has the table.
"""

import re
import json
import time
import base64
import urllib.error
import urllib.request

import procs

URL = "https://openrouter.ai/api/v1/chat/completions"
TIMEOUT_S = 300
RETRIES = 2  # on 429 / 5xx / a dropped connection


def routed(model):
    """Whether a model id is asked here (a provider's name in it) and not through Claude Code."""
    return "/" in (model or "")


def ask_json(text, images, model, effort, system):
    """Blocking: call it in a thread (asyncio.to_thread). Raises RuntimeError with the reason."""
    key = procs.secret("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY is not set: %s cannot be asked" % model)
    content = [
        {
            "type": "image_url",
            "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(b).decode("ascii")},
        }
        for b in images or []
    ]
    content.append({"type": "text", "text": text})
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": content},
        ],
        "usage": {"include": True},
    }
    if effort:
        body["reasoning"] = {"effort": effort}
    req = urllib.request.Request(
        URL,
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
    )
    why = "no answer"
    for attempt in range(RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r:
                d = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            why = "%d %s" % (e.code, e.read().decode("utf-8", "replace")[:300])
            if e.code not in (429, 500, 502, 503, 504) or attempt == RETRIES:
                break
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            why = str(e)
            if attempt == RETRIES:
                break
        else:
            if d.get("error"):
                why = json.dumps(d["error"])[:300]
                break
            said = (d["choices"][0]["message"].get("content") or "") if d.get("choices") else ""
            j = re.search(r"\{.*\}", said, re.DOTALL)
            try:
                out = json.loads(j.group(0)) if j else None
            except ValueError:
                out = None
            if not isinstance(out, dict):
                raise RuntimeError("no JSON from %s: %s" % (model, said[:300]))
            return out, float((d.get("usage") or {}).get("cost") or 0.0)
        time.sleep(2 * (attempt + 1))
    raise RuntimeError("%s did not answer: %s" % (model, why))
