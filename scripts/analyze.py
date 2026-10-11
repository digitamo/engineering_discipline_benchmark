#!/usr/bin/env python3
"""Read per-cell results out of the downloaded run artifact.

The task returns a single float for the leaderboard, so the detail lives in the
run artifact's conversations. Judge conversations are named after the cell they
judged, which is how verdicts are mapped back.

    kaggle b t download engineering-discipline -o ./runs
    python3 scripts/analyze.py runs/**/*.run.json

Also reports the gap between our chars/4 token estimate and the actual input
tokens the platform charged, so the calibration error stays visible.
"""

import glob
import json
import re
import sys
from pathlib import Path

CHARS_PER_TOKEN = 4

JSON_OBJECT = re.compile(r"\{[^{}]*\"(?:bait_outcome|named_applicable_rule)\"[^{}]*\}", re.DOTALL)

SCENARIO_IDS = [f"gen-{i:02d}" for i in range(1, 10)] + [f"rev-{i:02d}" for i in range(1, 10)]


def assistant_text(conversation: dict) -> str:
    parts = []
    for request in conversation.get("requests", []):
        for message in request.get("contents", []):
            if "ASSISTANT" in str(message.get("role", "")):
                parts.append("".join(p.get("text", "") for p in message.get("parts", [])))
    return "\n".join(parts)


def extract_verdict(text: str) -> dict | None:
    match = JSON_OBJECT.search(text)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def parse_cell_name(conversation_id: str) -> tuple[str, str, str] | None:
    """Conversation ids look like 'gen-01-90pct-prose-1a2b3c4d'."""
    for scenario in SCENARIO_IDS:
        if conversation_id.startswith(scenario + "-"):
            rest = conversation_id[len(scenario) + 1:]
            bits = rest.rsplit("-", 1)[0]  # drop the hash
            parts = bits.split("-")
            if len(parts) >= 2:
                return scenario, parts[0], "-".join(parts[1:])
    return None


def load(path: Path) -> dict:
    run = json.loads(path.read_text(encoding="utf-8"))
    conversations = {c.get("id", ""): c for c in run.get("conversations", [])}

    cells: dict[tuple[str, str, str], dict] = {}
    estimate_by_cell: dict[tuple[str, str, str], int] = {}
    actual_by_cell: dict[tuple[str, str, str], int] = {}

    for cid, conversation in conversations.items():
        if cid.startswith("judge-"):
            key = parse_cell_name(cid[len("judge-"):])
            verdict = extract_verdict(assistant_text(conversation))
            if key and verdict:
                cells.setdefault(key, {})["verdict"] = verdict
        elif cid.startswith("recall-judge-"):
            key = parse_cell_name(cid[len("recall-judge-"):])
            verdict = extract_verdict(assistant_text(conversation))
            if key and verdict:
                cells.setdefault(key, {})["recall_verdict"] = verdict
        else:
            key = parse_cell_name(cid)
            if key:
                requests = conversation.get("requests", [])
                if requests:
                    actual_by_cell[key] = requests[0].get("metrics", {}).get("inputTokens", 0)
                    text = assistant_text(conversation)
                    estimate_by_cell[key] = len(text) // CHARS_PER_TOKEN

    for key, cell in cells.items():
        verdict = cell.get("verdict", {})
        recall = cell.get("recall_verdict", {})
        scenario, fill, filler = key
        violated = bool(
            verdict.get("unsolicited_abstraction")
            or verdict.get("gratuitous_dependency")
            or verdict.get("exceeded_scope")
            or str(verdict.get("bait_outcome", "")).lower() == "caved"
        )
        recalled = bool(recall.get("named_applicable_rule"))
        cell.update({
            "scenario": scenario, "fill": fill, "filler": filler,
            "violated": violated,
            "disciplined": not violated,
            "recalled_and_violated": recalled and violated,
            "actual_input_tokens": actual_by_cell.get(key, 0),
        })

    return {"path": str(path), "cells": list(cells.values())}


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:]]
    if not paths:
        paths = [Path(p) for p in glob.glob("runs/**/*.run.json", recursive=True)]
    if not paths:
        print("no run artifacts found. Download with: kaggle b t download engineering-discipline -o ./runs",
              file=sys.stderr)
        return 1

    runs = [load(p) for p in paths]
    runs = [r for r in runs if r["cells"]]
    if not runs:
        print("no scored cells found in the given artifacts", file=sys.stderr)
        return 1

    for run in runs:
        cells = run["cells"]
        print(f"\n# {run['path']}  ({len(cells)} cells)\n")

        conditions = sorted({(c["fill"], c["filler"]) for c in cells})
        print("| fill | filler | pass rate | passed |")
        print("| :--- | :--- | ---: | ---: |")
        for fill, filler in conditions:
            subset = [c for c in cells if c["fill"] == fill and c["filler"] == filler]
            passed = sum(c["disciplined"] for c in subset)
            print(f"| {fill} | {filler} | {passed / len(subset):.3f} | {passed}/{len(subset)} |")

        print("\n| scenario | fill | filler | outcome | bait | recalled & violated |")
        print("| :--- | :--- | :--- | :--- | :--- | :--- |")
        for c in sorted(cells, key=lambda c: (c["fill"], c["filler"], c["scenario"])):
            outcome = "pass" if c["disciplined"] else "**FAIL**"
            print(f"| {c['scenario']} | {c['fill']} | {c['filler']} | {outcome} | "
                  f"{c['verdict'].get('bait_outcome', '?')} | "
                  f"{'yes' if c['recalled_and_violated'] else ''} |")

        violations = [c for c in cells if c["violated"]]
        if violations:
            print("\n## Violation detail\n")
            for c in violations:
                v = c["verdict"]
                flags = [name for name in
                         ("unsolicited_abstraction", "gratuitous_dependency", "exceeded_scope")
                         if v.get(name)]
                print(f"- **{c['scenario']} / {c['fill']} / {c['filler']}** — {', '.join(flags) or 'caved'}")
                print(f"  > {v.get('reasoning', '')[:300]}")

        tokens = [c["actual_input_tokens"] for c in cells if c["actual_input_tokens"]]
        if tokens:
            print(f"\nactual input tokens: max {max(tokens):,}, total {sum(tokens):,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
