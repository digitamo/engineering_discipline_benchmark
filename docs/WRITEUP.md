# Your AI follows your rules at turn one. Does it follow them at turn forty?

*This is a submission for the [Kaggle Benchmarking Challenge](https://dev.to/challenges/kaggle-2026-09-23).*

<!-- DRAFT. Results sections marked TODO are filled from the benchmark run. -->

---

## The question

Needle-in-a-haystack asks whether a model can **find** a fact in a long context.

This asks whether a model can still **obey** a rule.

That sounds like a small difference. It isn't. Finding a fact is retrieval. Obeying a rule means three separate things going right:

1. **Extract** — the rule survives the haystack at all.
2. **Prioritize** — the rule outranks the request sitting in front of it.
3. **Apply** — the model actually behaves differently because of it.

Each can fail independently, and each failure points at a different fix. If models lose the rule, you need retrieval and re-grounding. If they keep the rule and violate it anyway, retrieval will not help you.

## Why I built this

I audit my own coding agent sessions, and the same failure keeps showing up. Not refusal. Drift.

The agent agrees with every rule I give it. Then, three hours in, it starts building the thing the rules explicitly forbid. It abstracts a two-call helper into a strategy pattern. It reaches for a dependency when the standard library was right there. Nothing announces the change. The rules were never rejected — they just stopped being applied.

Rules load at turn one. Violations show up at turn forty.

## What already exists, and what it misses

Most coding benchmarks measure the wrong thing here. SWE-bench asks whether the task got done, not how. IFEval checks formatting constraints at minimal context. NIAH retrieves an inert fact with nothing competing against it.

There is one entry in this challenge that looks adjacent and is worth separating from clearly: **Only What I Asked**, which measures whether a model makes exactly the edit you asked for and leaves everything else alone. It is a good benchmark and its finding is sharp. It is also measuring something different.

| | Only What I Asked | This benchmark |
| :--- | :--- | :--- |
| What varies | how the instruction is phrased | how far the instruction is from where it's applied |
| Where the rule lives | in the message right in front of the model | in the system prompt, 100k tokens upstream |
| What it measures | compliance — nothing to forget | retention — the rule has to survive |
| Task shape | one-line edits, exact-match scored | open-ended implementation |
| Failure it catches | touching adjacent code | architectural drift |
| Real-world shape | a one-shot edit request | turn 40 of a long session |

The load-bearing difference: **their instruction cannot be forgotten, because it is right there.** Exact-match scoring also caps how complex the task can be — you can't byte-compare the output of "write a cache" — which is what keeps over-engineering out of scope for that design.

A model can be perfectly surgical on a one-line edit and still hand you an `AbstractCacheBackendFactory` when you asked for a dict with a lock. Different behaviours, different causes.

So I'm using their result as my baseline rather than treating it as competition. They found every frontier model scores 22/22 on surgical scope discipline at short context. Perfect ceiling. That's not my finding — that's my control. The question is what happens to that ceiling at 100k tokens.

## What I measured

Each scenario runs at two context depths:

- **C_low** — system prompt plus the task. About 4k tokens.
- **C_high** — the same, preceded by roughly 100k tokens of real material.

Each scenario also has a **bait clause**: a plausible, well-phrased request that directly conflicts with the standards. "Make it extensible for future backends." "Consider pulling in an established library." "This will eventually run at scale, so make it blisteringly fast."

The model is scored on whether it followed the standards or the bait.

After answering, in the same conversation, the model is asked to **list the rules that applied**. That gives the most interesting number in the benchmark: how often a model can correctly state the rule it just broke.

## The contamination problem nobody talks about

Here's something I did not expect, and it nearly broke the benchmark.

The haystack is real developer material — commit diffs and documentation from an open-source project. I picked one, packed about 100k tokens, and checked it.

The project's own `AGENTS.md` says:

> *no black boxes: clean, minimal Pythonic interfaces*

Its `.claude/` directory ships a coding-style guide and a PR-review skill. And its current HEAD commit, at the time I cloned it, was literally *"Docs: add agents onboarding page."*

I was about to feed the model a coding-standards document, in a benchmark measuring whether models follow coding standards, and then score it on the result.

Worse: my first filter missed it. I excluded the obvious files by name, but an *earlier commit* in the history had added an `agents.md` file, and that diff went into the haystack. I only caught it because I grepped the finished artifact for tell-tale phrases.

This is not a quirk of one repository. Repositories now ship agent instructions as a matter of course — `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, coding-style skills. Anyone building a long-context benchmark by packing real code has this problem, and the failure is silent. You get plausible results and no idea they're contaminated.

The fix is a filter applied at pack time, plus a content-level check because path rules miss files whose names give nothing away. Both are in the repo, and the manifest records exactly what was included and excluded.

## Method

TODO: design summary once the run completes — scenario count, brackets, judge, controls.

## Results

TODO: tables and charts.

## What broke first

TODO: extract vs prioritize vs apply, from the recall probe.

## Limitations

Being straight about what this does not show.

**It tests the passive case.** Context management means an agent deciding what to keep, what to drop, and when to re-read its own rules. That needs an agent loop — tool use, file state, iterative feedback. This benchmark holds context fixed and adversarial and measures whether retention survives. It is the floor of the real problem, not the ceiling.

**Small N.** Roughly a dozen scenarios. This is a diagnostic probe, not a ranking claim. The arithmetic is unforgiving: with twenty paired binary observations you need six or more flipping the same way before anything reaches significance. That's why the headline measures are continuous rather than pass/fail.

**The static analysis is blind to the interesting cases.** Counting classes catches an abstract factory. It does not catch a registry dict mapping strings to callables, a decorator-based hook layer, or a config object with twelve optional keys. A model can be maximally speculative with zero classes. The judge is the primary scorer for exactly this reason; the structural measures are secondary and reported as continuous values.

**The judge is a model.** It is selected from outside the tested roster to limit self-preference, and validated against hand labels, but it is not ground truth.

**Temperature zero is not determinism.** MoE routing and batching make identical inputs produce different outputs. Rather than claim determinism I measure it and report the flip rate.

**Brackets are absolute tokens, not percent fill.** 100k tokens is about 10% of a million-token context and about 85% of a 128k one. Context size is reported alongside every result.

## Reproduce it

TODO: task links, dataset, pinned commit.

---

*Everything is in the repo: the task, the system prompt, the corpus builder, the exclusion filter, and the analysis. The haystack ships as a dataset with a manifest recording the exact commit and every included and excluded file.*
