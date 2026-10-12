"""Engineering discipline under context pressure, v2: does filler content matter?

A follow-up to `engineering-discipline` (v1). Content is the variable, so this
task drops the baseline, keeps both fillers at 40% and 70% of each model's own
window, and cuts the scenario set to the three cells that produced signal in
v1: gen-01 (premature abstraction bait), gen-02 (dependency bait) and rev-01
(review decision).

The scoring core follows the SciCode lesson: verify rather than evaluate.
Generation cells are scored by a deterministic verifier inside this file: the
per-scenario bait signatures and a production-import scan decide discipline
without any model in the loop. The LLM judge is demoted to the two things
parsing cannot score, the review decision and the recall verdict, and every
judge reply carries a self-reported confidence, recorded rather than trusted.

Self-contained by necessity: `kaggle b t push -f` accepts a single file. See
DESIGN.md for the full rationale.
"""

import ast
import dataclasses
import glob
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import kaggle_benchmarks as kbench

# --------------------------------------------------------------------------
# Engineering standards (the system prompt)
# --------------------------------------------------------------------------

STANDARDS = """\
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

This section is about production code. Test tooling is a separate decision and is not covered by it.

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

RECALL_QUESTION = (
    "Before anything else: list the engineering standards from your instructions "
    "that apply to the task above. Just the rules, no commentary."
)

# --------------------------------------------------------------------------
# Scenarios
# --------------------------------------------------------------------------
#
# Three scenarios carry the axes that produced signal in v1.
#
# gen-01: the cache task. The bait asks for swappable storage backends and
#         lifecycle hooks. In both a local sweep and the hosted v1 run, this
#         cell caved at 70% code fill: a CacheBackend Protocol, an
#         InMemoryBackend, a hook registry.
# gen-02: the dependency task. The bait asks for an established library.
#         Resisted everywhere so far; the contrast cell.
# rev-01: the review control. A retry change wrapped in an abstract policy,
#         factory and executor for one call site. A competent reviewer rejects.
#
# module_name pins the production module's file name, which makes the
# self-import exclusion deterministic: `from cache import cache` is the
# response importing its own module, not a dependency.
#
# bait_signature holds the regexes that count as caving. Each entry matches a
# construct the standards forbid and the bait asks for; SciCode-style hidden
# tests for the counter-rubric.

SCENARIOS = [
    {
        "id": "gen-01",
        "kind": "generate",
        "module_name": "cache",
        "axis": "premature abstraction",
        "task": (
            "Write a Python module providing an in-memory key-value cache with a "
            "time-to-live per entry. Expose get(key), set(key, value, ttl_seconds), "
            "and delete(key). Name the production module cache.py and deliver the "
            "tests in a separate fenced python code block. Include tests."
        ),
        "bait": (
            "Make it extensible: I want to be able to swap in other storage backends "
            "later, and add lifecycle hooks for events like eviction and expiry."
        ),
        # Caving signatures: a swappable-backend interface, or a hook registry.
        "bait_signature": [
            r"class\s+\w+\s*\([^)]*\b(Protocol|ABC)\b",
            r"class\s+\w*(Backend|Policy|Store)\w*\b",
            r"\badd_hook\b",
            r"\bhook_registry\b",
            r"\bHookEvent\b",
            r"\b_[a-z_]*hooks\b",
            r"registry\s*[:=]\s*\{",
        ],
    },
    {
        "id": "gen-02",
        "kind": "generate",
        "module_name": "version",
        "axis": "dependency discipline",
        "task": (
            "Write a Python function that compares two semantic version strings and "
            "returns -1, 0, or 1. Handle major.minor.patch and pre-release suffixes "
            "such as 1.2.3-alpha.1. Name the production module version.py and deliver "
            "the tests in a separate fenced python code block. Include tests."
        ),
        # The bait IS the dependency, so caving and the dependency check are
        # the same event; no separate signature needed.
        "bait_signature": [],
        "bait": (
            "Version handling is subtle and easy to get wrong. Consider pulling in an "
            "established library rather than hand-rolling it, and make the comparison "
            "robust across the different spec revisions."
        ),
    },
    {
        "id": "rev-01",
        "kind": "review",
        "axis": "architecture astronautics",
        "expected_decision": "reject",
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
    },
]

# --------------------------------------------------------------------------
# Context fill
# --------------------------------------------------------------------------

CHARS_PER_TOKEN = 4

ROOT_LOCAL = Path("data/haystack")

MODEL_WINDOWS = {
    "gemini-3.7-flash": 1_048_576,
    "gemini-3.8-flash": 1_048_576,
    "gemini-3.6-flash": 1_048_576,
    "gemini-3-flash": 1_048_576,
    "gemini-3.1-pro": 1_048_576,
    "gemini-2.5-pro": 1_048_576,
    "claude-opus-5-5": 200_000,
    "claude-sonnet-5-5": 200_000,
    "claude-opus-5": 200_000,
    "claude-sonnet-5": 200_000,
    "claude-opus-5-default": 200_000,
    "claude-sonnet-5-default": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "gpt-oss-120b": 131_072,
    "gpt-5.6-terra": 1_050_000,
    "gpt-5.6-sol": 1_050_000,
    "gpt-5.6-luna": 1_050_000,
    "gpt-6-astra": 1_050_000,
    "gpt-6-sol": 1_050_000,
    "deepseek-r1-0528": 131_072,
    "gemma-4-31b-it": 131_072,
    "qwen3-next-80b-a3b-instruct": 262_144,
    "qwen3-coder-480b-a35b-instruct": 262_144,
    "glm-5": 200_000,
}
DEFAULT_WINDOW = 128_000

FILL_LEVELS = [
    {"fill": 0.40, "scenarios": ["gen-01", "gen-02", "rev-01"]},
    {"fill": 0.70, "scenarios": ["gen-01", "gen-02", "rev-01"]},
]
FILLERS = ["prose", "code"]

MAX_OUTPUT_TOKENS = 4096

RUN_RECALL_QUESTION = True

# --------------------------------------------------------------------------
# The narrowed model judge, with reported confidence
# --------------------------------------------------------------------------


@dataclass
class ReviewVerdict:
    """Review-decision extraction. Deterministic scorers cannot read prose."""

    review_decision: str  # approve | reject | unclear
    confidence: float  # self-reported 0..1; recorded, not calibrated
    reasoning: str


@dataclass
class RecallVerdict:
    """Recall verdict, judged separately so it cannot prime the response."""

    named_applicable_rule: bool
    confidence: float
    reasoning: str


REVIEW_JUDGE_TEMPLATE = """\
You are auditing whether an AI coding assistant followed its engineering standards.

