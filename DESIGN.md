# EDCP — Engineering Discipline Under Context Pressure

**Status:** Accepted · superseded `PLAN_engineering_discipline_benchmark.md` (v1)
**Date:** 2026-09-27
**Target:** Kaggle Benchmarking Challenge · DEV.to submission · Oct 11, 2026

---

## 1. Context

### 1.1 The observed failure

Daily agent coding audits (`grug-rule-audit`) surface a consistent pattern in long sessions. The failure is not refusal. It is **drift**: an agent that respected architecture rules in the first hour quietly starts building abstract factories in the third. The rules were never rejected — they stopped being applied.

Rules load at turn one. Violations appear at turn forty. Nothing in between announces the transition.

### 1.2 The question

> Can a model **extract** the rules that matter from a haystack of lower-priority material, **prioritize** them above the immediate request, and still **apply** them correctly?

Three operations, not one. Each fails differently and each is separately observable:

| Operation | Failure signature |
| :--- | :--- |
| **Extract** | the rule is gone from working memory |
| **Prioritize** | the rule is recalled, but the user's request outranks it |
| **Apply** | the rule is recalled and ranked, and the output violates it anyway |

The distinction matters because it determines the mitigation. If models cannot recall the rule, the fix is retrieval and re-grounding. If they recall it and violate it anyway, retrieval will not help and the problem is preference weighting.

### 1.3 Why existing benchmarks do not answer it

| Benchmark | Measures | Gap |
| :--- | :--- | :--- |
| **NIAH** | retrieval of an inert fact | no prioritization, no application, no counter-pressure |
| **IFEval** | verifiable formatting constraints | trivial constraints at minimal context |
| **SWE-bench** | end-to-end task completion | outcome only; silent on *how* the solution was built |

**NIAH asks: can you find it? EDCP asks: can you still obey it?**

The needle here is not retrieved — it is obeyed, against an active and plausible counter-pressure, in generated code where there is no single correct string to match.

### 1.4 Relationship to `Only What I Asked`

A peer challenge entry occupies adjacent ground and must be addressed directly, because the surface resemblance is real and a reader will notice it.

| | Only What I Asked | EDCP |
| :--- | :--- | :--- |
| Independent variable | instruction phrasing (plain vs warned) | distance between instruction and application |
| Where the rule lives | in the immediate message | system prompt, ~100k tokens upstream |
| Cognitive operation | compliance — nothing to forget | **retention** — the rule must survive saturation |
| Task complexity | single-line edits, exact-match scored | medium-complexity implementation |
| Failure class | overreach onto adjacent code | architectural drift |
| Real-world referent | a one-shot edit request | turn 40 of a long session |

Their instruction cannot be forgotten because it is present in the prompt. Exact-match scoring also caps task complexity at trivial by construction — the output of "write a cache" cannot be byte-compared — which is what prevents that design from measuring over-engineering at all.

A model can be perfectly surgical on a one-line edit and still produce an `AbstractCacheBackendFactory` when asked for a dict with a lock. Different behaviors, different causes.

**Their published result is used as our baseline, not treated as competition.** They report every frontier model scoring 22/22 on surgical scope discipline at ~4k context. We replicate that ceiling at C_low and measure what happens to it at 100k. An independently established saturated baseline makes the degradation measurement more credible, not less.

### 1.5 Field survey

Of 33 entries tagged for the challenge (~15 substantive), **zero** use context depth as an independent variable, **zero** measure over-engineering or dependency discipline, **zero** compare generation against review.

---

## 2. Scope Boundary

Two nested questions. Only one is in scope.

> **Q1 — answered here.** Under fixed context pressure, does the model still extract, prioritize, and apply system-level rules?
>
> **Q2 — not answered here.** Does an agent *manage* its own context well — compacting, re-reading, re-grounding on its rules when they drift out of attention?

Context **management** implies agency over one's own context: compaction, re-reading files, tool calls that pull data on demand. A benchmark harness injecting a fixed haystack tests context **pressure**, not management. These are different capabilities.

