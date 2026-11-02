#!/usr/bin/env python
"""A finished film in another language (studio/localize.py, kitcut.ai's Translate), end to end
through the API with the film itself stubbed: no Claude, no voice, seconds.

    python studio/test_localize.py

Covers: what a translation is given of the original (its code, pictures, cast, engine, music,
voice; never its narration takes, renders, YouTube drafts, share, notes or record) and what its
record says; the refusals (another's film, not finished, a new version being made, own voice,
scene by scene, its own language, a language it has, Russian and any language not offered); a
template's film (content.json, template/), one with people (rigs carried, their cost not) and one
with no narration (no vo.json, its own first message, unchanged fails) taken; the web pictures it
brought in carried; asking twice with one key is one film; Claude's first message; a narration
left untranslated fails, words left on screen get a turn; a film made in another language is not
an episode's next one; and the YouTube draft's language and "fresh".
"""

import os
import sys
import json
import asyncio
import tempfile

HOME = tempfile.mkdtemp(prefix="studio-localize-test-")
os.environ["STUDIO_HOME"] = HOME
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server  # noqa: E402 -- imports agent, which imports _env first
import agent  # noqa: E402
import episode  # noqa: E402
import localize  # noqa: E402
import store  # noqa: E402
import ytdraft  # noqa: E402
from film import Film, _write_json  # noqa: E402

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

TOKEN = "test-token"
ALICE, BOB = "u:" + "a" * 24, "u:" + "b" * 24
LINES = [
    {"text": "Bees visit thousands of flowers every single day."},
    {"text": "They carry nectar home inside a second stomach."},
    {"text": "Then they fan it with their wings until it thickens."},
]


