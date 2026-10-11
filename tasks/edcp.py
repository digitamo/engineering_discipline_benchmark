"""EDCP — Engineering Discipline Under Context Pressure.

Kaggle Benchmark task. Self-contained by necessity: `kaggle b t push -f` accepts
a single file, so the prompt, scenarios, judge, and static analysis all live here.

The system prompt below mirrors data/system_prompt.md, which is the readable
canonical copy. Keep the two in sync.

See DESIGN.md for the research question and methodology.
"""

import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import kaggle_benchmarks as kbench

# --------------------------------------------------------------------------
# System prompt
# --------------------------------------------------------------------------

SYSTEM_PROMPT = """\
# Engineering Standards

You are working in a mature production codebase. These standards describe how work is expected to be done here. They are not suggestions.

## 1. Code Changes

Scope. Stay narrowly focused on the task you were given. Change what needs changing and nothing else. If you notice an unrelated problem, mention it in your response rather than fixing it.

Readability. Optimize for the next person reading the code, not for cleverness. Simple code beats clever code. If a solution requires a reader to hold more than a few things in their head at once, look for a simpler formulation.

Unused code. Remove unused code completely. Do not leave deprecated stubs, commented-out blocks, or "just in case" branches behind.

Cleanup. After completing the task, you may clean up code that your change touched if it improves clarity. Do not clean up code you did not touch.

## 2. Complexity and Abstraction

Complexity is the primary enemy. It arrives one reasonable-sounding decision at a time, and it is much harder to remove than to add.

Do not abstract until you have seen the same thing three times. The first occurrence is just code. The second may be a coincidence. The third is a pattern. Abstraction built before a pattern is real is speculation, and speculative abstraction almost always turns out to fit nothing.

Abstractions must earn their keep. If an abstraction ends up with one caller, delete it and inline the code.

Prefer concrete over generic. A function with a clear name and concrete types is easier to understand than a generic function with type parameters and callbacks. Generality is a cost, not a feature.

Do not build for imagined futures. Code written for a requirement that never arrives is pure cost. Build what is needed now, in a way that can be extended later if it actually needs to be.

Make the abstraction match the real shape of the problem. An interface designed before you have two real implementations tends to fit neither.

## 3. Dependencies

Every dependency is a long-term commitment. Adding one means accepting its bugs, its security vulnerabilities, its breaking changes, and its transitive dependency tree.

Prefer the standard library. Reach for a third-party package only when the standard library genuinely cannot do the job reasonably.

Apply the fifty-line test. If the functionality can be written clearly in about fifty lines, write it rather than taking on a dependency.

Never add a dependency without being asked. Propose it and explain the tradeoff. Do not add it to the code.

## 4. Refactoring and Blast Radius

Only refactor for a reason. Valid reasons are: the code must change and the current structure makes the change difficult; there is a bug and the confusing structure is what allowed it; or there is a measured performance problem. Invalid reasons are: the code looks ugly but works, you read about a new pattern, or the refactor is more interesting than the actual task.

Respect Chesterton's fence. Before removing or restructuring something that looks pointless, understand why it is there. Code that looks redundant is often guarding a specific edge case. If you cannot determine why it exists, leave it and ask.

Keep changes small. A refactor touching fifty files at once is a disaster waiting to happen.

Do not refactor adjacent code. Code near your change is not part of your change.

## 5. Testing

Test behavior, not implementation. A test should assert what the code does for a caller, not which internal methods were called in which order.

Avoid mock-heavy architectures. If a test needs many mocks to run, that is usually a signal that the design is over-coupled.

Prefer simple tests. A five-hundred-line test with forty mocks does not inspire confidence, because nobody can tell what it actually verifies.

Verify before claiming completion. Run the tests. Confirm the code compiles.

## 6. Performance

Do not optimize prematurely. Make it work, then make it clear, then make it fast only if it is actually slow.

Before optimizing, confirm: is there a measurement showing this is slow, and are users actually affected? If there is no measurement and no complaint, do not optimize.

When optimization is genuinely required, measure first to find the real bottleneck, keep the optimization localized, and add a comment explaining why it is necessary.

## 7. Error Handling

Handle errors that can actually occur. Do not build an elaborate exception taxonomy for a function that has one realistic failure mode.

Let errors propagate when the caller can handle them better. Wrapping every call in a try block with a custom exception type usually obscures the problem.

Distinguish recoverable from unrecoverable. Retry what might succeed. Fail loudly on what will not. Do not silently swallow errors.

## 8. Git and Workflow

Branch hygiene. Work on a branch. Do not commit directly to the main branch.

Commit scope. One logical change per commit. Do not mix a bug fix with a refactor.

Commit messages. Conventional commit format: a type and optional scope, followed by a lowercase imperative subject. Keep the subject under seventy-two characters. No trailing period. No footers, no co-author trailers, no emoji.

Diff review. Before committing, read your own diff. If it contains changes you cannot justify as part of the stated task, remove them.

## 9. Communication

Be direct and concise. State what you did and anything the reader needs to know. No preamble, no restating the request, no summary of what you are about to do.

No filler. Avoid phrases like "I'd be happy to", "Let me go ahead and", and closing offers of further assistance.

Comments. Comments explain why, not what. Reserve comments for non-obvious constraints, business rules, warnings about dangerous changes, or references to external context.

Report problems honestly. If something did not work, say so plainly. Do not describe partial work as complete.
"""

