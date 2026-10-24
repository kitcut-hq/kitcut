"""Leo ep. 12 pilot: the first minute re-shot with MiniMax H3, voice and music kept from the KitCut episode.

Prompts follow MiniMax's full-reference format (subject_definitions, summary, retention_analysis,
detailed_description, overall_soundscape, non_diegetic_music) and the rules learned on this pilot,
which live in .claude/skills/video-h3/SKILL.md in the kitcut repo.

python3 leo_pilot.py plan     -> one Wan2GP settings file per shot into shots/, linted
python3 leo_pilot.py check    -> lint every prompt against the rules, print word counts
python3 leo_pilot.py assemble <outdir>  -> cut each shot to its slot, lay the episode's voice + music, mix
"""
import json
import re
import subprocess
import sys
from pathlib import Path

D = Path("/srv/kitcut/scratch/h3test")
SHOTS = D / "shots"
STEMS = D / "ep12copy" / "audio"
END = 71.6
MIN_WORDS = 180  # hard floor; MiniMax's guide wants 350-500 for a generation task, v1 had 60-100 and the model invented the gaps

# Every subject is described in full every time: the model has no memory between shots.
SUBJECTS = {
    "leo": ("leo_ref.png",
            "Leo, a four-year-old boy: a round peach face with pink cheeks, a small brown button nose and dot eyes, "
            "spiky zig-zag blond hair, yellow pixel-style sunglasses pushed up on top of his head, a red T-shirt with a white "
            "number 4, blue shorts and bare feet",
            "his face, spiky blond hair, the sunglasses on top of his head, the red number-4 T-shirt, blue shorts and bare feet"),
    "car": ("car_ref.png",
            "the family car, a long silver two-door coupe with a low sloping roof, dark window frames, red tail lights "
            "and five-spoke silver wheels",
            "the silver colour, the long two-door body, the low roof and the wheels"),
}
STYLE = ("The target video is a flat 2D hand-drawn crayon cartoon for young children, in the exact drawing style of the "
         "reference pictures: thick dark outlines, visible diagonal crayon hatching inside every colour, a soft pastel palette, "
         "flat even lighting with no realistic shading, simple rounded shapes. The setting is a sunny Los Angeles afternoon.")
INTERIOR = ("The car interior is light grey throughout: grey fabric seats, grey door panels, a grey dashboard and a grey roof "
            "lining. Leo's blue child car seat, with black shoulder straps and a red chest clip, sits in the middle of the grey back seat.")
SOUND_TAIL = " There is no speech and no vocal sound of any kind; a narrator is added later."

