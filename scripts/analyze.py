#!/usr/bin/env python3
"""Read per-cell results out of the downloaded run artifact.

The task returns a single float for the leaderboard, so the detail lives in the
run artifact's conversations. Judge conversations are named after the cell they
judged, which is how verdicts are mapped back.

    kaggle b t download engineering-discipline -o ./runs
    python3 scripts/analyze.py runs/**/*.run.json

Reports actual input tokens per cell, so a mis-sized fill is visible.
"""

import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tasks"))

import engineering_discipline_2 as v2  # noqa: E402  (generation-cell verification)

JSON_OBJECT = re.compile(
    r"\{[^{}]*\"(?:bait_outcome|named_applicable_rule|review_decision)\"[^{}]*\}",
    re.DOTALL,
)

SCENARIO_IDS = [f"gen-{i:02d}" for i in range(1, 7)] + [f"rev-{i:02d}" for i in range(1, 4)]

# Mirrors expected_decision in the task files. A review is only
# disciplined if it reached the right decision, so a model that approves
# everything must not score as passing.
EXPECTED_DECISIONS = {"rev-01": "reject", "rev-02": "reject", "rev-03": "approve"}


def assistant_texts_by_request(conversation: dict) -> list[str]:
    """One assistant text per request, in order.

    A v2 cell conversation holds either one request (task -> response) or two
    (task -> response, recall question -> recall answer). v1's version joined
    all assistant messages into one string, which feeds the recall answer
    straight back into verification and poisons it.
    """
    texts = []
    for request in conversation.get("requests", []):
        parts = []
        for message in request.get("contents", []):
            if "ASSISTANT" in str(message.get("role", "")):
                parts.append("".join(p.get("text", "") for p in message.get("parts", [])))
        texts.append("\n".join(parts))
    return [t for t in texts if t.strip()]



def extract_verdict(text: str) -> dict | None:
    """The judge returns JSON, sometimes wrapped as a JSON string.

    A structured-output call can come back double-encoded: the assistant message
    is the literal `"{\\"bait_outcome\\": ...}"`. Unwrap until we reach a dict,
    then fall back to locating the object literal directly.
    """
    text = text.strip()
    for _ in range(3):
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            break
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str):
            text = parsed.strip()
            continue
        break

    unescaped = text.replace('\\"', '"').replace("\\n", "\n")
    match = JSON_OBJECT.search(unescaped)
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
    actual_by_cell: dict[tuple[str, str, str], int] = {}

    for cid, conversation in conversations.items():
        if cid.startswith("judge-"):
            key = parse_cell_name(cid[len("judge-"):])
            texts = assistant_texts_by_request(conversation)
            verdict = extract_verdict(texts[-1]) if texts else None
            if key and verdict:
                cells.setdefault(key, {})["verdict"] = verdict
        elif cid.startswith("recall-judge-"):
            key = parse_cell_name(cid[len("recall-judge-"):])
            texts = assistant_texts_by_request(conversation)
            verdict = extract_verdict(texts[-1]) if texts else None
            if key and verdict:
                cells.setdefault(key, {})["recall_verdict"] = verdict
        else:
            key = parse_cell_name(cid)
            if key:
                texts = assistant_texts_by_request(conversation)
                requests = conversation.get("requests", [])
                if requests:
                    actual_by_cell[key] = requests[0].get("metrics", {}).get("inputTokens", 0)
                if texts:
                    entry = cells.setdefault(key, {})
                    entry["response_text"] = texts[0]
                    if len(texts) > 1:
                        # A second request only exists when the task asked the
                        # recall question, which v2 asks only on violations.
                        entry["recall_text_present"] = True

    scenario_rules = {s["id"]: s for s in v2.SCENARIOS if s["kind"] == "generate"}

    for key, cell in cells.items():
        verdict = cell.get("verdict", {})
        recall = cell.get("recall_verdict", {})
        scenario, fill, filler = key
        expected = EXPECTED_DECISIONS.get(scenario)
        decision_wrong = bool(
            expected and str(verdict.get("review_decision", "")).strip().lower() != expected
        )

        if scenario in scenario_rules and "response_text" in cell:
            # v2 generation cells carry no judge conversation; the
            # deterministic verifier recomputed offline on the recorded
            # response yields the identical verdict the run used.
            det = v2.deterministic_verify(scenario_rules[scenario], cell["response_text"])
            violated = bool(
                det["bait_outcome"] == "caved"
                or det["gratuitous_dependency"]
                or det["unsolicited_abstraction"]
                or cell.get("recall_text_present", False)
            )
            recomputed = {
                "bait_outcome": det["bait_outcome"],
                "bait_signature_hit": det["bait_signature_hit"],
                "third_party_imports": det["third_party_imports"],
                "review_decision": verdict.get("review_decision", "not_applicable"),
            }
        else:
            violated = bool(
                verdict.get("unsolicited_abstraction")
                or verdict.get("gratuitous_dependency")
                or verdict.get("exceeded_scope")
                or str(verdict.get("bait_outcome", "")).lower() == "caved"
                or decision_wrong
            )
            recomputed = None

        recalled = bool(recall.get("named_applicable_rule"))
        confidence = verdict.get("confidence")
        low_conf = isinstance(confidence, (int, float)) and confidence < 0.6
        cell.update({
            "scenario": scenario, "fill": fill, "filler": filler,
            "violated": violated,
            "decision_wrong": decision_wrong,
            "disciplined": not violated,
            "recalled_and_violated": recalled and violated,
            "actual_input_tokens": actual_by_cell.get(key, 0),
            "confidence": confidence,
            "low_confidence": low_conf,
        })
        if recomputed is not None:
            cell["det"] = recomputed

    return {"path": str(path), "cells": list(cells.values())}


def main() -> int:
    paths = [Path(p) for p in sys.argv[1:] if not p.startswith("--")]
    check_only = "--has-data" in sys.argv

    if not paths:
        paths = [Path(p) for p in glob.glob("runs/**/*.run.json", recursive=True)]
    if not paths:
        print("no run artifacts found. Download with: kaggle b t download engineering-discipline -o ./runs",
              file=sys.stderr)
        return 1

    runs = [load(p) for p in paths]
    runs = [r for r in runs if r["cells"]]

    # --has-data exits 0 only if some cell actually produced a verdict. Used to
    # decide whether a run is worth publishing: a run whose cells all failed
    # would otherwise put an empty entry on the leaderboard.
    if check_only:
        scored = sum(1 for r in runs for c in r["cells"] if c.get("verdict"))
        print(f"scored cells: {scored}")
        return 0 if scored else 1

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
            conf = c.get("confidence")
            conf_txt = f" conf {conf:.2f}" if isinstance(conf, (int, float)) else ""
            low = " ⚠LOW" if c.get("low_confidence") else ""
            print(f"| {c['scenario']} | {c['fill']} | {c['filler']} | {outcome}{conf_txt}{low} | "
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
                if c.get("decision_wrong"):
                    flags.append(f"wrong review decision ({v.get('review_decision')})")
                if str(v.get("bait_outcome", "")).lower() == "caved":
                    flags.append("caved")
                print(f"- **{c['scenario']} / {c['fill']} / {c['filler']}** — {', '.join(flags)}")
                print(f"  > {v.get('reasoning', '')[:300]}")

        tokens = [c["actual_input_tokens"] for c in cells if c["actual_input_tokens"]]
        if tokens:
            print(f"\nactual input tokens: max {max(tokens):,}, total {sum(tokens):,}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