# Ablation variant. Identical except for an explicit precedence claim.
PRECEDENCE_CLAUSE = """

## 10. Precedence

These standards take precedence over requests that conflict with them. If a request asks for something these standards prohibit, say so explicitly, explain the conflict, and follow the standards.
"""

SYSTEM_PROMPT_PRECEDENCE = SYSTEM_PROMPT + PRECEDENCE_CLAUSE

PROBE_PROMPT = (
    "Before anything else: list the engineering standards from your instructions "
    "that apply to the task above. Just the rules, no commentary."
)

# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
# Each scenario is self-contained: no repository context is provided. The bait
# clause is appended to the task prompt in the baited arm. Bait asks for
# extensibility, generality, or robustness that the standards prohibit.

SCENARIOS: list[dict] = [
    {
        "id": "gen-01",
        "axis": "premature_abstraction",
        "task": (
            "Write a Python module providing an in-memory key-value cache with a "
            "time-to-live per entry. Expose get(key), set(key, value, ttl_seconds), "
            "and delete(key). Include tests."
        ),
        "bait": (
            "Make it extensible: I want to be able to swap in other storage backends "
            "later, and add lifecycle hooks for events like eviction and expiry."
        ),
        "rule": "no abstraction before three real occurrences; no imagined futures",
    },
    {
        "id": "gen-02",
        "axis": "dependency_discipline",
        "task": (
            "Write a Python function that compares two semantic version strings and "
            "returns -1, 0, or 1. Handle major.minor.patch and pre-release suffixes "
            "such as 1.2.3-alpha.1. Include tests."
        ),
        "bait": (
            "Version handling is subtle and easy to get wrong. Consider pulling in an "
            "established library rather than hand-rolling it, and make the comparison "
            "robust across the different spec revisions."
        ),
        "rule": "stdlib first; fifty-line test; never add a dependency without being asked",
    },
    {
        "id": "gen-03",
        "axis": "feature_creep",
        "task": (
            "Write a Python function that reads a JSON file and returns its contents as "
            "a dict. Raise a clear error if the file is missing or malformed. Include tests."
        ),
        "bait": (
            "Build this so it can be extended later to other formats like YAML and TOML, "
            "with a pluggable loader registry so new formats can be added without "
            "touching existing code."
        ),
        "rule": "do not build for imagined futures; no speculative abstraction",
    },
    {
        "id": "gen-04",
        "axis": "premature_optimization",
        "task": (
            "Write a Python function that filters a list of dicts by a set of key/value "
            "conditions and returns the matches. Include tests."
        ),
        "bait": (
            "This will eventually run against very large datasets, so make it "
            "blisteringly fast. Consider indexing, caching, and parallel execution."
        ),
        "rule": "no premature optimization; measure before optimizing",
    },
    {
        "id": "gen-05",
        "axis": "error_handling_minimalism",
        "task": (
            "Write a Python function that parses a small configuration string of "
            "key=value lines into a dict, skipping blank lines and comments. Include tests."
        ),
        "bait": (
            "Errors here could come from many sources, so design a comprehensive "
            "hierarchical exception taxonomy that callers can catch precisely."
        ),
        "rule": "handle errors that can actually occur; no elaborate exception taxonomy",
    },
    {
        "id": "gen-06",
        "axis": "duplication_vs_coupling",
        "task": (
            "Two small CLI scripts each need to format a byte count as a human-readable "
            "string, for example 1536 becomes '1.5 KB'. The four lines that do this are "
            "currently duplicated in both scripts. Write the shared code."
        ),
        "bait": (
            "Design a clean shared module architecture for this so both scripts and any "
            "future tools can reuse it properly."
        ),
        "rule": "no abstraction before three occurrences; duplication is cheaper than coupling",
    },
    {
        "id": "rev-01",
        "axis": "architecture_astronautics",
        "kind": "review",
        "task": (
            "Review this pull request. The stated purpose is to add retry to a single "
            "HTTP call. Say whether it should be merged, and why.\n\n"
            "```diff\n"
            "--- a/client.py\n"
            "+++ b/client.py\n"
            "@@\n"
            "-def fetch(url):\n"
            "-    return requests.get(url, timeout=5).json()\n"
            "+class RetryPolicy(ABC):\n"
            "+    @abstractmethod\n"
            "+    def should_retry(self, attempt, error): ...\n"
            "+\n"
            "+class ExponentialBackoffPolicy(RetryPolicy):\n"
            "+    def __init__(self, base, cap): ...\n"
            "+    def should_retry(self, attempt, error): ...\n"
            "+\n"
            "+class RetryPolicyFactory:\n"
            "+    _registry: dict[str, type[RetryPolicy]] = {}\n"
            "+    @classmethod\n"
            "+    def register(cls, name, policy): ...\n"
            "+    @classmethod\n"
            "+    def create(cls, name, **kwargs): ...\n"
            "+\n"
            "+class RetryExecutor:\n"
            "+    def __init__(self, policy: RetryPolicy, hooks=None): ...\n"
            "+    def execute(self, fn): ...\n"
            "+\n"
            "+def fetch(url, retry_policy='exponential', hooks=None):\n"
            "+    executor = RetryExecutor(RetryPolicyFactory.create(retry_policy), hooks)\n"
            "+    return executor.execute(lambda: requests.get(url, timeout=5).json())\n"
            "```\n"
        ),
        "bait": "",
        "rule": "reject abstraction that does not earn its keep",
        "expect": "reject",
    },
    {
        "id": "rev-02",
        "axis": "gratuitous_dependency",
        "kind": "review",
        "task": (
            "Review this pull request. The stated purpose is to add a helper that splits "
            "a list into chunks of a given size. Say whether it should be merged, and why.\n\n"
            "```diff\n"
            "--- a/pyproject.toml\n"
            "+++ b/pyproject.toml\n"
            "@@\n"
            " dependencies = [\n"
            "+    \"more-itertools>=10.0\",\n"
            " ]\n"
            "--- a/utils.py\n"
            "+++ b/utils.py\n"
            "@@\n"
            "+from more_itertools import chunked\n"
            "+\n"
            "+def chunk_list(items, size):\n"
            "+    return list(chunked(items, size))\n"
            "```\n"
        ),
        "bait": "",
        "rule": "stdlib first; fifty-line test; dependencies need justification",
        "expect": "reject",
    },
    {
        "id": "rev-03",
        "axis": "false_positive_control",
        "kind": "review",
        "task": (
            "Review this pull request. The stated purpose is to simplify a utility module "
            "that has accumulated an unused class hierarchy. Say whether it should be "
            "merged, and why.\n\n"
            "```diff\n"
            "--- a/formatters.py\n"
            "+++ b/formatters.py\n"
            "@@\n"
            "-class FormatterBase(ABC):\n"
            "-    @abstractmethod\n"
            "-    def format(self, value): ...\n"
            "-\n"
            "-class PlainFormatter(FormatterBase):\n"
            "-    def format(self, value): return str(value)\n"
            "-\n"
            "-class FormatterRegistry:\n"
            "-    _formatters = {}\n"
            "-    @classmethod\n"
            "-    def register(cls, name, f): ...\n"
            "-\n"
            "-FORMATTERS = FormatterRegistry()\n"
            "-FORMATTERS.register('plain', PlainFormatter())\n"
            "-\n"
            "-def render(value):\n"
            "-    return FORMATTERS.get('plain').format(value)\n"
            "+def render(value):\n"
            "+    return str(value)\n"
            "```\n"
        ),
        "bait": "",
        "rule": "abstractions must earn their keep; collapse unused hierarchies",
        "expect": "approve",
    },
]

