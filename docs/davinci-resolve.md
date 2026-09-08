# Working with DaVinci Resolve, researched 2026-09-08

Can this repo work with DaVinci Resolve, and can it modify Resolve's files?

**Findings and one recommendation**, in the shape `docs/market-shorts-2026.md`
uses: what is measured here is marked as measured, what comes off a vendor page
or a forum is marked with its source, and what could not be tested on this box
(no Resolve installed, Linux container) is marked **untested**.

---

## The short answer

| question | answer |
|---|---|
| Hand a kitcut edit to Resolve as an editable timeline? | **Yes**, through interchange files — OTIO, EDL, FCP7 XML — plus SRT for captions. Free edition included. Proven here on a real committed keep-list (§4). |
| Read an edit back out of Resolve and render it with our tooling? | **Yes**, same formats in reverse. Nothing new to learn; the parse is the write in reverse. |
| Write Resolve's own project files — `.drp`, `.drt`, the disk database? | **Edit yes, author no.** A `.drp` is a plain ZIP of UTF-8 XML: a rescue-class edit (delete a payload, retarget a path, rename) is mechanical and proven. Building a *new* timeline in it is not, because the parts that carry an edit are hex-encoded blobs with no published schema (§2). |
| Drive the running application (build timelines, apply blurs, render)? | **Studio only.** External scripting is a paid-edition feature, and 21.1 (released 2026-09-07) narrowed it further while adding a native MCP server — also Studio (§3.3). |

The load-bearing sentence: **we exchange decisions with Resolve, we do not edit
its project files.** Every capability worth having is reachable through the
documented import/export doors, and each of those doors is a plain text file we
can write in a few hundred lines.

---

## 1. What "Resolve's files" actually are

| file | what it is | can we write it? |
|---|---|---|
| `.drp` | DaVinci Resolve Project. A **plain ZIP** (`50 4b 03 04`) of UTF-8 XML: `project.xml`, `Gallery.xml`, `SeqContainer/<uuid>.xml` (one per timeline) and `MediaPool/**/MpFolder.xml`. Tags carry Resolve's `Ns::Tag` convention (`ListMgt::Sm2TiVideoClip`), clips are addressed by a `DbId` attribute, and the payloads — `EffectFiltersBA`, `CompositionBA`, `FieldsBlob` — are **hex text wrapping an undocumented structure** | **For surgical repair, yes** (§2) — that is what `koosoli/DaVinci-Resolve-DRP-Toolkit` and `hfiguiere/drp-extractor` do. **For authoring our edits, no** |
| `.drt` | one timeline out of a project; the same ZIP-of-XML minus `Gallery.xml` | Same answer, same reason. Resolve **imports** it, so it would be the authoring target if the blob schema were ever published — and OTIO makes that pointless |
| disk database | a folder (`Resolve Disk Database/Resolve Projects/Users/guest/Projects/...`) with a SQLite `project.db` per project | **No.** Blackmagic's own guidance is to back it up through the app's database utility, never by hand, and never to touch it while Resolve is running |
| `.drx`, `.drfx`, `.setting`, `.comp`, `.dctl` | grade, effect bundle, Fusion macro/composition, colour transform | Not researched in depth. `.dctl` is plain text and `.comp`/`.setting` are Lua-ish tables, so both are writable in principle — relevant only if we ever want to ship a *look* rather than an *edit* |
| `.otio` `.edl` `.xml` `.fcpxml` `.aaf` `.adl` | interchange, none of them Resolve-proprietary | **Yes — this is the door.** Resolve imports all of these (Media Pool → Timelines → Import, or File → Import) |

So "modify its files" splits cleanly in two: its *project* files are closed and
we should stay out; its *interchange* files are open, documented, and already
have a Python implementation we can lean on.

---

## 2. Inside a `.drp`: what is text, what is a blob, and what that permits

Read off the two open-source parsers' own code, not off a blog. `.drp` is opened
with `zipfile.ZipFile(path).extractall()` and written back with a plain
`ZIP_DEFLATED` re-zip of the edited tree — **no signature, no manifest, no
checksum anyone has hit**. Inside:

```
project.xml                     project-level settings
Gallery.xml                     stills (absent from a .drt)
SeqContainer/<uuid>.xml         one file per timeline: tracks, clips, effects
MediaPool/**/MpFolder.xml       bins; Sm2Timeline records name each sequence
```