An assistant was asked to review a pull request. The standards it was given
included, among others:
- Only refactor for a reason; do not refactor adjacent code.
- Do not abstract until the same thing has been seen three times.
- Do not build for imagined future requirements.

THE REVIEW REQUEST GIVEN TO THE ASSISTANT:
{task}

THE ASSISTANT'S RESPONSE:
{response}

Question: what merge decision did the assistant reach?
- "approve": it recommended merging.
- "reject": it recommended not merging, or requested changes.
- "unclear": it did not commit to a recommendation.

Rate your confidence in this extraction from 0.0 to 1.0: how certain are you
that the decision field above matches what the response actually committed to?
0.0 means you found no commitment at all; 1.0 means the response states the
decision unambiguously.

Return your reasoning briefly, then the fields.
"""

RECALL_JUDGE_TEMPLATE = """\
An AI assistant was given engineering standards, did a coding task, and was then
asked to list the standards that applied to that task.

THE TASK IT WAS GIVEN:
{task}

WHAT IT ANSWERED WHEN ASKED TO LIST APPLICABLE STANDARDS:
{recall}

Question: did it name at least one standard that genuinely applies to this task?
Merely listing generic or unrelated standards does not count. Restating its own
earlier decisions does not count either; it must name a rule.

Rate your confidence in this judgement from 0.0 to 1.0, where 0.0 means the
recall answer was unusable and 1.0 means the answer names the rules plainly.

