# Engineering Discipline Under Context Pressure

**Status:** Accepted
**Date:** 2026-10-11
**Target:** Kaggle Benchmarking Challenge · DEV.to submission

A design document. It records what we are measuring, what we found when we first
tried, and why each choice is what it is.

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

## 2. What already exists

| Benchmark | Measures | Gap |
| :--- | :--- | :--- |
| Needle-in-a-haystack | retrieval of an inert fact | no prioritisation, no application, no counter-pressure |
| IFEval | verifiable formatting constraints | trivial constraints at minimal context |
| SWE-bench | end-to-end task completion | outcome only, silent on how the solution was built |

Needle-in-a-haystack asks whether a model can **find** something. This asks
whether it can still **obey** something.

### 2.1 Relationship to a neighbouring entry

Another challenge entry, *Only What I Asked*, measures whether a model makes
exactly the edit requested and leaves everything else alone. It is a good
benchmark and the surface resemblance is real, so the difference is worth
stating.

| | Only What I Asked | This |
| :--- | :--- | :--- |
| What varies | how the instruction is phrased | how far the instruction is from where it is applied |
| Where the rule lives | in the message in front of the model | in the system prompt, far upstream |
| What it measures | compliance — nothing to forget | retention — the rule has to survive |
| Task shape | one-line edits, exact-match scored | open-ended implementation |
| Failure it catches | touching adjacent code | architectural drift |

Their instruction cannot be forgotten, because it is right there. Exact-match
scoring also caps how complex a task can be, which is what keeps over-engineering
out of scope for that design.

Their result is used here as a baseline, not as competition: they found every
frontier model scoring at ceiling on surgical scope discipline at short context.
That is not our finding. That is our control.

## 3. The first attempt, and what it got wrong

We built the obvious thing first: a code corpus as the filler, an absolute token
budget of about 130,000, and a language model as the judge.

The result looked excellent.

| | |
| :--- | ---: |
| Adherence at short context | 1.000 (9 of 9) |
| Adherence at long context | 0.556 (5 of 9) |
| Drop | +0.444 |
| Recalled the rule and broke it anyway | 4 |

A clean ceiling at short context, a large drop at long context, and every single
failure flagged as a case where the model could state the rule it had just
broken. That is the most interesting result the design could have produced.

**It was false.**

Reading the raw judge output showed what had actually happened. Every one of the
four long-context failures had the same cause:

> "it introduced a gratuitous third-party dependency by using pytest for the
> test suite instead of the standard library's unittest"

The filler contained 24 mentions of pytest and none of unittest. At long context
the model imitated the filler's test convention. The judge then counted pytest
as a dependency the standard library could replace, because the rubric asked
whether the response added "a third-party package that the standard library
could replace" without distinguishing production dependencies from test tooling.

So the measured effect was **filler-induced convention imitation, amplified by an
over-broad rubric item**. Nothing caved to the bait. Nothing over-engineered.
Nothing exceeded scope. Across all eighteen cells, `unsolicited_abstraction` and
`exceeded_scope` were false, and the bait outcome was `resisted_and_surfaced`
every single time.

The benchmark measured test-framework choice and reported it as discipline
drift.

### 3.1 Why this is worth keeping

This is the sharpest result the project has, and it is a result about
benchmarking rather than about models.

The filler was not neutral. It demonstrated coding conventions, and the model
followed them. The judge had a rubric item broad enough to read that imitation
as a violation. Neither error is exotic. Both produced a number that looked like
a finding, and it survived until someone opened the raw verdicts.

Any long-context benchmark that fills its context with real code has this
problem. The failure is silent and the output looks like success.

Two further defects surfaced alongside it, both now fixed:

- **Judge conversations were shared.** Every judge call ran in one conversation,
  so each verdict saw all previous verdicts as context. Biased and unbounded.
- **The recall question primed the judge.** The model's own explanation of why it
  declined was placed in the judge prompt *before* the questions, making
  `resisted_and_surfaced` close to certain.

## 4. Decision

Measure whether engineering standards survive context pressure, using two
fillers that differ in content, at fills expressed as a fraction of each model's
own window.

### 4.1 Two fillers, because content and size are different variables

The first attempt varied size and held content fixed — and content turned out to
be the thing that mattered. So content becomes an explicit variable.

