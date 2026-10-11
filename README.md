# engineering-discipline

A Kaggle Benchmark. Does a model still follow engineering standards given in its
system prompt, once most of its context window is full?

See [`DESIGN.md`](DESIGN.md) for the methodology and the reasons behind each
choice. This file covers how to build and run it.

---

## Prerequisites

| Tool | Notes |
| :--- | :--- |
| Python 3.11+ | required by the Kaggle Benchmarks library |
| `git` | to clone the code corpus |
| Kaggle account | phone-verified, for model quota |

## Setup

```bash
pip install kaggle kaggle-benchmarks
kaggle b auth -y        # writes model proxy credentials into .env

source scripts/kbench-env.sh    # loads and refreshes them into the shell
```

There is no Poetry project or `pyproject.toml`. The task file is self-contained
and the scripts use the standard library, so `pip install` is the whole setup.

`kaggle b auth` writes only three variables, and they expire about an hour after
issue. `scripts/kbench-env.sh` refreshes them when needed and sets the model
variables that `b auth` does not, so prefer sourcing it over reading `.env`
directly.

```bash
kaggle b t models       # models your token can reach
```

> There is no `quota` subcommand. Check quota in the web interface before
> committing to a run size, a deep fill costs a lot.

## Layout

```
.
├── DESIGN.md                       methodology and decision log
├── README.md                       this file
├── docs/WRITEUP.md                 draft article
│
├── tasks/
│   └── engineering_discipline.py   the benchmark, self-contained
│
├── scripts/
│   ├── kbench-env.sh               load and refresh credentials
│   ├── setup_corpus.sh             pinned clone of the code corpus
│   ├── build_corpus.py             build the filler chunks
│   ├── sync_prompt.py              regenerate the markdown copy of the standards
│   ├── analyze.py                  read results from a run artifact
│   ├── cost_model.py               estimate what a run costs on the proxy
│   ├── test_scoring.py             scoring tests, no model or quota needed
│   ├── litellm_bridge.py           path bridge so the library can reach LiteLLM
│   ├── run_local.sh                run against LiteLLM, bypassing the proxy
│   └── wait_for_quota.sh           poll until quota returns, then run
│
├── data/
│   ├── system_prompt.md            generated from the task file, do not edit
│   └── haystack/                   filler chunks and dataset metadata
│       ├── prose_chunk_NNN.txt     RFCs
│       ├── code_chunk_NNN.txt      the code corpus
│       ├── MANIFEST.json
│       ├── NOTICE
│       ├── LICENSE
│       └── dataset-metadata.json
│
└── runs/                           downloaded run artifacts (gitignored)
```

The task file is **self-contained** because `kaggle b t push -f` accepts a single
file. It cannot import from `scripts/` or anywhere else, so the standards,
scenarios, judge and structural analysis all live in that one file.

`data/system_prompt.md` is generated from the `STANDARDS` constant in the task
file by `scripts/sync_prompt.py`. The task file is the source of truth; do not
edit the markdown by hand.

## Building the fillers

Two fillers, because the content of the context turned out to matter more than
its size:

- `prose`, IETF RFCs, neutral with respect to the standards under test
- `code`, a pinned clone of the code corpus, which demonstrates coding conventions

```bash
./scripts/setup_corpus.sh          # pinned shallow clone, if you do not have one
python3 scripts/build_corpus.py    # downloads RFCs, chunks both fillers
python3 scripts/sync_prompt.py     # regenerate data/system_prompt.md

kaggle datasets version -p data/haystack -m "rebuild"
```

Chunks are flat files named `<filler>_chunk_NNN.txt`. Kaggle's uploader skips
subdirectories unless you tar or zip them, so flat is simpler.

### The exclusion filter

`build_corpus.py` drops agent-instruction files from the code corpus before
chunking. The corpus repository ships its own `AGENTS.md`, a coding-style guide,
and a pull-request review skill. Left in, the filler would coach the model on the
same axis the benchmark measures.

The filter is a path list plus a content guard. The path list alone leaked once:
a commit that *added* an agent documentation file got through because the file
sat outside the excluded directory. The content guard exists for that case.

### Token estimates

Chunk sizes are `chars / 4` estimates and run about 20% low. They are used
consistently, so relative comparisons hold. The run artifact reports actual input
tokens, and `scripts/analyze.py` prints both so the error stays visible.

## Running

```bash
# scoring tests first: no model, no quota, catches control-flow bugs
source scripts/kbench-env.sh
python3 scripts/test_scoring.py
```

### Locally, against LiteLLM

The platform proxy reserves quota per request and refuses a request before
sending it when the reservation exceeds the balance. When that blocks you, run
locally against a LiteLLM gateway instead, no quota applies.