def touch(p, body="x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(body)
    return p


def original(client=ALICE, **rec):
    """A finished, narrated film from an idea, with everything a made film has in its folder."""
    f = Film.create("How bees make honey", 30, "drawn", client=client)
    touch(f.path("film.js"), 'SK.text("How bees make honey", {size: 64});\nconst c = "#ffcc00";\n')
    touch(f.path("cast", "bee.js"), "export default {}")
    touch(f.path("images", "hive.png"))
    touch(f.path("music", "score.json"), "{}")
    touch(f.path("sfx.json"), "[]")
    _write_json(f.path("vo.json"), {"language": "en", "voice": "kc-warm", "lines": LINES})
    touch(f.path("audio", "vo", "timeline.json"), '{"lines": []}')
    touch(f.path("audio", "vo", "line1.mp3"))
    touch(f.path("outputs", "film.mp4"))
    touch(f.path("web", "film_web.mp4"))
    touch(f.path("web", "logo.png"))  # a picture it brought in from the web: SK.image('web_logo')
    touch(f.path("youtube", "UC" + "x" * 22, "draft.json"), '{"title": "How bees make honey"}')
    touch(f.path("share", "card.jpg"))
    touch(f.path("notes", "n1.json"), "{}")
    touch(f.path("versions", "v1", "film.js"))
    f.update(**{"state": "done", "ok": True, "title": "How bees make honey", "version": 2, **rec})
    return f


async def main():
    agent.STORE = store.MemoryStore()
    started = []
    server.start = lambda f, finish_only=False, resume=None: started.append(f.id)
    bad = []

    def check(ok, what, detail=""):
        print("%s  %s%s" % ("ok  " if ok else "FAIL", what, "" if ok else "  -- %s" % detail))
        if not ok:
            bad.append(what)

    def refused(spec, client=ALICE):
        try:
            localize.check(spec, client)
        except localize.Refused as e:
            return e.status, e.reason
        return None

    src = original()
    spec = {"from": src.id, "version": 2, "language": "es", "key": "hold-1"}

    # ---- what is refused, before anything is made
    check(refused(spec) is None, "a finished, narrated film of one's own can be translated")
    check(refused(spec, BOB) == (404, "localize"), "another's film is no such film")
    for lang in ("ru", "RU", "rus", "russian", "ru-RU", "ja", "xx", ""):
        check(
            refused({**spec, "language": lang}) == (400, "language"),
            "%r is not a language it is made in" % lang,
        )
    check(refused({**spec, "language": "en"}) == (409, "same"), "never its own language")
    check(refused({**spec, "key": "../x"}) == (400, "localize"), "a key is the site's hold id")
    for what, rec, reason in (
        ("not finished", {"state": "running"}, "state"),
        ("its own voice", {"narrator": {"source": "elevenlabs"}}, "own_voice"),
        ("scene by scene", {"mode": "scenes"}, "long"),
    ):
        f = original(**rec)
        check(
            refused({**spec, "from": f.id}) == (409, reason),
            "a film %s is refused (%s)" % (what, reason),
            refused({**spec, "from": f.id}),
        )

    ov = original(narrator={"source": "elevenlabs", "voice": "v" * 20, "model": "eleven_v3"})
    ov_spec = {**spec, "from": ov.id}
    grant = {"source": "elevenlabs", "voice": "v" * 20, "model": "eleven_v3", "grant": "g" * 43}

    def refused_with(narrator):
        try:
            localize.check(ov_spec, ALICE, None, narrator)
        except localize.Refused as e:
            return e.status, e.reason
        return None

    check(refused_with(None) == (409, "own_voice"), "its own voice, asked with no pass: refused")
    check(refused_with(grant) is None, "its own voice, asked with a pass to that voice: taken")
    check(
        refused_with({**grant, "voice": "w" * 20}) == (409, "own_voice"),
        "a pass to another voice: refused",
    )
    for what, rec in (
        ("a template's", {"template": {"id": "t-x", "version": 1}}),
        ("people from photos", {"people": [{"id": "p1", "name": "Ann"}]}),
        ("no narration", {"narration": False}),
    ):
        f = original(**rec)
        check(refused({**spec, "from": f.id}) is None, "a film %s is taken" % what)

    # ---- a template's film with no narration, and people drawn from photos: laid in
    tpl = original(template={"id": "t-x", "version": 1}, narration=False)
    os.remove(tpl.path("vo.json"))
    touch(tpl.path("content.json"), '{"title": "Spring open day at the hive"}')
    touch(tpl.path("template", "logo.png"))
    touch(tpl.path("rigs", "p1", "rig.json"), "{}")
    touch(tpl.path("rigs", "spend.jsonl"), '{"cost_usd": 0.4}')
    t_new = Film.create("How bees make honey", 30, "drawn", client=ALICE)
    localize.seed(t_new, tpl, "de", 1, "hold-t")
    t_has = lambda *p: os.path.exists(t_new.path(*p))  # noqa: E731
    check(
        t_has("content.json") and t_has("template", "logo.png") and t_has("rigs", "p1", "rig.json"),
        "a template's words and pictures, and the people's rigs, are carried",
    )
    check(not t_has("rigs", "spend.jsonl"), "what drawing the people cost is not")
    check(
        not t_has("vo.json") and t_new.record().get("narration") is False,
        "a film with no narration gets none, and records nothing",
    )
    check("content.json" in t_new.editable(), "its content.json is Claude's to translate")
    t_msg = localize.ask(t_new)
    check(
        "no narration" in t_msg and "content.json" in t_msg and "German" in t_msg,
        "its first message: the words on screen only, content.json included",
        t_msg[:200],
    )
    check(localize.untranslated(t_new), "nothing changed: untranslated, and it fails")
    touch(t_new.path("content.json"), '{"title": "Tag der offenen Tür im Bienenstock"}')
    check(not localize.untranslated(t_new), "its words translated: not")
    touch(t_new.path("content.json"), '{"title": "Spring open day at the hive"}')
    touch(t_new.path("film.js"), 'SK.text("Wie Bienen Honig machen", {size: 64});\n')
    check(
        localize.leftovers(t_new) == ["Spring open day at the hive"],
        "words left in content.json are found",
        localize.leftovers(t_new),
    )

    # ---- through the API
    async with TestClient(TestServer(server.make_app(TOKEN))) as c:
        me = {"Authorization": "Bearer " + TOKEN, "X-Client-Ip": ALICE}
        bob = {**me, "X-Client-Ip": BOB}

        async def ask(body, headers=me):
            r = await c.post("/api/films", json=body, headers=headers)
            return r.status, await r.json()

        st, j = await ask({"localize": {**spec, "language": "ru"}})
        check(st == 400 and j.get("reason") == "language", "Russian is refused at once", (st, j))
        st, j = await ask({"localize": spec}, bob)
        check(st == 404, "another's film is refused", (st, j))
        n_films = len(Film.all())
        st, j = await ask({"localize": spec})
        check(
            st == 202 and j.get("localized", {}).get("from") == src.id and started == [j.get("id")],
            "a translation starts as a film of its own",
            (st, j, started),
        )
        new = Film.open(j.get("id"))
        check(len(Film.all()) == n_films + 1 and new is not None, "one new film")
        rec = new.record()
        check(
            rec.get("localized")
            == {"from": src.id, "version": 2, "language": "es", "key": "hold-1"}
            and rec.get("client") == ALICE
            and rec.get("prompt") == "How bees make honey"
            and new.length == 30,
            "its record says what it is a translation of, with the original's idea and length",
            rec,
        )
        has = lambda *p: os.path.exists(new.path(*p))  # noqa: E731
        check(
            all(
                has(p)
                for p in (
                    "film.js",
                    "cast/bee.js",
                    "images/hive.png",
                    "music/score.json",
                    "sfx.json",
                )
            ),
            "it is given the original's code, cast, pictures, music and sounds",
        )
        check(has("web", "logo.png"), "the pictures it brought in from the web are carried")
        check(
            not any(
                has(p)
                for p in (
                    "audio/vo/line1.mp3",
                    "outputs/film.mp4",
                    "web/film_web.mp4",
                    "youtube",
                    "share",
                    "notes",
                    "versions/v1",
                )
            ),
            "never the original's narration takes, renders, YouTube drafts, share, notes or versions",
            sorted(os.listdir(new.dir)),
        )
        with open(new.path("vo.json"), encoding="utf-8") as fh:
            vo = json.load(fh)
        with open(new.path("localize", "vo.json"), encoding="utf-8") as fh:
            was = json.load(fh)
        check(
            vo.get("language") == "es"
            and vo.get("voice") == "kc-warm"
            and vo.get("lines") == LINES,
            "its narration: the same voice and lines, its language Spanish, to translate",
            vo,
        )
        check(
            was.get("language") == "en" and has("localize", "timeline.json"),
            "the original's narration and word times are there to read",
        )
        with open(src.path("youtube", "UC" + "x" * 22, "draft.json"), encoding="utf-8") as fh:
            check("bees" in fh.read(), "the original is untouched")

        st, j2 = await ask({"localize": spec})
        check(
            st == 202 and j2.get("id") == new.id and len(started) == 1,
            "asked twice with one key: the same film",
            (st, j2),
        )
        st, j3 = await ask({"localize": {**spec, "key": "hold-2"}})
        check(
            st == 409 and j3.get("reason") == "exists" and j3.get("film") == new.id,
            "a language it has, being made, is not made twice",
            (st, j3),
        )
        st, j4 = await ask(
            {"localize": {**spec, "from": new.id, "language": "de", "key": "hold-3"}}
        )
        check(
            st == 409 and j4.get("reason") == "state",
            "a translation being made is not a source",
            j4,
        )
        st, j5 = await ask({"localize": {**spec, "key": "hold-4"}}, bob)
        check(st == 404, "another asking with another's key gets nothing", (st, j5))

    # ---- Claude's part
    msg = localize.ask(new)
    check(
        "Translate the film into Spanish" in msg and "never paint" in msg and "3 lines" in msg,
        "the first message: translate the words said and shown, keep everything else",
        msg[:200],
    )
    check(agent.ask(new) == msg if hasattr(agent, "ask") else True, "the agent asks it so")
    check(localize.untranslated(new), "a narration left as the original's is untranslated")
    _write_json(
        new.path("vo.json"),
        {
            **vo,
            "lines": [
                {"text": "Las abejas visitan miles de flores cada día."},
                {"text": "Llevan el néctar a casa en un segundo estómago."},
                {"text": "Luego lo abanican con sus alas hasta que espesa."},
            ],
        },
    )
    check(not localize.untranslated(new), "a translated narration is not")
    check(not localize.untranslated(src), "an original is never untranslated")
    check(
        localize.leftovers(new) == ["How bees make honey"],
        "words of the original still on screen are found (never code)",
        localize.leftovers(new),
    )
    touch(new.path("film.js"), 'SK.text("Cómo hacen miel las abejas", {size: 64});\n')
    check(localize.leftovers(new) == [], "none once translated")
    check(episode.wanted(new) is False, "a translation is never an episode's next one")

    # ---- only the words change: the clock, the code, the sound and the pictures are the original's
    strict = original()
    touch(
        strict.path("film.js"),
        'const T = "How bees make honey";\nSK.text(T, {size: 64, color: "#ffcc00", font: "Sofia Sans"});\n'
        "SK.at(2.5, () => SK.image('web_logo', 0, 0));\nconst cue = SK.w(1, 'nectar');\n",
    )
    _write_json(
        strict.path("audio", "vo", "timeline.json"),
        {
            "duration": 30.0,
            "lines": [
                {"i": 0, "start": 0.5, "end": 3.0},
                {"i": 1, "start": 3.4, "end": 7.0},
                {"i": 2, "start": 8.0, "end": 12.0},
            ],
        },
    )
    sl = localize.slots(
        {"lines": LINES}, localize._read(strict.path("audio", "vo", "timeline.json")), 30
    )
    check(
        [x["start"] for x in sl] == [0.5, 3.4, 8.0]
        and abs(sl[0]["end_by"] - 3.28) < 1e-6
        and abs(sl[2]["end_by"] - 29.4) < 1e-6,
        "each line's slot: where the original said it, to the next line (or the fade)",
        sl,
    )
    s_new = Film.create("How bees make honey", 30, "drawn", client=ALICE)
    localize.seed(s_new, strict, "es", 2, "hold-s")
    with open(s_new.path("vo.json"), encoding="utf-8") as fh:
        s_vo = json.load(fh)
    check(
        [ln.get("start") for ln in s_vo["lines"]] == [0.5, 3.4, 8.0],
        "the translation's lines start where the original's did",
        s_vo["lines"],
    )
    check(localize.check_film(s_new)["ok"] is False, "untranslated and unrecorded: not passed")

    def record_es(ends=(2.9, 7.1, 11.0), starts=(0.5, 3.4, 8.0)):
        os.makedirs(s_new.path("audio", "vo"), exist_ok=True)
        _write_json(
            s_new.path("audio", "vo", "timeline.json"),
            {
                "lines": [
                    {"i": i, "start": a, "end": b} for i, (a, b) in enumerate(zip(starts, ends))
                ]
            },
        )

    record_es()
    js_es = (
        'const T = "Cómo hacen miel las abejas";\nSK.text(T, {size: 64, color: "#ffcc00", font: "Sofia Sans"});\n'
        "SK.at(2.5, () => SK.image('web_logo', 0, 0));\nconst cue = SK.w(1, 'néctar');\n"
    )
    touch(s_new.path("film.js"), js_es)
    rep = localize.check_film(s_new)
    check(
        rep["ok"] and rep["words"] == 2, "words said and shown changed, nothing else: passed", rep
    )
    for what, js in (
        ("a size", js_es.replace("size: 64", "size: 72")),
        ("a colour", js_es.replace("#ffcc00", "#ff0000")),
        ("a font", js_es.replace('"Sofia Sans"', '"Arial"')),
        ("a time", js_es.replace("2.5", "3.0")),
        ("a picture's name", js_es.replace("'web_logo'", "'web_other'")),
        ("a line of code", js_es + "SK.text('extra');\n"),
    ):
        touch(s_new.path("film.js"), js)
        check(localize.check_film(s_new)["ok"] is False, "%s changed: caught" % what)
    touch(s_new.path("film.js"), js_es + "// un comentario traducido\n")
    check(localize.check_film(s_new)["ok"], "a comment is not the film: passed")
    touch(s_new.path("film.js"), js_es)
    touch(s_new.path("sfx.json"), '[{"t": 1}]')
    check(localize.check_film(s_new)["ok"] is False, "the sounds moved: caught")
    touch(s_new.path("sfx.json"), "[]")
    touch(s_new.path("images", "new.png"))
    check(localize.check_film(s_new)["ok"] is False, "a new picture: caught")
    os.remove(s_new.path("images", "new.png"))
    touch(s_new.path("web", "logo.png"), "other bytes")
    check(localize.check_film(s_new)["ok"] is False, "a picture changed: caught")
    touch(s_new.path("web", "logo.png"))
    check(localize.check_film(s_new)["ok"], "all put back: passed")
    record_es(ends=(3.6, 7.1, 11.0))
    rep = localize.check_film(s_new)
    check(
        not rep["ok"] and any("line 0 ends" in x for x in rep["problems"]),
        "a line said past its time: caught",
        rep["problems"],
    )
    record_es(starts=(0.5, 3.9, 8.0))
    check(localize.check_film(s_new)["ok"] is False, "a line that starts elsewhere: caught")
    record_es()
    vo_bad = dict(s_vo, voice="Puck")
    _write_json(s_new.path("vo.json"), vo_bad)
    check(localize.check_film(s_new)["ok"] is False, "another narrator: caught")
    _write_json(s_new.path("vo.json"), s_vo)
    # the film's own engine module (a scene layer pinning labels): its words may change, nothing else
    touch(strict.path("engine", "court.js"), "label('STEP IN TO THE BALL', 10, 20);\n")
    touch(s_new.path("engine", "court.js"), "label('PASO HACIA LA BOLA', 10, 20);\n")
    check(localize.own_modules(s_new) == ["engine/court.js"], "the film's own modules are found")
    check(localize.check_film(s_new)["ok"], "a label in the film's own module translated: passed")
    touch(s_new.path("engine", "court.js"), "label('PASO HACIA LA BOLA', 10, 24);\n")
    check(localize.check_film(s_new)["ok"] is False, "a number in the module changed: caught")
    touch(s_new.path("engine", "court.js"), "label('PASO HACIA LA BOLA', 10, 20);\n")
    s_new.update(localized=s_new.record()["localized"])
    check(
        s_new.writable(s_new.path("engine", "court.js")),
        "a translation may write its engine modules",
    )
    msg_s = localize.ask(s_new)
    check(
        "ONLY WORDS CHANGE" in msg_s and "must be said by 3.28 s" in msg_s,
        "its first message: only words, and each line's time",
        msg_s[:300],
    )
    check(
        localize.wordish("21st")
        and not localize.wordish("p1")
        and not localize.wordish("#fff")
        and not localize.wordish("left")
        and not localize.wordish("assets/a.png")
        and localize.wordish("Shop now")
        and not localize.wordish("700 48px Sofia Sans"),
        "what is a word and what is a setting",
    )

    # ---- a film whose narration is in its manifest (a Short built by hand and imported)
    inl = original()
    os.remove(inl.path("vo.json"))
    with open(inl.manifest, encoding="utf-8") as fh:
        im = json.load(fh)
    im["vo"] = {
        "voice": "Iapetus",
        "language": "en",
        "lines": [dict(x, start=1.0 + 4 * k) for k, x in enumerate(LINES)],
    }
    _write_json(inl.manifest, im)
    check(localize.narrated(inl), "a narration in the manifest is a narration")
    inl.update(length=23)

    i_new = Film.create("How bees make honey", 30, "drawn", client=ALICE)
    localize.seed(i_new, inl, "es", 2, "hold-i")
    with open(i_new.manifest, encoding="utf-8") as fh:
        check(json.load(fh).get("vo") == "vo.json", "it becomes the translation's vo.json")
    with open(i_new.path("vo.json"), encoding="utf-8") as fh:
        i_vo = json.load(fh)
    check(
        i_vo.get("voice") == "Iapetus" and i_vo.get("language") == "es" and len(i_vo["lines"]) == 3,
        "the same narrator, in Spanish",
        i_vo,
    )
    check(i_new.record().get("length") == 23, "the original's length, exactly (23 s, not 5)")

    # ---- a new film keeps its words on screen in words.json, apart from its code
    fresh = Film.create("How bees make honey", 30, "drawn", client=ALICE)
    with open(fresh.manifest, encoding="utf-8") as fh:
        check(
            (json.load(fh).get("data") or {}).get("words") == "words.json"
            and os.path.exists(fresh.path("words.json"))
            and "words.json" in fresh.editable(),
            "a new film has words.json, read as SK.DATA.words, and may write it",
        )
    touch(
        fresh.path("film.js"),
        "const W = SK.DATA.words;\nSK.text(W.title, {font: 'Sofia Sans'});\n"
        "SK.text('Spring open day', {size: 40});\nconst c = SK.w(0, 'Bees');\n",
    )
    check(
        localize.words_in_code(fresh) == ["Spring open day"],
        "words still written in film.js are named (never a cue word or a font)",
        localize.words_in_code(fresh),
    )
    _write_json(fresh.path("vo.json"), {"language": "en", "voice": "kc-warm", "lines": LINES})
    _write_json(fresh.path("words.json"), {"title": "How bees make honey", "tag": "Open Dec 21"})
    fresh.update(state="done", ok=True)
    w_new = Film.create("How bees make honey", 30, "drawn", client=ALICE)
    localize.seed(w_new, fresh, "de", 1, "hold-w")
    check(
        "words.json" in localize.ask(w_new) and "never the names" in localize.ask(w_new),
        "a translation of it is told its words are in words.json",
    )
    _write_json(
        w_new.path("words.json"), {"title": "Wie Bienen Honig machen", "tag": "Offen 21. Dez."}
    )
    touch(
        w_new.path("film.js"),
        "const W = SK.DATA.words;\nSK.text(W.title, {font: 'Sofia Sans'});\n"
        "SK.text('Tag der offenen Tür', {size: 40});\nconst c = SK.w(0, 'Bienen');\n",
    )
    _write_json(w_new.path("vo.json"), localize._read(w_new.path("vo.json")))
    rep = localize.check_film(w_new)
    check(
        not any("words.json" in x for x in rep["problems"]),
        "its words translated in words.json: no problem",
        rep["problems"],
    )
    _write_json(w_new.path("words.json"), {"title": "Wie Bienen Honig machen", "subtitle": "x"})
    check(
        any("words.json" in x for x in localize.check_film(w_new)["problems"]),
        "a name in words.json changed: caught",
    )
    old_style = original()
    os.remove(old_style.path("words.json"))  # as a film made before words.json
    o_new = Film.create("How bees make honey", 30, "drawn", client=ALICE)
    localize.seed(o_new, old_style, "de", 1, "hold-o")
    check(not os.path.exists(o_new.path("words.json")), "a film from before words.json gets none")

    # ---- the YouTube draft
    check(
        ytdraft.options({"language": "es", "fresh": True}) == {"language": "es", "fresh": True},
        "a draft ask may say the film's language and fresh",
    )
    check(
        ytdraft.options({"language": "ru"}) == {}
        and ytdraft.options({"language": "ru-RU", "fresh": "yes"}) == {}
        and ytdraft.options({"language": "<b>"}) == {}
        and ytdraft.options(None) == {},
        "never Russian, nothing else",
    )
    check(
        ytdraft.material(new).get("language") == "es",
        "a translation's draft is written in its language",
        ytdraft.material(new).get("language"),
    )

    print("\n%d failed" % len(bad) if bad else "\nall passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
