"""Make every script in this repo run under the project's own interpreter.

This exists because of a specific, very confusing failure mode on this machine.
A user-level PYTHONPATH pointed at Python 3.11's site-packages, so Python 3.13
imported 3.11's *compiled* extensions and died with "DLL load failed" or
"numpy.core.multiarray failed to import". A virtualenv does NOT protect you
from this: PYTHONPATH is prepended to sys.path inside a venv too. Worse, pip
reads the same path, decides a dependency is already satisfied, and silently
declines to install it into the venv -- which is how you end up with a venv
that is missing yaml and idna for no visible reason.

So: import this first, before anything third-party. If a .venv exists and we
are not already cleanly inside it, re-exec into it with PYTHONPATH stripped.
Running `python scripts/anything.py` with any interpreter then does the right
thing, and so does a shell that still has the old variable exported.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SENTINEL = "VIDEDIT_PY_BOOTSTRAPPED"


def venv_python(root=ROOT):
    """Path to the project interpreter, or None if the venv is not built yet."""
    for rel in (("Scripts", "python.exe"), ("bin", "python")):
        p = os.path.join(root, ".venv", *rel)
        if os.path.exists(p):
            return p
    return None


def load_dotenv(path=None, override=False):
    """Read KEY=VALUE lines from the repo's .env into os.environ.

    Keeps credentials out of both the shell profile and the repo -- `.env` is
    gitignored. Values already in the environment win unless override is set.
    """
    p = path or os.path.join(ROOT, ".env")
    if not os.path.exists(p):
        return {}
    got = {}
    with open(p, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            got[k] = v
            if override or not os.environ.get(k):
                os.environ[k] = v
    return got


def clean_env(env=None):
    """A child environment with the poisoned variable removed."""
    e = dict(os.environ if env is None else env)
    e.pop("PYTHONPATH", None)
    e.setdefault("PYTHONIOENCODING", "utf-8")
    return e


def _in_venv(py):
    return os.path.normcase(os.path.dirname(os.path.dirname(py))) == \
           os.path.normcase(sys.prefix)


def site_roots():
    """Every site-packages directory that belongs to THIS interpreter.

    Used for two things: pruning foreign paths, and finding the pip-installed
    CUDA DLLs under <root>/nvidia/*/bin. It has to look past purelib -- a
    Microsoft Store Python puts pip installs in the user site, so a purelib-only
    search finds no cuBLAS and GPU inference degrades to CPU without saying so.
    """
    import sysconfig
    import site

    def norm(x):
        return os.path.normcase(os.path.abspath(x))

    roots = {norm(x) for x in (sysconfig.get_paths().get("purelib"),
                               sysconfig.get_paths().get("platlib")) if x}
    for getter in (lambda: [site.getusersitepackages()], site.getsitepackages):
        try:
            roots.update(norm(x) for x in getter())
        except Exception:
            pass
    return roots


def prune_foreign_site_packages():
    """Fallback for when there is no .venv to re-exec into.

    sys.path is frozen at interpreter startup, so clearing os.environ in-process
    is too late -- but we can still drop the entries that belong to a different
    install before any third-party import happens.
    """
    own = site_roots()
    sys.path[:] = [x for x in sys.path
                   if "site-packages" not in x.lower()
                   or os.path.normcase(os.path.abspath(x)) in own]


def bootstrap():
    py = venv_python()
    if py is None:
        return                                   # not set up yet; run as found
    if _in_venv(py) and not os.environ.get("PYTHONPATH"):
        return                                   # already clean
    if os.environ.get(_SENTINEL):
        return                                   # re-exec already tried once
    script = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else ""
    if not os.path.isfile(script):
        return          # -c, -m or a REPL: nothing to hand to a child
    env = clean_env()
    env[_SENTINEL] = "1"
    # NOT os.execve: on Windows that is _execve, which spawns a new process and
    # kills this one instead of replacing it. The shell then sees the parent
    # die abnormally (bash reports a segfault) and the exit code is lost. A
    # subprocess we wait on keeps stdio attached and the status intact.
    import subprocess
    sys.stdout.flush()
    sys.stderr.flush()
    r = subprocess.run([py, "-X", "utf8", script] + sys.argv[1:], env=env)
    sys.exit(r.returncode)


def utf8_stdio():
    """Windows consoles default to cp1252 and explode on Cyrillic."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass


bootstrap()
prune_foreign_site_packages()
utf8_stdio()
load_dotenv()

# For subprocess calls: the interpreter to spawn, and an env that stays clean.
PY = [venv_python() or sys.executable, "-X", "utf8"]
ENV = clean_env()
