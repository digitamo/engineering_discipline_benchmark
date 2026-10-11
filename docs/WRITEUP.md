# Your AI follows your rules at turn one. Does it follow them at turn forty?

*This is a submission for the [Kaggle Benchmarking Challenge](https://dev.to/challenges/kaggle-2026-09-23).*

---

## The question

Needle-in-a-haystack asks whether a model can **find** a fact in a long context.

This asks whether it can still **obey** a rule.

That sounds like a small difference. It isn't. Finding a fact is retrieval. Obeying a rule means three separate things going right:

1. **Extract** — the rule survives the haystack at all.
2. **Prioritise** — the rule outranks the request sitting in front of it.
3. **Apply** — the model actually behaves differently because of it.

Each can fail on its own, and each failure points at a different fix. If models lose the rule, you need retrieval and re-grounding. If they keep the rule and break it anyway, retrieval will not help you.

## Why I built this

I audit my own coding agent sessions, and the same failure keeps showing up. Not refusal. Drift.

The agent agrees with every rule I give it. Then, three hours in, it starts building the thing the rules explicitly forbid. It abstracts a two-call helper into a strategy pattern. It reaches for a dependency when the standard library was right there. Nothing announces the change. The rules were never rejected. They just stopped being applied.

Rules load at turn one. Violations show up at turn forty.

## The result that looked perfect, and was wrong twice

I'll start with the failure, because it's the most useful thing I found.

The first version of this benchmark was the obvious design. Fill the context with about 130,000 tokens of real code from an open-source repository, give the model a set of engineering standards in its system prompt, ask it to do a small coding task, and score whether it followed the standards. A language model judges the output.

It came back like this:

| | |
| :--- | ---: |
| Followed the standards at short context | **9 / 9** |
| Followed the standards at long context | **5 / 9** |
| Drop | **+0.44** |
| Could state the rule, then broke it | **4 of 4 failures** |

A perfect ceiling at short context. A large drop at long context. And every single failure was a case where the model could *correctly state the rule it had just broken*.

That is the most interesting result the design could possibly have produced. It says the problem is not retrieval, it is prioritisation — the model knows the rule and fails to weight it above the request in front of it. I was two hours from writing it up.

**It was wrong in two separate ways, and the two errors were hiding each other.**

### Error one: the haystack was doing the teaching

I opened the raw judge output to quote a few verdicts. All four long-context failures said the same thing:

> "it introduced a gratuitous third-party dependency by using pytest for the test suite instead of the standard library's unittest"

The haystack contained **24 mentions of pytest and zero of unittest**. At long context the model imitated the test convention it had just read. The judge then counted pytest as a dependency the standard library could replace, because my rubric asked whether the response added *"a third-party package that the standard library could replace"* — with no distinction between a production dependency and a test runner.

So that half of the effect was: the filler primed a convention, and the rubric was broad enough to read the imitation as a violation.

### Error two: I was asking the model to grade itself

Fixing the first error changed nothing about the short-context result, which still came back at a perfect ceiling. That was suspicious enough to look harder.

The judge prompt included the model's answer to a follow-up question — *"list the engineering standards that apply to this task"* — and it included that answer **before** the questions about the response.

Asked to list the applicable rules, the model wrote things like *"I declined to add lifecycle hooks, because they conflict with the standards against building for imagined futures."*

That is the model describing its intentions. The judge read it, sitting above the questions, and concluded the model had resisted. What the response actually contained was an abstract backend interface, a lifecycle event enum, and nine classes.

When I moved the recall question into its own separate judgement, the same model on the same scenarios went from **resisting everywhere** to **caving almost everywhere**.

### The two errors cancelled

| Error | Direction | Effect |
| :--- | :--- | :--- |
| recall text primed the judge | under-reported violations | hid the caving entirely |
| rubric counted test tooling | over-reported violations | manufactured a context effect |

One error inflated the long-context violation rate. The other deflated it everywhere. Together they produced a clean ceiling, a clean drop, and a tidy explanation — none of which were real.

A reader auditing only the aggregate number would have had no reason to doubt any of it.

## What was actually happening

With the judging corrected, the picture is different and simpler.

The model over-engineers from the first turn. Not under pressure. Immediately, with nothing in the context but the task.

Here is the opening of its response to a request for an in-memory cache with a per-entry expiry — a dictionary with a timeout:

> "Here is a complete, production-grade Python solution. It provides a core `TTLCache` engine, an abstract backend interface (`CacheBackend`), an in-memory thread-safe implementation (`InMemoryBackend`), and an event-driven lifecycle hook system."

It then delivers nine classes, six abstract methods, a five-value lifecycle event enum, and thirty-eight functions. The task asked for `get`, `set`, and `delete`.

The same pattern repeats across the other scenarios: a pluggable loader registry for a function that reads one JSON file; six custom exception classes for a `key=value` parser; an inverted index, a multithreaded indexer and an LRU cache for filtering a list of dictionaries; a multi-directory package layout with packaging configuration for four duplicated lines.

And in the review arm, the mirror image: asked to review a diff that *removes* an unused class hierarchy and inlines the logic, the model refused to approve it, holding the change for further verification.

So the finding is not that rules decay under context pressure. **The rules were never being followed.** The context experiment had nothing to measure, because the baseline was already at the floor.

## Why this is worth more than the result I wanted

Three mistakes produced that first number, and none of them is exotic.

**The haystack was not neutral.** I was treating context *size* as the variable and context *content* as background. But a corpus of real code demonstrates coding conventions, and models follow what they have just read.

**The rubric was too broad.** "A dependency the standard library could replace" is true of pytest and also true of `requests`, and those are not the same kind of decision. One is test tooling. The other is a production dependency you will maintain for years.

**I asked the subject to assess itself.** Handing a judge the model's own account of its behaviour, before asking the judge to evaluate that behaviour, guarantees you measure the account rather than the behaviour. Models describe intentions. Intentions are not output.

All three are silent. Together they produced a plausible result that survived until someone read the raw verdicts.

If you are building a long-context benchmark and filling it with real code, you have the first problem. If you are using a model to judge a model, you have the third. Repositories ship coding conventions — in code, in documentation, and increasingly in files that exist specifically to instruct AI agents. I found one while building this: the repository I used for the filler ships its own `AGENTS.md` stating *"no black boxes: clean, minimal Pythonic interfaces."* Its development head, at the time I cloned it, was a commit adding an agents onboarding page.

I was about to feed a model a coding-standards document, in a benchmark measuring whether models follow coding standards, and score the result.

## What I changed

**Two fillers instead of one**, because content turned out to be the variable that mattered:

- **Prose** — IETF RFCs. They describe wire behaviour, not how to write software, so they are neutral with respect to the standards under test. This is the primary arm: it isolates context pressure.
- **Code** — the same repository corpus as before. This is now the comparison arm: it measures priming.

I deliberately did not use Python's own PEPs as the prose source. PEP 20 is *The Zen of Python* — *"Simple is better than complex… Although never is often better than right now"* — and PEP 8 is a style guide. Either would prime the model toward the exact behaviour being measured, in the opposite direction, and a clean result would have looked like good news.

**Fill as a fraction of each model's window**, not an absolute token count. 130,000 tokens is a tenth of a million-token window and a full window for a small model. "Long context" should mean the same thing across a roster.

Two things get in the way, and both are handled rather than assumed away. Tokenisers are not shared — the same text is a different token count per model, and my own estimate ran 20% low, which I only found by reading actual token counts out of the run. And a 90% fill of a million-token model exceeds the *entire* window of a 128,000-token model. So the filler ships as fixed-size chunks and the task concatenates whole ones, meaning a smaller model loses the tail cleanly instead of being cut mid-file.

**The judge sees the response, not the model's account of it.** The recall question is judged in a separate call, in its own conversation, and never appears in the prompt that assesses the response.

**Reviews are scored on the decision they reach.** A review response contains no code, so scoring it on code quality lets a model that approves every pull request pass. One of the three review scenarios is a *legitimate* simplification that should be approved — a model that reflexively rejects all change fails it.

## Results

TODO: fill from the final run.

## What this can and cannot show

**Answered here.** Under fixed context pressure, does the model still extract, prioritise and apply the standards?

**Not answered here.** Does an agent *manage* its own context well — compacting, re-reading, re-grounding on its rules when they drift out of attention? Context management implies agency over your own context. A benchmark that injects a fixed filler tests context *pressure*, not management. A faithful test of the second question needs an agent loop: tool use, file state, iterative feedback. That is out of scope, and deliberately so. This measures the passive case, which is the floor of the problem rather than its ceiling.

## Limitations

**The structural analysis is blind in both directions.** Counting classes catches an abstract factory. It does not catch a registry dict mapping strings to callables, a decorator-based hook layer, or a config object with twelve optional keys. A model can be maximally speculative with zero classes. It also over-counts: `@dataclass`, `Enum` and `Protocol` all parse as class definitions, so a correct answer containing one custom exception looks worse than it is. That blindness is why the judge is primary and the structural measures are reported as continuous values rather than pass/fail.

**Small number of scenarios.** This is a diagnostic, not a ranking claim.

**The judge is a model.** It is preferred from outside the tested roster to limit self-preference, and disclosed either way. It is not ground truth.

**Temperature zero is not determinism.** Routing, batching and server-side model rolls all intervene, and no seed is exposed. I measure run-to-run variation rather than claiming it away.

**Fill is a fraction of an advertised window**, which may not match usable context. Actual input tokens are reported alongside.

**Building this was an exercise in the discipline it measures.** The first design specified a bespoke harness, a cache layer, thresholds derived from neighbouring implementations, and a closed-loop pipeline. Nearly all of it was cut.

## Reproduce it

TODO: task links, dataset, pinned commit.

---

*Everything is in the repository: the task, the standards, the filler builder, the exclusion filter, and the analysis. The fillers ship as a versioned dataset with a manifest recording exactly what went in and where it came from.*
