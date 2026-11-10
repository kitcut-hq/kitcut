"""Experiments on the Leo H3 pilot: one change each against a pilot shot, same seed unless noted.

python3 leo_exp.py plan   -> writes exp/<name>.json
"""

# ruff: noqa: INP001, T201  (a helper beside a skill, not a package; printing is its output)

import json
from pathlib import Path

D = Path("/srv/kitcut/scratch/h3test")
SHOTS = D / "shots"
EXP = D / "exp"

# name: (base shot, overrides, what it tests)
RUNS = {
    # yield on a shot whose staging works (v8 S01: the series' cabin), so a failed seed is the
    # model, not the prompt
    "S01_seed7": ("S01", {"seed": 7}, "yield: same shot, another seed"),
    "S01_seed99": ("S01", {"seed": 99}, "yield: same shot, a third seed"),
}


def plan() -> None:
    """Write one settings file per experiment from its base shot's settings."""
    EXP.mkdir(exist_ok=True)
    for name, (base, over, why) in RUNS.items():
        cfg = json.loads((SHOTS / f"{base}.json").read_text())
        cfg.update(over)
        cfg["output_filename"] = name
        (EXP / f"{name}.json").write_text(json.dumps(cfg, indent=1))
        print(f"{name:12s} {why}")


if __name__ == "__main__":
    plan()
