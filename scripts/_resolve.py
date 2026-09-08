"""Talk to DaVinci Resolve, or hand it a timeline it can open. One module.

Resolve is scriptable, but only if a preference says so, so any tool that drives
it has to survive the case where it cannot. This module therefore has two
halves and every caller gets both:

  LIVE      connect() returns the running application. The edit is built and
            rendered with nobody clicking anything.
  HANDOFF   fcpxml() writes the same edit as a file Resolve imports. Nothing
            is required of the machine -- Resolve does not even have to be
            installed on it.

Three things about the live half cost real time to learn:

  Do NOT set PYTHONPATH to reach the API. Blackmagic's own README tells you to,
  and on this machine that variable is the single worst thing you can export:
  a user-level PYTHONPATH pointing 3.13 at 3.11's site-packages is what
  `_env.py` exists to undo, and pip reads it too. The Modules/ shim it wants on
  the path does nothing but load `fusionscript` from a known file, so this
  module loads that extension directly by path and leaves the environment
  alone.

  `scriptapp("Resolve")` returning None is not an error message. It is the same
  None whether Resolve is not running, is still starting up, or is running with
  external scripting switched off -- which is the DEFAULT. why_not_connected()
  tells those three apart by looking for the process, so the operator is told
  which one it is instead of guessing.

  The bundled interpreter is not required. Resolve 21.1 ships ResolvePython
  3.14 where `import DaVinciResolveScript` works out of the box, but it has no
  pip, so a script that needs this repo's dependencies cannot run in it. The
  .dll loads happily into our own venv, so everything here runs under the
  project interpreter like every other script in the repo.

Frames, not seconds, are the unit. Resolve addresses source media by frame and
so does every cut this repo makes, so a plan crosses the boundary as integer
frames and the conversion happens once, in secs_to_frames().
"""

import os
import sys
import subprocess
import xml.sax.saxutils as _sx

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _env  # noqa: E402,F401 -- re-execs into .venv; before any 3rd-party import