# start, end (episode s), subjects in frame, summary, description, soundscape.
# Say only what IS in frame: naming something that must stay out tends to bring it in.
SHOTS_LIST = [
    (0.0, 9.0, ["leo"], "Leo sits proudly in his car seat in the back of the moving car.",
     "[Shot 1] A static medium shot, framed from between the two front seats, looks straight back at the back seat at Leo's eye level. INTERIOR "
     "<Subject 1> sits upright in the blue car seat in the exact centre of the frame, alone on the wide grey back seat, the black straps over his "
     "shoulders and the red clip across his red number-4 T-shirt. His small bare feet stick out over the front edge of the car seat. Behind him the "
     "rear window shows a bright blue sky, and pastel pink, yellow and mint buildings and tall palm trees slide slowly from right to left as the car "
     "drives. The daylight inside the car is soft, even and bright on his face. For the first two seconds he swings his bare feet back and forth and "
     "looks around. Then he folds his arms across his chest, lifts his chin high, puffs out his cheeks and narrows his eyes, holding a very serious "
     "grown-up pose, and nods once slowly as if he is the boss of the car. Around the sixth second he glances sideways at the camera with one eyebrow "
     "raised, and his serious face breaks into a huge proud grin; his arms stay folded and his shoulders bounce once with pride. The camera pushes in "
     "with small amplitude at slow speed, starting with the whole car seat and back seat in frame and ending with Leo framed from the knees up in the "
     "middle of the picture. The car sways very gently as it drives, and the palm trees keep passing in the rear window. At the end he is still "
     "grinning at the camera.",
     "A soft steady hum of the car engine and tyres rolling on a smooth road, a faint creak of the car seat."),
    (9.0, 16.0, ["car"], "The dusty family car drives along a sunny street to the car wash.",
     "[Shot 1] A wide side-on tracking shot at road level, the camera at the height of the car's wheels. <Subject 2> drives from the left side of the "
     "frame towards the right along a quiet two-lane street. Its silver sides are streaked with brown dust and splashed with round dark-brown mud "
     "spots, and dried mud cakes the wheel arches and the lower doors; the dusty windows hide the inside of the car. Behind it, a row of pastel pink, "
     "butter-yellow, mint-green and lilac two-storey buildings with plain blank walls, flat roofs and simple square windows passes by, with tall palm "
     "trees between them, under a clear blue sky with two small round white clouds. Bright afternoon sunlight lights the scene evenly. The camera "
     "tracks right alongside the car at the same speed, keeping it in the centre of the frame while the background scrolls past behind it. A small "
     "puff of dust lifts from the back wheel. "
     "[Shot 2] At 00:04.000, the shot cuts to a static wide view down the street from the pavement. <Subject 2> slows down and turns right into the "
     "forecourt of a car wash: a long, low pastel-turquoise building with plain blank walls and a wide open arch, inside which two giant round blue "
     "brushes stand upright in a light mist of water spray. Two palm trees stand at the corners of the forecourt. The dusty silver car rolls slowly "
     "towards the arch and stops at the edge of the forecourt facing the brushes, while the camera holds still.",
     "Car engine, tyres on tarmac, a light breeze in the palm leaves, a bird chirping once, then a distant rush of water spray."),
    (16.0, 23.4, ["leo"], "Leo cheers about the car wash, and his feet are bare.",
     "[Shot 1] A static medium shot from between the front seats looks straight back at <Subject 1> in his blue car seat in the middle of the back seat. "
     "INTERIOR Through the rear window behind him a blue sky, palm trees and the top of a pastel-turquoise building are visible. In the first second his "
     "eyes open wide with excitement; then he throws both arms straight up above his head with his fists clenched, his mouth wide open in a delighted "
     "silent cheer, and bounces up and down in the seat so that the straps wobble. His bare feet kick up and down over the front edge of the seat, and "
     "he shakes both fists in the air twice in triumph. "
     "[Shot 2] At 00:03.500, the shot cuts to a close-up at seat level of his two small bare feet dangling over the front edge of the blue car seat, "
     "with the grey back seat and its grey fabric behind them. His feet are bare, with pink toes and pink soles. The ten toes wiggle happily and the "
     "feet cross and uncross. The camera tilts up with small amplitude at slow speed from the feet to his knees and the hem of his blue shorts, where "
     "his small hands rest, drumming on his knees with excitement. Soft even daylight fills the car from the side windows for the whole shot.",
     "Car interior hum, the soft thump of his heels against the car seat, a rustle of the seat straps."),
    (23.4, 28.3, [], "One small sneaker lies on the car floor, and the other one is nowhere.",
     "[Shot 1] A low close-up at floor level inside a car, looking across the grey carpeted floor under the grey front passenger seat, with the grey seat "
     "rails and the bottom of a grey door panel in the frame. Soft daylight from the side window falls evenly across the carpet. On the carpet lie a "
     "scatter of golden biscuit crumbs, a small green toy dinosaur lying on its side, and one single tiny red child's sneaker with a white rubber sole "
     "and white laces, lying on its side near the seat rail. The shot starts on the crumbs and the green dinosaur. The camera trucks right with small "
     "amplitude at slow speed along the floor, passes the dinosaur and the single red sneaker, and continues across a stretch of plain empty grey "
     "carpet, as if searching. It slows down and comes to rest on a bare patch of grey carpet under the seat where nothing lies at all, and holds "
     "there for the last second. One crumb rolls a little as the car moves. The whole shot stays low on the floor, at the height of a crumb.",
     "Quiet car interior, a crumb crunching softly, the low hum of the engine."),
    (28.3, 33.0, ["car"], "The line for the car wash is very long.",
     "[Shot 1] A high wide shot looking down over a sunny car wash entrance in the afternoon. A long curving line of small rounded cartoon cars in bright "
     "red, yellow, blue, green, purple and orange waits nose to tail on grey tarmac with white lane markings, snaking from the bottom right of the frame "
     "up to a long, low pastel-turquoise car wash building at the top left, which has plain blank walls and a wide open arch holding two giant round "
     "blue brushes. A fine mist of water rises from the arch. <Subject 2>, with dusty silver sides and mud spots, waits at the very end of the line in "
     "the bottom right foreground, the last car of all. Rows of palm trees and pastel pink and yellow buildings stand behind the car wash under a clear "
     "blue sky. The first car in the line rolls forward into the arch and the whole line shuffles one car-length forward, the silver car last. "
     "The camera pedestals up with large amplitude at slow speed, rising higher and higher above the line so that more and more waiting cars come into "
     "view, revealing how very long the line is. By the end of the shot the silver car is a small shape at the bottom of the frame and the line fills "
     "the whole picture.",
     "Idling engines, a distant rush of water spray from the car wash, a car door closing far away."),
    (33.0, 42.3, ["leo"], "Leo counts the cars in front of him on his fingers.",
     "[Shot 1] A medium close-up from inside the car, from beside the back seat, looking at <Subject 1> in three-quarter profile as he faces the side "
     "window on the right of the frame. INTERIOR Through the side window, colourful small cars in red, yellow, blue and green wait in line on a sunny "
     "street with palm trees and pastel buildings. Soft even daylight comes through the window onto his face. Leo raises his right hand and counts the "
     "cars on his fingers, raising one finger at a time while his eyes move from car to car, his lips moving silently and his brow frowning with "
     "concentration. He reaches four fingers, then five, then hesitates, wiggles his fingers, looks at his hand in confusion and tries again. After a "
     "moment he gives up, drops his hand, shrugs with both shoulders and turns from the window towards the camera with a big happy smile, as if the "
     "number does not matter. The camera arcs with small amplitude at slow speed from his profile round to the front of his face, ending on his smile "
     "with the window and the waiting cars behind him.",
     "Muffled idling engines outside the closed window, the soft car interior hum."),
    (42.3, 51.0, ["leo"], "The tradition while waiting: a chocolate bar from the shop.",
     "[Shot 1] A wide shot inside a small, bright car wash shop with plain pastel-yellow walls and a light wooden floor. A long wooden shelf at child "
     "height is full of colourful chocolate bars in purple, gold, red and green wrappers, arranged in neat rows and lit warmly so they glow like "
     "treasure. The camera pushes in with medium amplitude at slow speed towards the shelf. "
     "[Shot 2] At 00:03.500, the shot cuts to a close-up of the middle of the shelf: rows of chocolate bars fill the frame. The small hand and red "
     "sleeve of <Subject 1> reach in from the bottom of the frame, hover over the bars for a moment, and take one purple chocolate bar with a gold "
     "stripe. "
     "[Shot 3] At 00:05.500, the shot cuts to a static medium shot of <Subject 1> standing barefoot on the wooden floor in front of the shelf, hugging "
     "the purple chocolate bar to his chest with both arms, his eyes wide and shining and a huge smile on his face. He sways happily from side to side "
     "with the chocolate held tight. Warm even light fills the shop.",
     "A soft shop door chime, a gentle crinkle of a wrapper, quiet shop ambience."),
    (51.0, 58.0, ["car", "leo"], "The car has only two doors, and Leo sits in the back, far from both.",
     "[Shot 1] A side-on medium-wide shot of <Subject 2>, now clean and shiny silver, parked on a sunny forecourt with palm trees and pastel buildings "
     "behind it under a blue sky. Its long silver body has exactly one door on this side, at the front, and behind that door a long fixed rear side "
     "window and a long silver rear panel. The camera trucks right with small amplitude at slow speed along the car, from the front wheel past the "
     "single front door to the rear side window. Through the rear side window, <Subject 1> sits in his blue car seat in the middle of the back seat, "
     "far behind the front door, and waves at the camera with one hand, smiling. INTERIOR The camera comes to rest framing the rear side window with "
     "Leo waving inside it, and the long silver panel below.",
     "Outdoor forecourt ambience, distant water spray, a palm frond rustling in the breeze."),
    (58.0, 62.0, [], "At the next car, another dad folds the front seat forward.",
     "[Shot 1] A static medium close-up beside the open front door of a different small blue car on a sunny forecourt, with a palm tree and a pastel "
     "wall in the background. A stranger dad, seen from the chest down, wearing a green shirt, khaki trousers and brown shoes, leans into the doorway, "
     "pulls the lever at the side of the beige front passenger seat and folds the seat forward with both hands, so that the way into the back seat "
     "opens up in the usual, ordinary way. He holds the folded seat and steps back half a pace. The camera holds a static shot at waist height, framing "
     "the door, the folding seat and his hands. Bright even afternoon sunlight lights the scene. The movement is calm, practised and ordinary.",
     "A seat lever clunk, the seat creaking forward, footsteps on tarmac, distant water spray."),
    (62.0, 66.0, ["leo"], "The sunroof opens, and Leo is going out through the roof.",
     "[Shot 1] A static medium shot from the front seats looking back and slightly up at <Subject 1>. INTERIOR Above him, the rectangular sunroof in the "
     "grey roof lining slides open from front to back, and bright sunlight and blue sky pour in through the opening, lighting him from above. Leo, "
     "unbuckled, the black straps hanging loose beside him, stands up on the seat of his blue car seat, points straight up at the open sunroof with both "
     "index fingers and opens his mouth wide in silent excitement, bouncing on his toes. His spiky blond hair and the sunglasses on his head catch the "
     "light. By the end of the shot he is standing tall with both arms reaching up towards the open sky. The camera tilts up with small amplitude at "
     "slow speed to follow his arms towards the sunroof.",
     "The electric whirr of the sunroof sliding open, a rush of outdoor air."),
    (66.0, 71.6, ["leo", "car"], "Dad lifts Leo up and out through the sunroof.",
     "[Shot 1] A low-angle medium shot from the ground beside <Subject 2>, looking up at the roof of the car against a clear blue sky with palm trees at "
     "the edges of the frame. The sunroof is open. Two adult hands with forearms in short white T-shirt sleeves reach in from the bottom edge of the "
     "frame, hold <Subject 1> under his arms and lift him smoothly up out of the sunroof into the sunshine. Leo, barefoot, rises above the silver roof, "
     "throws both arms up like a champion and beams with his eyes closed in joy, his bare feet dangling. The hands hold him high for a moment against "
     "the sky. The camera tilts up with small amplitude at slow speed, following him up, and ends with Leo framed against the blue sky, arms up, the "
     "silver roof at the bottom of the frame. Bright even sunlight.",
     "Outdoor air, a soft whoosh as he is lifted, palm leaves rustling."),
]


