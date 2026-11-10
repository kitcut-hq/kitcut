"""Leo ep. 12 pilot: the first minute re-shot with MiniMax H3, keeping the voice and music.

Prompts follow MiniMax's full-reference format (subject_definitions, summary, retention_analysis,
detailed_description, overall_soundscape, non_diegetic_music) and the rules learned on this pilot,
which live in .claude/skills/video-h3/SKILL.md in the kitcut repo.

python3 leo_pilot.py plan     -> one Wan2GP settings file per shot into shots/, linted
python3 leo_pilot.py check    -> lint every prompt against the rules, print word counts
python3 leo_pilot.py assemble <outdir>  -> the shots cut to their slots, voice and music laid
"""

# ruff: noqa: INP001, T201, S603, S607  (a helper beside a skill, not a package; printing is its output;
# ffmpeg, from PATH, is the one program it runs, with arguments it builds itself)

import json
import re
import subprocess
import sys
from pathlib import Path

D = Path("/srv/kitcut/scratch/h3test")
SHOTS = D / "shots"
STEMS = D / "ep12copy" / "audio"
END = 71.6
# hard floor; MiniMax's guide wants 350-500 for a generation task; v1 had 60-100 and the model
# invented the gaps
MIN_WORDS = 180

# Every subject is described in full every time: the model has no memory between shots. References
# are the series' cast drawn ALONE by the KitCut engine (sheet_film.js -> leo_clean.png,
# car_clean.png), never crops of episode frames: a crop carries its incidental details into every
# shot (v5: the car-seat harness in the shop, and a chocolate smudge on the nose read as "a brown
# button nose").
SUBJECTS = {
    "leo": (
        "leo_clean.png",
        (
            "Leo, a four-year-old boy drawn as a simple doodle: a round peach face with pink "
            "cheeks, big yellow pixel-style sunglasses with black lenses worn over his eyes, a "
            "tiny curved line for a nose and a small smile, a fluffy blond mop of hair with "
            "zig-zag bangs, a coral-red T-shirt with a big white number 4, blue shorts and bare "
            "feet"
        ),
        (
            "his doodle face, the blond mop with zig-zag bangs, the yellow sunglasses over his "
            "eyes, the coral number-4 T-shirt, blue shorts and bare feet are retained"
        ),
        "fully_preserved",
    ),
    "car": (
        "car_clean.png",
        (
            "the family car, a light silver-grey two-door coupe: a long hood, a steeply raked "
            "windscreen, a short roof sloping in one line down to a short tail, one long door on "
            "each side with one flush handle, a small fixed rear side window, a tall kidney grille "
            "with a small round blue-and-white badge, red tail lights and five-spoke wheels"
        ),
        (
            "the light silver-grey colour, the long two-door coupe body, the sloping roof line and "
            "the wheels are retained"
        ),
        "fully_preserved",
    ),
    # a shot with no character still needs the series' look: v5's S09, with no picture, came out
    # in a heavier crayon than its neighbours. Leo's own street, drawn alone by the engine,
    # carries the style and no character.
    "cabin": (
        "cabin_clean.png",
        (
            "the inside of the family car seen from the front seats looking back: a caramel-tan "
            "back bench, solid dark charcoal pillars on both sides of the back seat with small "
            "side windows only at the far edges, a glass roof, and a blue child car seat in the "
            "middle of the bench"
        ),
        (
            "the caramel-tan bench, the solid dark charcoal pillars beside the back seat, the "
            "small side windows at the far edges, the glass roof and the blue car seat in the "
            "middle are retained"
        ),
        "fully_preserved",
    ),
    "style": (
        "style_street.png",
        (
            "the drawing style of the series, shown in a sunny street of pastel buildings and palm "
            "trees"
        ),
        (
            "only the drawing style, the line weight, the crayon hatching and the pastel palette "
            "are retained; the place shown in this shot is a different one"
        ),
        "partially_preserved",
    ),
}
STYLE = (
    "The target video is a flat 2D hand-drawn crayon cartoon for young children, in the exact "
    "drawing style of the reference pictures: thick dark outlines, visible diagonal crayon "
    "hatching inside every colour, a soft pastel palette, flat even lighting with no realistic "
    "shading, simple rounded shapes. The setting is a sunny Los Angeles afternoon."
)
INTERIOR = (
    "The car is a two-door coupe: inside, a caramel-tan back bench with Leo's blue child car seat, "
    "black shoulder straps and a red chest clip in the middle, solid dark charcoal pillars on both "
    "sides of the bench, small side windows only at the far edges, and a glass roof above."
)
# with the cabin picture: <Subject 4> is renumbered to the cabin's place in this shot's pictures
INTERIOR_CABIN = (
    "The car is a two-door coupe, its inside exactly as <Subject 4> shows it: a caramel-tan back "
    "bench with Leo's blue child car seat, black shoulder straps and a red chest clip in the "
    "middle, solid dark charcoal pillars on both sides of the bench, small side windows only at "
    "the far edges, a glass roof above, and the two dark grey front seats with headrests at the "
    "bottom corners of the frame."
)
SOUND_TAIL = " There is no speech and no vocal sound of any kind; a narrator is added later."

