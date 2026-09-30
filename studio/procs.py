"""The processes a film runs: what each one may see, and that none outlives its film.

Secrets. The studio's keys (Claude, MongoDB, Google, OpenRouter...) are read from its .env file
(STUDIO_ENV_FILE, else the code's own .env) into SECRETS and taken out of os.environ, so nothing
started from here inherits them by accident: not Claude Code, not a browser, not ffmpeg. A step
is handed only what it needs (step_env): the voice gets the Google keys, the painter OpenRouter's,
the render and the mix none at all. KITCUT_DOTENV=0 stops the scripts reading a .env of their own.
Settings that are not secrets (STUDIO_* but the token and the media SAS) stay ordinary
environment variables.

Lifetime. On Windows every step runs in a Job Object of its own: killing it (a timeout, a
cancelled film) takes down the step and everything it started -- browsers, ffmpeg -- in one call,
and since the job is set to die with its last handle, a server that is killed outright takes all
of them with it. A step may use at most STUDIO_FILM_MEM_GB (12) of memory. On Linux under
systemd (the Azure VM: studio/deploy/kitcut-studio@.service, Delegate=yes) the same is a cgroup v2
per step: memory.max is the cap, cgroup.kill the one call, and stopping the service takes every
step's cgroup with it. Anywhere else the step leads a process group of its own and the group is
killed, with no memory cap.
"""

import os
import sys
import time
import signal
import itertools
import asyncio
import subprocess