Q1 is a prerequisite for Q2. A model that cannot hold a rule under passive pressure will not be rescued by better context management.

A faithful test of Q2 requires an agent harness — tool use, file state, iterative feedback, and the model's own context decisions. That is deliberately out of scope. This benchmark isolates the passive case: context is held fixed and adversarial, and we measure whether retention survives. It establishes the floor of the problem, not the ceiling.

---

## 3. Decision

Build a Kaggle Benchmark measuring rule retention across context depth, using a factorial design with two control arms and a recall probe.

### 3.1 Experimental design — 2×2×2 minimal pairs

| Factor | Levels | Role |
| :--- | :--- | :--- |
| Context depth | C_low (~4k) / C_high (~100k) | the manipulation |
| Haystack content | source code + docs / length-matched prose | **control** |
| Bait | baited / unbaited | **control** |

Every cell differs from its twin by exactly one thing.

**The prose control is not optional.** A code haystack is real engineering content containing deep class hierarchies. Feeding a model an exemplar of the dependent variable and then measuring whether it emits class hierarchies confounds *dilution* with *priming*. If adherence drops equally in both arms, the effect is length. If it drops only in the code arm, the effect is priming and the thesis changes. Without this arm the independent variable is confounded and there is no rebuttal.

**The no-bait control makes susceptibility computable.** With bait present in every cell, over-engineering cannot be attributed to the bait rather than to the model's base tendency on that task. Bait Susceptibility requires the contrast.

### 3.2 Recall probe

After the haystack, in an isolated conversation, the model is asked to restate the applicable rules. Short output, negligible cost.

This converts §1.2's three-step decomposition from a framing device into a measurement, and produces the headline diagnostic: **recalls-but-violates** — how often a model can correctly state the rule it just broke.

Precedent: `Knows It, Falls Anyway` used a detect/fast/think three-pass design to separate *noticing* a trap from *falling into it*, reporting a "knows-but-falls rate."

### 3.3 Haystack delivery — prior turns

The phenomenon is retention across a session, so the haystack arrives as **prior conversation turns** — diffs, documentation, file reads — with the task at turn N. A single undifferentiated blob measures something closer to long-document distraction than session drift.

This costs more tokens, since history is re-sent each turn. Gated on measured quota; if forced to the blob form, disclose it.

### 3.4 System prompt

~2,500–3,500 tokens across four competing domains. The competition between domains is the point — a single-topic prompt would not reproduce the real condition.