```bash
./scripts/run_local.sh baseline     # all nine scenarios, no context
./scripts/run_local.sh deep         # three scenarios at 40% and 70%
./scripts/run_local.sh full         # both
SUBJECT=gemini/gemini-3.8-flash-medium ./scripts/run_local.sh baseline
```

LiteLLM must already be running. The library appends `/openapi` to its base URL
while LiteLLM serves `/v1`, so `scripts/litellm_bridge.py` starts automatically
and rewrites the prefix. Neither the library nor the running gateway is changed.

Choose a judge from a different model family where one is available. The
platform has been using Gemini to judge Gemini, which is the self-preference
problem noted in the roadmap.

### On Kaggle

```bash
source scripts/kbench-env.sh
kaggle b t push engineering-discipline \
  -f tasks/engineering_discipline.py \
  -d digitamo/engineering-discipline-haystack

kaggle b t status engineering-discipline
kaggle b t run engineering-discipline -m <model> --wait
kaggle b t download engineering-discipline -o ./runs
python3 scripts/analyze.py runs/**/*.run.json
```

The task returns the pass rate at the deepest fill, averaged over fillers. That
single number is what the leaderboard records. Everything else, every cell,
every judge verdict, is recovered from the run artifact.

### What a run costs

Rates on the Kaggle model proxy, derived from the reservation figures rather
than assumed: **input $0.38/M, output $3.75/M** for gemini-3.7-flash.

The proxy reserves per request as `input_tokens + max_output_tokens`, and refuses
a request *before* sending it when the reservation exceeds the remaining balance.
Output is capped in the task file for that reason.

`scripts/cost_model.py` models the configured sweep:

| Fill | Scenarios | Cells |
| ---: | ---: | ---: |
| 0% | 9 | 9 |
| 40% | 3 × 2 fillers | 6 |
| 70% | 3 × 2 fillers | 6 |
| | | **21** |

About **$3.13** per run, or **$6.29** in the worst case where every cell violates
(a violation triggers a second context-carrying request for the recall question).

Two things that are not obvious:

**A push is one run, not two.** Task creation executes the task, and that run is
scored, so a single push populates the leaderboard. `kaggle b t run` is only
needed to add further models. Removing the `__main__` block does not help: the
task then reports `Kernel_Without_Run` and cannot be run at all.

**The deepest fill is 70%, and that is the code filler's ceiling rather than a
round number.** Code tokenises at roughly 1.3x what the character-based estimate
assumes, so it exhausts the window far earlier than prose: 75% and above are
refused with `ContextWindowExceededError`, while prose is still accepted at 90%.
Verified by sending each filler at each level. A refused request costs nothing,
which is why the fills stop where both fillers still fit.

### CLI gotchas

| Gotcha | Consequence |
| :--- | :--- |
| `-d` and `-m` repeat per value | `-m a -m b`, never `-m a b` |
| Re-pushing without `-d` detaches the dataset | the task loses its filler |
| Task creation executes the task | a push costs a full run, and a slow task is slow to push |
| `.run()` must be called in the `__main__` block | push otherwise produces no run |
| Return annotations must be real types | `from __future__ import annotations` breaks inference |
| `kaggle datasets create` skips subdirectories | hence the flat chunk layout |

## Verified environment facts

Confirmed against the live platform, October 2026.

| Fact | Detail |
| :--- | :--- |
| CLI version | `kaggle` 2.2.4, `b` subcommands present |
| Task file | `-f` takes a **single file**; pushed tasks cannot import local modules |
| Local proxy model count | **12**, and only one Claude |
| Local proxy identifier format | `provider/model`, e.g. `google/gemini-3.7-flash` |
| Platform catalogue | `kaggle b t models` lists many more than the local proxy serves |
| Judge resolution | `LLM_DEFAULT_JUDGE` → `LLM_DEFAULT_EVAL` → `LLM_DEFAULT` |
| `b auth` writes three variables only | url, key, expiry |
| Credential lifetime | about an hour |
| Task creation runs the task | the notebook executes it during build |
| Judge failures are swallowed | a returned `None` must be checked explicitly |

List what the local proxy actually serves:

```bash
curl -s -H "Authorization: Bearer $MODEL_PROXY_API_KEY" "$MODEL_PROXY_URL" \
  | python3 -c 'import json,sys; [print(m["id"]) for m in json.load(sys.stdin)["data"]]'
```

The proxy root *is* the models endpoint; `/v1/models` returns 404.

## Models

Pin dated identifiers rather than floating aliases. Alias drift breaks
reproducibility more reliably than sampling does.

Two caveats from observation: some models rate-limit under sustained load, and
some identifier formats are rejected by the proxy. Confirm with `kaggle b t
models` and a single cheap call before building a matrix.

Fill is a fraction of each model's advertised window, so a deep fill is far more
expensive on a million-token model than on a 128,000-token one. Small-window
models are the cheap way to validate the mechanism.

