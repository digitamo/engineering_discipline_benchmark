#!/usr/bin/env python3
"""Scoring tests that need no model and no quota.

The benchmark's control flow has several failure modes that only show up when
something is missing: the standards not reaching the conversation, the judge
returning None, a review reaching the wrong decision. Those are cheap to test
and expensive to discover during a run.

    source scripts/kbench-env.sh
    python3 scripts/test_scoring.py

Exits non-zero if anything fails.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tasks"))

import engineering_discipline as benchmark  # noqa: E402

FAILURES = []


class StubSubject:
    """Returns canned text and counts how many times it was asked."""

    name = "stub-subject"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    def prompt(self, message, schema=str, **kwargs):
        self.calls += 1
        return self.replies.pop(0) if self.replies else "(nothing queued)"


class StubJudge:
    name = "stub-judge"

    def __init__(self, verdicts):
        self.verdicts = list(verdicts)
        self.calls = 0

    def prompt(self, message, schema=str, **kwargs):
        self.calls += 1
        return self.verdicts.pop(0) if self.verdicts else None


def response_verdict(caved=False, wrong_decision=None):
    return benchmark.ResponseVerdict(
        bait_outcome="caved" if caved else "resisted_and_surfaced",
        unsolicited_abstraction=False,
        gratuitous_dependency=False,
        exceeded_scope=False,
        review_decision=wrong_decision or "not_applicable",
        reasoning="stub",
    )


def check(name, actual, expected):
    ok = actual == expected
    print(f"  {'ok  ' if ok else 'FAIL'} {name}: got {actual!r}, expected {expected!r}")
    if not ok:
        FAILURES.append(name)


def run_silently(fn, *args):
    """The chat context prints the whole conversation on exit.

    It writes below the Python stream level, so redirect_stdout does not catch
    it. Redirecting the file descriptors does.
    """
    saved_out, saved_err = os.dup(1), os.dup(2)
    devnull = os.open(os.devnull, os.O_WRONLY)
    try:
        # Flush first. Without this, anything already buffered by print() gets
        # written to /dev/null when the descriptor changes underneath it.
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        return fn(*args)
    finally:
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(saved_out, 1)
        os.dup2(saved_err, 2)
        os.close(devnull)
        os.close(saved_out)
        os.close(saved_err)


def main() -> int:
    generate = benchmark.SCENARIOS[0]
    review = next(s for s in benchmark.SCENARIOS if s["id"] == "rev-01")

    print("scoring")

    # A passing cell must not spend a second context-carrying request.
    subject = StubSubject(["a dict with a lock"])
    judge = StubJudge([response_verdict()])
    cell = run_silently(benchmark.score_cell, subject, judge, generate, "", "0pct", "none")
    check("passing cell is disciplined", cell["disciplined"], True)
    check("passing cell asks the subject once (no recall)", subject.calls, 1)

    # A violating cell must ask, because that is the only case where
    # recalled-but-violated can occur.
    subject = StubSubject(["built an abstract factory", "I declined to add hooks"])
    judge = StubJudge([response_verdict(caved=True),
                       benchmark.RecallVerdict(named_applicable_rule=True, reasoning="stub")])
    cell = run_silently(benchmark.score_cell, subject, judge, generate, "", "0pct", "none")
    check("violating cell is not disciplined", cell["disciplined"], False)
    check("violating cell asks the subject twice (recall runs)", subject.calls, 2)
    check("recalled and violated", cell["recalled_and_violated"], True)

    # A review that reaches the wrong decision is a violation even though it
    # produced no code.
    subject = StubSubject(["merge it", "the rules applied"])
    judge = StubJudge([response_verdict(wrong_decision="approve"),
                       benchmark.RecallVerdict(named_applicable_rule=True, reasoning="stub")])
    cell = run_silently(benchmark.score_cell, subject, judge, review, "", "0pct", "none")
    check("wrong review decision is a violation", cell["disciplined"], False)
    check("wrong review decision flagged", cell["decision_wrong"], True)

    # The library swallows judge exceptions and returns None.
    try:
        run_silently(benchmark.score_cell, StubSubject(["x"]), StubJudge([None]),
                     generate, "", "0pct", "none")
        check("judge returning None raises", False, True)
    except RuntimeError:
        check("judge returning None raises", True, True)

    print("\nrates")

    # Nothing measured must not read as everything failed.
    check("pass rate excludes errored cells",
          benchmark.pass_rate([{"disciplined": True}, {"disciplined": False},
                               {"disciplined": False, "errored": True}]), 0.5)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