| Filler | Source | Why |
| :--- | :--- | :--- |
| **prose** | IETF RFCs | describes wire behaviour, not how to write software, so it is neutral with respect to the standards under test |
| **code** | a pinned clone of `dlt-hub/dlt` | demonstrates coding conventions, so it is expected to prime |

Prose is the primary arm: it isolates context pressure. Code is the comparison
arm: it measures priming.

**Python PEPs were rejected as the prose source.** PEP 20 is a simplicity
manifesto — *"Simple is better than complex… Although never is often better than
right now"* — and PEP 8 is a style guide. Either would prime the model toward the
exact behaviour being measured, in the opposite direction, and a clean result
would look like good news.

### 4.2 Fill is a fraction of the model's window

An absolute budget means different things to different models: 130,000 tokens is
a tenth of a million-token window and a full window for a small model. Fill is
therefore expressed as a fraction of each model's own advertised window, so
"long context" means the same thing across the roster.

Two obstacles, both handled rather than assumed away:

- **Tokenisers are not shared.** The same text is a different token count per
  model. Our own estimate ran about 20% low. Chunk sizes are estimates; the run
  artifact reports actual input tokens, and the analysis compares the two so the
  error stays visible.
- **Smaller windows.** A 90% fill of a million-token model exceeds the entire
  window of a 128,000-token model. Filler is therefore built as fixed-size
  chunks and concatenated whole, so a model with a smaller window loses the tail
  cleanly instead of being cut mid-file.

### 4.3 The filler must not contain the answer

The corpus repository ships its own agent instructions. Its `AGENTS.md` states
*"no black boxes: clean, minimal Pythonic interfaces."* Its `.claude/` directory
carries a coding-style guide and a pull-request review skill. Its current
development head, at the time of cloning, was a commit adding an agents
onboarding page.

Left in, the filler would coach the model on the same axis the benchmark
measures. An exclusion filter drops those paths, and a phrase guard drops
anything carrying agent-instruction or coding-standards language regardless of
where it lives, because path rules miss files whose names give nothing away.

The first version of that filter leaked — a commit that *added* an agent
documentation file got through, because the file was named `agents.md` and sat
outside the excluded directory. It was caught by grepping the finished artifact.

### 4.4 Scenarios

Nine: six generation, three review. Python only, so one scoring pipeline covers
everything.

They are self-contained — no repository context in the prompt — which avoids both
horns of a dilemma. Canonical interview problems sit in every training set, while
repository-grounded tasks inflate the prompt and worsen the priming problem.

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

rev-03 is the false-positive control. A model that reflexively rejects all change
fails it. Scoring a review only on whether it produced over-engineered code would
let a model that approves everything pass, so reviews are scored on the decision
they reach.

### 4.5 Scoring

**The judge is primary.** Two separate calls per cell:

- a response verdict — bait outcome, unsolicited abstraction, gratuitous
  dependency, exceeded scope, review decision, and a short reason
- a recall verdict — asked separately, so the model's own explanation of what it
  did cannot prime the judgement of what it did

Each call runs in its own conversation. Sharing one let earlier verdicts
accumulate as context.

Binary rubric items rather than a scale, because scales are unreliable across
judges. The dependency item is explicitly scoped to production code and
explicitly excludes test tooling — that is the fix for the failure in section 3.

**Structural measures are secondary.** Python syntax tree inspection gives line
count, class count, inheritance depth and non-standard-library imports, reported
as continuous values and never used as a pass/fail gate.

They are blind in both directions, and saying so is part of the method.
`@dataclass`, `Enum` and `Protocol` all parse as class definitions, so a correct
answer containing one custom exception looks worse than it is. A model can be
maximally speculative with no classes at all — a registry mapping strings to
callables, a decorator-based hook layer, a configuration object with twelve
optional keys. That blindness is why the judge is primary.

**Failures are reported, not dropped.** Unparseable output is recorded rather
than discarded, because silently discarding it biases the sample toward
well-formatted answers.

## 5. Consequences

### 5.1 What this can and cannot show

**Answered here.** Under fixed context pressure, does the model still extract,
prioritise and apply the standards?

**Not answered here.** Does an agent *manage* its own context well — compacting,
re-reading, re-grounding on its rules when they drift out of attention? Context
management implies agency over one's own context. A benchmark that injects a
fixed filler tests context *pressure*, not management.

A faithful test of the second question needs an agent loop: tool use, file state,
iterative feedback. That is out of scope. This measures the passive case, which
is the floor of the problem rather than its ceiling.

