"""Experiments on the Leo H3 pilot: one change each against a shot of the pilot, same seed unless the seed is the change.

python3 leo_exp.py plan   -> writes exp/<name>.json
"""
import json
from pathlib import Path

D = Path("/srv/kitcut/scratch/h3test")
SHOTS = D / "shots"
EXP = D / "exp"

# name: (base shot, overrides, what it tests)
RUNS = {
    "S06_seed7": ("S06", {"seed": 7}, "yield: same shot, another seed"),
    "S06_seed99": ("S06", {"seed": 99}, "yield: same shot, a third seed"),
    "S06_5s": ("S06", {"video_length": "5.0s"}, "length: 5 s against 9.3 s"),
    "S06_pdd": ("S06", {"model_type": "minimax_h3_ref2va_pruned_pdd"}, "model: Ref2VA PDD against FastH3"),
}


def plan():
    EXP.mkdir(exist_ok=True)
    for name, (base, over, why) in RUNS.items():
        cfg = json.loads((SHOTS / f"{base}.json").read_text())
        cfg.update(over)
        cfg["output_filename"] = name
        (EXP / f"{name}.json").write_text(json.dumps(cfg, indent=1))
        print(f"{name:12s} {why}")


if __name__ == "__main__":
    plan()