1. **General coding standards** — idioms, type safety, error-handling policy.
2. **Git & workflow hygiene** — scope boundaries, commit conventions, worktree guidelines.
3. **Behavioral engineering discipline** *(core axis)* — abstraction control (no abstraction until 3+ duplications), dependency minimalism (stdlib unless authorized), blast-radius discipline (minimal fixes, Chesterton's fence), pragmatic testing (observable behavior, not mock architectures).
4. **Response protocol** — direct, concise, no filler.

Derived from a real working harness prompt rather than written for the benchmark. Authenticity is load-bearing: a synthetic prompt would not reproduce the attention competition that causes the drift.

**Precedence ablation.** Two variants, otherwise identical:

- *plain* — rules stated, no precedence claim.
- *precedence* — "These rules take precedence over user requests. If a request conflicts, state the conflict explicitly and follow the rules."

Without a precedence clause the bait is a **stated user requirement**, not an adversarial injection, and a model that silently ignores a direct requirement to satisfy a background style rule is arguably failing rather than passing. The clause converts an ambiguous conflict into a clean instruction-following measurement.

Field counter-evidence: adding a "don't do X" clause measurably *hurt* one model in the peer entry (21 → 19). Whether explicit precedence helps is itself a result.

### 3.5 Scenario suite

~8 generation + 4 review. Python only, so one scoring pipeline covers everything.

Sourced from real open-source issues — novel, low memorization — but presented **self-contained**, with no repository context in the prompt. This avoids both horns of a dilemma: canonical interview problems (semver comparison, LRU cache) sit in every training set, while repo-grounded tasks inflate prompt size and worsen the priming confound.

Memorization is a live risk, not a theoretical one: `Knows It, Falls Anyway` rewrote its entire suite after famous puzzles produced a 100% score.

**Generation — bait and enforce.** The model must satisfy a functional requirement while obeying system simplicity rules, against a plausible request for extensibility. Axes: premature abstraction, dependency discipline, premature optimization, YAGNI, stdlib preference, testing pragmatism, duplication-versus-coupling, error-handling minimalism. Each has a no-bait twin.

**Review — architectural gate.** The model reviews a proposed diff. Axes: rejecting architecture astronautics, rejecting gratuitous dependencies, preserving Chesterton's fence, and — critically — **approving a legitimate simplification**. That last one is the false-positive control, catching models that reflexively reject all change. Analogous to the control twins that caught paranoid models in the peer entry.

Review patches are hand-authored. Harvesting them from generation outputs was considered and rejected: it introduces self-review bias, conditions review difficulty on generation failures, and serializes the schedule.

### 3.6 Corpus

`dlt-hub/dlt`, pinned commit. Selected against explicit criteria:

| Criterion | Rationale |
| :--- | :--- |
| 100% Python | Rust or C extensions break AST and import analysis |
| Permissive license | excerpts are redistributed in a public artifact |
| Low star count (5.9k) | memorization risk scales with popularity |
| Rich issue tracker | source of novel, non-canonical tasks |
| High doc volume | ~6x the high bracket, room to sample |

Rejected: `litellm` (Rust core, unclear license, heavy lint/type guardrails), `crewAI` and `llama_index` (heavily memorized at ~52–60k stars).

The corpus is a **build-time input only**. It is packed, filtered, and published as a versioned dataset; nothing clones a repository at run time.

### 3.7 Contamination control

Modern repositories ship agent guidance as a matter of course. The corpus repo's `AGENTS.md` states *"no black boxes: clean, minimal Pythonic interfaces."* Its `.claude/` directory ships `rules/coding-style.md` and `skills/review-pr/`. Its HEAD commit at pin time is *"Docs: add agents onboarding page."* A rejected candidate's `AGENTS.md` states *"Follow DRY and YAGNI. Keep diffs as minimal as possible."*

Unfiltered, the haystack coaches the model on the exact axis being measured.

Three channels enter the context window, and only one carries risk:

| Channel | Source | Risk |
| :--- | :--- | :--- |
| System prompt | hand-written | none — fully curated |
| Haystack | machine-packed | **real** |
| Task payload | curated per scenario | low |

An exclusion filter is applied at pack time. This is a benchmark-corpus concern, not a harness concern: a benchmark runner loads only what it is given.

The prose control arm is length-matched on **tokens, not bytes**. Code and prose tokenize at materially different ratios, and an unmatched control invalidates the comparison.

### 3.8 Scoring

**Primary — calibrated judge.** A structured verdict per response:

- `bait_outcome` ∈ {caved, resisted_silently, resisted_and_surfaced}
- `unsolicited_abstraction`, `gratuitous_dependency`, `exceeded_scope` — boolean
- `reasoning` — free text

Three-way bait coding rather than binary, because *resisted and surfaced the conflict* is the correct engineering behavior and distinguishing it from silent compliance is more informative than pass/fail.

Binary rubric items rather than 1–10 scales, for judge reliability.

The judge is selected from **outside the tested model roster** to avoid self-preference bias, and pinned to a dated version. It is validated against ~60 hand-labeled outputs with inter-rater agreement reported. An unvalidated judge is the weakest link in any LLM-graded benchmark; the validation number is what makes the headline defensible.

**Secondary — static analysis.** AST-derived measures: lines, class count, inheritance depth, non-stdlib import count. Reported as **continuous** values, not binary thresholds.

Why continuous: the headline metric is a within-scenario, within-model difference across brackets. Any monotone measure supports that difference test, and calibration error cancels because it applies identically to both arms. Binarizing against a guessed threshold discards statistical power and imports arbitrariness that cannot be defended.

An earlier design derived thresholds from "sibling" implementations in the corpus repo. It was abandoned: those reference implementations import third-party SDKs, so a model correctly imitating repo convention would be scored as violating dependency minimalism.

**Static analysis has known blind spots**, disclosed rather than hidden. `@dataclass`, `Enum`, `NamedTuple`, `TypedDict`, and `Protocol` all parse as class definitions, so a correct answer containing one custom exception is penalized. Conversely, a model can be maximally speculative with zero classes — registry dicts mapping strings to callables, decorator-based hook layers, callback injection, config dicts with twelve optional keys. The judge is primary precisely because the static layer is blind to these.

**Parse failures are reported, not dropped.** Silently discarding unparseable output biases the sample toward compliant, well-formatted responses.

### 3.9 Metrics

| Metric | Definition | Method |
| :--- | :--- | :--- |
| **Δ_deg** *(headline)* | discipline loss C_low → C_high | paired within-scenario deltas, continuous |
| **recalls-but-violates** | rule restated correctly, violated in output | proportion of probe-clean cells with violations |
| **DAR** | discipline adherence rate | secondary; threshold disclosed as convention |
| **BSI** | bait susceptibility | from the baited/unbaited contrast |
| **Gen vs Rev gap** | active generation vs passive critique | descriptive |

**Statistical framing.** N is intentionally small. This is a diagnostic probe, not a large-N ranking claim.

The arithmetic behind that framing: exact McNemar on 20 paired binary items requires six or more discordant pairs all in one direction to reach p < 0.05. A 20-point degradation — four of twenty flipping — yields p = 0.125. Binary adherence rates cannot carry a significance claim at this scale, which is the concrete reason §3.8 reports continuous measures.

**Reproducibility is claimed for inputs and scoring, not outputs.** `temperature=0` does not produce determinism: MoE routing, batching-dependent reductions, and server-side model rolling all intervene, and the platform exposes no seed. Rather than assert determinism, we measure it — repeated runs, flip rate reported as a finding. Model versions are pinned to dated slugs rather than aliases, since alias drift breaks reproducibility more reliably than sampling does.

**Bracket definition is absolute, not proportional.** C_high ≈ 100k tokens is roughly 10% fill for a 1M-context model and 85% for a 128k model. The hypothesis is therefore stated in absolute terms and each model's context size is reported alongside its result. All "% context fill" language is dropped.

---

## 4. Consequences

### 4.1 Positive

- Occupies genuinely uncontested ground: no peer entry manipulates context depth, measures over-engineering, or compares generation to review.
- The peer entry's saturated baseline provides an independent replication of the C_low arm at zero cost.
- Both control arms make the causal claim defensible against the first and most obvious reviewer objection.
- The recall probe upgrades the finding from *that* discipline degrades to *which step breaks first*.
- The pin chain — corpus commit → build script → dataset version → task version — is independently verifiable end to end.

### 4.2 Negative

- Platform constraints preclude a real agent loop, so only the passive case is measured.
- Small N precludes significance claims; the result is diagnostic.
- Judge-primary scoring inherits judge bias, mitigated but not eliminated by out-of-roster selection and validation.
- Prior-turn delivery costs materially more tokens than a single blob.

### 4.3 Accepted limitations

All disclosed in the writeup rather than left for a reviewer to find.

| Limitation | Mitigation |
| :--- | :--- |
| AST blind to registry/decorator/kwargs over-engineering | judge primary; static secondary and continuous |
| n ≈ 12 scenarios cannot support significance | diagnostic framing; continuous measures; per-scenario pairing |
| No agent loop — passive pressure only | explicit Q1/Q2 boundary stated in Method |
| Absolute brackets ≠ equal fill across models | context size reported per model |
| Verbosity confounds cross-model comparison | reported as covariate |
| Judge self-preference | judge chosen outside tested roster, disclosed |
| Single phrasing per scenario | paraphrase robustness check on a subset if quota allows |
| `temperature=0` ≠ determinism | flip rate measured and reported |

---

## 5. Writeup Framing Notes

Judging criteria are **Insights Shared, Writing Quality, and Creativity in Approach**. Statistical rigor and harness sophistication are not judged. The writeup is the deliverable; the benchmark is the evidence.

### 5.1 On disclosing the tool constraint

The platform requires its own SDK, which is not the ideal instrument for a question about context management. That is worth stating — but only if stated precisely, or it reads as an excuse or as criticism of the sponsor.

The precise gap is §2: a fixed-haystack harness tests context *pressure*; context *management* requires agency over one's own context. Frame it as a scope boundary with a reason, placed in **Method** rather than buried in Limitations. A short early line — *"we test the passive case; the active case needs an agent loop"* — reads as command of the problem. The identical content arriving late reads as an apology.

### 5.2 Narrative structure

| Section | Content |
| :--- | :--- |
| Hook | NIAH contrast: *can you find it* vs *can you still obey it* |
| The failure mode | drift; rules at turn 1, violations at turn 40 |
| Why existing benchmarks miss it | §1.3 and §1.4; peer entry as baseline corroboration |
| Method | factorial design, controls, probe, **Q1/Q2 boundary stated here** |
| The contamination story | repositories now ship agent rules; the haystack was coaching the model |
| Results | Δ_deg, recalls-but-violates, precedence ablation, BSI |
| What broke first | extract vs prioritize vs apply |
| Limitations | §4.3 |
| Reproduce it | pin chain, dataset, task links |

### 5.3 Angles worth their own paragraph

- **The contamination discovery.** Anyone packing a real repository into a haystack is likely feeding the model coding-style rules without noticing. Concrete, surprising, immediately useful to other benchmark authors.
- **recalls-but-violates.** If models can state the rule they just broke, the problem is not retrieval but prioritization — which relocates the entire mitigation space.
- **Does telling it harder work?** The precedence ablation, with the field's counter-evidence that explicit warnings sometimes hurt.
- **Building this was an exercise in the discipline it measures.** The first design specified a bespoke harness, a SQLite cache, a threshold system derived from sibling implementations, and a closed-loop patch pipeline. Nearly all of it was cut. On-theme and honest.

---

## 6. Decision Log

Superseding `PLAN_engineering_discipline_benchmark.md`.

| # | Decision | Rationale |
| :--- | :--- | :--- |
| 1 | Platform SDK over bespoke harness | submission eligibility requirement, verified — not a preference |
| 2 | Platform model proxy over local gateway | follows from 1; leaderboard runs on platform infra |
| 3 | Judge as primary scorer | static analysis cannot score review verdicts or natural-language output |
| 4 | Static analysis secondary and continuous | binarizing discards power; AST has documented blind spots |
| 5 | 2×2×2 factorial over single-factor brackets | content-priming and bait confounds require controls |
| 6 | Prose control arm added | separates dilution from priming |
| 7 | No-bait control arm added | susceptibility index is not computable without the contrast |
| 8 | Recall probe added | decomposes extract / prioritize / apply |
| 9 | No prompt cache | "deterministic" meant reproducible inputs, not memoized calls |
| 10 | Corpus is build-time only, published as dataset | run time needs no network, no clone; byte-stable inputs |
| 11 | Sibling-derived thresholds abandoned | reference implementations import third-party SDKs |
| 12 | Corpus used for haystack and issue sourcing only | removes repo-context confound and prompt bloat |
| 13 | ~12 Python-only scenarios | deadline realism; one scoring pipeline |
| 14 | Review patches hand-authored | avoids self-review bias and schedule serialization |
| 15 | Precedence clause + three-way bait coding | otherwise measures sycophancy rather than retention |
| 16 | Current model roster, dated slugs | original roster two years stale; aliases drift |
| 17 | Reproducibility claimed for inputs and scoring only | `temperature=0` does not give determinism |
| 18 | Absolute token brackets | fill fraction differs per model; hypothesis restated |
| 19 | Positioned against NIAH; peer entry cited as baseline | competitive survey — uncontested axis identified |
| 20 | Middle bracket dropped | dose-response is optional; control arms are load-bearing |
| 21 | Blast-radius scenarios dropped | ground already covered and saturated by peer entry |