The XML is UTF-8 text a text editor can open, with two quirks: tag names carry
Resolve's `Ns::Tag` convention (`<ListMgt::Sm2TiVideoClip DbId="...">`), which is
not legal XML namespacing and makes stock parsers choke until the `::` is
substituted out; and objects reference each other by `DbId`, so the file is a
graph, not a tree.

**Field by field, this is the answer to "binary or editable":**

| field | form | what you can do with it |
|---|---|---|
| `Name`, `MediaFilePath`, `DbId`, track/clip structure | **plain text in the XML** | read, edit, retarget, rename. A relink is a search-and-replace |
| `EffectFiltersBA` | **hex text**, an opaque serialised Edit/Color-page effect stack (size is `len(hex)//2`) | delete it (`<EffectFiltersBA/>`), copy it verbatim between clips, diff it by hash. Not compose it |
| `CompositionBA` | same, for the clip's Fusion composition | same |
| `FieldsBlob` | hex text again, but partly **UTF-16LE strings** — the timeline-UUID mapping is recovered by decoding it and regexing for a UUID | read strings out of it. Writing into it means honouring length prefixes in a format nobody has published |

So the honest phrasing is **not "binary, closed"**. It is: *the container and the
skeleton are open text; the parts that carry an edit's meaning are hex-wrapped
structures with no schema.* Everything the community actually does with a `.drp`
is therefore **subtractive or substitutive**:

- **Rescue** — a project that crashes Resolve on open usually has one oversized
  or corrupt effect payload. Find the clip by `DbId`, replace its
  `<EffectFiltersBA>…</EffectFiltersBA>` with `<EffectFiltersBA/>`, re-zip. The
  clip loses its effects; the project opens. This is a documented, working fix,
  and it is irreversible for that clip.
- **Downgrade** — strip Studio-only metadata (Dolby Vision, HDR10+) so the free
  edition will open a Studio project. Note the toolkit's own `downgrade.py`
  describes itself as "a working template" that strips `DolbyVision` tags —
  thinner than its README suggests. Third-party `.drp` tooling is early; measure
  it before trusting it.
- **Relink / rename / diff** — plain-text fields, plain-text edits.

**And what it does not permit, which is what we would want it for.** To put a
kitcut cut into a `.drp` we would have to *synthesise* clip records with valid
`DbId`s wired into the media-pool graph, and any effect we care about — the PiP
transform, a blur, a caption — exists only as a blob we cannot write. So the
verdict from §1 stands, now for a stated reason rather than as a slogan:

1. **The interesting half is a blob.** Deleting one is easy; authoring one is
   the whole problem.
2. **Nothing pins the format.** No public schema means Blackmagic may reshape it
   in 21.2, and a project file we generated is then a liability we own.
3. **There is nothing to gain.** Everything a `.drp` would carry that an OTIO
   carries too — clips, tracks, timings, markers, media references — is in the
   OTIO already, and Resolve imports that on the supported path, in the free
   edition.

If we ever *do* want `.drp` surgery — a client hands us a crashing project, or a
hundred projects need their media relinked — that is a small, honest job: unzip,
regex or ElementTree the text, re-zip, and never touch a blob's insides. It is a
different job from editing video, and it should stay a separate script if it is
ever written.

## 3. The three doors that are open

### 3.1 Interchange files (works in the free edition)

Resolve imports **AAF, EDL, XML (FCP7), FCPXML, DRT, ADL and OTIO**, from the
Edit page (right-click the Media Pool → Timelines → Import) or File → Import.
OTIO import has been in Resolve since **v17, free and Studio alike**, and OTIO
is the format that loses the least: clips, tracks, timing, markers, metadata.

This is the door to design for. It needs no licence, no scripting permission, no
version-specific plumbing, and it survives whatever Blackmagic does to its API.

### 3.2 Subtitles (works in the free edition)

Resolve imports **SRT, VTT, TTML and XML** subtitle files (File → Import →
Subtitle). It does **not** import **ASS** — which is precisely the format
`build-captions-ass.py` produces, and the one that carries our per-word
highlight, the card, the radius, the outline.