def build(n):
    s, e, subj, summary, desc, sound = SHOTS_LIST[n - 1]
    defs = "\n".join(f"<Subject {i}> is {SUBJECTS[k][1]}, from <Picture {i}>." for i, k in enumerate(subj, 1))
    keep = "\n".join(f"<Subject {i}> (appears in [Shot 1]): fully_preserved - {SUBJECTS[k][2]} are retained." for i, k in enumerate(subj, 1))
    # descriptions are written with <Subject 1> = Leo and <Subject 2> = the car; renumber, in one pass, to this
    # shot's picture order (two sequential replaces swapped a label twice on 2026-10-23)
    canon = {"1": "leo", "2": "car"}
    desc = re.sub(r"<Subject (\d)>", lambda m: f"<Subject {subj.index(canon[m.group(1)]) + 1}>", desc)
    body = STYLE + " " + desc.replace("INTERIOR ", INTERIOR + " ")
    parts = []
    if subj:
        parts.append("subject_definitions:\n" + defs)
    parts.append(f"summary:\n[reference generation] {summary}" if subj else f"summary:\n{summary}")
    if subj:
        parts.append("retention_analysis:\n" + keep)
    parts += ["detailed_description:\n" + body, "overall_soundscape:\n" + sound + SOUND_TAIL, "non_diegetic_music:\nN/A"]
    return s, e, subj, "\n\n".join(parts)


