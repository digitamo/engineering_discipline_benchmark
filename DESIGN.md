# Engineering Discipline Under Context Pressure

**Status:** Accepted
**Date:** 2026-10-11 · revised 2026-10-12
**Target:** Kaggle Benchmarks · post-competition continuation (v2)

A design document. It records what this benchmark measures, why each choice is
what it is, and how the design changed after the first run. The intent behind
it, agent coding session audits and the behavioural rules that became the
system prompt, is recorded in the project handoff notes rather than here.

---

## 1. The problem

Rules for how software should be built are given to a coding assistant once, at
the start of a session. Then the session runs for hours. The observed failure is
not refusal. It is drift: an assistant that respected the architecture rules in
the first hour quietly starts building abstract factories in the third. The
rules were never rejected. They stopped being applied.

The question:

> Can a model extract the rules that matter from a mass of lower-priority
> material, rank them above the request in front of it, and still act on them?

Three operations, each of which can fail on its own:

| Operation | What failure looks like |
| :--- | :--- |
| Extract | the rule is gone from working memory |
| Prioritise | the rule is recalled, but the request outranks it |
| Apply | the rule is recalled and ranked, and the output violates it anyway |

The distinction matters because it determines the remedy. If models cannot
recall the rule, the fix is retrieval and re-grounding. If they recall it and
break it anyway, retrieval will not help.

## 2. Design decisions

### 2.1 Two fillers, because content and size are different variables

Size was the obvious variable to test; content turned out to matter more, so
content is an explicit variable in the design.

| Filler | Source | Why |
| :--- | :--- | :--- |
| **prose** | IETF RFCs | describes wire behaviour, not how to write software, so it is neutral with respect to the standards under test |
| **code** | a pinned clone of `dlt-hub/dlt` | demonstrates coding conventions, so it is expected to prime |

Prose is the primary arm: it isolates context pressure. Code is the comparison
arm: it measures priming.

The `dlt` codebase is not an active workspace for the task; it is used strictly
as a synthetic code haystack. Its commit history, utility functions, and pipeline
plumbing provide realistic syntactic volume and architectural conventions,
measuring cross-attention interference and convention priming without requiring
a multi-file execution environment inside the benchmark.

**Python PEPs were rejected as the prose source.** PEP 20 is a simplicity
manifesto, *"Simple is better than complex… Although never is often better than
right now"*, and PEP 8 is a style guide. Either would prime the model toward the
exact behaviour being measured, in the opposite direction, and a clean result
would look like good news.

### 2.2 Fill is a fraction of the model's window

An absolute budget means different things to different models: 130,000 tokens is
a tenth of a million-token window and a full window for a small model. Fill is
therefore expressed as a fraction of each model's own advertised window, so
"long context" means the same thing across the roster.

Two obstacles, both handled rather than assumed away:

- **Tokenisers are not shared.** The same text is a different token count per
model. Chunk sizes are estimates; the run artifact reports actual input tokens,
and the analysis compares the two so the error stays visible.
- **Smaller windows.** A deep fill of a million-token model exceeds the entire
window of a 128,000-token model. Filler is therefore built as fixed-size chunks
and concatenated whole, so a model with a smaller window loses the tail cleanly
instead of being cut mid-file.

### 2.3 The filler must not contain the answer

The corpus repository ships its own agent instructions. Its `AGENTS.md` states
*"no black boxes: clean, minimal Pythonic interfaces."* Its `.claude/` directory
carries a coding-style guide and a pull-request review skill. Left in, the
filler would coach the model on the same axis the benchmark measures.

An exclusion filter drops those paths, and a phrase guard drops anything
carrying agent-instruction or coding-standards language regardless of where it
lives, because path rules miss files whose names give nothing away. The first
version of that filter leaked one file whose name gave nothing away; the catch
was grepping the finished artifact.

### 2.4 Scenarios

**v1:** nine, six generation and three review. Python only, so one scoring
pipeline covers everything. They are self-contained: no repository context in
the prompt, which avoids both horns of a dilemma. Canonical interview problems
sit in every training set, while repository-grounded tasks inflate the prompt
and worsen the priming problem. The scenarios are intentionally synthetic units
(caches, parsers, diff reviews) rather than open GitHub issues from the filler
repository; this fits the single-file execution constraint and separates task
logic from background filler noise.

Generation scenarios ask for something simple while the request also carries a
plausible argument for making it general:

| | Task | The request also asks for |
| :--- | :--- | :--- |
| gen-01 | in-memory cache with expiry | swappable storage backends and lifecycle hooks |
| gen-02 | semantic version comparison | an established library, for robustness |
| gen-03 | read a JSON file | a pluggable registry for future formats |
| gen-04 | filter a list of dictionaries | indexing, caching and parallelism for scale |
| gen-05 | parse a small config string | a comprehensive exception hierarchy |
| gen-06 | share four lines between two scripts | a shared module architecture |

Review scenarios ask for a merge decision on a diff, and carry the decision a
competent reviewer should reach:

| | Diff | Should be |
| :--- | :--- | :--- |
| rev-01 | retry logic becomes an abstract policy, factory and executor | rejected |
| rev-02 | a one-line helper pulls in an external package | rejected |
| rev-03 | an unused class hierarchy collapses into a function | approved |

rev-03 is the false-positive control. A model that reflexively rejects all
change fails it. Reviews are scored on the decision they reach, never on the
code they praise or pan.

**v2:** the set contracts to `gen-01`, `gen-02`, `rev-01`, the cells that
produced signal. The 0% baseline is removed: the measurable variable is the
prose-versus-code contrast under load, not the empty-window ceiling, and every
v1 baseline cell but one passed clean.

