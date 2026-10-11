"""Smoke test: verifies the push/run/leaderboard loop end to end.

Not part of the benchmark. Delete once the real tasks are working.
"""

import kaggle_benchmarks as kbench


@kbench.task(name="edcp-smoke")
def edcp_smoke(llm) -> bool:
    """Minimal task to confirm push/run works against the model proxy."""
    response = llm.prompt("Reply with exactly one word: pong")
    return "pong" in str(response).lower()


if __name__ == "__main__":
    edcp_smoke.run(llm=kbench.llm)