def lint(prompt, dur, subj):
    """The rules a prompt must pass before a GPU minute is spent on it."""
    problems = []
    desc = prompt.split("detailed_description:\n")[1].split("\n\noverall_soundscape")[0]
    words = len(desc.split())
    if words < MIN_WORDS:
        problems.append(f"description {words} words; the guide wants 350-500")
    for m in re.finditer(r"At 00:(\d\d)\.(\d{3})", desc):
        if int(m.group(1)) + int(m.group(2)) / 1000 >= dur:
            problems.append(f"cut at {m.group(0)} is past the {dur:.1f}s clip")
    # every label must point at the picture its words describe: Leo's words next to Leo's label
    defs = dict(re.findall(r"<Subject (\d+)> is (\w+)", prompt))
    for i, after in re.findall(r"<Subject (\d+)>(.{0,60})", desc):
        who = defs.get(i, "")
        if ("car seat" in after or "his " in after or " he " in after) and who != "Leo":
            problems.append(f"<Subject {i}> is '{who}' but is described as Leo: '{after[:40]}'")
    for bad in ("no shoes", "no socks", "no adults", "no hands", "no text", "no signs", "shadow", "Dad's legs"):
        if bad.lower() in desc.lower():
            problems.append(f"names something that must stay out: '{bad}'")
    used = set(re.findall(r"<Subject (\d+)>", desc))
    if any(int(i) > len(subj) for i in used):
        problems.append(f"uses <Subject {max(used)}> but defines only {len(subj)}")
    return words, problems


