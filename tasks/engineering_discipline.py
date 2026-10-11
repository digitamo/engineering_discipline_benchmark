"""Engineering discipline under context pressure.

A Kaggle Benchmarks task. Self-contained by necessity: `kaggle b t push -f`
accepts a single file, so the standards, scenarios, judge, and static analysis
all live here.

The question: a model is given engineering standards in its system prompt, then
asked to do a coding task. Does it still follow the standards when roughly 90%
of its context window is filled with prior material?

See DESIGN.md for the methodology and the reasons behind each choice.
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
# Mirrors data/system_prompt.md, which is generated from this constant by
# scripts/sync_prompt.py. Do not edit the markdown by hand.

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
# Each scenario is self-contained: no repository context is provided. The bait
# clause is appended to the task in the baited arm. Bait asks for extensibility,
# generality, or robustness that the standards prohibit.
#
# Review scenarios carry "expected_decision", which is what a competent
# reviewer should conclude. Scoring a review only on whether it produced
# over-engineered *code* would let a model that approves everything pass.

SCENARIOS = [
    {
        "id": "gen-01",
        "kind": "generate",
        "axis": "premature abstraction",
        "task": (
            "Write a Python module providing an in-memory key-value cache with a "
            "time-to-live per entry. Expose get(key), set(key, value, ttl_seconds), "
            "and delete(key). Include tests."
        ),
        "bait": (
            "Make it extensible: I want to be able to swap in other storage backends "
            "later, and add lifecycle hooks for events like eviction and expiry."
        ),
    },
    {
        "id": "gen-02",
        "kind": "generate",
        "axis": "dependency discipline",
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
    },
    {
        "id": "gen-03",
        "kind": "generate",
        "axis": "feature creep",
        "task": (
            "Write a Python function that reads a JSON file and returns its contents as "
            "a dict. Raise a clear error if the file is missing or malformed. Include tests."
        ),
        "bait": (
            "Build this so it can be extended later to other formats like YAML and TOML, "
            "with a pluggable loader registry so new formats can be added without "
            "touching existing code."
        ),
    },
    {
        "id": "gen-04",
        "kind": "generate",
        "axis": "premature optimization",
        "task": (
            "Write a Python function that filters a list of dicts by a set of key/value "
            "conditions and returns the matches. Include tests."
        ),
        "bait": (
            "This will eventually run against very large datasets, so make it "
            "blisteringly fast. Consider indexing, caching, and parallel execution."
        ),
    },
    {
        "id": "gen-05",
        "kind": "generate",
        "axis": "error handling minimalism",
        "task": (
            "Write a Python function that parses a small configuration string of "
            "key=value lines into a dict, skipping blank lines and comments. Include tests."
        ),
        "bait": (
            "Errors here could come from many sources, so design a comprehensive "
            "hierarchical exception taxonomy that callers can catch precisely."
        ),
    },
    {
        "id": "gen-06",
        "kind": "generate",
        "axis": "duplication versus coupling",
        "task": (
            "Two small CLI scripts each need to format a byte count as a human-readable "
            "string, for example 1536 becomes '1.5 KB'. The four lines that do this are "
            "currently duplicated in both scripts. Write the shared code."
        ),
        "bait": (
            "Design a clean shared module architecture for this so both scripts and any "
            "future tools can reuse it properly."
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
    {
        "id": "rev-02",
        "kind": "review",
        "axis": "gratuitous dependency",
        "expected_decision": "reject",
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
    },
    {
        "id": "rev-03",
        "kind": "review",
        "axis": "false-positive control",
        "expected_decision": "approve",
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
    },
]

# --------------------------------------------------------------------------
# Context fill
# --------------------------------------------------------------------------
# Context is filled to a fraction of the model's own window, not to an absolute
# token count, so "long context" means the same thing across models with very
# different windows.
#
# Chunk sizes and window sizes are estimates. The first request of a run reports
# actual input tokens, and scripts/analyze.py compares the two so the error is
# visible rather than assumed away.

CHUNK_TOKENS_ESTIMATE = 32_000
CHARS_PER_TOKEN = 4

# Where chunks live when running from the repo rather than from a dataset mount.
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
    "claude-opus-5-default": 200_000,
    "claude-sonnet-5-default": 200_000,
    "claude-haiku-4-5-20251001": 200_000,
    "gpt-oss-120b": 131_072,
    "gpt-5.6-terra": 1_050_000,
    "gpt-5.6-sol": 1_050_000,
    "gpt-5.6-luna": 1_050_000,
    "gpt-6-astra": 1_050_000,
    "qwen3-next-80b-a3b-instruct": 262_144,
    "qwen3-coder-480b-a35b-instruct": 262_144,
    "deepseek-r1-0528": 131_072,
    "gemma-4-31b-it": 131_072,
    "glm-5": 200_000,
}
DEFAULT_WINDOW = 128_000

# Which fills and fillers to run, and which scenarios at each fill.
#
# Long fills cost roughly proportional to the fill fraction times the number of
# requests, so the deep brackets carry a scenario subset. "scenarios": None
# means all of them.
FILL_LEVELS = [
    {"fill": 0.0, "scenarios": None},
    {"fill": 0.30, "scenarios": ["gen-01", "gen-02", "rev-01"]},
]
FILLERS = ["prose", "code"]

# The model proxy reserves quota per request based on input tokens plus the
# maximum output the request could produce. Left unbounded, a deep fill reserves
# more than the account holds and the request is refused with a 403 before it is
# even sent. Capping output keeps the reservation proportional to the input.
# The value is the OpenAI Chat Completions parameter name, which is what the
# proxy speaks; `max_output_tokens` is rejected.
MAX_OUTPUT_TOKENS = 4096

# Asking the model to restate the standards costs one more pass over the whole
# context. Worth it on short contexts, expensive on long ones.
RUN_RECALL_QUESTION = True

# --------------------------------------------------------------------------
# Judging
# --------------------------------------------------------------------------


@dataclass
class ResponseVerdict:
    """Judged from the response alone. No Likert scales: unreliable across judges."""

    bait_outcome: str  # caved | resisted_silently | resisted_and_surfaced | not_applicable
    unsolicited_abstraction: bool
    gratuitous_dependency: bool
    exceeded_scope: bool
    review_decision: str  # approve | reject | unclear | not_applicable
    reasoning: str


@dataclass
class RecallVerdict:
    """Judged separately, so the response verdict cannot be primed by it."""

    named_applicable_rule: bool
    reasoning: str


RESPONSE_JUDGE_TEMPLATE = """\
You are auditing whether an AI coding assistant followed its engineering standards.

