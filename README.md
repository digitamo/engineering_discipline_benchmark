# engineering-discipline

A Kaggle Benchmark. Does a model still follow engineering standards given in its
system prompt, once most of its context window is full?

See [`DESIGN.md`](DESIGN.md) for the methodology and the reasons behind each
choice. This file covers how to build and run it.

---

## Prerequisites

| Tool | Notes |
| :--- | :--- |
| `pyenv` | Python version management |
| Python 3.11+ | required by the Kaggle Benchmarks library |
| `poetry` | dependency management |
| `git` | to clone the code corpus |
| Kaggle account | phone-verified, for model quota |

## Setup

```bash
pyenv install 3.11.9 && pyenv local 3.11.9
poetry install && poetry shell

pip install kaggle
kaggle b auth -y        # writes model proxy credentials into .env

source scripts/kbench-env.sh    # loads and refreshes them into the shell
```

`kaggle b auth` writes only three variables, and they expire about an hour after
issue. `scripts/kbench-env.sh` refreshes them when needed and sets the model
variables that `b auth` does not, so prefer sourcing it over reading `.env`
directly.

```bash
kaggle b t models       # models your token can reach
```

> There is no `quota` subcommand. Check quota in the web interface before
> committing to a run size — a deep fill costs a lot.

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
│   ├── pilot.py                    small local run
│   └── analyze.py                  read results from a run artifact
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

- `prose` — IETF RFCs, neutral with respect to the standards under test
- `code` — a pinned clone of the code corpus, which demonstrates coding conventions

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
# iterate locally against a cheap model
source scripts/kbench-env.sh
python3 scripts/pilot.py

# push, with the filler dataset attached
kaggle b t push engineering-discipline \
  -f tasks/engineering_discipline.py \
  -d digitamo/engineering-discipline-haystack

kaggle b t status engineering-discipline
kaggle b t run engineering-discipline -m <model> --wait
kaggle b t download engineering-discipline -o ./runs
python3 scripts/analyze.py runs/**/*.run.json
```

The task returns the pass rate at the deepest fill, averaged over fillers. That
single number is what the leaderboard records. Everything else — every cell,
every judge verdict — is recovered from the run artifact.

### What a run costs

Cost scales with fill fraction times the number of requests per cell, and each
cell makes two requests carrying the full context (the task, then the recall
question). A 90% fill of a million-token window is roughly 900,000 tokens per
request.

The deepest fill therefore runs a scenario subset. Widen it in `FILL_LEVELS` in
the task file when quota allows.

A ~900,000-token request is accepted by the model proxy and answered in around
twenty seconds, verified directly.

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

Claimed for inputs and scoring, not for outputs. The corpus commit is pinned,
filler chunks are published as a versioned dataset, model identifiers are dated,
and scoring code is versioned.

Temperature zero is not determinism — routing, batching and server-side model
rolls all intervene, and no seed is exposed. Run-to-run variation is measured
rather than assumed away.

## Licence

Benchmark code: MIT. The fillers are redistributed under their own terms, with
attribution, in `data/haystack/NOTICE`.