### 2.5 Scoring

**The lessons that shaped it.** The first run was wrong in three design-relevant
ways: a filler demonstrating coding conventions was treated as neutral
background; a dependency rubric broad enough to count test tooling as a
production dependency; and, when the task file was restructured, the
standards were defined but never delivered to the conversation. Two of the
three errors masked each other, which is why the aggregate read clean. Design
responses: the filler-content guard in 2.3, the production-code dependency
scope below, and a guard that fails loudly if the standards are absent from
the conversation, verified in both directions.

**Judge protocol.** Two separate calls per cell, each in its own conversation:
a response verdict and a recall verdict, the latter asked separately so the
model's own explanation of what it did cannot prime the judgement of what it
did. Binary rubric items rather than a scale, because scales are unreliable
across judges.

**Deterministic-first hybrid (v2).** Following the SciCode lesson, verify
rather than evaluate: generation cells are scored entirely by deterministic
checks inside the task file, per-scenario bait signatures (the constructs the
bait asks for and the standards forbid) plus a production-import scan against
the standard library. The LLM judge is demoted to the two roles parsing cannot
cover: review-decision extraction and the recall verdict. Judge replies carry a
self-reported `confidence`, recorded per cell and surfaced in the analysis; it
is treated as reported rather than calibrated. The known blind spots, registry
dicts, decorator layers, novel framerings, move from hidden to stated.

**Structural measures are secondary and continuous.** Syntax tree inspection
gives line count, class count, inheritance depth and imports, always reported,
never used as a pass/fail gate.

**Failures are reported, not dropped.** Unparseable output is recorded rather
than discarded, because silently discarding it biases the sample toward
well-formatted answers.

## 3. Consequences

### 3.1 What this can and cannot show

**Answered here.** Under fixed context pressure, does the model still extract,
prioritise and apply the standards?

**Not answered here.** Does an agent *manage* its own context well? Compacting,
re-reading, re-grounding on its rules when they drift out of attention? Context
management implies agency over one's own context. A benchmark that injects a
fixed filler tests context *pressure*, not management.

A faithful test of the second question needs an agent loop: tool use, file
state, iterative feedback. That is out of scope. This measures the passive case,
which is the floor of the problem rather than its ceiling.

### 3.2 Limits

| Limit | Handling |
| :--- | :--- |
| Structural measures are blind to registry and decorator over-engineering | bait signatures narrow it; blind spots stated, not hidden |
| Small number of scenarios | reported as a diagnostic, not a ranking claim |
| No agent loop, so only passive pressure is measured | stated as a scope boundary, in the method rather than in limitations |
| Fill is a fraction of an advertised window, which may not match usable context | actual input tokens are reported alongside |
| Verbosity confounds cross-model comparison of structural measures | reported as a covariate |
| The judge is a model, and shares a family with some tested models | disclosed; under the v2 hybrid its scope is two rubric items |
| One phrasing per scenario | a paraphrase check is a possible extension |
| No seed, so identical inputs can produce different outputs | run-to-run variation is measured rather than assumed away |
| Model-proxy quota is reserved per request and is finite | deep fills run a scenario subset; a run cut short records failures per cell rather than discarding the whole run |

### 3.3 Reproducibility

Claimed for **inputs and scoring**, not for outputs:

- the corpus commit is pinned
- filler chunks are built once and published as a versioned dataset
- model versions are pinned to dated identifiers rather than floating aliases
- scoring code is versioned

Temperature zero does not produce determinism. Mixture-of-experts routing,
batching-dependent reductions and server-side model rolling all intervene, and
no seed is exposed. Rather than assert determinism, we measure it.

## 4. Decision log

| # | Decision | Reason |
| :--- | :--- | :--- |
| 1 | Use the platform's own library rather than a bespoke runner | submission eligibility, verified, not a preference |
| 2 | The judge was the primary scorer in v1 | structural analysis alone cannot score review verdicts or prose |
| 3 | Structural analysis is secondary and continuous | binarising discards statistical power; the measures have known blind spots |
| 4 | No prompt cache | reproducible inputs, not memoised calls |
| 5 | Corpus is build-time only, published as a dataset | run time needs no network and no clone; inputs stay byte-stable |
| 6 | Fillers are chunked and concatenated whole | a smaller window loses the tail cleanly rather than being cut mid-file |
| 7 | Fill is a fraction of each model's window | an absolute budget means different things to different models |
| 8 | Prose is the primary filler, code the comparison | content, not size, is the variable that mattered |
| 9 | RFCs rather than PEPs as the prose source | PEP 20 and PEP 8 would prime the measured axis |
| 10 | Two separate judge calls per cell | the recall answer must not prime the response verdict |
| 11 | Each judge call gets its own conversation | sharing one let verdicts accumulate as context |
| 12 | Dependency violations are scoped to production code | the over-broad rubric reading imitation as violation |
| 13 | Reviews are scored on the decision reached | otherwise a model that approves everything passes |
| 14 | Exclusion filter plus a content guard | path rules miss files whose names give nothing away |
| 15 | Scenario subset at the deepest fill | cost scales with fill fraction and request count |
| 16 | Reproducibility claimed for inputs and scoring only | temperature zero is not determinism |
| 17 | Scope stated as passive pressure only | a faithful test of context management needs an agent loop |
| 18 | v2: deterministic-first hybrid scoring | parseable behaviour should be verified, not judged; SciCode lesson |
| 19 | v2: judge replies carry self-reported confidence | recorded rather than calibrated; confidence-agreement is auditable down the road |
| 20 | v2: baseline removed, three-signal scenarios only | the prose-code contrast under load is the measurable variable; freed budget buys cross-family roster |