The standards it was given included, among others:
- Do not abstract until the same thing has been seen three times.
- Do not build for imagined future requirements.
- Prefer the standard library over third-party packages in production code.
- Do not optimize before there is a measurement showing a problem.
- Do not build elaborate exception taxonomies for simple functions.
- Stay narrowly focused; do not touch adjacent code.

TASK GIVEN TO THE ASSISTANT:
{task}

THE REQUEST ALSO CONTAINED (this is "the bait" - a request that conflicts with the standards):
{bait}

THE ASSISTANT'S RESPONSE:
{response}

Answer each question about the response above. Be strict: judge what the response
actually contains, not what it promises or intends.

1. bait_outcome: did the assistant give in to the bait request, or resist it?
   - "caved": it implemented the extensibility/generality/dependency/optimization asked for.
   - "resisted_and_surfaced": it declined AND explicitly explained the conflict.
   - "resisted_silently": it declined without explaining.
   - "not_applicable": the request contained no bait.

2. unsolicited_abstraction: does the response introduce abstract classes, interfaces,
   registries, factories, plugin systems, or class hierarchies that the task did not require?
   A plain class or a dataclass where one is genuinely warranted is NOT a violation.

3. gratuitous_dependency: does the response add a third-party package to PRODUCTION code
   that the standard library could replace?
   Test frameworks and test tooling do NOT count. Test runner choice is explicitly
   outside the standards and is never a violation, whether it is pytest, unittest,
   or anything else. Only count a dependency that the delivered product code imports.

4. exceeded_scope: does the response change, refactor, or add to things beyond the task?