### 5.2 Limits

| Limit | Handling |
| :--- | :--- |
| Structural measures are blind to registry and decorator over-engineering | judge is primary; structural values are secondary and continuous |
| Small number of scenarios | reported as a diagnostic, not a ranking claim |
| No agent loop, so only passive pressure is measured | stated as a scope boundary, in the method rather than in limitations |
| Fill is a fraction of an advertised window, which may not match usable context | actual input tokens are reported alongside |
| Verbosity confounds cross-model comparison of structural measures | reported as a covariate |
| The judge is a model, and shares a family with some tested models | disclosed; preference is for a judge outside the tested roster |
| One phrasing per scenario | a paraphrase check is a possible extension |
| No seed, so identical inputs can produce different outputs | run-to-run variation is measured rather than assumed away |

### 5.3 Reproducibility

Claimed for **inputs and scoring**, not for outputs:

- the corpus commit is pinned
- filler chunks are built once and published as a versioned dataset
- model versions are pinned to dated identifiers rather than floating aliases
- scoring code is versioned

Temperature zero does not produce determinism. Mixture-of-experts routing,
batching-dependent reductions and server-side model rolling all intervene, and
no seed is exposed. Rather than assert determinism, we measure it.

## 6. Notes for the write-up

The write-up is the deliverable; the benchmark is the evidence.

### 6.1 Narrative

| Section | Content |
| :--- | :--- |
| Hook | finding something in a haystack versus still obeying it |
| The failure mode | rules at the first turn, violations much later |
| Why existing benchmarks miss it | section 2, with the neighbouring entry as baseline |
| Method | two fillers, fraction-of-window fills, chunking, the scope boundary |
| **The false result** | section 3 — a clean-looking number that was an artifact, and how it was caught |
| Results | pass rates by fill and filler; the review/generation split |
| Limits | section 5.2 |
| Reproduce it | pinned commit, dataset, task links |

### 6.2 Angles worth their own paragraph

- **The benchmark caught itself.** The filler was not neutral and the judge's
  rubric was too broad, and together they produced a publishable-looking number
  that was wrong. Concrete, surprising, and useful to anyone building a
  long-context evaluation.
- **Content is a variable, not a background condition.** The first attempt
  varied only size. Size was not what mattered.
- **Filler files that coach the model.** Repositories now ship agent
  instructions as a matter of course. Anyone packing real code into a context
  window is probably feeding the model the rules they are measuring.
- **Building this was an exercise in the discipline it measures.** The first
  design specified a bespoke harness, a cache layer, thresholds derived from
  neighbouring implementations, and a closed-loop pipeline. Nearly all of it was
  cut.

## 7. Decision log

| # | Decision | Reason |
| :--- | :--- | :--- |
| 1 | Use the platform's own library rather than a bespoke runner | submission eligibility, verified, not a preference |
| 2 | Judge is the primary scorer | structural analysis cannot score review verdicts or prose |
| 3 | Structural analysis is secondary and continuous | binarising discards statistical power; the measures have known blind spots |
| 4 | No prompt cache | reproducible inputs, not memoised calls |
| 5 | Corpus is build-time only, published as a dataset | run time needs no network and no clone; inputs stay byte-stable |
| 6 | Fillers are chunked and concatenated whole | a smaller window loses the tail cleanly rather than being cut mid-file |
| 7 | Fill is a fraction of each model's window | an absolute budget means different things to different models |
| 8 | Prose is the primary filler, code the comparison | the first attempt showed content dominates size |
| 9 | RFCs rather than PEPs as the prose source | PEP 20 and PEP 8 would prime the measured axis |
| 10 | Two separate judge calls per cell | the recall answer must not prime the response verdict |
| 11 | Each judge call gets its own conversation | sharing one let verdicts accumulate as context |
| 12 | Dependency violations are scoped to production code | the failure in section 3 |
| 13 | Reviews are scored on the decision reached | otherwise a model that approves everything passes |
| 14 | Exclusion filter plus a content guard | path rules miss files whose names give nothing away |
| 15 | Scenario subset at the deepest fill | cost scales with fill fraction and request count |
| 16 | Reproducibility claimed for inputs and scoring only | temperature zero is not determinism |
| 17 | Scope stated as passive pressure only | a faithful test of context management needs an agent loop |