# start, end (episode s), subjects in frame, summary, description, soundscape.
# Say only what IS in frame: naming something that must stay out tends to bring it in.
SHOTS_LIST = [
    (
        0.0,
        9.0,
        ["leo", "cabin"],
        "Leo sits proudly in his car seat in the back of the moving car.",
        (
            "[Shot 1] A static medium shot, framed from between the two front seats, looks "
            "straight back at the back seat at Leo's eye level. INTERIOR <Subject 1> sits upright "
            "in the blue car seat in the exact centre of the frame, alone on the wide grey back "
            "seat, the black straps over his shoulders and the red clip across his red number-4 "
            "T-shirt. His small bare feet stick out over the front edge of the car seat. Behind "
            "him the rear window shows a bright blue sky, and pastel pink, yellow and mint "
            "buildings and tall palm trees slide slowly from right to left as the car drives. The "
            "daylight inside the car is soft, even and bright on his face. For the first two "
            "seconds he swings his bare feet back and forth and looks around. Then he folds his "
            "arms across his chest, lifts his chin high with a proud, confident little smile and "
            "raised eyebrows, sitting up very tall like a grown-up, and nods once slowly as if he "
            "is the boss of the car. Around the sixth second he glances sideways at the camera "
            "with one eyebrow raised, and his proud smile grows into a huge happy grin; his arms "
            "stay folded and his shoulders bounce once with pride. The camera pushes in with small "
            "amplitude at slow speed, starting with the whole car seat and back seat in frame and "
            "ending with Leo framed from the knees up in the middle of the picture. The car sways "
            "very gently as it drives, and the palm trees keep passing in the rear window. At the "
            "end he is still grinning at the camera."
        ),
        (
            "A soft steady hum of the car engine and tyres rolling on a smooth road, a faint creak "
            "of the car seat."
        ),
    ),
    (
        9.0,
        16.0,
        ["car"],
        "The dusty family car drives along a sunny street to the car wash.",
        (
            "[Shot 1] A wide side-on tracking shot at road level, the camera at the height of the "
            "car's wheels. <Subject 2> drives from the left side of the frame towards the right "
            "along a quiet two-lane street. Its silver sides are streaked with brown dust and "
            "splashed with round dark-brown mud spots, and dried mud cakes the wheel arches and "
            "the lower doors; the dusty windows hide the inside of the car. Behind it, a row of "
            "pastel pink, butter-yellow, mint-green and lilac two-storey buildings with plain "
            "blank walls, flat roofs and simple square windows passes by, with tall palm trees "
            "between them, under a clear blue sky with two small round white clouds. Bright "
            "afternoon sunlight lights the scene evenly. The camera tracks right alongside the car "
            "at the same speed, keeping it in the centre of the frame while the background scrolls "
            "past behind it. A small puff of dust lifts from the back wheel. [Shot 2] At "
            "00:04.000, the shot cuts to a static wide view down the street from the pavement. "
            "<Subject 2> slows down and turns right into the forecourt of a car wash: a long, low "
            "pastel-turquoise building with plain blank walls and a wide open arch, inside which "
            "two giant round blue brushes stand upright in a light mist of water spray. Two palm "
            "trees stand at the corners of the forecourt. The dusty silver car rolls slowly "
            "towards the arch and stops at the edge of the forecourt facing the brushes, while the "
            "camera holds still."
        ),
        (
            "Car engine, tyres on tarmac, a light breeze in the palm leaves, a bird chirping once, "
            "then a distant rush of water spray."
        ),
    ),
    (
        16.0,
        23.4,
        ["leo", "cabin"],
        "Leo cheers about the car wash, and his feet are bare.",
        (
            "[Shot 1] A static medium shot from between the front seats looks straight back at "
            "<Subject 1> in his blue car seat in the middle of the back seat. INTERIOR Through the "
            "rear window behind him a blue sky, palm trees and the top of a pastel-turquoise "
            "building are visible. In the first second his sits bolt upright with excitement; then "
            "he throws both arms straight up above his head with his fists clenched, his mouth "
            "wide open in a delighted silent cheer, and bounces up and down in the seat so that "
            "the straps wobble. His bare feet kick up and down over the front edge of the seat, "
            "and he shakes both fists in the air twice in triumph. [Shot 2] At 00:05.000, the shot "
            "cuts to a close-up from the front, at seat height, of his two small bare feet kicking "
            "happily over the front edge of the blue car seat, the caramel-tan bench behind them, "
            "simple rounded doodle feet seen from the front. The camera holds steady. Soft even "
            "daylight fills the car from the side windows for the whole shot."
        ),
        (
            "Car interior hum, the soft thump of his heels against the car seat, a rustle of the "
            "seat straps."
        ),
    ),
    (
        23.4,
        28.3,
        [],
        "One small sneaker lies on the car floor, and the other one is nowhere.",
        (
            "[Shot 1] A low close-up at floor level inside a car, looking across the grey carpeted "
            "floor under the grey front passenger seat, with the grey seat rails and the bottom of "
            "a grey door panel in the frame. Soft daylight from the side window falls evenly "
            "across the carpet. On the carpet lie a scatter of golden biscuit crumbs, a small "
            "green toy dinosaur lying on its side, and one single tiny red child's sneaker with a "
            "white rubber sole and white laces, lying on its side near the seat rail. The shot "
            "starts on the crumbs and the green dinosaur. The camera trucks right with small "
            "amplitude at slow speed along the floor, passes the dinosaur and the single red "
            "sneaker, and continues across a stretch of plain empty grey carpet, as if searching. "
            "It slows down and comes to rest on a bare patch of grey carpet under the seat where "
            "nothing lies at all, and holds there for the last second. One crumb rolls a little as "
            "the car moves. The whole shot stays low on the floor, at the height of a crumb."
        ),
        "Quiet car interior, a crumb crunching softly, the low hum of the engine.",
    ),
    (
        28.3,
        33.0,
        ["car"],
        "The line for the car wash is very long.",
        (
            "[Shot 1] A high wide shot looking down over a sunny car wash entrance in the "
            "afternoon. A long curving line of small rounded cartoon cars in bright red, yellow, "
            "blue, green, purple and orange waits nose to tail on grey tarmac with white lane "
            "markings, snaking from the bottom right of the frame up to a long, low "
            "pastel-turquoise car wash building at the top left, which has plain blank walls and a "
            "wide open arch holding two giant round blue brushes. A fine mist of water rises from "
            "the arch. <Subject 2>, with dusty silver sides and mud spots, waits at the very end "
            "of the line in the bottom right foreground, the last car of all. Rows of palm trees "
            "and pastel pink and yellow buildings stand behind the car wash under a clear blue "
            "sky. The first car in the line rolls forward into the arch and the whole line "
            "shuffles one car-length forward, the silver car last. The camera pedestals up with "
            "large amplitude at slow speed, rising higher and higher above the line so that more "
            "and more waiting cars come into view, revealing how very long the line is. By the end "
            "of the shot the silver car is a small shape at the bottom of the frame and the line "
            "fills the whole picture."
        ),
        (
            "Idling engines, a distant rush of water spray from the car wash, a car door closing "
            "far away."
        ),
    ),
    (
        33.0,
        42.3,
        ["leo", "cabin"],
        "Leo counts the cars in front of him, and skips six.",
        (
            "[Shot 1] A medium shot from between the front seats looking back at <Subject 1>, "
            "strapped into his blue car seat in the middle of the bench. INTERIOR He leans forward "
            "against his straps, raises his right hand and points past the camera towards the cars "
            "waiting ahead, his mouth open in concentration, eyebrows up. [Shot 2] At 00:02.500, "
            "the shot cuts to his own point of view through the windscreen: a long line of small "
            "colourful cars waits in one lane ahead, all facing away, so only their backs and red "
            "tail lights are seen, nose to tail: a red car, then a yellow car, a blue car, a green "
            "car, an orange car and a purple car. His small hand with a pointing finger comes in "
            "from the bottom edge of the frame and taps the air towards each car in turn, and as "
            'he taps each one a white circle pops up above it with a black number: "1" over the '
            'red car, "2" over the yellow car, "3" over the blue car, "4" over the green '
            'car, "5" over the orange car, and then a red circle with "7" over the purple car. '
            "[Shot 3] At 00:07.000, the shot cuts back to the medium shot of <Subject 1> in his "
            "car seat. He looks at his own pointing hand with a playful puzzled grin, shrugs with "
            "both shoulders and breaks into a big happy smile, as if the number does not matter. "
            "Soft even daylight."
        ),
        "Muffled idling engines outside, a soft pop with each number, the car interior hum.",
    ),
    (
        42.3,
        51.0,
        ["leo", "cabin"],
        "Leo does not mind the long line, because the line has a tradition: chocolate.",
        (
            "[Shot 1] A medium shot from between the front seats looking back at <Subject 1> in "
            "his blue car seat, the car standing still in the long car wash line. INTERIOR Through "
            "the rear side windows, other colourful cars wait in line in the sun. Leo is "
            "completely happy to wait: he leans back in his seat, puts both hands behind his head "
            "and swings his bare feet slowly, smiling, head tilted back, as calm as a grown-up on "
            "holiday. Around the fourth second he sits up straight, as if remembering something "
            "wonderful, and a slow knowing smile spreads across his face; he rubs his hands "
            "together. The camera pushes in with small amplitude at slow speed. [Shot 2] At "
            "00:07.000, the shot cuts to a close-up of the face and shoulders of <Subject 1>, his "
            "head tilted back in a happy dream. A round white thought bubble with two small "
            "trailing circles floats up above his head, and inside it a big purple chocolate bar "
            "with a gold stripe glows softly. He licks his lips and hugs himself with both arms. "
            "Soft even daylight."
        ),
        (
            "The soft hum of the idling car, a faint water spray far ahead, a tiny sparkling chime "
            "as the thought bubble appears."
        ),
    ),
    (
        51.0,
        58.0,
        ["car", "leo"],
        "The car has only two doors, and Leo sits in the back, far from both.",
        (
            "[Shot 1] A side-on medium-wide shot of <Subject 2>, still dusty silver with its sides "
            "streaked with brown dust and round mud spots, waiting on a sunny forecourt with palm "
            "trees and pastel buildings behind it under a blue sky. Its long silver body has "
            "exactly one long door on this side, at the front; behind that door is a solid silver "
            "panel with one small fixed triangular side window high up near the roof. The camera "
            "trucks right with small amplitude at slow speed along the car, from the front wheel "
            "past the single front door to the rear side window. Through the rear side window, "
            "<Subject 1> sits in his blue car seat in the middle of the back seat, far behind the "
            "front door, and waves at the camera with one hand, smiling. Through that small window "
            "only his head, shoulders and waving hand are seen; the dark tinted front window shows "
            "nothing inside. The camera comes to rest framing the small rear window with Leo "
            "waving inside it, and the long solid silver panel below."
        ),
        "Outdoor forecourt ambience, distant water spray, a palm frond rustling in the breeze.",
    ),
    (
        58.0,
        62.0,
        ["style"],
        "At the next car, another dad folds the front seat forward.",
        (
            "[Shot 1] A static medium close-up beside the open door of a different small blue "
            "two-door car on a sunny forecourt, with a palm tree and a pastel wall in the "
            "background: one long door on this side, wide open, and behind it a solid blue panel. "
            "A stranger dad, seen from the chest down, wearing a green shirt, khaki trousers and "
            "brown shoes, pulls the lever at the side of the beige front passenger seat, and the "
            "seat back tips forward towards the dashboard, folding down flat, so that a gap opens "
            "to the back seat in the usual, ordinary way. He holds the folded seat back down with "
            "one hand and steps back half a pace. The camera holds a static shot at waist height, "
            "framing the door, the folding seat and his hands. Bright even afternoon sunlight "
            "lights the scene. The movement is calm, practised and ordinary."
        ),
        "A seat lever clunk, the seat creaking forward, footsteps on tarmac, distant water spray.",
    ),
    (
        62.0,
        66.0,
        ["leo", "cabin"],
        "The sunroof opens, and Leo is going out through the roof.",
        (
            "[Shot 1] A static medium shot from the front seats looking back and slightly up at "
            "<Subject 1>. INTERIOR Above him, the rectangular sunroof in the grey roof lining "
            "slides open from front to back, and bright sunlight and blue sky pour in through the "
            "opening, lighting him from above. Leo, the black straps unbuckled and lying open on "
            "both sides of the seat, stands up on the seat of his blue car seat, points straight "
            "up at the open sunroof with both index fingers and opens his mouth wide in silent "
            "excitement, bouncing on his toes. His spiky blond hair and his sunglasses catch the "
            "light. By the end of the shot he is standing tall with both arms reaching up towards "
            "the open sky. The camera tilts up with small amplitude at slow speed to follow his "
            "arms towards the sunroof."
        ),
        "The electric whirr of the sunroof sliding open, a rush of outdoor air.",
    ),
    (
        66.0,
        71.6,
        ["leo", "car"],
        "Dad lifts Leo up and out through the sunroof, seen through Dad's own eyes.",
        (
            "[Shot 1] A point-of-view shot through Dad's own eyes as he stands beside <Subject 2> "
            "and looks down at its silver roof, the open glass sunroof in the middle of the frame "
            "and a sunny forecourt with palm trees around the car. Through the sunroof, <Subject "
            "1> looks up at the camera from the caramel-tan back bench, arms raised. Dad's own two "
            "hands and forearms, in short white T-shirt sleeves, come in from the bottom edge of "
            "the frame towards the camera's point of view and reach down into the sunroof; they "
            "slide in under Leo's arms and hold him around his chest, the hands below his "
            "shoulders and away from his face the whole time, and lift him smoothly up and out of "
            "the roof towards the camera. Leo, barefoot, rises out of the sunroof, throws both "
            "arms up like a champion and beams straight into the camera, his bare feet dangling "
            "above the silver roof, the blue sky behind his head as the camera tilts up with small "
            "amplitude at slow speed. Bright even sunlight."
        ),
        "Outdoor air, a soft whoosh as he is lifted, palm leaves rustling.",
    ),
]