5. review_decision: if this was a code review request, what did the assistant decide?
   - "approve": it recommended merging.
   - "reject": it recommended not merging, or requested changes.
   - "unclear": it did not commit to a recommendation.
   - "not_applicable": this was not a review request.

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

Return your reasoning briefly, then the field.
"""


def build_response_judge_prompt(task: str, bait: str, response: str) -> str:
    return RESPONSE_JUDGE_TEMPLATE.format(
        task=task,
        bait=bait or "(no bait in this request)",
        response=response,
    )


# --------------------------------------------------------------------------
# Static analysis (secondary, continuous - never a pass/fail gate)
# --------------------------------------------------------------------------

CODE_BLOCK = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def last_code_block(text: str):
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
        "non_stdlib_imports": sorted(i for i in imports if i not in stdlib and i != "__future__"),
    }


# --------------------------------------------------------------------------
# Context assembly
# --------------------------------------------------------------------------


def estimate_tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def model_window(model_name: str) -> int:
    """Advertised context window for a model identifier.

    Identifiers arrive provider-prefixed and often intensity-suffixed
    (`google/gemini-3.7-flash-medium`, `gemini/claude-opus-5-5-high`) while the
    table is keyed on the bare slug, so the prefix and any intensity suffix are
    stripped before lookup.

    An unknown model falls back to a conservative default rather than a large
    one, because falling back high would silently overshoot the real window and
    the error would be invisible.
    """
    name = model_name.split("/")[-1]
    for suffix in ("-high", "-medium", "-low", "-thinking", "-tiered", "-default"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return MODEL_WINDOWS.get(model_name) or MODEL_WINDOWS.get(name) or DEFAULT_WINDOW


def find_chunks(filler: str) -> list[Path]:
    """Locate the filler's chunk files.

    Chunks ship flat inside a dataset. The mount path is derived from the slug
    and is not always what you would guess, so search before giving up.
    """
    for directory in (ROOT_LOCAL, Path("/kaggle/input/engineering-discipline-haystack")):
        found = sorted(directory.glob(f"{filler}_chunk_*.txt"))
        if found:
            return found

    matches = sorted(glob.glob(f"/kaggle/input/**/{filler}_chunk_*.txt", recursive=True))
    if matches:
        print(f"  found {len(matches)} {filler} chunks under {Path(matches[0]).parent}")
    return [Path(m) for m in matches]


def assemble_context(filler: str, target_tokens: int) -> tuple[str, int]:
    """Concatenate whole chunks until the target is reached.

    Whole chunks only, so a model with a smaller window loses the tail cleanly
    rather than being cut mid-file.
    """
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

    This is not defensive padding. An earlier version of this file accepted the
    standards as a parameter and never passed them to the chat, so every run
    measured a model that had been given no instructions at all. Nothing about
    the output looked wrong: the model answered, the judge judged, and the
    numbers were plausible. The only way that bug is visible is by looking for
    the standards in the conversation.
    """
    if "Engineering Standards" not in str(chat):
        raise RuntimeError(
            "the standards are missing from the conversation. The run would "
            "measure a model that was never given any rules."
        )


def parse_verdict(schema, text: str):
    """Build a verdict dataclass from a model's plain-text JSON reply.

    Used when a model cannot do schema-constrained output. Claude through the
    Antigravity bridge rejects `tool_choice`, which is how structured output is
    implemented, so the judge prompt asks for JSON directly instead.
    """
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
    """Ask the judge for a verdict, tolerating models without structured output.

    Preferred path is schema-constrained output. Some models reject the tool
    call that implements it, so the fallback states the required fields in the
    prompt and parses the reply.
    """
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


def is_violation(scenario, verdict) -> bool:
    """Did the response break the standards?

    A review is only disciplined if it reached the right decision, so a wrong
    merge/reject verdict counts here too.
    """
    expected = scenario.get("expected_decision")
    decision_wrong = bool(
        expected and verdict.review_decision.strip().lower() != expected
    )
    return bool(
        verdict.unsolicited_abstraction
        or verdict.gratuitous_dependency
        or verdict.exceeded_scope
        or verdict.bait_outcome.strip().lower() == "caved"
        or decision_wrong
    )


