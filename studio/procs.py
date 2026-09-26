"""The processes a film runs: what each one may see, and that none outlives its film.

Secrets. The studio's keys (Claude, MongoDB, Google, OpenRouter...) are read from its .env file
(STUDIO_ENV_FILE, else the code's own .env) into SECRETS and taken out of os.environ, so nothing
started from here inherits them by accident: not Claude Code, not a browser, not ffmpeg. A step
is handed only what it needs (step_env): the voice gets the Google keys, the painter OpenRouter's,
the render and the mix none at all. KITCUT_DOTENV=0 stops the scripts reading a .env of their own.
Settings that are not secrets (STUDIO_* but the token) stay ordinary environment variables.

Lifetime. On Windows every step runs in a Job Object of its own: killing it (a timeout, a
cancelled film) takes down the step and everything it started -- browsers, ffmpeg -- in one call,
and since the job is set to die with its last handle, a server that is killed outright takes all
of them with it. A step may use at most STUDIO_FILM_MEM_GB (12) of memory. Elsewhere the step
leads a process group of its own and the group is killed.
"""

import os
import sys
import signal
import asyncio
import subprocess

SECRETS = {}
# settings from the .env that are not secret, and stay in the environment
CONFIG = ("STUDIO_", "HTML2IMG_BROWSER", "VIDEDIT_ENCODER", "HF_HOME")
# a key with one of these names is a secret wherever it comes from (the .env or the shell)
KNOWN_SECRETS = (
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
    "MONGODB_URI",
    "STUDIO_TOKEN",
    "GOOGLE_SERVICE_ACCOUNT_KEY",
    "GEMINI_API_KEY",
    "OPENROUTER_API_KEY",
    "ELEVENLABS_API_KEY",
)
# what each kind of step needs, beyond the basics
NEEDS = {
    "voice": (
        "GOOGLE_SERVICE_ACCOUNT_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
        "GEMINI_API_KEY",
    ),
    "paint": (
        "OPENROUTER_API_KEY",
        "GOOGLE_SERVICE_ACCOUNT_KEY",
        "GOOGLE_CLOUD_PROJECT",
        "GOOGLE_CLOUD_LOCATION",
    ),
}
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
    return k.startswith(CONFIG) and k != "STUDIO_TOKEN"


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
    if locks:
        env["KITCUT_LOCKS_DIR"] = locks
    for k in NEEDS.get(kind, ()):
        if SECRETS.get(k):
            env[k] = SECRETS[k]
    return env


# ------------------------------------------------------------------ lifetime
class Job:
    """A step's process and everything it starts, killed as one."""

    def __init__(self, mem_gb=None):
        self.h, self.pids = None, []
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
            mem = mem_gb or float(os.environ.get("STUDIO_FILM_MEM_GB") or 12)
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

    def kill(self):
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


SUSPENDED = 0x4  # CREATE_SUSPENDED: the step waits until it is in its job (Job.add)


class StepTimeout(Exception):
    pass


async def run(argv, cwd, env, timeout, on_line=None, jobs=None):
    """Run one step to the end. Returns (exit code, the last lines it printed). Raises
    StepTimeout past `timeout` seconds; a cancelled caller kills it too. `jobs` (a set) holds
    the live ones, so a film can kill whatever it has running."""
    job = Job()
    kw = (
        {"start_new_session": True}
        if os.name != "nt"
        else {"creationflags": subprocess.CREATE_NO_WINDOW | SUSPENDED}
    )
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