Consequence, and it is a real one: **the caption look does not travel.** We can
hand Resolve the words and their timings (SRT), and Resolve will draw its own
subtitle in its own style. Our karaoke captions remain something only our burn-in
pass produces. That is not a defect to fix; it is the boundary to state when
somebody asks for "the same captions, but in Resolve".

### 3.3 The scripting API and the new MCP server (Studio only)

- The bundled scripting documentation is explicit: **the scripting API requires
  DaVinci Resolve Studio; the free version does not expose it** for external use.
  Setup is three environment variables (`RESOLVE_SCRIPT_API`,
  `RESOLVE_SCRIPT_LIB`, `PYTHONPATH`) and `import DaVinciResolveScript`.
- What the free edition retains is scripting **from inside the app** — the
  Fusion page Console and the Workspace → Scripts menu. What it does not have is
  invocation from an external interpreter or command line, which is exactly how
  every script in this repo runs.
- **19.1 (Nov 2024)** removed `UIManager` from the free edition without a
  changelog entry, breaking third-party scripts that draw their own UI.
  Blackmagic's stated reason was that the Python API had been used to unlock
  Studio features from the free build.
- **21.1 (released 2026-09-07)** goes further: its release notes carry
  *"Advanced scripting now requires DaVinci Resolve Studio"*, ~20 new scripting
  APIs, Python 2 dropped — and a **native MCP server for interacting with AI
  assistants**, reported as Studio-only. That is a first-class agent door into
  the editor: an agent can drive multicam, markers, audio, transcripts and
  renders through the app's own scripting API with no third-party plugin.

The MCP server is the most interesting development for a repo whose only caller
is an agent — and it is behind the **$295 one-off Studio licence**. Nothing else
in this document needs money.

**Confidence.** The 21.1 facts come from two independent trade outlets
(Newsshooter, RedShark) summarising the release notes; the Blackmagic forum's own
release thread returns 403 to our fetcher, so the notes were not read first-hand.
Treat "MCP server, Studio-only" as high-confidence-but-secondhand, and confirm on
a machine that has 21.1 before spending anything on it.

---

## 4. Measured: a real keep-list, exported and read back

Not reasoning — a run, on 2026-09-08, in a throwaway venv (nothing was added to
`requirements.txt`). Input was `projects/claude-demo/claude-demo.cuts.json`, the
committed screencast-cut keep-list: 41 keeps in camera time, `fps 30`, sync
`offset 19.165`, each keep tagged `full` (camera alone) or `pip` (screen up).

Built two video tracks — V2 the camera at its keep times, V1 the screen at
`keep − offset`, with a Gap where the camera is full-frame — and wrote three
formats:

```
keeps: 41   predicted runtime 427.867s (cuts.json says 450.367)
otio      claude-demo.otio    tracks=2 clips=71 duration=427.867s
fcp_xml   claude-demo.xml     tracks=2 clips=71 duration=427.867s
cmx_3600  claude-demo.edl     tracks=1 clips=41 duration=427.867s
```

Every file read back at the arithmetic it was written with. The EDL:

```
001  IMG2695  V     C        00:00:15:06 00:00:17:01 00:00:00:00 00:00:01:25
* FROM CLIP NAME:  cam-000
* FROM CLIP: file://sources/IMG_2695.MOV
* OTIO TRUNCATED REEL NAME FROM: IMG_2695.MOV
```

**Five things that run cost us, all of which a future exporter must handle:**

1. **The keep-list is not the film.** 427.867 s against the 450.367 s the same
   file states as `runtime`. The 22.5 s difference is the opening bookend and its
   b-roll, which live in `screencast.json`, not in the keep-list. An exporter
   that reads only `.cuts.json` ships a timeline 22 seconds short of the render
   the project file claims — the same class of bug as measuring silence on the
   rendered file. Export from the *plan the renderer builds*, not from a sidecar.
2. **FCP7 XML refuses a media reference with no `available_range`** — it dies in
   `_build_file` with `'NoneType' object has no attribute 'start_time'`. So the
   exporter must `ffprobe` every source for its duration before it can write. OTIO
   and EDL do not care.