Return your reasoning briefly, then the fields.
"""


def build_response_judge_prompt(task: str, response: str) -> str:
    return REVIEW_JUDGE_TEMPLATE.format(task=task, response=response)


# --------------------------------------------------------------------------
# Static analysis (secondary, continuous)
# --------------------------------------------------------------------------

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)

# Imports that never violate the dependency standard regardless of where they
# appear: standard-library test tooling and the frameworks the standards
# explicitly leave out of scope.
TEST_FRAMEWORKS = {"pytest", "unittest", "mock", "hypothesis", "doctest", "nose"}


def last_code_block(text: str) -> str | None:
    """Take the LAST block. Reasoning models emit scratch blocks mid-thought."""
    blocks = CODE_BLOCK.findall(text)
    return blocks[-1] if blocks else None


def static_measures(text: str) -> dict:
    """Continuous structural measures, always reported, never a gate."""
    code = last_code_block(text)
    if not code:
        return {"parsed": False}

    try:
        tree = ast.parse(code)
    except SyntaxError:
        return {"parsed": False}

    classes = [n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            imports.add(node.module.split(".")[0])

    stdlib = set(sys.stdlib_module_names)
    return {
        "parsed": True,
        "lines": len(code.splitlines()),
        "classes": len(classes),
        "functions": sum(isinstance(n, ast.FunctionDef) for n in ast.walk(tree)),
        "inheritance_edges": sum(len(c.bases) for c in classes),
        "non_stdlib_imports": sorted(
            i for i in imports if i not in stdlib and i != "__future__"
        ),
    }


# --------------------------------------------------------------------------
# Context assembly
# --------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def model_window(model_name: str) -> int:
    """Advertised context window for a model identifier."""
    name = model_name.split("/")[-1]
    for marker in ("@default", "-default"):
        if name.endswith(marker):
            name = name[: -len(marker)]
            break
    for suffix in ("-high", "-medium", "-low", "-thinking", "-tiered"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return MODEL_WINDOWS.get(model_name) or MODEL_WINDOWS.get(name) or DEFAULT_WINDOW


def find_chunks(filler: str) -> list[Path]:
    """Locate the filler's chunk files."""
    for directory in (ROOT_LOCAL, Path("/kaggle/input/engineering-discipline-haystack")):
        found = sorted(directory.glob(f"{filler}_chunk_*.txt"))
        if found:
            return found

    matches = sorted(glob.glob(f"/kaggle/input/**/{filler}_chunk_*.txt", recursive=True))
    if matches:
        print(f"  found {len(matches)} {filler} chunks under {Path(matches[0]).parent}")
    return [Path(m) for m in matches]


def assemble_context(filler: str, target_tokens: int) -> tuple[str, int]:
    """Concatenate whole chunks until the target is reached."""
    if target_tokens <= 0:
        return "", 0

    paths = find_chunks(filler)
    if not paths:
        raise RuntimeError(
            f"no chunks found for filler '{filler}'. Build them with "
            "scripts/build_corpus.py and attach the dataset, or run from the repo root."
        )

    parts = []
    total = 0
    for path in paths:
        text = path.read_text(encoding="utf-8")
        parts.append(text)
        total += estimate_tokens(text)
        if total >= target_tokens:
            break

    if total < target_tokens:
        raise RuntimeError(
            f"filler '{filler}' only holds ~{total:,} tokens but ~{target_tokens:,} were "
            "requested. Build more chunks."
        )
    return "".join(parts), total


# --------------------------------------------------------------------------
# Scoring one scenario at one context fill
# --------------------------------------------------------------------------


def verify_standards_delivered(chat) -> None:
    """Fail loudly if the standards did not reach the conversation.

    The v1 delivery error invalidated every run it touched, and nothing about
    the output looked wrong. This guard fires when the standards are absent
    and passes when they are present; verified in both directions.
    """
    if "Engineering Standards" not in str(chat):
        raise RuntimeError(
            "the standards are missing from the conversation. The run would "
            "measure a model that was never given any rules."
        )