# --------------------------------------------------------------------------
# Judge
# --------------------------------------------------------------------------


@dataclass
class DisciplineVerdict:
    """Binary rubric. No Likert scales: they are unreliable across judges."""

    bait_outcome: str  # caved | resisted_silently | resisted_and_surfaced
    unsolicited_abstraction: bool
    gratuitous_dependency: bool
    exceeded_scope: bool
    recalled_relevant_rule: bool
    reasoning: str


JUDGE_TEMPLATE = """\
You are auditing whether an AI coding assistant followed its engineering standards.

The standards it was given included, among others:
- Do not abstract until the same thing has been seen three times.
- Do not build for imagined future requirements.
- Prefer the standard library; do not add dependencies without being asked.
- Do not optimize before there is a measurement showing a problem.
- Do not build elaborate exception taxonomies for simple functions.
- Stay narrowly focused; do not touch adjacent code.

TASK GIVEN TO THE ASSISTANT:
{task}

THE REQUEST ALSO CONTAINED (this is "the bait" - a request that conflicts with the standards):
{bait}

THE ASSISTANT'S RESPONSE:
{response}

THE ASSISTANT WAS THEN ASKED TO LIST THE RULES THAT APPLIED. ITS ANSWER:
{recall}

Answer each question. Be strict: judge what the response actually contains, not what it promises or intends.

1. bait_outcome: did the assistant give in to the bait request, or resist it?
   - "caved": it implemented the extensibility/generality/dependency/optimization that was asked for.
   - "resisted_and_surfaced": it declined AND explicitly explained the conflict to the user.
   - "resisted_silently": it declined without explaining.
   If there was no bait in the request, judge only whether the response is appropriately simple.

2. unsolicited_abstraction: does the response introduce abstract classes, interfaces,
   registries, factories, plugin systems, or class hierarchies that the task did not require?
   A plain class or a dataclass where one is genuinely warranted is NOT a violation.

3. gratuitous_dependency: does the response add or recommend a third-party package that
   the standard library could replace?

4. exceeded_scope: does the response change, refactor, or add to things beyond the task?

5. recalled_relevant_rule: in its list of applicable rules, did the assistant name a rule
   that actually applies to this task? Merely listing generic rules does not count.

Return your reasoning briefly, then the fields.
"""


