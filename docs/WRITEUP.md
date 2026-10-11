# Your AI Follows Your Rules at Turn One. Does It Follow Them at Turn Forty?

*This is a submission for the [Kaggle Benchmarking Challenge](https://dev.to/challenges/kaggle-2026-09-23).*

Published benchmark: [kaggle.com/benchmarks/tasks/digitamo/engineering-discipline](https://kaggle.com/benchmarks/tasks/digitamo/engineering-discipline)  
Fillers dataset: [kaggle.com/datasets/digitamo/engineering-discipline-haystack](https://kaggle.com/datasets/digitamo/engineering-discipline-haystack)

---

I look through my AI coding logs pretty often, and I keep seeing the same failure mode.

The model never refuses a rule. It just drifts.

At the start of a session, I give the assistant clear engineering standards in its system prompt: keep changes small, stick to the standard library, avoid speculative abstractions, and leave untouched code alone. On turn one, it follows every word. Forty turns and three hours later, it is quietly building abstract factories, plugin registries, and class hierarchies for a twenty-line script.

It never pushed back on the prompt. It just stopped caring.

Most long-context tests check whether a model can pull an isolated needle out of a haystack. Finding an inert fact is easy. Obeying engineering rules while writing new code requires three distinct steps:

1. **Extract:** Did the rule stay in working memory as the window filled up?
2. **Prioritise:** Does the rule beat out a user prompt asking for over-engineered features?
3. **Apply:** Does the output code actually stay simple?

I wanted to find where that chain snaps. Along the way, my benchmark broke three separate times. Those mistakes taught me more about evaluation design than the models did.

---

## Benchmark Design and Constraints

The initial plan called for a bespoke test runner, SQLite prompt caching, and an oracle extracting heuristics from adjacent repositories. Building a complex harness to measure over-engineering was contradictory, and Kaggle's single-file SDK constraint (`kaggle-benchmarks`) required a simpler architecture.

The implementation consolidates all standards, scenarios, judge logic, and static analysis into a single self-contained file with no local imports.

The evaluation uses nine focused Python tasks:
- **Six generation tasks:** Small utilities (caches, parsers, filters) paired with bait clauses prompting for premature extensibility, optimization, or dependencies.
- **Three review tasks:** Pull request diffs scored on merge decisions, including a control diff where simplifying an unused hierarchy must be approved.

Context is filled to three depths scaled to each model's advertised window: 0%, 40%, and 70%. Two filler corpora isolate context volume from stylistic priming:
- **Prose (IETF RFCs):** Network specifications that dilute attention without demonstrating coding conventions.
- **Code (`dlt-hub/dlt` @ `ff414a0`):** Production Python code acting as a synthetic haystack to test convention priming.

Fills stop at 70%. Python code tokenizes at ~1.3 times standard character-based estimates; exceeding 75% on a 1M-token window triggers immediate context overflow rejections.

---

## Methodological Autopsy: How Benchmark Design Fails

The initial run yielded an apparently clean degradation curve: 1.000 adherence at baseline falling to 0.556 at 130k tokens. Every failure flagged a model that cited the exact rule it had just broken.

The result was an artifact of three independent errors:

### 1. Convention Priming and Rubric Scope
The code filler contained 24 references to `pytest` and zero to `unittest`. The model adopted the test framework demonstrated in its context. The judge rubric penalized any non-standard-library dependency without distinguishing production requirements from test tooling. The model had not abandoned architectural discipline; it simply imitated context conventions.

### 2. Self-Assessment Contamination
The judge prompt originally included the model's self-reported reasoning before the evaluation rubric. When asked why it declined an extensibility hook, the model stated adherence to simplicity standards. The judge evaluated stated intent rather than delivered code, overlooking that the response contained nine classes and an event registry. Isolating the recall query into a separate conversation reversed the outcome from uniform compliance to widespread failure.

### 3. Delivery Omission
During task refactoring, the `system_instructions` argument was omitted from chat session initialization. The standards were defined in code and referenced in judge prompts, but never passed to the subject model. The model was not defying constraints; it was operating unconstrained.

Errors 1 and 2 masked each other: the biased judge suppressed baseline violations, while the broad rubric generated false context-induced failures.

A verification guard (`verify_standards_delivered()`) now halts execution if instructions are absent from the active session. Flawed benchmarks rarely crash; they produce plausible metrics that survive until raw conversation artifacts are audited.

---

## Empirical Results

The full sweep was evaluated on `gemini-3.7-flash` (1M window) using `claude-opus-5.5` as judge to prevent intra-family evaluation bias. Due to Kaggle proxy quota reservation constraints, this sweep was executed via LiteLLM.

| Context Fill | Filler Type | Tokens | Scenarios | Adherence Rate |
|---:|:---|---:|---:|---:|
| **0%** | None | 0 | 9 | **0.889** (8/9) |
| **40%** | Prose (RFCs) | ~447,000 | 3 | **1.000** (3/3) |
| **40%** | Code (`dlt`) | ~428,000 | 3 | **1.000** (3/3) |
| **70%** | Prose (RFCs) | ~734,000 | 3 | **1.000** (3/3) |
| **70%** | Code (`dlt`) | ~755,000 | 3 | **0.667** (2/3) |

Two concrete failures occurred across 21 scored cells:

- **Baseline (`gen-06`):** Asked to deduplicate four formatting lines between two scripts, the model implemented an unprompted unit ladder to petabytes, negative-value handling, and trailing-zero stripping that altered existing output behavior. This was baseline scope creep independent of context pressure.
- **70% Code Context (`gen-01`):** Asked for an in-memory TTL cache with bait requesting extensibility, the model conceded under 755k tokens of code context. It generated a `CacheBackend` protocol, `InMemoryBackend`, and hook registry spanning 6 classes, 26 functions, and 163 lines.

Under 734k tokens of neutral prose, compliance was 100%. Degradation appeared specifically when dense code context primed architectural complexity.

---

## Evaluation Boundaries: Prompts Versus Sandboxes

This benchmark measures passive context pressure: static tokens concatenated into a prompt. This design isolates token dilution and priming under controlled conditions, establishing the baseline floor of the behavior.

A more faithful evaluation of engineering discipline requires an active agent harness: tool access (filesystem, shell), a real repository, and iterative multi-turn execution within a sandboxed environment.

That setup evaluates active context management: whether an assistant re-reads upstream instructions, compacts its scratchpad, or limits blast radius when modifying an unfamiliar codebase.

Synthetic prompts isolate and measure these variables within platform constraints today. Active agent sandboxes represent the necessary next step.

---

## Reproduction

All task definitions, corpus generators, and scoring tests are in the repository:

```bash
# Verify environment and execute local scoring tests
source scripts/kbench-env.sh
python3 scripts/test_scoring.py

# Execute local sweep via LiteLLM
./scripts/run_local.sh full

# Execute on Kaggle (subject to quota availability)
kaggle b t push engineering-discipline -f tasks/engineering_discipline.py -d digitamo/engineering-discipline-haystack
kaggle b t download engineering-discipline -o ./runs
python3 scripts/analyze.py runs/**/*.run.json
```