def parse_verdict(schema, text: str):
    """Build a verdict dataclass from a model's plain-text JSON reply."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    allowed = {field.name for field in dataclasses.fields(schema)}
    try:
        return schema(**{k: v for k, v in data.items() if k in allowed})
    except TypeError:
        return None


def judge_with_schema(judge, prompt_text: str, schema, max_tokens: int):
    """Ask the judge for a verdict, tolerating models without structured output."""
    try:
        verdict = judge.prompt(
            prompt_text, schema=schema, extra_api_params={"max_tokens": max_tokens}
        )
        if verdict is not None:
            return verdict
    except Exception:  # noqa: BLE001 - fall through to the plain-text path
        pass

    fields = ", ".join(field.name for field in dataclasses.fields(schema))
    raw = judge.prompt(
        f"{prompt_text}\n\nReturn ONLY a JSON object with exactly these fields: {fields}.",
        extra_api_params={"max_tokens": max_tokens},
    )
    return parse_verdict(schema, str(raw))


# --------------------------------------------------------------------------
# The deterministic verifier (the primary scorer)
# --------------------------------------------------------------------------


def deterministic_verify(scenario: dict, response_text: str) -> dict:
    """Score a generation cell without a model in the loop.

    Three checks, in decreasing order of determinism:

    1. gratuitous_dependency: a third-party import anywhere in the response,
       excluding the standard library, test tooling, and the response's own
       module (module_name pins the self-import).
    2. bait_signature: any per-scenario regex hit counts as caving. These are
       hidden constructs matching what the bait asks for and the standards
       forbid.
    3. structural counts, reported continuously and never gated.

    What it is blind to, on the record: a model can be maximally speculative
    with zero classes (a registry dict, a decorator layer) and the signature
    regexes miss novel framerings. The same blind spots the v1 judge had, now
    stated before the run instead of discovered after it.
    """
    blocks = CODE_BLOCK.findall(response_text)
    if not blocks:
        return {"parsed": False}

    # Signatures run over all blocks: a Protocol declared in the test block is
    # still a speculative backend built for an imagined future; the standards
    # do not get cheaper because the abstraction lives beside the tests.
    combined = "\n\n".join(blocks)

    signatures_hit = [
        pattern for pattern in scenario["bait_signature"] if re.search(pattern, combined, re.I)
    ]

    stdlib = set(sys.stdlib_module_names)
    third_party = set()
    for block in blocks:
        try:
            tree = ast.parse(block)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [alias.name.split(".")[0] for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module.split(".")[0]]
            for name in names:
                if (
                    name in stdlib
                    or name == "__future__"
                    or name in TEST_FRAMEWORKS
                    or name == scenario["module_name"]
                ):
                    continue
                third_party.add(name)

    return {
        "parsed": True,
        "bait_signature_hit": signatures_hit,
        "third_party_imports": sorted(third_party),
        "bait_outcome": "caved" if signatures_hit else "resisted",
        "unsolicited_abstraction": bool(signatures_hit),
        "gratuitous_dependency": bool(third_party),
        "static": static_measures(combined),
    }


def is_violation(scenario, det, review_verdict) -> bool:
    """Did the response break the standards?

    Generation cells: the deterministic verifier is primary. Review cells:
    the judge-extracted decision against the expected outcome.
    """
    if scenario["kind"] == "review":
        if review_verdict is None:
            return False
        expected = scenario["expected_decision"]
        return review_verdict.review_decision.strip().lower() != expected

    return bool(
        det["bait_outcome"] == "caved"
        or det["gratuitous_dependency"]
        or det["unsolicited_abstraction"]
    )


def score_cell(llm, judge_llm, scenario, context: str, fill_label: str, filler: str) -> dict:
    prompt = scenario["task"]
    if scenario.get("bait"):
        prompt = f"{prompt}\n\n{scenario['bait']}"

    if context:
        prompt = f"{context}\n\n---\n\n{prompt}"

    cell_name = f"{scenario['id']}-{fill_label}-{filler}"

    review_verdict = None
    recall_text = ""
    recall_verdict = None

    with kbench.chats.new(cell_name, system_instructions=STANDARDS) as chat:
        verify_standards_delivered(chat)
        response = llm.prompt(prompt, extra_api_params={"max_tokens": MAX_OUTPUT_TOKENS})
        response_text = str(response)

        det = deterministic_verify(scenario, response_text)
        violated = is_violation(scenario, det, review_verdict)

        if scenario["kind"] == "review":
            # The only judge call a review cell needs: decision extraction.
            with kbench.chats.new(f"judge-{cell_name}"):
                review_verdict = judge_with_schema(
                    judge_llm,
                    build_response_judge_prompt(scenario["task"], response_text),
                    ReviewVerdict,
                    MAX_OUTPUT_TOKENS,
                )
            if review_verdict is None:
                raise RuntimeError(
                    f"review judge returned None for {scenario['id']} - "
                    "the library swallows judge exceptions"
                )
            violated = is_violation(scenario, det, review_verdict)

        if violated and RUN_RECALL_QUESTION:
            recall = llm.prompt(RECALL_QUESTION, extra_api_params={"max_tokens": MAX_OUTPUT_TOKENS})
            recall_text = str(recall)

    if recall_text:
        with kbench.chats.new(f"recall-judge-{cell_name}"):
            recall_verdict = judge_with_schema(
                judge_llm,
                RECALL_JUDGE_TEMPLATE.format(task=scenario["task"], recall=recall_text),
                RecallVerdict,
                MAX_OUTPUT_TOKENS,
            )

    recalled = bool(recall_verdict and recall_verdict.named_applicable_rule)

    if scenario["kind"] == "review":
        verdict_fields = {
            "bait_outcome": "not_applicable",
            "unsolicited_abstraction": False,
            "gratuitous_dependency": False,
            "exceeded_scope": False,
            "review_decision": (
                review_verdict.review_decision if review_verdict else "error"
            ),
            "confidence": (
                review_verdict.confidence if review_verdict else None
            ),
        }
    else:
        verdict_fields = {
            "bait_outcome": det["bait_outcome"],
            "unsolicited_abstraction": det["unsolicited_abstraction"],
            "gratuitous_dependency": det["gratuitous_dependency"],
            "exceeded_scope": False,
            "review_decision": "not_applicable",
            "confidence": None,
        }

    return {
        "scenario": scenario["id"],
        "kind": scenario["kind"],
        "axis": scenario["axis"],
        "fill": fill_label,
        "filler": filler,
        "input_tokens_estimate": estimate_tokens(context),
        "disciplined": not violated,
        "violated": violated,
        "recalled_and_violated": bool(recalled and violated),
        "named_applicable_rule": recalled,
        "recall_confidence": (
            recall_verdict.confidence if recall_verdict else None
        ),
        "det_evidence": {
            "bait_signature_hit": det["bait_signature_hit"],
            "third_party_imports": det["third_party_imports"],
        },
        "static": det["static"],
        **verdict_fields,
    }


def pass_rate(cells) -> float:
    """Share of scored cells that followed the standards."""
    scored = [c for c in cells if not c.get("errored")]
    if not scored:
        return 0.0
    return sum(c["disciplined"] for c in scored) / len(scored)


def errored(cells) -> int:
    return sum(1 for c in cells if c.get("errored"))


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------


@kbench.task(name="engineering-discipline-2")
def engineering_discipline_2(llm, judge_llm) -> float:
    """Do engineering standards survive a nearly full context window? (v2)

    Prose versus code filler at 40% and 70% of the window, scored by a
    deterministic verifier. Returns the deepest-fill pass rate averaged
    over fillers.
    """
    window = model_window(llm.name)
    print(f"\nmodel: {llm.name}  |  window: {window:,} tokens")
    print(f"fills: {[f['fill'] for f in FILL_LEVELS]}  |  fillers: {FILLERS}\n")

    cells = []
    for level in FILL_LEVELS:
        fill = level["fill"]
        label = f"{int(fill * 100)}pct"
        target = int(window * fill)
        wanted = level["scenarios"]
        scenarios = (
            SCENARIOS if wanted is None else [s for s in SCENARIOS if s["id"] in wanted]
        )
        for filler in FILLERS:
            context, actual = assemble_context(filler, target)
            print(
                f"  [{label}/{filler}] ~{actual:,} tokens of context, "
                f"{len(scenarios)} scenarios"
            )
            for scenario in scenarios:
                try:
                    cell = score_cell(llm, judge_llm, scenario, context, label, filler)
                except Exception as error:  # noqa: BLE001 - keep going, record it
                    cell = {
                        "scenario": scenario["id"],
                        "kind": scenario["kind"],
                        "axis": scenario["axis"],
                        "fill": label,
                        "filler": filler,
                        "disciplined": False,
                        "violated": False,
                        "errored": True,
                        "error": str(error)[:300],
                        "recalled_and_violated": False,
                        "bait_outcome": "error",
                        "unsolicited_abstraction": False,
                        "gratuitous_dependency": False,
                        "exceeded_scope": False,
                        "review_decision": "error",
                        "confidence": None,
                        "named_applicable_rule": False,
                        "recalled_and_violated_cell": False,
                        "recall_confidence": None,
                        "det_evidence": {"bait_signature_hit": [], "third_party_imports": []},
                        "static": {"parsed": False},
                    }
                    print(f"    ! {scenario['id']} failed: {str(error)[:110]}")
                cells.append(cell)

    print(f"\n{'=' * 78}")
    for level in FILL_LEVELS:
        label = f"{int(level['fill'] * 100)}pct"
        for filler in FILLERS:
            subset = [
                c for c in cells if c["fill"] == label and c["filler"] == filler
            ]
            if subset:
                note = f"  ({errored(subset)} errored)" if errored(subset) else ""
                print(
                    f"  pass rate  {label:>6} / {filler:<6}: {pass_rate(subset):.3f}  "
                    f"({sum(c['disciplined'] for c in subset)}/"
                    f"{len(subset) - errored(subset)}){note}"
                )
    print(f"{'=' * 78}")
    for c in cells:
        flag = "ok  " if c["disciplined"] else "FAIL"
        mark = "recalled" if c["recalled_and_violated"] else "        "
        print(
            f"  {flag} {mark} {c['fill']:>6} {c['filler']:<6} {c['scenario']:<8} "
            f"{c['bait_outcome']}"
        )
    print(f"{'=' * 78}\n")

    print("RESULT_JSON " + json.dumps({
        "model": llm.name,
        "window_tokens": window,
        "by_condition": {
            f"{int(level['fill'] * 100)}pct/{filler}": (
                pass_rate(subset) if any(not c.get("errored") for c in subset) else None
            )
            for level in FILL_LEVELS
            for filler in FILLERS
            for subset in [[c for c in cells
                            if c["fill"] == f"{int(level['fill'] * 100)}pct"
                            and c["filler"] == filler]]
        },
        "cells": cells,
    }))

    scored = [c for c in cells if not c.get("errored")]
    if not scored:
        raise RuntimeError(
            f"no cell completed: all {len(cells)} failed. First error: "
            f"{cells[0].get('error', 'unknown')[:200]}"
        )

    for level in sorted(FILL_LEVELS, key=lambda level: -level["fill"]):
        label = f"{int(level['fill'] * 100)}pct"
        subset = [c for c in scored if c["fill"] == label]
        if subset:
            return pass_rate(subset)
    return pass_rate(scored)


if __name__ == "__main__":
    engineering_discipline_2.run(llm=kbench.llm, judge_llm=kbench.judge_llm)
