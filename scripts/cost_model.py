#!/usr/bin/env python3
"""Estimate what a run costs on the Kaggle model proxy.

The proxy reserves quota per request as `input_tokens * input_rate +
max_output_tokens * output_rate`, and refuses a request before sending it when
the reservation exceeds the remaining balance. So the binding number is the
reservation, not the tokens actually spent.

Rates for gemini-3.7-flash were derived by submitting two requests that differ
only in `max_tokens` and solving for the two unknowns:

    input  $0.38 / M tokens
    output $3.75 / M tokens

    python3 scripts/cost_model.py
"""

CHARS_PER_TOKEN = 4

INPUT_RATE = 0.38 / 1_000_000
OUTPUT_RATE = 3.75 / 1_000_000

WINDOW = 1_048_576
MAX_OUTPUT = 4096
JUDGE_OUTPUT = 1024

STANDARDS_TOKENS = 1_500
TASK_TOKENS = 200
JUDGE_INPUT_TOKENS = 2_000

# Fillers applied at every non-zero fill. A zero fill has no context, so no
# filler applies there.
FILLERS = ["prose", "code"]


def request_cost(input_tokens: int, max_output: int = MAX_OUTPUT) -> float:
    return input_tokens * INPUT_RATE + max_output * OUTPUT_RATE


def cell_cost(context_tokens: int, violates: bool) -> tuple[float, float]:
    """Returns (cost, reservation) for one cell.

    A cell makes one task request, plus a recall request when it violated,
    because the recall re-sends the whole conversation.
    """
    task_input = context_tokens + STANDARDS_TOKENS + TASK_TOKENS
    cost = request_cost(task_input)
    peak = request_cost(task_input)

    if violates:
        recall_input = task_input + MAX_OUTPUT
        cost += request_cost(recall_input)
        peak = max(peak, request_cost(recall_input))
        cost += request_cost(JUDGE_INPUT_TOKENS, JUDGE_OUTPUT) * 2
    else:
        cost += request_cost(JUDGE_INPUT_TOKENS, JUDGE_OUTPUT)

    return cost, peak



def sweep(label: str, levels) -> None:
    """levels: list of (fill, scenario_count). Fillers apply at every non-zero fill."""
    cells = 0
    peak = 0.0
    none_violate = 0.0
    all_violate = 0.0

    for fill, n_scenarios in levels:
        context = int(WINDOW * fill)
        applicable = FILLERS if context else ["none"]
        for _ in applicable:
            for i in range(n_scenarios):
                cells += 1
                c0, r = cell_cost(context, False)
                c1, _ = cell_cost(context, True)
                none_violate += c0
                all_violate += c1
                peak = max(peak, r)

    print(f"\n{label}")
    print(f"  cells                : {cells}")
    print(f"  largest reservation  : ${peak:.4f}")
    print(f"  cost, none violate   : ${none_violate:.2f}")
    print(f"  cost, all violate    : ${all_violate:.2f}")


def main() -> int:
    print(f"rates: input ${INPUT_RATE * 1e6:.2f}/M, output ${OUTPUT_RATE * 1e6:.2f}/M")
    print(f"window: {WINDOW:,} tokens, max output {MAX_OUTPUT}")

    # The configured sweep. Keep this in step with FILL_LEVELS in the task file.
    sweep("configured: 9 at 0%, 3 scenarios x 2 fillers at 30%, 60%, 90%",
          [(0.0, 9), (0.30, 3), (0.60, 3), (0.90, 3)])

    print("\nA push is one run, not two: task creation executes the task and that")
    print("run is scored, so it populates the leaderboard by itself.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