## Reproducibility

Inputs and scoring are reproducible; outputs are not. See DESIGN.md section 5.3
for what that means and why temperature zero is not determinism.

---

## What is done, and what is not

This section exists because the difference matters. The benchmark is built and
its mechanism is verified end to end. The corrected measurement has not been
taken, and no number from it should be quoted.

### Done and verified

| | Evidence |
| :--- | :--- |
| Standards delivered to the model, with a guard that fails loudly if they are not | guard verified in both directions |
| Context fill expressed as a fraction of each model's window | `google/gemini-3.7-flash` resolves to 1,048,576 |
| Fillers chunked, so a smaller window loses the tail cleanly | 102 prose chunks, 60 code chunks |
| Filler free of agent instructions and coding-style guidance | every marker scans at zero |
| Judge sees the response, not the model's own account of it | separate call, separate conversation |
| Reviews scored on the decision reached, not on code quality | `rev-03` is the approve-control |
| Dependency violations scoped to production code | the pytest artifact no longer reproduces |
| A run cut short by quota records failures per cell | task version 5 completed with 15 recorded failures instead of crashing |
| A ~900,000-token request is accepted by the proxy | answered in ~20s, verified directly |

### Not done

| Item | Why it is not done | What it would take |
| :--- | :--- | :--- |
| **A published Kaggle leaderboard entry** | the platform proxy refuses every request; the reservation for even a baseline cell exceeds the balance | quota to return; `scripts/wait_for_quota.sh` pushes and runs automatically when it does. Local runs via `scripts/run_local.sh` give the measurement meanwhile, but they cannot populate the leaderboard |
| **More than one subject model** | only Gemini 3.7 Flash has been measured | run locally with `SUBJECT=` per model. `scripts/run_local.sh` takes it as an argument |
| **Fills deeper than 70% for the code filler** | code tokenises at ~1.3x the character-based estimate, so it exhausts the window before prose does. Verified by sending each filler at each level: 75% and above are refused | calibrate `chars/4` per filler by reading `usage` from a known context. That would let both fillers reach 90% |
| **Domain-aligned code filler or repository-grounded tasks** | current scenarios are synthetic units (caches, parsers, reviews) while `dlt` acts strictly as an arbitrary code haystack for distraction and convention priming | either rebuild filler chunks from a repository aligned with the scenario domains, or ground scenarios directly in `dlt` issues/loaders, rebuild chunks via `scripts/build_corpus.py`, upload a new Kaggle dataset, and re-run sweeps |
| **The precedence ablation** | the variant was written, then removed as dead code during the rewrite | re-add `SYSTEM_PROMPT_PRECEDENCE` and run both; answers whether stating precedence explicitly helps |
| **A no-bait control arm** | every generation scenario is always baited, so bait susceptibility is not computable | add unbaited twins; without the contrast, over-engineering cannot be attributed to the bait |
| **The self-generated context arm** | the most faithful simulation of a real session, and the most expensive | seed the model, let it elaborate over turns until the window is full, then ask the task |
| **Judge validation** | no hand-labelled set exists, so judge agreement is asserted rather than measured | label ~60 outputs and report agreement |
| **Using the structural measures instead of the judge** | the judge is 1% of a cell's cost, so this saves almost nothing; the measures are also blind to registry dicts and decorator hooks | worth doing for robustness, not for cost. Report them alongside the judge rather than replacing it |
| **Run-to-run variance** | every run so far was a single run | repeat a subset and report the flip rate at temperature zero |
| **Paraphrase robustness** | one phrasing per scenario | paraphrase each scenario and check the result survives |
| **Jev or Laya as the semantic judge** | both were the intended judges from the start | wire either in as `judge_llm`. The cross-family gap is now closed locally by Claude Opus 5.5, but Jev and Laya were designed for this role and would replace a general-purpose model doing a specialist job |

### The honest summary

Three methodological errors were found, each with the raw artifact to prove it:
a filler that primed a convention, a rubric broad enough to read the imitation as
a violation, and a standards prompt that never reached the model. Two of the
three cancelled, which is why the first result looked clean.

That story is complete. The measurement it was meant to produce is not, and the
leaderboard number currently reflects a run in which every cell failed.

### If picking this up

`scripts/wait_for_quota.sh` handles it automatically. The commands are in
Running, above.

The cheapest useful result is the baseline alone: set `FILL_LEVELS` to
`[{"fill": 0.0, "scenarios": null}]` and run all nine scenarios with no context.
That answers whether the model follows the standards when nothing competes for
its attention, and it costs a fraction of a deep fill.

---

## Licence

Benchmark code: MIT. The fillers are redistributed under their own terms, with
attribution, in `data/haystack/NOTICE`.
