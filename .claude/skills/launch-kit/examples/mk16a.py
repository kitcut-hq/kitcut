# Reference copy from projects/instafill-ph-launch/ (2026-11-24), as it shipped.
# Paths are relative to that project folder; copy into projects/<id>/ and adapt.
# Writes the 16:9 "variant A" manifests (2026-11-24): captions16a/16c/16d,
# tour16a.json + its blank chrome, phone16a.json, compose16a.json, desk16a.json.
# Variant A: no magnifier card. The process is the phone on the left with big
# captions on the right; when the PDF opens, the page flies out of the phone
# into a large sheet on the right, toured with highlights, captions under it.
import copy
import json
import os

from PIL import Image

D = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def load(n):
    return json.load(open(os.path.join(D, n), encoding="utf-8"))


def dump(o, n):
    json.dump(o, open(os.path.join(D, n), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


def K(s):
    return "   ".join(" ".join(w) for w in s.split())


CARD = [700, 40, 1160, 850]  # x, y, w, h of the sheet
BG = "#EDEFF2"

# captions -------------------------------------------------------------------
base = load("captions16b.json")
base.pop("badges", None)
cam = copy.deepcopy(base)
cam["_comment"] = "16:9 variant A, camera parts: bottom-centre, the reel's draft-6 words."
cam["outdir"] = "temp/caps16d"
cam["style"].update({"balance": False})
cam["captions"] = [
    {"id": "k0", "kicker": K("THE PROBLEM"), "text": "A letter full of *details?*"},
    {"id": "k0b", "kicker": K("THE PROBLEM"), "text": "And a form *to fill?*"},
    {"id": "k1", "kicker": K("STEP 1"), "text": "Just snap the *request.*"},
    {"id": "k8", "kicker": K("THE RESULT"), "text": "One photo in. *A filled ACORD 25* out."},
]
dump(cam, "captions16d.json")

right = copy.deepcopy(base)
right["_comment"] = "16:9 variant A, process: big two-line captions in the empty right half, beside the phone."
right["outdir"] = "temp/caps16a"
right["style"].update({"size": 68, "line_h": 84, "cx": 1280, "bottom": 430, "balance": True,
                       "one_line_max": 560, "kicker_size": 28, "pad_x": 46, "pad_y": 26})
right["captions"] = [
    {"id": "k2", "kicker": K("STEP 2"), "text": "Open the *Instafill Agent.*"},
    {"id": "k3", "kicker": K("STEP 2"), "text": "Add the photo and the *policies.*"},
    {"id": "k4", "kicker": K("STEP 3"), "text": "Ask for the *ACORD 25.*"},
    {"id": "k5a", "kicker": K("STEP 4"), "text": "It finds the *blank form.*"},
    {"id": "k5b", "kicker": K("STEP 4"), "text": "Flat PDF?|It makes it *fillable.*"},
    {"id": "k5c", "kicker": K("STEP 4"), "text": "Then fills it|from *your files.*"},
    {"id": "k6", "kicker": K("STEP 5"), "text": "Done.|*Open the PDF.*"},
]
right["badges"] = [{"id": "speed", "text": "8×  ·  REAL WAIT 50 SEC", "fast_forward": True,
                    "top": 40, "right": 40, "size": 26}]
dump(right, "captions16a.json")

under = copy.deepcopy(base)
under["_comment"] = "16:9 variant A, the sheet: one-line captions under the toured page."
under["outdir"] = "temp/caps16c"
under["style"].update({"size": 50, "line_h": 62, "cx": CARD[0] + CARD[2] / 2, "bottom": 34,
                       "balance": False, "max_w": 1150})
under["captions"] = [
    {"id": "k7a", "kicker": K("CHECK IT"), "text": "Client and insurers: *from the policies.*"},
    {"id": "k7b", "kicker": K("CHECK IT"), "text": "Every policy and *limit.*"},
    {"id": "k7c", "kicker": K("CHECK IT"), "text": "Extra insureds: *from the letter.*"},
]
dump(under, "captions16c.json")

# the sheet's tour -------------------------------------------------------------
os.makedirs(os.path.join(D, "temp/review"), exist_ok=True)
Image.new("RGB", (CARD[2], CARD[3]), BG).save(os.path.join(D, "temp/review/blank1160x850.png"))
t = load("tour16.json")
t["_comment"] = ("16:9 variant A: the same stops and times as tour.json (the phone's own tour), "
                 "on a large sheet beside the phone; opens on the whole page.")
t["chrome"] = "projects/instafill-ph-launch/temp/review/blank1160x850.png"
t["viewport"] = [0, 0, CARD[2], CARD[3]]
t["bg"] = BG
s = (CARD[3] - 40) / 4400
t["start"] = {"s": round(s, 4), "x": round((CARD[2] - 3400 * s) / 2), "y": 20}
labels = [["Agency", "Client"], ["Agency contact", "Insurers"], ["Policy numbers and dates", "Extra insureds"],
          ["Every limit"], ["From the letter"], [""], ["Certificate holder"]]
for st, ls in zip(t["stops"], labels):
    for m, lab in zip(st["marks"], ls):
        m["label"] = lab
    if "rect" in st:  # ~0.55x: readable type (20-24 px) with the block around it in view
        st["width"] = max(2000, round((st["rect"][2] - st["rect"][0]) * 1.15))
t["style"]["label_size"] = 30
t["out"] = "projects/instafill-ph-launch/temp/c16a/sheet.mp4"
dump(t, "tour16a.json")

# the phone track ----------------------------------------------------------------
p = load("phone16.json")
p["_comment"] = "16:9 variant A phone track: as phone16.json, no Chrome (starts on instafill.ai loaded), picker from its first drawn frame."
p["output"] = "projects/instafill-ph-launch/temp/c16a/phone.mp4"
p["edl"][0]["from"] = 18.25
p["edl"][3]["from"] = 31.85
dump(p, "phone16a.json")
dur = sum((e["to"] - e["from"]) / e.get("speed", 1) for e in p["edl"])
import subprocess  # noqa: E402
_pf = os.path.join(D, "temp/c16a/phone.mp4")
if os.path.exists(_pf):  # the rendered track is frame-rounded per segment: trust it
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", _pf], capture_output=True, text=True).stdout)
t_tour = dur - 16.4

dump({"_comment": "16:9 variant A middle section (compose16a.py). card: x, y, w, h of the toured sheet; "
      "sheet_from: section second the PDF tour starts (the sheet flies out of the phone then).",
      "bg": "temp/review/desk_bg.png", "phone_box": [210, 66, 948], "card": CARD,
      "sheet_from": round(t_tour, 3), "fly": 0.7, "dur": round(dur, 3),
      "phone": "temp/c16a/phone.mp4", "sheet": "temp/c16a/sheet.mp4", "out": "temp/c16a/middle.mp4"},
     "compose16a.json")

# the film -------------------------------------------------------------------------
m = load("desk16.json")
m["_comment"] = ("16:9 Desk Demo variant A (2026-11-24): no magnifier card -- phone left + big captions right "
                 "for the process, then the page flies out of the phone into a large toured sheet (compose16a.py). "
                 "Draft-6 words; the phone walks in to the letter in one shot; end card without a white panel.")
m["output"] = "projects/instafill-ph-launch/outputs/desk-draft4.mp4"
m["sources"]["mid"]["path"] = "projects/instafill-ph-launch/temp/c16a/middle.mp4"
snap = {"src": "snap", "from": 0.4, "to": 8.4, "speed": 0.85,
        "_why": "one shot: the letter, the phone comes in and frames it (the old cut 2.2-3.8 made it pop in)"}
mid = {"src": "mid", "from": 0.15, "to": round(dur - 0.04, 3), "_why": "compose16a.py middle (first 4 frames decode blank)"}
top = {"src": "top", "from": 8.8, "to": 13.35, "speed": 0.85, "_why": "letter + phone with the filled form, top-down; end card"}
m["edl"] = [snap, mid, top]
off = (8.4 - 0.4) / 0.85 - 0.15  # film = section + off
film = off + 0.15 + (mid["to"] - 0.15) + (13.35 - 8.8) / 0.85
sheet = t_tour + off

tmpl = m["image_overlays"][0]


def ov(img, at, dur_):
    o = copy.deepcopy(tmpl)
    o["image"] = "projects/instafill-ph-launch/temp/" + img + ".png"
    o["at"], o["dur"] = round(at, 2), round(dur_, 2)
    return o


sec = lambda x: x + off  # noqa: E731
bounds = [0]
for e in p["edl"]:
    bounds.append(bounds[-1] + (e["to"] - e["from"]) / e.get("speed", 1))
# bounds: 0 home, 1 agent, 2 sheet-menu, 3 picker, 4 typing, 5 agent, 6 finished, 7 viewer, 8 tour, 9 end
o = [ov("caps16d/k0", 0.1, 2.9), ov("caps16d/k0b", 3.1, 2.9), ov("caps16d/k1", 6.1, sec(0.15) - 6.3),
     ov("caps16a/k2", sec(0.15), bounds[2] - 0.25),
     ov("caps16a/k3", sec(bounds[2]) + 0.1, bounds[4] - bounds[2] - 0.3),
     ov("caps16a/k4", sec(bounds[4]) + 0.1, bounds[5] - bounds[4] - 0.3)]
a = sec(bounds[5]) + 0.1
o += [ov("caps16a/k5a", a, 2.0), ov("caps16a/k5b", a + 2.1, 1.9), ov("caps16a/k5c", a + 4.1, 2.0),
      ov("caps16a/speed", a, 6.1), ov("caps16a/k6", sec(bounds[6]) + 0.1, bounds[8] - bounds[6] - 0.3)]
o += [ov("caps16c/k7a", sheet + 0.8, 3.7), ov("caps16c/k7b", sheet + 4.65, 4.15), ov("caps16c/k7c", sheet + 9.0, 5.6)]
cam_at = off + mid["to"]
o += [ov("caps16d/k8", cam_at + 0.1, 2.6)]
end = copy.deepcopy(m["image_overlays"][-1])
end["image"] = "projects/instafill-ph-launch/temp/caps6/end16.png"
end["at"] = round(film - 2.55, 2)
end["in"] = {"type": "fade", "dur": 0.6}
end.pop("background", None)
o.append(end)
m["image_overlays"] = o
dump(m, "desk16a.json")
print("section", round(dur, 2), "tour at", round(t_tour, 2), "film", round(film, 2), "sheet at film", round(sheet, 2))