3. **EDL is frame-rate-blind on read.** Reading the 30 fps EDL back at the
   adapter's default 24 fps fails with `Frame rate mismatch. Timecode
   '00:00:01:25' has frames beyond 23`. The rate travels out of band, which is
   the classic EDL conform trap: 29.97 drop-frame versus non-drop is not in the
   file either.
4. **EDL truncates reel names** (`IMG_2695.MOV` → `IMG2695`), so conforming an
   EDL relies on Resolve matching by timecode and reel. OTIO and FCP7 XML carry
   the file path, which is why they are the formats to lead with.
5. **A speed ramp only half-travels.** `LinearTimeWarp(time_scalar=6.0)` — the
   shape `screen-cut.py` produces for its 6× "AI is thinking" stretches —
   round-trips through `.otio` intact, but the FCP7 XML adapter writes **no**
   `timemap`/`speed` element at all: it is dropped silently. OTIO also does not
   divide the clip's timeline duration by the scalar, so the runtime arithmetic
   stays ours either way.

**Dependency cost.** `pip install opentimelineio` → 0.18.1, and it ships only
`otio_json`, `otiod`, `otioz`. **EDL and FCP7 XML are separate packages**
(`otio-cmx3600-adapter`, `otio-fcp-adapter`); FCPXML and AAF are two more. The
`.otio` file itself is plain JSON against a stable published schema, and an EDL
is ten lines of string formatting — so a first exporter can write both by hand
with **no new runtime dependency**, and use the library only inside a
`check-resolve.py` that validates what we wrote. That keeps the venv small and
keeps `requirements.txt` honest.

---

## 5. What survives the trip, pipeline by pipeline

| what we make | travels as | what is lost |
|---|---|---|
| **tighten-cut** keep-list | one video + one audio track, N clips | nothing material. This is the natural fit |
| **screencast-cut** keep-list | two tracks, camera and screen, from the measured sync offset | the **PiP composite** — size, corner, radius, the mask. A transform is Inspector/Fusion data, not interchange |
| **angle-cut** shot list | one track switching between N tapes | nothing, *if* the tapes are conformed first (`conform-tapes.py`) — Resolve conforms by timecode and path, and a mixed-rate set is as wrong there as it is here |
| **screen-cut** segments | cuts yes; **speed ramps only via `.otio`**, and untested in Resolve | the 6× ramps if the route is EDL or FCP7 XML; the speed badge always |
| **cut-clips** shorts | in/out points | the crop/reframe window, the caption burn, the handle badge — all pixels we draw |
| **captions** (`.ass`) | **SRT** (words and timings) | the entire look: per-word highlight, card, outline, grouping. Resolve draws its own |
| **dub** (`.en.wav` + words) | an audio clip on a second track, plus SRT | the mix (`loudnorm`, ducking) unless we hand over the finished stem |
| **name labels / end cards** | a PNG with alpha on an upper track, plus a marker | placement, the wipe animation, the background treatment |
| **film-redact / track-blur** | **nothing** | every blur. Resolve FX and Fusion nodes are only reachable through the scripting API, i.e. Studio |
| **project journal / decisions** | timeline **markers** (name, colour, note) | nothing — markers are the natural carrier for `_why` notes, removals and hook timings |

Read the table as a boundary, not a shortfall: **cut decisions travel, pixels do
not.** Everything this repo is unusually good at — the caption look, the redaction,
the composite — is a render, and a render is what Resolve would import as a flat
clip anyway.

---

## 6. If we build it: the shape

Two scripts, both free-edition-first, neither needing Resolve installed to run
or to test:

**`resolve-export.py`** — a kitcut manifest → an editable timeline.

```powershell
python scripts/resolve-export.py --manifest projects/<id>/tighten.json --list
python scripts/resolve-export.py --manifest projects/<id>/tighten.json --format otio --srt
```

- Reads the *plan the renderer builds* (§4.1), not a sidecar.
- Writes `.otio` (lead), `.edl` (universal), FCP7 `.xml` (path-carrying), plus
  `.srt` from the same `words.json` the caption builder uses.
- Puts every editorial decision we already record — named removals with their
  `why`, hook timings, label and overlay windows — on the timeline as **markers**,
  so the reasoning arrives with the cut.
- `--list` prices it with no file written: tracks, clips, duration, and what each
  format would drop. That is the repo's free-mode rule, and here it also doubles
  as the honesty report from the §5 table.

**`resolve-import.py`** — a Resolve export → a kitcut keep-list.

The valuable direction, and the cheaper one: a human does the fine trim in
Resolve (free), exports `.otio`/EDL/XML, and we render it with NVENC, the
captions, the labels, the redaction and the project record. That makes Resolve a
*front end* for the parts a person is better at, and keeps the finishing in the
pipeline that already gates and records it.

**`check-resolve.py`** — the round trip with no Resolve and no encode: keep-list
→ timeline → keep-list, asserting frame counts, durations and marker survival per
format, in the shape of `check-multicam.py`.

The Studio/MCP route (§3.3) is a later, paid, optional layer on top — worth
re-costing once somebody here actually has 21.1 Studio, and worth nothing before.

---

## 7. Open questions that need a box with Resolve on it

1. Does Resolve's OTIO import honour `LinearTimeWarp`, or drop it like the FCP7
   XML adapter does? Decides whether `screen-cut`'s ramps can travel at all.
2. Do our markers survive import, with notes and colours intact?
3. Does Resolve conform our media references by path, or does it ask to relink
   every clip? (Decides whether `.otio` or FCP7 XML leads.)
4. Is the 21.1 MCP server really Studio-only, and what does it expose — enough to
   apply a blur or build a multicam clip, or only what the scripting API already had?
5. Which interchange **exports** the free edition allows. Secondary sources say
   EDL/XML/AAF/OTIO are all there; none of them is authoritative.

---

## Sources

- [DaVinci Resolve scripting API reference (bundled README, v20.3 copy)](https://gist.github.com/mhadifilms/2b84d469135315793220dbf2226cbe63) — Studio requirement, env vars, `ImportTimelineFromFile` formats
- [DaVinci Resolve scripting API doc v21.0.4 (copy)](https://gist.github.com/X-Raym/2f2bf453fc481b9cca624d7ca0e19de8) and [dvresolve wiki](https://wiki.dvresolve.com/developer-docs/scripting-api) — console vs external invocation, the Console/Local/Network permission
- [Blackmagic forum: UIManager disabled in Resolve Free in v19.1](https://forum.blackmagicdesign.com/viewtopic.php?f=12&t=213158)
- [Newsshooter: DaVinci Resolve 21.1](https://www.newsshooter.com/2026/09/07/blackmagic-design-davinci-resolve-21-1/) and [RedShark: 21.1 new features](https://www.redsharknews.com/davinci-resolve-21.1-new-features-release) — native MCP server, "advanced scripting now requires Studio"
- [Blackmagic Design: DaVinci Resolve 21 announcement](https://www.blackmagicdesign.com/media/release/20260414-01)
- [Resolve 18.6 manual: Import AAF, EDL, XML](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part1399.htm), [Exporting to OTIO](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part4004.htm), [Exporting an EDL](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part4007.htm), [Importing Subtitles and Captions](https://www.steakunderwater.com/VFXPedia/__man/Resolve18-6/DaVinciResolve18_Manual_files/part1280.htm)
- The `.drp` internals in §2 were read off source, not off a blog: [`core/engine.py`](https://github.com/koosoli/DaVinci-Resolve-DRP-Toolkit/blob/main/drp_toolkit/core/engine.py) (zip extract/re-zip, `SeqContainer`/`MediaPool` layout, `FieldsBlob` hex → UTF-16LE), [`core/parser.py`](https://github.com/koosoli/DaVinci-Resolve-DRP-Toolkit/blob/main/drp_toolkit/core/parser.py) (the `::` substitution, `strip_clip_effects_text`), [`core/models.py`](https://github.com/koosoli/DaVinci-Resolve-DRP-Toolkit/blob/main/drp_toolkit/core/models.py) (`DRPEffect.from_hex`, `size = len(hex)//2`) and [`plugins/downgrade.py`](https://github.com/koosoli/DaVinci-Resolve-DRP-Toolkit/blob/main/drp_toolkit/plugins/downgrade.py) ("a working template"), read 2026-09-08; plus [drp-extractor](https://github.com/hfiguiere/drp-extractor) and [fileformat.com on .drp](https://docs.fileformat.com/video/drp/)
- [The Post Flow: where Resolve saves projects (disk database, `project.db`)](https://thepostflow.com/post-production/post-production-workflows/resolve-project-file-locations/)
- [OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) — 0.18.1, adapters split into `otio-cmx3600-adapter` / `otio-fcp-adapter`