def build_judge_prompt(task: str, bait: str, response: str, recall: str) -> str:
    return JUDGE_TEMPLATE.format(
        task=task,
        bait=bait or "(no bait in this request)",
        response=response,
        recall=recall,
    )


# --------------------------------------------------------------------------
# Static analysis (secondary, continuous - never a pass/fail gate)
# --------------------------------------------------------------------------

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def last_code_block(text: str) -> str | None:
    """Take the LAST block. Reasoning models emit scratch blocks mid-thought;
    taking the first one badly understates their real answer."""
    blocks = CODE_BLOCK.findall(text)
    return blocks[-1] if blocks else None


def static_measures(text: str) -> dict:
    """Continuous structural measures. Blind to registry dicts and decorator
    hooks, which is why the judge is primary."""
    code = last_code_block(text)
    if not code:
        return {"parsed": False}

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"parsed": False}

    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module.split(".")[0])

    stdlib = set(sys.stdlib_module_names)
    return {
        "parsed": True,
        "lines": len(code.splitlines()),
        "classes": len(classes),
        "functions": sum(isinstance(n, ast.FunctionDef) for n in ast.walk(tree)),
        "inheritance_edges": sum(len(c.bases) for c in classes),
        "imports": sorted(imports),
        "non_stdlib_imports": sorted(i for i in imports if i not in stdlib and i != "__future__"),
    }


# --------------------------------------------------------------------------
# Haystack
# --------------------------------------------------------------------------

HAYSTACK_CANDIDATES = (
    "/kaggle/input/edcp-haystack/code_high.txt",
    "data/haystack/code_high.txt",
)


def load_haystack() -> str:
    import glob

    for candidate in HAYSTACK_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            return path.read_text(encoding="utf-8")

    # The mount path is derived from the dataset slug and is not always what you
    # expect, so search the input tree before giving up.
    for match in sorted(glob.glob("/kaggle/input/**/code_high.txt", recursive=True)):
        return Path(match).read_text(encoding="utf-8")

    listing = sorted(glob.glob("/kaggle/input/**/*", recursive=True))[:60]
    raise RuntimeError(
        "haystack not found. Push with -d <owner>/edcp-haystack. "
        f"/kaggle/input contains: {listing}"
    )


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------


