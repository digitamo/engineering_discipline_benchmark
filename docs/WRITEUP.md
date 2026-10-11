# Your AI Follows Your Rules at Turn One. Does It Follow Them at Turn Forty?

*This is a submission for the [Kaggle Benchmarking Challenge](https://dev.to/challenges/kaggle-2026-09-23).*

Published benchmark: [kaggle.com/benchmarks/tasks/digitamo/engineering-discipline](https://kaggle.com/benchmarks/tasks/digitamo/engineering-discipline)  
Fillers dataset: [kaggle.com/datasets/digitamo/engineering-discipline-haystack](https://kaggle.com/datasets/digitamo/engineering-discipline-haystack)  
Source code: [github.com/digitamo/engineering_discipline_benchmark](https://github.com/digitamo/engineering_discipline_benchmark)

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

## Catching Three Flaws in the Benchmark

The first run showed a clean degradation curve: 1.000 at baseline dropping to 0.556 at 130k tokens. Every failure flagged a model that cited the exact rule it just broke.

It looked real, but three hidden bugs had produced it:

1. **Convention priming:** The code filler used `pytest`. The model copied it, and an over-broad rubric treated the test tool as an illegal dependency.
2. **Self-assessment bias:** The judge read the model's self-justification before grading the code. It believed the model's promise to stay simple, missing that the output had nine classes and an event hook enum.
3. **Missing system prompt:** During a refactor, the `system_instructions` argument was dropped from the chat call. The model never saw the rules.

The first two bugs masked each other. Priming the judge with the model's intent hid baseline failures, while the broad rubric invented context errors.

A runtime guard (`verify_standards_delivered()`) now stops execution if instructions are missing. Broken benchmarks rarely crash. They produce plausible numbers until you inspect the raw transcripts.

---

## Empirical Results

The full sweep evaluated `gemini-3.7-flash` (1M window) judged by `claude-opus-5.5` to avoid family bias. I ran this locally after running out of Kaggle proxy quota, but I plan to re-run the sweep on the platform and share the public leaderboard once quota resets.

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

The full codebase, task definitions, corpus generators, and scoring tests are available in the [benchmark repository](https://github.com/digitamo/engineering_discipline_benchmark):

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