# Where Blackmagic puts the scripting extension, per platform. $RESOLVE_SCRIPT_LIB
# wins when the operator has set it (a non-default install location).
_LIB_CANDIDATES = {
    "win32": [r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"],
    "darwin": [
        "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/"
        "Libraries/Fusion/fusionscript.so"
    ],
    "linux": [
        "/opt/resolve/libs/Fusion/fusionscript.so",
        "/home/resolve/libs/Fusion/fusionscript.so",
    ],
}

_app = None


def lib_path():
    """The fusionscript extension for this machine, or None."""
    env = os.environ.get("RESOLVE_SCRIPT_LIB")
    if env and os.path.exists(env):
        return env
    key = "linux" if sys.platform.startswith("linux") else sys.platform
    for p in _LIB_CANDIDATES.get(key, []):
        if os.path.exists(p):
            return p
    return None


def is_running():
    """Is the Resolve application up? Used only to explain a failed connect."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["tasklist", "/FI", "IMAGENAME eq Resolve.exe"],
                capture_output=True,
                text=True,
                env=_env.ENV,
            ).stdout
            return "Resolve.exe" in out
        out = subprocess.run(
            ["pgrep", "-fl", "Resolve"], capture_output=True, text=True, env=_env.ENV
        ).stdout
        return bool(out.strip())
    except (OSError, subprocess.SubprocessError):
        return False


def connect():
    """The running Resolve application, or None. Never raises, never mutates env."""
    global _app
    if _app is not None:
        return _app
    lib = lib_path()
    if not lib:
        return None
    try:
        import importlib.machinery
        import importlib.util

        loader = importlib.machinery.ExtensionFileLoader("fusionscript", lib)
        spec = importlib.util.spec_from_loader("fusionscript", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        _app = mod.scriptapp("Resolve")
    except Exception:  # noqa: BLE001 -- diagnosis is the caller's
        _app = None
    return _app


def why_not_connected():
    """Which of the failures it is, in words the operator can act on.

    The last branch is the one that matters, and it is bad news: external
    scripting is a STUDIO feature. Resolve 21.1's release notes say "Advanced
    scripting now requires DaVinci Resolve Studio", and measured on the free
    21.1, scriptapp("Resolve") returns None from both this venv and the
    bundled ResolvePython. So do NOT send a free-edition operator hunting for
    a Preferences toggle: their edition does not have one, and saying otherwise
    costs them the search and then costs you their trust in the next sentence.
    """
    if not lib_path():
        return (
            "DaVinci Resolve is not installed here (no fusionscript library "
            "at any known path; set $RESOLVE_SCRIPT_LIB if it is somewhere "
            "unusual)."
        )
    if not is_running():
        return "DaVinci Resolve is not running. Start it and try again."
    return (
        "Resolve is running but will not accept a script connection. On DaVinci "
        "Resolve STUDIO, turn it on once: Preferences > System > General > "
        "'External scripting using' -> Local. On the FREE edition there is "
        "nothing to turn on -- 21.1's notes state that advanced scripting "
        "requires Studio -- so use the FCPXML/SRT handoff instead."
    )


def require():
    """Connect or exit with the reason. For scripts whose whole job is Resolve."""
    r = connect()
    if r is None:
        print("!! " + why_not_connected())
        sys.exit(3)
    return r


# ---------------------------------------------------------------------------
# Live half: project, media, timeline, render.
# ---------------------------------------------------------------------------


def open_project(resolve, name, create=True, media_dir=None):
    """Load `name`, or create it. Returns the Project.

    Resolve has no "get or create", and CreateProject on an existing name fails
    rather than returning the existing one, so the order matters: load first.
    """
    pm = resolve.GetProjectManager()
    p = pm.LoadProject(name)
    if p is None and create:
        p = pm.CreateProject(name) if media_dir is None else pm.CreateProject(name, media_dir)
    return p


def import_media(project, paths):
    """Import files into the media pool; returns {abs path: MediaPoolItem}.

    Re-importing a file already in the pool creates a DUPLICATE pool entry, so
    the pool is read first and existing entries are reused.
    """
    mp = project.GetMediaPool()
    root = mp.GetRootFolder()
    have = {}
    for it in root.GetClipList() or []:
        fp = it.GetClipProperty("File Path")
        if fp:
            have[os.path.normcase(os.path.abspath(fp))] = it
    want = [os.path.abspath(p) for p in paths]
    missing = [p for p in want if os.path.normcase(p) not in have]
    if missing:
        mp.SetCurrentFolder(root)
        for it in mp.ImportMedia(missing) or []:
            fp = it.GetClipProperty("File Path")
            if fp:
                have[os.path.normcase(os.path.abspath(fp))] = it
    return {p: have.get(os.path.normcase(p)) for p in want}


def secs_to_frames(t, fps):
    """One place, so a plan and a render cannot round differently."""
    return int(round(float(t) * float(fps)))


def build_timeline(project, name, segments, fps, replace=True):
    """A timeline whose clips are `segments`, in order, cut to frame.

    Each segment is {"item": MediaPoolItem, "start": sec, "end": sec}. Resolve's
    endFrame is INCLUSIVE, so a half-open [start, end) range in seconds becomes
    endFrame = last frame, not one past it -- getting that wrong lengthens every
    single clip by a frame and the drift is invisible until the audio is late.
    """
    mp = project.GetMediaPool()
    if replace:
        for i in range(1, (project.GetTimelineCount() or 0) + 1):
            tl = project.GetTimelineByIndex(i)
            if tl and tl.GetName() == name:
                mp.DeleteTimelines([tl])
                break
    infos = []
    for s in segments:
        a = secs_to_frames(s["start"], fps)
        b = secs_to_frames(s["end"], fps) - 1
        if b < a:
            continue
        infos.append({"mediaPoolItem": s["item"], "startFrame": a, "endFrame": b})
    if not infos:
        return None
    tl = mp.CreateTimelineFromClips(name, infos)
    if tl:
        project.SetCurrentTimeline(tl)
    return tl


def import_subtitles(timeline, srt_path):
    """Put an .srt onto the timeline as a subtitle track. True if it landed.

    Counted before and after rather than trusting the return value: the call
    reports success on a file Resolve then silently declines to place.
    """
    before = timeline.GetTrackCount("subtitle") or 0
    timeline.ImportIntoTimeline(os.path.abspath(srt_path))
    return (timeline.GetTrackCount("subtitle") or 0) > before


def render(
    project, out_dir, out_name, preset=None, settings=None, wait=True, poll=5.0, on_progress=None
):
    """Queue one render of the current timeline and (by default) run it.

    Returns the job status dict. A Resolve render reports progress as a
    percentage, which is what makes it worth waiting on rather than blocking
    blind.
    """
    import time

    project.DeleteAllRenderJobs()
    if preset:
        project.LoadRenderPreset(preset)
    cfg = {"TargetDir": os.path.abspath(out_dir), "CustomName": out_name}
    cfg.update(settings or {})
    if not project.SetRenderSettings(cfg):
        raise RuntimeError("Resolve rejected the render settings: %r" % cfg)
    job = project.AddRenderJob()
    if not job:
        raise RuntimeError("Resolve would not queue a render job")
    project.StartRendering([job], isInteractiveMode=False)
    if not wait:
        return {"JobId": job, "JobStatus": "Rendering"}
    while project.IsRenderingInProgress():
        st = project.GetRenderJobStatus(job) or {}
        if on_progress:
            on_progress(st)
        time.sleep(poll)
    return project.GetRenderJobStatus(job) or {}


# ---------------------------------------------------------------------------
# Handoff half: the same edit as a file, for when scripting is switched off.
# ---------------------------------------------------------------------------


def _rat(frames, fps):
    """FCPXML time: a rational in seconds. Resolve rejects a bare decimal."""
    return "%d/%ds" % (int(frames), int(round(fps)))


def _file_url(path):
    """file:// URL for a media path. Windows drive letters get the extra slash.

    Only space and # are escaped: Resolve resolves a percent-encoded path, but
    over-encoding a Windows path (the colon especially) makes it fail to relink.
    """
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p  # C:/x -> /C:/x
    return "file://" + p.replace("%", "%25").replace(" ", "%20").replace("#", "%23")


def fcpxml(path, name, sources, segments, fps, width, height):
    """Write the cut as FCPXML that Resolve imports as a timeline.

    `sources` is [{"path", "duration"}]; `segments` is [{"src", "start", "end"}]
    where src indexes sources. Chosen over EDL because an EDL carries no file
    paths and has to be relinked by hand, and over OTIO because Resolve's
    FCPXML import is the one with a decade of mileage on it.
    """
    fpsi = int(round(fps))
    fmt = "FFVideoFormat%dx%dp%d" % (width, height, fpsi)
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        "<!DOCTYPE fcpxml>",
        '<fcpxml version="1.9">',
        "  <resources>",
        '    <format id="r0" name="%s" frameDuration="1/%ds" width="%d" '
        'height="%d" colorSpace="1-1-1 (Rec. 709)"/>' % (fmt, fpsi, width, height),
    ]
    for i, s in enumerate(sources):
        dur = secs_to_frames(s["duration"], fps)
        out.append(
            '    <asset id="a%d" name="%s" start="0s" duration="%s" hasVideo="1" '
            'hasAudio="1" format="r0" audioSources="1" audioChannels="2" '
            'audioRate="48000">' % (i, _sx.escape(os.path.basename(s["path"])), _rat(dur, fps))
        )
        out.append(
            '      <media-rep kind="original-media" src="%s"/>' % _sx.escape(_file_url(s["path"]))
        )
        out.append("    </asset>")
    out.append("  </resources>")

    total = sum(secs_to_frames(g["end"], fps) - secs_to_frames(g["start"], fps) for g in segments)
    out += [
        "  <library>",
        '    <event name="%s">' % _sx.escape(name),
        '      <project name="%s">' % _sx.escape(name),
        '        <sequence format="r0" duration="%s" tcStart="0s" '
        'tcFormat="NDF" audioLayout="stereo" audioRate="48kHz">' % _rat(total, fps),
        "          <spine>",
    ]
    at = 0
    for g in segments:
        a = secs_to_frames(g["start"], fps)
        b = secs_to_frames(g["end"], fps)
        n = b - a
        if n <= 0:
            continue
        out.append(
            '            <asset-clip ref="a%d" offset="%s" name="%s" '
            'start="%s" duration="%s" format="r0" tcFormat="NDF"/>'
            % (
                g["src"],
                _rat(at, fps),
                _sx.escape(g.get("name") or "clip"),
                _rat(a, fps),
                _rat(n, fps),
            )
        )
        at += n
    out += [
        "          </spine>",
        "        </sequence>",
        "      </project>",
        "    </event>",
        "  </library>",
        "</fcpxml>",
        "",
    ]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    return path
