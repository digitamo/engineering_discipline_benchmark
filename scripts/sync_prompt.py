#!/usr/bin/env python3
"""Generate data/system_prompt.md from the STANDARDS constant in the task file.

The task file is self-contained because `kaggle b t push -f` accepts only one
file, so the standards have to be inlined there. This script makes that inlined
copy the single source of truth and regenerates the readable markdown from it,
rather than relying on a comment asking people to keep two copies in step.

    python3 scripts/sync_prompt.py
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TASK_FILE = ROOT / "tasks" / "engineering_discipline.py"
OUT_FILE = ROOT / "data" / "system_prompt.md"

PATTERN = re.compile(r'^STANDARDS = """\\\n(.*?)^"""$', re.DOTALL | re.MULTILINE)


def main() -> int:
    source = TASK_FILE.read_text(encoding="utf-8")
    match = PATTERN.search(source)
    if not match:
        print(f"error: could not find STANDARDS in {TASK_FILE}", file=sys.stderr)
        return 1

    standards = match.group(1)
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(standards, encoding="utf-8")

    print(f"wrote {OUT_FILE.relative_to(ROOT)}  ({len(standards):,} chars, "
          f"~{len(standards) // 4:,} tokens)")

    # Verify round-trip: the file we just wrote must be what the task will send.
    if OUT_FILE.read_text(encoding="utf-8") != standards:
        print("error: round-trip mismatch", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
