#!/usr/bin/env python3
"""Pilot: a few scenarios across both brackets, locally, before the full run.

    source scripts/kbench-env.sh
    python3 scripts/pilot.py [n_scenarios]

Purpose is to answer two questions cheaply:
  1. Does the loop work end to end (haystack, probe, judge, static)?
  2. Is there a ceiling/floor problem? If adherence is already low at C_low,
     there is no room for degradation to show and the design needs revisiting.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tasks"))

import edcp  # noqa: E402
import kaggle_benchmarks as kbench  # noqa: E402

n = int(sys.argv[1]) if len(sys.argv) > 1 else 2
scenarios = edcp.SCENARIOS[:n]

print(f"pilot: {len(scenarios)} scenario(s) x 2 brackets")
haystack = edcp.load_haystack()
print(f"haystack: {len(haystack):,} chars (~{len(haystack) // 4:,} tokens)\n")

cells = []
for scenario in scenarios:
    for bracket, ctx in (("low", ""), ("high", haystack)):
        t0 = time.time()
        cell = edcp.score_cell(kbench.llm, kbench.judge_llm, scenario, ctx, edcp.SYSTEM_PROMPT)
        cell["bracket"] = bracket
        cells.append(cell)
        v = cell["verdict"]
        print(
            f"  [{bracket:4}] {cell['id']:8} "
            f"disciplined={cell['disciplined']!s:5} "
            f"bait={v.bait_outcome:22} "
            f"abs={v.unsolicited_abstraction!s:5} "
            f"dep={v.gratuitous_dependency!s:5} "
            f"scope={v.exceeded_scope!s:5} "
            f"rbv={cell['recalls_but_violates']!s:5} "
            f"({time.time() - t0:.0f}s)"
        )

low = [c for c in cells if c["bracket"] == "low"]
high = [c for c in cells if c["bracket"] == "high"]
dar_low = sum(c["disciplined"] for c in low) / len(low)
dar_high = sum(c["disciplined"] for c in high) / len(high)

print(f"\nDAR low  : {dar_low:.2f}")
print(f"DAR high : {dar_high:.2f}")
print(f"delta_deg: {dar_low - dar_high:+.2f}")
print(f"recalls_but_violates: {sum(c['recalls_but_violates'] for c in cells)}")

print("\n--- static measures ---")
for c in cells:
    s = c["static"]
    print(f"  {c['bracket']:4} {c['id']:8} {s}")
