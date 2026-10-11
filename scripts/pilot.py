#!/usr/bin/env python3
"""Small local run, to exercise the loop without spending a full run.

    source scripts/kbench-env.sh
    python3 scripts/pilot.py [fill_fraction] [n_scenarios]

Cheap by default: a tiny fill and a couple of scenarios. Raise the fill once the
loop is known to work. Use a small-window model for cheap iteration.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tasks"))

import engineering_discipline as benchmark  # noqa: E402
import kaggle_benchmarks as kbench  # noqa: E402

fill = float(sys.argv[1]) if len(sys.argv) > 1 else 0.03
count = int(sys.argv[2]) if len(sys.argv) > 2 else 2

# Override the module constants rather than editing the task file, so the
# published task keeps its real configuration.
benchmark.FILL_LEVELS = [
    {"fill": 0.0, "scenarios": None},
    {"fill": fill, "scenarios": [s["id"] for s in benchmark.SCENARIOS[:count]]},
]

print(f"pilot: fill={fill}, {count} scenario(s), model={kbench.llm.name}")
benchmark.engineering_discipline.run(llm=kbench.llm, judge_llm=kbench.judge_llm)