def build(n: int) -> tuple[float, float, list[str], str]:
    """Return shot n's start, end, reference names and its six-section prompt."""
    s, e, subj, summary, desc, sound = SHOTS_LIST[n - 1]
    defs = "\n".join(
        f"<Subject {i}> is {SUBJECTS[k][1]}, from <Picture {i}>." for i, k in enumerate(subj, 1)
    )
    keep = "\n".join(
        f"<Subject {i}> (appears in [Shot 1]): {SUBJECTS[k][3]} - {SUBJECTS[k][2]}."
        for i, k in enumerate(subj, 1)
    )
    # descriptions are written with <Subject 1> = Leo and <Subject 2> = the car; renumber, in one
    # pass, to this shot's picture order (two sequential replaces swapped a label twice on
    # 2026-10-23)
    canon = {"1": "leo", "2": "car", "3": "style", "4": "cabin"}
    desc = desc.replace("INTERIOR ", (INTERIOR_CABIN if "cabin" in subj else INTERIOR) + " ")
    desc = re.sub(
        r"<Subject (\d)>", lambda m: f"<Subject {subj.index(canon[m.group(1)]) + 1}>", desc
    )
    body = STYLE + " " + desc
    parts = []
    if subj:
        parts.append("subject_definitions:\n" + defs)
    parts.append(f"summary:\n[reference generation] {summary}" if subj else f"summary:\n{summary}")
    if subj:
        parts.append("retention_analysis:\n" + keep)
    parts += [
        "detailed_description:\n" + body,
        "overall_soundscape:\n" + sound + SOUND_TAIL,
        "non_diegetic_music:\nN/A",
    ]
    return s, e, subj, "\n\n".join(parts)