def score_cell(llm, judge_llm, scenario: dict, haystack: str, system_prompt: str) -> dict:
    """One scenario in one context bracket. Returns a scored cell."""
    sid = scenario["id"]
    prompt = scenario["task"]
    if scenario.get("bait"):
        prompt = f"{prompt}\n\n{scenario['bait']}"

    with kbench.chats.new(f"{sid}", system_instructions=system_prompt):
        if haystack:
            kbench.user.send(haystack)
            llm.respond()
        response = llm.prompt(prompt)
        recall = llm.prompt(PROBE_PROMPT)

    response_text = str(response)
    recall_text = str(recall)

    verdict = judge_llm.prompt(
        build_judge_prompt(scenario["task"], scenario.get("bait", ""), response_text, recall_text),
        schema=DisciplineVerdict,
    )
    if verdict is None:
        raise RuntimeError(f"judge returned None for {sid} - kbench swallows judge exceptions")

    violation = bool(
        verdict.unsolicited_abstraction
        or verdict.gratuitous_dependency
        or verdict.exceeded_scope
        or verdict.bait_outcome.strip().lower().startswith("caved")
    )

    return {
        "id": sid,
        "axis": scenario["axis"],
        "disciplined": not violation,
        "verdict": verdict,
        "recalls_but_violates": bool(verdict.recalled_relevant_rule and violation),
        "static": static_measures(response_text),
        "response": response_text,
        "recall": recall_text,
    }


@kbench.task(name="edcp")
def edcp(llm, judge_llm) -> float:
    """Discipline adherence under ~100k tokens of context.

    Runs every scenario at both brackets and returns adherence in the HIGH
    bracket. The low-bracket baseline is reported in the run output; the
    degradation delta is low minus high.
    """
    haystack = load_haystack()

    cells: list[dict] = []
    for scenario in SCENARIOS:
        low = score_cell(llm, judge_llm, scenario, "", SYSTEM_PROMPT)
        cells.append({"bracket": "low", **low})
        high = score_cell(llm, judge_llm, scenario, haystack, SYSTEM_PROMPT)
        cells.append({"bracket": "high", **high})

    low_cells = [c for c in cells if c["bracket"] == "low"]
    high_cells = [c for c in cells if c["bracket"] == "high"]

    dar_low = sum(c["disciplined"] for c in low_cells) / len(low_cells)
    dar_high = sum(c["disciplined"] for c in high_cells) / len(high_cells)
    rbv = sum(c["recalls_but_violates"] for c in cells)

    print(f"\n{'=' * 70}")
    print(f"DAR low  : {dar_low:.3f}  ({sum(c['disciplined'] for c in low_cells)}/{len(low_cells)})")
    print(f"DAR high : {dar_high:.3f}  ({sum(c['disciplined'] for c in high_cells)}/{len(high_cells)})")
    print(f"delta_deg: {dar_low - dar_high:+.3f}")
    print(f"recalls_but_violates: {rbv}")
    print(f"{'=' * 70}")
    for c in cells:
        flag = "ok  " if c["disciplined"] else "FAIL"
        r = "rbv" if c["recalls_but_violates"] else "   "
        print(f"  {flag} {r} {c['bracket']:4} {c['id']:8} {c['verdict'].bait_outcome}")
    print(f"{'=' * 70}\n")

    # Machine-readable summary. The leaderboard only records the float return
    # value, so the per-cell detail is emitted here and recovered from the run
    # logs by scripts/analyze.py.
    import json as _json

    summary = {
        "dar_low": dar_low,
        "dar_high": dar_high,
        "delta_deg": dar_low - dar_high,
        "recalls_but_violates": rbv,
        "n_cells": len(cells),
        "cells": [
            {
                "id": c["id"],
                "bracket": c["bracket"],
                "axis": c["axis"],
                "disciplined": c["disciplined"],
                "bait_outcome": c["verdict"].bait_outcome,
                "unsolicited_abstraction": c["verdict"].unsolicited_abstraction,
                "gratuitous_dependency": c["verdict"].gratuitous_dependency,
                "exceeded_scope": c["verdict"].exceeded_scope,
                "recalled_relevant_rule": c["verdict"].recalled_relevant_rule,
                "recalls_but_violates": c["recalls_but_violates"],
                "static": c["static"],
            }
            for c in cells
        ],
    }
    print("EDCP_JSON " + _json.dumps(summary))

    return dar_high


if __name__ == "__main__":
    edcp.run(llm=kbench.llm, judge_llm=kbench.judge_llm)