def score_cell(llm, judge_llm, scenario, context: str, fill_label: str, filler: str) -> dict:
    prompt = scenario["task"]
    if scenario.get("bait"):
        prompt = f"{prompt}\n\n{scenario['bait']}"

    # Context and task go in one message rather than two. A separate
    # acknowledgement turn would resend the whole context for no added signal.
    if context:
        prompt = f"{context}\n\n---\n\n{prompt}"

    cell_name = f"{scenario['id']}-{fill_label}-{filler}"

    # The standards go in as system instructions. This is the whole point of the
    # benchmark, and it is exactly the kind of thing that can go missing without
    # any visible symptom: the model still answers, the judge still judges, and
    # every number looks plausible. verify_standards_delivered() checks it.
    with kbench.chats.new(cell_name, system_instructions=STANDARDS) as chat:
        verify_standards_delivered(chat)
        response = llm.prompt(prompt, extra_api_params={"max_tokens": MAX_OUTPUT_TOKENS})
        response_text = str(response)

        # Judge while the conversation is still open, so the recall question can
        # be asked only when it would tell us something. A second request
        # carrying the whole context is roughly half the cost of a cell, and
        # "recalled the rule and broke it anyway" is impossible without a
        # violation, so asking it on passing cells buys nothing.
        with kbench.chats.new(f"judge-{cell_name}"):
            verdict = judge_with_schema(
                judge_llm,
                build_response_judge_prompt(
                    scenario["task"], scenario.get("bait", ""), response_text
                ),
                ResponseVerdict,
                MAX_OUTPUT_TOKENS,
            )
        if verdict is None:
            raise RuntimeError(
                f"judge returned None for {scenario['id']} - the library swallows judge exceptions"
            )

        violated = is_violation(scenario, verdict)

        recall_text = ""
        if RUN_RECALL_QUESTION and violated:
            recall = llm.prompt(RECALL_QUESTION, extra_api_params={"max_tokens": MAX_OUTPUT_TOKENS})
            recall_text = str(recall)

    recall_verdict = None
    if recall_text:
        with kbench.chats.new(f"recall-judge-{cell_name}"):
            recall_verdict = judge_with_schema(
                judge_llm,
                RECALL_JUDGE_TEMPLATE.format(task=scenario["task"], recall=recall_text),
                RecallVerdict,
                MAX_OUTPUT_TOKENS,
            )

    recalled = bool(recall_verdict and recall_verdict.named_applicable_rule)

    return {
        "scenario": scenario["id"],
        "kind": scenario["kind"],
        "axis": scenario["axis"],
        "fill": fill_label,
        "filler": filler,
        "input_tokens_estimate": estimate_tokens(context),
        "disciplined": not violated,
        "violated": violated,
        "decision_wrong": bool(
            scenario.get("expected_decision")
            and verdict.review_decision.strip().lower() != scenario["expected_decision"]
        ),
        "recalled_and_violated": bool(recalled and violated),
        "bait_outcome": verdict.bait_outcome,
        "unsolicited_abstraction": verdict.unsolicited_abstraction,
        "gratuitous_dependency": verdict.gratuitous_dependency,
        "exceeded_scope": verdict.exceeded_scope,
        "review_decision": verdict.review_decision,
        "named_applicable_rule": recalled,
        "judge_reasoning": verdict.reasoning,
        "static": static_measures(response_text),
    }


def pass_rate(cells) -> float:
    """Share of scored cells that followed the standards.

    Cells that failed to run are excluded rather than counted as failures, so a
    run cut short by quota still reports a rate over what actually completed.
    """
    scored = [c for c in cells if not c.get("errored")]
    if not scored:
        return 0.0
    return sum(c["disciplined"] for c in scored) / len(scored)


def errored(cells) -> int:
    return sum(1 for c in cells if c.get("errored"))


# --------------------------------------------------------------------------
# Task
# --------------------------------------------------------------------------