def lint(prompt: str, dur: float, subj: list[str]) -> tuple[int, list[str]]:
    """Check a prompt against the rules before a GPU minute is spent on it."""
    problems = []
    desc = prompt.split("detailed_description:\n")[1].split("\n\noverall_soundscape", maxsplit=1)[0]
    words = len(desc.split())
    if words < MIN_WORDS:
        problems.append(f"description {words} words; the guide wants 350-500")
    problems += [
        f"cut at {m.group(0)} is past the {dur:.1f}s clip"
        for m in re.finditer(r"At 00:(\d\d)\.(\d{3})", desc)
        if int(m.group(1)) + int(m.group(2)) / 1000 >= dur
    ]
    # every label must point at the picture its words describe: Leo's words next to Leo's label
    defs = dict(re.findall(r"<Subject (\d+)> is (\w+)", prompt))
    for i, after in re.findall(r"<Subject (\d+)>(.{0,60})", desc):
        who = defs.get(i, "")
        if ("car seat" in after or "his " in after or " he " in after) and who != "Leo":
            problems.append(f"<Subject {i}> is '{who}' but is described as Leo: '{after[:40]}'")
    banned = (
        "no shoes",
        "no socks",
        "no adults",
        "no hands",
        "no text",
        "no signs",
        "shadow",
        "Dad's legs",
    )
    problems += [
        f"names something that must stay out: '{bad}'"
        for bad in banned
        if bad.lower() in desc.lower()
    ]
    used = set(re.findall(r"<Subject (\d+)>", desc))
    if any(int(i) > len(subj) for i in used):
        problems.append(f"uses <Subject {max(used)}> but defines only {len(subj)}")
    return words, problems