SECRETS = {}
# settings from the .env that are not secret, and stay in the environment
CONFIG = ("STUDIO_", "HTML2IMG_BROWSER", "VIDEDIT_ENCODER", "VIDEDIT_WEBCODECS", "HF_HOME")
# a key with one of these names is a secret wherever it comes from (the .env or the shell)
KNOWN_SECRETS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "MONGODB_URI",
    "STUDIO_TOKEN",
    "STUDIO_MEDIA_SAS",
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "ELEVENLABS_API_KEY",
    # the studio's own key to kitcut.ai's voice relay: a person's own ElevenLabs voice is
    # spoken there, with the workspace's key, which never comes here (tools.voice)
    "KITCUT_SITE_TOKEN",
)
# where a person's own voice is spoken: kitcut.ai's relay (its lib/connections/relay.js)
RELAY = (os.environ.get("STUDIO_VOICE_RELAY") or "https://kitcut.ai/api/studio/voice").rstrip("/")
# what each kind of step needs, beyond the basics
NEEDS = {
    "voice": (
        "GOOGLE_SERVICE_ACCOUNT_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GEMINI_API_KEY",
        "ELEVENLABS_API_KEY",  # the backup voice, for a line Gemini refuses
        "OPENROUTER_API_KEY",  # the scorer that listens to the takes (SCORER)
    ),
    "people": ("OPENROUTER_API_KEY",),  # the image model that draws them (head-rig.py)
    "paint": (
        "OPENROUTER_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ),
}
# who listens to the narration's takes (sketch-vo.py's SKETCH_SCORER): Whisper large-v3 on Groq,
# through OpenRouter. Held to a local large-v3 referee it caught the most bad takes of every
# service (English: missed 1 of 20; Ukrainian: 0 of 4, no false alarm) with word starts 0.08-0.12 s
# from the referee's, as close as the VM's own small.en -- in 9-17 s a film where small.en took
# 265 s, for $0.003. MAI-Transcribe 2, the faster-looking first pick, was 0.24-0.26 s off
# (scripts/vo-scorer-bench.py, docs/studio-speed.md). STUDIO_SCORER=local puts Whisper back on the
# machine (one with a GPU); a failed call scores that take locally either way.
SCORER = "openrouter:openai/whisper-large-v3"
# what a Windows (or other) process needs to start at all, and nothing else of ours
BASICS = (
    "SystemRoot",
    "SYSTEMROOT",
    "windir",
    "SystemDrive",
    "PATH",
    "PATHEXT",
    "COMSPEC",
    "USERPROFILE",
    "HOMEDRIVE",
    "HOMEPATH",
    "HOME",
    "LOCALAPPDATA",
    "APPDATA",
    "ProgramData",
    "ProgramFiles",
    "ProgramFiles(x86)",
    "ProgramW6432",
    "CommonProgramFiles",
    "CommonProgramFiles(x86)",
    "CommonProgramW6432",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
    "OS",
    "LANG",
    "LC_ALL",
    "TZ",
    "HF_HOME",
    "HTML2IMG_BROWSER",
    "VIDEDIT_ENCODER",
    "VIDEDIT_WEBCODECS",
    "VIDEDIT_WEBCODECS_BITRATE",
    "CUDA_PATH",
)


def read_env_file(path):
    """KEY=VALUE lines, as scripts/_env.py reads them, without touching os.environ."""
    got = {}
    if path and os.path.exists(path):
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, _, v = line.partition("=")
                got[k.strip()] = v.strip().strip('"').strip("'")
    return got


def is_config(k):
    return k.startswith(CONFIG) and k not in KNOWN_SECRETS


def load_secrets(path):
    """Read the studio's .env into SECRETS (settings into os.environ), then take every secret,
    and every Claude Code variable a surrounding session passed down, out of os.environ."""
    for k, v in read_env_file(path).items():
        if is_config(k):
            os.environ.setdefault(k, v)
        else:
            SECRETS.setdefault(k, v)
    for k in list(os.environ):
        if k in KNOWN_SECRETS or k in SECRETS:
            SECRETS.setdefault(k, os.environ[k])
            os.environ.pop(k)
        elif k.startswith(("CLAUDE", "ANTHROPIC_")) and k != "CLAUDE_CODE_GIT_BASH_PATH":
            os.environ.pop(k)
    return SECRETS


def secret(k, default=""):
    return (SECRETS.get(k) or default).strip()


def step_env(film, kind=None, locks=None, home=None):
    """The environment one pipeline step runs with: the basics, TEMP inside the film, and only
    the keys its kind needs."""
    env = {k: os.environ[k] for k in BASICS if k in os.environ}
    tmp = film.path("temp", "tmp")
    os.makedirs(tmp, exist_ok=True)
    env.update(
        TEMP=tmp,
        TMP=tmp,
        TMPDIR=tmp,
        PYTHONIOENCODING="utf-8",
        KITCUT_DOTENV="0",  # the scripts read no .env: what they need is below
        VIDEDIT_WORKSPACE=home or os.path.dirname(os.path.dirname(film.dir)),
        HF_HUB_OFFLINE="1",
        SKETCH_RENDER_OFFLINE="1",  # the render page reaches nothing but its own server
        SKETCH_WHISPER_DEVICE="cpu",  # the GPU stays free for the renders
    )
    if kind == "voice":
        scorer = os.environ.get("STUDIO_SCORER", "").strip() or SCORER
        if scorer != "local" and (
            not scorer.startswith("openrouter:") or SECRETS.get("OPENROUTER_API_KEY")
        ):
            env["SKETCH_SCORER"] = scorer
    if locks:
        env["KITCUT_LOCKS_DIR"] = locks
    # a person's own ElevenLabs voice (film.own_voice): the relay, the film's grant and the
    # studio's token to the relay -- and none of the studio's own voice keys, so nothing of
    # this film's narration can be spoken on KitCut's account by mistake
    own = film.own_voice() if kind == "voice" else None
    needs = ("OPENROUTER_API_KEY",) if own else NEEDS.get(kind, ())
    for k in needs:
        if SECRETS.get(k):
            env[k] = SECRETS[k]
    if own:
        env.update(
            ELEVENLABS_RELAY=RELAY,
            ELEVENLABS_GRANT=own["grant"],
            ELEVENLABS_FILM=film.id,
            KITCUT_SITE_TOKEN=SECRETS.get("KITCUT_SITE_TOKEN", ""),
        )
    return env


# ------------------------------------------------------------------ lifetime
_CGROUP = [None]  # the delegated cgroup v2 directory steps go under; False when there is none
_STEPS = itertools.count(1)


def cgroup_root():
    """The server's own cgroup, when systemd delegated it (Delegate=yes), prepared for steps.

    cgroup v2 lets a group either hold processes or hand controllers to children, not both, so
    the server first moves itself into a leaf `server/`, then turns the memory controller on for
    the children. Step groups a crashed server left behind are removed. Outside a systemd
    service (INVOCATION_ID unset) nothing is moved: a dev server keeps today's process groups.
    """
    if _CGROUP[0] is not None:
        return _CGROUP[0]
    _CGROUP[0] = False
    if not sys.platform.startswith("linux") or not os.environ.get("INVOCATION_ID"):
        return False
    try:
        with open("/proc/self/cgroup", encoding="utf-8") as f:
            rel = next(ln[3:].strip() for ln in f if ln.startswith("0::"))
        base = "/sys/fs/cgroup" + rel
        if os.path.basename(base) == "server":
            base = os.path.dirname(base)
        os.makedirs(os.path.join(base, "server"), exist_ok=True)
        _write(os.path.join(base, "server", "cgroup.procs"), os.getpid())
        _write(os.path.join(base, "cgroup.subtree_control"), "+memory")
        for d in os.listdir(base):
            if d.startswith("step-"):
                _rmdir_cgroup(os.path.join(base, d))
        _CGROUP[0] = base
    except (OSError, StopIteration) as e:
        print("procs: no delegated cgroup (%s): steps run with no memory cap" % e, file=sys.stderr)
    return _CGROUP[0]


def _write(path, value):
    with open(path, "w", encoding="utf-8") as f:
        f.write(str(value))


def _rmdir_cgroup(path, tries=20):
    """Remove a step's cgroup: kill what is left in it, then wait for the kernel to empty it."""
    try:
        _write(os.path.join(path, "cgroup.kill"), 1)
    except OSError:
        pass
    for _ in range(tries):
        try:
            os.rmdir(path)
            return True
        except FileNotFoundError:
            return True
        except OSError:
            time.sleep(0.05)
    return False


class Job:
    """A step's process and everything it starts, killed as one."""

    def __init__(self, mem_gb=None):
        self.h, self.pids, self.cg = None, [], None
        mem = mem_gb or float(os.environ.get("STUDIO_FILM_MEM_GB") or 12)
        if os.name != "nt":
            root = cgroup_root()
            if root:
                self.cg = os.path.join(root, "step-%d-%d" % (os.getpid(), next(_STEPS)))
                os.makedirs(self.cg)
                _write(os.path.join(self.cg, "memory.max"), int(mem * (1 << 30)))
                # over the cap the whole step dies, as a Job Object's would, not one random child
                _write(os.path.join(self.cg, "memory.oom.group"), 1)
        if os.name == "nt":
            import win32job

            self.h = win32job.CreateJobObject(None, "")  # no security attributes: not inherited
            info = win32job.QueryInformationJobObject(
                self.h, win32job.JobObjectExtendedLimitInformation
            )
            info["BasicLimitInformation"]["LimitFlags"] |= (
                win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                | win32job.JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
                | win32job.JOB_OBJECT_LIMIT_JOB_MEMORY
            )
            info["JobMemoryLimit"] = int(mem * (1 << 30))
            win32job.SetInformationJobObject(
                self.h, win32job.JobObjectExtendedLimitInformation, info
            )

    def add(self, proc):
        """Put a process started suspended (SUSPENDED) into the job, then let it run: a venv's
        python.exe is a launcher that starts the real interpreter at once, and a child started
        before the parent joins the job would not be in it."""
        self.pids.append(proc.pid)
        if self.h is not None:
            import ctypes
            import win32job

            handle = int(proc._transport.get_extra_info("subprocess")._handle)
            win32job.AssignProcessToJobObject(self.h, handle)
            if ctypes.windll.ntdll.NtResumeProcess(ctypes.c_void_p(handle)) != 0:
                raise OSError("could not resume the step's process")

    def enter(self):
        """preexec_fn: the child joins its cgroup before it can start anything of its own."""
        _write(os.path.join(self.cg, "cgroup.procs"), os.getpid())

    def kill(self):
        if self.cg is not None:
            try:
                _write(os.path.join(self.cg, "cgroup.kill"), 1)
            except OSError:
                pass
        if self.h is not None:
            import win32job

            try:
                win32job.TerminateJobObject(self.h, 1)
            except Exception:  # noqa: BLE001 -- already gone
                pass
        else:
            for pid in self.pids:
                try:
                    os.killpg(pid, signal.SIGKILL)
                except OSError:
                    pass

    def close(self):
        if self.h is not None:
            self.h.Close()  # with KILL_ON_JOB_CLOSE this also ends anything still running
            self.h = None
        if self.cg is not None:
            _rmdir_cgroup(self.cg)  # like KILL_ON_JOB_CLOSE: nothing outlives its step
            self.cg = None


SUSPENDED = 0x4  # CREATE_SUSPENDED: the step waits until it is in its job (Job.add)


class StepTimeout(Exception):
    pass


async def run(argv, cwd, env, timeout, on_line=None, jobs=None):
    """Run one step to the end. Returns (exit code, the last lines it printed). Raises
    StepTimeout past `timeout` seconds; a cancelled caller kills it too. `jobs` (a set) holds
    the live ones, so a film can kill whatever it has running."""
    job = Job()
    if os.name == "nt":
        kw = {"creationflags": subprocess.CREATE_NO_WINDOW | SUSPENDED}
    else:
        kw = {"start_new_session": True}
        if job.cg is not None:
            kw["preexec_fn"] = job.enter
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=cwd,
        env=env,
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
        limit=1 << 20,
        **kw,
    )
    try:
        job.add(proc)
    except Exception:
        job.kill()
        job.close()
        raise
    if jobs is not None:
        jobs.add(job)
    tail = []

    async def pump():
        async for raw in proc.stdout:
            line = raw.decode("utf-8", "replace").rstrip()
            if line.strip():
                tail.append(line)
                del tail[:-40]
                if on_line:
                    on_line(line)
        return await proc.wait()

    try:
        code = await asyncio.wait_for(pump(), timeout)
    except asyncio.TimeoutError:
        job.kill()
        raise StepTimeout("stopped after %d s" % timeout) from None
    except BaseException:
        job.kill()
        raise
    finally:
        if jobs is not None:
            jobs.discard(job)
        job.close()
    return code, tail


def python():
    """The interpreter the pipeline scripts run under: this one (the checkout's .venv)."""
    return sys.executable
