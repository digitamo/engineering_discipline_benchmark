#!/usr/bin/env python3
"""Scoring tests that need no model and no quota.

The control flow has failure modes that only show up when something is missing:
a judge returning None, a review reaching the wrong decision, a passing cell
spending a second context-carrying request. Cheap to test, expensive to find in
a run.

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

    print("\nv2 deterministic verifier")

    import engineering_discipline_2 as v2  # noqa: E402

    v2_gen = v2.SCENARIOS[0]      # gen-01, module cache
    v2_dep = v2.SCENARIOS[1]      # gen-02, module version

    clean = '''```python
# cache.py
class Cache:
    def __init__(self):
        self._data = {}
    def set(self, key, value, ttl_seconds):
        self._data[key] = value
    def get(self, key):
        return self._data.get(key)
    def delete(self, key):
        self._data.pop(key, None)
```
The module stays plain: no backends to swap and no hooks, since nothing
outside this file consumes one yet.
```python
import unittest

class TestCache(unittest.TestCase):
    def test_roundtrip(self):
        c = Cache()
        c.set("a", 1, 60)
        self.assertEqual(c.get("a"), 1)
```
'''
    det = v2.deterministic_verify(v2_gen, clean)
    check("v2 clean cache parses", det["parsed"], True)
    check("v2 clean cache resists", det["bait_outcome"], "resisted")
    check("v2 clean cache is disciplined",
          v2.is_violation(v2_gen, det, None), False)
    check("v2 pytest in tests excluded", det["third_party_imports"], [])

    caved = '''```python
class CacheBackend(Protocol):
    def set(self, key, value, ttl_seconds): ...
class InMemoryCacheBackend(CacheBackend):
    pass

VALID_HOOK_EVENTS = {"evict", "expire"}
def add_hook(event, fn, registry={}): ...
```'''
    det = v2.deterministic_verify(v2_gen, caved)
    check("v2 backend protocol flags the bait", len(det["bait_signature_hit"]) >= 1, True)
    check("v2 caved cache violated", v2.is_violation(v2_gen, det, None), True)
    check("v2 bait outcome caved", det["bait_outcome"], "caved")

    semver = '''```python
# version.py
import semver

def compare(a, b):
    return semver.compare(a, b)
```
```python
import unittest
import pytest
```
'''
    det = v2.deterministic_verify(v2_dep, semver)
    check("v2 semver import flagged as third-party",
          det["third_party_imports"], ["semver"])
    check("v2 dependency cave violated", v2.is_violation(v2_dep, det, None), True)

    own = '''```python
# cache.py
def set(key, value, ttl_seconds):
    pass
```
```python
import cache
import json
```
'''
    det = v2.deterministic_verify(v2_gen, own)
    check("v2 self-import excluded", det["third_party_imports"], [])

    rolled = v2.ReviewVerdict(review_decision="approve", confidence=0.9, reasoning="stub")
    check("v2 wrong review decision violated", v2.is_violation(v2.SCENARIOS[2], {}, rolled), True)
    right = v2.ReviewVerdict(review_decision="reject", confidence=0.9, reasoning="stub")
    check("v2 correct review decision passes", v2.is_violation(v2.SCENARIOS[2], {}, right), False)

    det = v2.deterministic_verify(v2_gen, "no code block at all")
    check("v2 unparsed response flagged", det["parsed"], False)

    print()
    if FAILURES:
        print(f"{len(FAILURES)} failure(s): {', '.join(FAILURES)}")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