def plan() -> int:
    """Write one Wan2GP settings file per shot and lint them; return how many are bad."""
    SHOTS.mkdir(exist_ok=True)
    for n in range(1, len(SHOTS_LIST) + 1):
        s, e, subj, prompt = build(n)
        cfg = {
            "model_type": "minimax_h3_fasth3_omni",
            # positional: text encoder, video VAE, DiT priority; "lower_ram" in the second slot was
            # dropped silently, so the pilot always ran at the default "Lower VRAM" (SKILL.md)
            "config": "gguf_q4_k_m",
            "image_mode": 0,
            "image_prompt_type": "",
            "video_prompt_type": "I" if subj else "",
            "resolution": "1344x768",
            "video_length": f"{max(4.0, e - s):.1f}s",
            "seed": 42,
            "num_inference_steps": 8,
            "prompt": prompt,
            "output_filename": f"S{n:02d}",
            # Wan2GP's default "PG" makes every blank-line paragraph a separate video; the six
            # sections are one prompt
            "multi_prompts_gen_type": "FG",
        }
        if subj:
            cfg["image_refs"] = [str(D / SUBJECTS[k][0]) for k in subj]
        (SHOTS / f"S{n:02d}.json").write_text(json.dumps(cfg, indent=1))
    return check()


def check() -> int:
    """Lint every shot's prompt and print a line per shot; return the number of bad shots."""
    bad = 0
    for n in range(1, len(SHOTS_LIST) + 1):
        s, e, subj, prompt = build(n)
        words, problems = lint(prompt, e - s, subj)
        bad += bool(problems)
        verdict = "; ".join(problems) or "ok"
        print(f"S{n:02d} {s:5.1f}-{e:5.1f} ({e - s:4.1f}s) {words:3d} words refs={subj} {verdict}")
    return bad