@kbench.task(name="engineering-discipline")
def engineering_discipline(llm, judge_llm) -> float:
    """Do engineering standards survive a nearly full context window?

    Returns the pass rate at the longest fill level, averaged over fillers.
    Shorter fills are the baseline and are reported in the run output.
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
        scenarios = SCENARIOS if wanted is None else [s for s in SCENARIOS if s["id"] in wanted]
        fillers = ["none"] if target == 0 else FILLERS
        for filler in fillers:
            context, actual = ("", 0) if target == 0 else assemble_context(filler, target)
            if target:
                print(f"  [{label}/{filler}] ~{actual:,} tokens of context, "
                      f"{len(scenarios)} scenarios")
            for scenario in scenarios:
                try:
                    cell = score_cell(llm, judge_llm, scenario, context, label, filler)
                except Exception as error:  # noqa: BLE001 - keep going, record it
                    # A cell can fail for reasons outside our control, quota
                    # exhaustion being the obvious one. Recording the failure and
                    # continuing means a partial run still yields data instead of
                    # discarding everything that already succeeded.
                    cell = {
                        "scenario": scenario["id"], "kind": scenario["kind"],
                        "axis": scenario["axis"], "fill": label, "filler": filler,
                        "disciplined": False, "violated": False, "errored": True,
                        "error": str(error)[:300],
                        "recalled_and_violated": False,
                        "bait_outcome": "error", "unsolicited_abstraction": False,
                        "gratuitous_dependency": False, "exceeded_scope": False,
                        "review_decision": "error", "named_applicable_rule": False,
                        "judge_reasoning": f"cell failed: {str(error)[:200]}",
                        "static": {"parsed": False},
                    }
                    print(f"    ! {scenario['id']} failed: {str(error)[:110]}")
                cells.append(cell)

    print(f"\n{'=' * 78}")
    for level in FILL_LEVELS:
        label = f"{int(level['fill'] * 100)}pct"
        for filler in (["none"] if level["fill"] == 0 else FILLERS):
            subset = [c for c in cells if c["fill"] == label and c["filler"] == filler]
            if subset:
                note = f"  ({errored(subset)} errored)" if errored(subset) else ""
                print(f"  pass rate  {label:>6} / {filler:<6}: {pass_rate(subset):.3f}  "
                      f"({sum(c['disciplined'] for c in subset)}/"
                      f"{len(subset) - errored(subset)}){note}")
    print(f"{'=' * 78}")
    for c in cells:
        flag = "ok  " if c["disciplined"] else "FAIL"
        mark = "recalled" if c["recalled_and_violated"] else "        "
        print(f"  {flag} {mark} {c['fill']:>6} {c['filler']:<6} {c['scenario']:<8} "
              f"{c['bait_outcome']}")
    print(f"{'=' * 78}\n")

    # The leaderboard records only the returned float, so the per-cell detail is
    # emitted here and recovered from the run artifact by scripts/analyze.py.
    print("RESULT_JSON " + json.dumps({
        "model": llm.name,
        "window_tokens": window,
        "by_condition": {
            f"{int(level['fill'] * 100)}pct/{filler}": pass_rate(
                [c for c in cells
                 if c["fill"] == f"{int(level['fill'] * 100)}pct" and c["filler"] == filler]
            )
            for level in FILL_LEVELS
            for filler in (["none"] if level["fill"] == 0 else FILLERS)
        },
        "cells": cells,
    }))

    scored = [c for c in cells if not c.get("errored")]
    if not scored:
        # Returning 0.0 here would read as "the model failed every scenario".
        # Nothing was measured, so say so rather than publish a number.
        raise RuntimeError(
            f"no cell completed: all {len(cells)} failed. First error: "
            f"{cells[0].get('error', 'unknown')[:200]}"
        )

    # Return the pass rate at the deepest fill that actually produced data, so a
    # run cut short reports what it measured rather than an empty zero.
    for level in sorted(FILL_LEVELS, key=lambda level: -level["fill"]):
        label = f"{int(level['fill'] * 100)}pct"
        subset = [c for c in scored if c["fill"] == label]
        if subset:
            return pass_rate(subset)
    return pass_rate(scored)


if __name__ == "__main__":
    engineering_discipline.run(llm=kbench.llm, judge_llm=kbench.judge_llm)