def plan():
    SHOTS.mkdir(exist_ok=True)
    for n in range(1, len(SHOTS_LIST) + 1):
        s, e, subj, prompt = build(n)
        cfg = dict(model_type="minimax_h3_fasth3_omni", config="gguf_q4_k_m,lower_ram", image_mode=0, image_prompt_type="",
                   video_prompt_type="I" if subj else "", resolution="1344x768", video_length=f"{max(4.0, e - s):.1f}s",
                   seed=42, num_inference_steps=8, prompt=prompt, output_filename=f"S{n:02d}",
                   # Wan2GP's default "PG" makes every blank-line paragraph a separate video; the six sections are one prompt
                   multi_prompts_gen_type="FG")
        if subj:
            cfg["image_refs"] = [str(D / SUBJECTS[k][0]) for k in subj]
        (SHOTS / f"S{n:02d}.json").write_text(json.dumps(cfg, indent=1))
    return check()


def check():
    bad = 0
    for n in range(1, len(SHOTS_LIST) + 1):
        s, e, subj, prompt = build(n)
        words, problems = lint(prompt, e - s, subj)
        bad += bool(problems)
        print(f"S{n:02d} {s:5.1f}-{e:5.1f} ({e - s:4.1f}s) {words:3d} words refs={subj} {'; '.join(problems) or 'ok'}")
    return bad


def assemble(outdir):
    out = D / outdir
    parts = []
    for n, (s, e, *_rest) in enumerate(SHOTS_LIST, 1):
        dur = e - s
        cut = out / f"cut_S{n:02d}.mkv"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(out / f"S{n:02d}.mp4"), "-filter_complex",
                        f"[0:v]scale=1344:768,fps=24,tpad=stop_mode=clone:stop_duration=3,trim=duration={dur:.3f},setpts=PTS-STARTPTS[v];"
                        f"[0:a]aresample=48000,apad,atrim=duration={dur:.3f},asetpts=PTS-STARTPTS[a]",
                        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-c:a", "pcm_s16le", str(cut)],
                       check=True)
        parts.append(str(cut))
    lst = out / "concat.txt"
    lst.write_text("".join(f"file '{p}'\n" for p in parts))
    joined = out / "joined.mkv"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy", str(joined)], check=True)

    # The episode's own voice and music stems (sketch-audio --stems on a copy of the episode); the model's sound
    # replaces the episode's sound effects, which were timed to KitCut's picture, at the loudness those had.
    vo, music, sfx = (STEMS / f"stem_{k}.wav" for k in ("vo", "music", "sfx"))
    gain_db = lufs(sfx, END) - lufs(joined, END)
    print(f"model sound gain {gain_db:+.1f} dB (to the episode's sound-effect level)")
    fc = (f"[0:a]volume={gain_db:.2f}dB[fx];[1:a]atrim=0:{END:.2f}[v];[2:a]atrim=0:{END:.2f}[m];"
          "[v][m][fx]amix=inputs=3:normalize=0,loudnorm=I=-14:TP=-1.5[mix]")
    dest = D / f"leo-ep12-h3-{outdir}.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(joined), "-i", str(vo), "-i", str(music), "-filter_complex", fc,
                    "-map", "0:v", "-map", "[mix]", "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
                    "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-t", f"{END:.2f}", "-movflags", "+faststart", str(dest)], check=True)
    print("wrote", dest)


def lufs(path, dur):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-t", f"{dur:.2f}", "-i", str(path), "-map", "0:a", "-af", "ebur128", "-f", "null", "-"],
                       capture_output=True, text=True)
    return float([ln for ln in r.stderr.splitlines() if ln.strip().startswith("I:")][-1].split()[1])


if __name__ == "__main__":
    cmd, *rest = sys.argv[1:]
    sys.exit({"plan": plan, "check": check, "assemble": assemble}[cmd](*rest) or 0)