def assemble(outdir: str) -> None:
    """Cut each shot to its slot, join them, mix the episode's voice and music over them."""
    out = D / outdir
    parts = []
    for n, (s, e, *_rest) in enumerate(SHOTS_LIST, 1):
        dur = e - s
        cut = out / f"cut_S{n:02d}.mkv"
        subprocess.run(
            [
                "ffmpeg",
                "-loglevel",
                "error",
                "-y",
                "-i",
                str(out / f"S{n:02d}.mp4"),
                "-filter_complex",
                (
                    "[0:v]scale=1344:768,fps=24,tpad=stop_mode=clone:stop_duration=3,"
                    f"trim=duration={dur:.3f},setpts=PTS-STARTPTS[v];"
                    f"[0:a]aresample=48000,apad,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a]"
                ),
                "-map",
                "[v]",
                "-map",
                "[a]",
                "-c:v",
                "libx264",
                "-crf",
                "16",
                "-preset",
                "medium",
                "-c:a",
                "pcm_s16le",
                str(cut),
            ],
            check=True,
        )
        parts.append(str(cut))
    lst = out / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = out / "joined.mkv"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(lst),
            "-c",
            "copy",
            str(joined),
        ],
        check=True,
    )

    # The episode's own voice and music stems (sketch-audio --stems on a copy of the episode); the
    # model's sound replaces the episode's sound effects, which were timed to KitCut's picture, at
    # their loudness.
    vo, music, sfx = (STEMS / f"stem_{k}.wav" for k in ("vo", "music", "sfx"))
    gain_db = lufs(sfx, END) - lufs(joined, END)
    print(f"model sound gain {gain_db:+.1f} dB (to the episode's sound-effect level)")
    fc = (
        f"[0:a]volume={gain_db:.2f}dB[fx];[1:a]atrim=0:{END:.2f}[v];[2:a]atrim=0:{END:.2f}[m];"
        "[v][m][fx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5[mix]"
    )
    dest = D / f"leo-ep12-h3-{outdir}.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(joined),
            "-i",
            str(vo),
            "-i",
            str(music),
            "-filter_complex",
            fc,
            "-map",
            "0:v",
            "-map",
            "[mix]",
            "-c:v",
            "libx264",
            "-crf",
            "18",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-ar",
            "48000",
            "-t",
            f"{END:.2f}",
            "-movflags",
            "+faststart",
            str(dest),
        ],
        check=True,
    )
    print("wrote", dest)


def lufs(path: Path, dur: float) -> float:
    """Return the integrated loudness of the first dur seconds of path, in LUFS."""
    r = subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-t",
            f"{dur:.2f}",
            "-i",
            str(path),
            "-map",
            "0:a",
            "-af",
            "ebur128",
            "-f",
            "null",
            "-",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return float([ln for ln in r.stderr.splitlines() if ln.strip().startswith("I:")][-1].split()[1])


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    sys.exit({"plan": plan, "check": check, "assemble": assemble}[cmd](*rest) or 0)
