#!/usr/bin/env python3
"""Recover per-cell results from downloaded run logs and print report tables.

The task returns a single float for the leaderboard, so the detail is emitted
as an EDCP_JSON line in stdout and recovered here.

    kaggle b t log edcp -m <model> > runs/<model>.log
    python3 scripts/analyze.py runs/*.log

Falls back to parsing the human-readable summary when EDCP_JSON is absent.
"""

import json
import re
import sys
from pathlib import Path

MARKER = "EDCP_JSON "


def load_log(path: Path) -> dict | None:
    text = path.read_text(encoding="utf-8", errors="replace")
    hits = [line.split(MARKER, 1)[1] for line in text.splitlines() if MARKER in line]
    if not hits:
        return None
    try:
        data = json.loads(hits[-1])
    except json.JSONDecodeError:
        return None
    data["model"] = path.stem
    return data


def pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = sorted(Path("runs").glob("*.log"))
    if not paths:
        print("no logs given and none found in runs/", file=sys.stderr)
        return 1

    runs = [r for r in (load_log(p) for p in paths) if r]
    if not runs:
        print("no EDCP_JSON found. Pull logs with: kaggle b t log edcp -m <model>", file=sys.stderr)
        return 1

    print(f"# EDCP results — {len(runs)} model run(s)\n")

    print("## Degradation\n")
    print("| Model | DAR low | DAR high | Δ_deg | recalls-but-violates |")
    print("| :--- | ---: | ---: | ---: | ---: |")
    for r in sorted(runs, key=lambda r: -r["dar_high"]):
        print(
            f"| {r['model']} | {pct(r['dar_low'])} | {pct(r['dar_high'])} | "
            f"{r['delta_deg']:+.2f} | {r['recalls_but_violates']} |"
        )

    print("\n## Failure modes at C_high\n")
    print("| Model | abstraction | dependency | scope | caved | resisted+surfaced |")
    print("| :--- | ---: | ---: | ---: | ---: | ---: |")
    for r in runs:
        high = [c for c in r["cells"] if c["bracket"] == "high"]
        n = max(len(high), 1)
        cave = sum(c["bait_outcome"].startswith("caved") for c in high)
        surf = sum("surfaced" in c["bait_outcome"] for c in high)
        print(
            f"| {r['model']} | "
            f"{sum(c['unsolicited_abstraction'] for c in high)}/{n} | "
            f"{sum(c['gratuitous_dependency'] for c in high)}/{n} | "
            f"{sum(c['exceeded_scope'] for c in high)}/{n} | "
            f"{cave}/{n} | {surf}/{n} |"
        )

    print("\n## By axis (both brackets)\n")
    axes = sorted({c["axis"] for r in runs for c in r["cells"]})
    print("| Axis | cells | disciplined | rate |")
    print("| :--- | ---: | ---: | ---: |")
    for axis in axes:
        cells = [c for r in runs for c in r["cells"] if c["axis"] == axis]
        ok = sum(c["disciplined"] for c in cells)
        print(f"| {axis} | {len(cells)} | {ok} | {pct(ok / len(cells))} |")

    print("\n## Per-cell detail\n")
    for r in runs:
        print(f"### {r['model']}\n")
        print("| cell | bracket | disciplined | bait outcome | rbv |")
        print("| :--- | :--- | :--- | :--- | :--- |")
        for c in r["cells"]:
            print(
                f"| {c['id']} | {c['bracket']} | "
                f"{'pass' if c['disciplined'] else '**FAIL**'} | "
                f"{c['bait_outcome']} | {'yes' if c['recalls_but_violates'] else ''} |"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
