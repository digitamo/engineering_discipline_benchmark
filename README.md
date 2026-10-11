# edcp — Engineering Discipline Under Context Pressure

A Kaggle Benchmark measuring whether LLMs still apply system-prompt engineering rules after ~100k tokens of context.

**NIAH asks: can you find it? This asks: can you still obey it?**

See [`DESIGN.md`](DESIGN.md) for the research question, methodology, and decision record. This file covers how to build and run it.

---

## Prerequisites

| Tool | Version | Purpose |
| :--- | :--- | :--- |
| `pyenv` | — | Python version management |
| Python | 3.11+ | required by `kaggle-benchmarks` |
| `poetry` | — | dependency management |
| `git` | — | corpus clone |
| Kaggle account | phone-verified | model proxy quota access |

> Accounts registered after 2025-12-15 need additional identity verification to execute task notebooks.

---

## Setup

```bash
pyenv install 3.11.9 && pyenv local 3.11.9
poetry install
poetry shell

kaggle b init -y        # mints MODEL_PROXY_* creds into .env, scaffolds local dev
kaggle b t models       # confirm available model slugs
kaggle b quota          # CHECK THIS FIRST — it sizes the entire run matrix
```

`.env` after `kaggle b init`:

```env
MODEL_PROXY_URL=...
MODEL_PROXY_API_KEY=...
LLM_DEFAULT=<slug>           # kbench.llm
LLM_DEFAULT_EVAL=<slug>      # kbench.judge_llm
LLMS_AVAILABLE=<slug>,<slug> # authorized for your token

TARGET_REPO_URL=https://github.com/dlt-hub/dlt.git
TARGET_REPO_PATH=./target_repo
TARGET_REPO_COMMIT=ff414a0a4abbae8413678ff0da6fc66533236cc9
```

> **Quota gates the design, not engineering time.** Full 2×2×2 costs roughly 3M input tokens per model per repeat. Run `kaggle b quota` before committing to a matrix size. If forced to cut, cut repeats before control arms.

---

## Project structure

```
.
├── DESIGN.md                 # research question, methodology, decision log
├── README.md                 # this file
├── pyproject.toml
├── .env.example
│
├── tasks/                    # kbench entrypoints — one task per notebook
│   ├── edcp_gen.py           # generation arm
│   └── edcp_rev.py           # review arm
│
├── edcp/
│   ├── prompts.py            # SYSTEM_PROMPT_PLAIN | SYSTEM_PROMPT_PRECEDENCE
│   ├── corpus.py             # build-time packer + CORPUS_EXCLUDE
│   ├── static_eval.py        # AST measures -> @assertion_handler
│   ├── judge.py              # prompt_fn + DisciplineVerdict schema
│   └── probe.py              # rule-restatement recall check
│
├── scripts/
│   └── setup_corpus.sh       # pinned shallow clone
│
├── data/
│   ├── scenarios/*.json      # task specs
│   ├── patches/*.patch       # hand-authored review diffs
│   └── haystack/             # built artifact -> Kaggle Dataset
│       ├── code_high.txt
│       ├── prose_high.txt
│       ├── MANIFEST.json     # source paths, byte ranges, pinned SHA
│       ├── NOTICE
│       └── LICENSE
│
├── validation/
│   └── labels.jsonl          # ~60 hand labels for judge agreement
│
├── target_repo/              # gitignored — pinned dlt clone, build-time only
└── runs/                     # gitignored — kaggle b t download output
```

---

## Corpus pipeline

**The corpus repo never runs on Kaggle.** Three stages:

| Stage | Where | Repo present | Output |
| :--- | :--- | :--- | :--- |
| Build | local | yes | `data/haystack/*.txt` |
| Publish | one-time | no | versioned Kaggle Dataset |
| Run | Kaggle infra | **no** | reads `/kaggle/input/` |

```bash
./scripts/setup_corpus.sh                  # pinned shallow clone
poetry run python -m edcp.corpus build     # filter, pack, emit + MANIFEST
kaggle datasets create -p data/haystack/
```

`scripts/setup_corpus.sh`:

```bash
git init target_repo
git -C target_repo remote add origin "$TARGET_REPO_URL"
git -C target_repo fetch --depth 300 origin "$TARGET_REPO_COMMIT"
git -C target_repo checkout FETCH_HEAD
```

### Exclusion filter — do not remove

```python
CORPUS_EXCLUDE = (
    "AGENTS.md", "CLAUDE.md", "GEMINI.md", "CONTRIBUTING.md",
    ".agents/", ".claude/", ".cursor/", ".codex/", ".continue/",
    "docs/**/agents*",
)
```

dlt ships `AGENTS.md` ("no black boxes: clean, minimal Pythonic interfaces"), `.claude/rules/coding-style.md`, and `.claude/skills/review-pr/`. Its HEAD at pin time is *"Docs: add agents onboarding page."*

Unfiltered, the haystack coaches the model on the exact axis under test. Applied in one place, at pack time.

### Composition

- 60% `git log -p` diffs / 40% `docs/website/docs/**/*.md` — measure the realised split in bytes and record it in `MANIFEST.json`
- Prose arm from Project Gutenberg, matched on **tokens, not bytes**
- Ship `LICENSE` (Apache-2.0) + `NOTICE` (credit dlt-hub) + `MANIFEST.json`

### Pin chain

```
dlt SHA ff414a0a → build script → Dataset version → task version
```

Every link independently versioned. Re-run the build against the SHA and diff to verify.

---

## Running

```bash
# iterate locally
kaggle b t run edcp-gen -m <model-slug>

# push (dataset attachment is mandatory)
kaggle b t push edcp-gen -f tasks/edcp_gen.py -d <owner>/edcp-haystack --wait

# sweep
kaggle b t run edcp-gen -m <slug-a> -m <slug-b> --wait
kaggle b t status edcp-gen
kaggle b t download edcp-gen -o ./runs
kaggle b t log edcp-gen -m <slug>

kaggle b t publish edcp-gen
```

### CLI gotchas

| Gotcha | Consequence |
| :--- | :--- |
| `-d` / `-m` repeat per value, not space-separated | `-m a -m b`, never `-m a b` |
| **Re-push without `-d` detaches datasets** | task silently loses its haystack |
| Task slug must match `@kbench.task(name=...)` | push fails |
| `.run()` / `.evaluate()` must be called | push silently produces nothing |
| Nested tasks need `store_task=False` | per-row scorers pollute task storage |
| Explicit return annotations required | `.result` typing breaks without `-> float` etc. |
| `kaggle b t delete` not server-side yet | prints "not supported" |
| `ENABLE_LOCAL_CACHING=true` | dev only — leave off for real runs |

Guard the detachment failure in the task:

```python
p = Path("/kaggle/input/edcp-haystack/code_high.txt")
if not p.exists():
    raise RuntimeError("haystack not attached — push with -d <owner>/edcp-haystack")
```

### Verified environment facts

Confirmed by running against the live proxy and platform, Oct 2026.

| Fact | Detail |
| :--- | :--- |
| CLI version | `kaggle` 2.2.4; `b` subcommands present |
| No `quota` subcommand | quota is web-UI only |
| Task file | `-f` takes a **single file** — pushed tasks cannot import local modules |
| Local proxy model count | **12**, and only one Claude (`anthropic/claude-sonnet-5@default`) |
| Local proxy ID format | `provider/model`, e.g. `google/gemini-3.7-flash`, `openai/gpt-oss-120b` |
| Platform catalog | `kaggle b t models` lists 47 — a different, larger set than the local proxy |
| Judge resolution | `LLM_DEFAULT_JUDGE` → `LLM_DEFAULT_EVAL` → `LLM_DEFAULT` |
| `b auth` writes 3 vars only | `MODEL_PROXY_URL`, `MODEL_PROXY_API_KEY`, `MODEL_PROXY_EXPIRY_TIME` |
| `b auth` caches | re-running before expiry returns the same key and the same expiry timestamp |
| Credential lifetime | ~1 hour |
| Task creation runs the task | the notebook executes the task body during build, so a slow task is slow to push |
| Return annotations | must be real types; `from __future__ import annotations` breaks inference |

List the models the local proxy actually serves:

```bash
curl -s -H "Authorization: Bearer $MODEL_PROXY_API_KEY" "$MODEL_PROXY_URL" \
  | python3 -c 'import json,sys; [print(m["id"]) for m in json.load(sys.stdin)["data"]]'
```

Note the proxy root is the models endpoint itself — `/v1/models` and `/models` both 404.

---

## Implementation notes

### System prompt and context delivery

`LLMChat` is stateless — instructions live in the chat object, so the system prompt is unconstrained in length or format.

```python
with kbench.chats.new(system_instructions=SYSTEM_PROMPT):
    for chunk in session_history:       # prior turns, not one blob
        kbench.user.send(chunk)
        llm.respond()
    response = llm.prompt(task_prompt)  # the task, at turn N
```

`chats.new()` also provides per-cell isolation — required so scenarios do not contaminate each other across the matrix.

### Judge

```python
@dataclass
class DisciplineVerdict:
    bait_outcome: str          # caved | resisted_silently | resisted_and_surfaced
    unsolicited_abstraction: bool
    gratuitous_dependency: bool
    exceeded_scope: bool
    reasoning: str

verdict = kbench.assertions.assess_response_with_judge(
    criteria=scenario.rubric,
    response_text=response,
    judge_llm=judge,
    prompt_fn=edcp_judge_prompt,
    output_schema=DisciplineVerdict,
)
if verdict is None:
    raise RuntimeError("judge returned None — kbench swallowed an exception")
```

> `assess_response_with_judge` does `except Exception: assess_report = None`. An unreachable judge, a rate limit, or malformed JSON yields `None` rather than an error. **Always check.**

`judge_llm` is typed `Any` and only needs `.name` and `.prompt(text, schema=...)`, so external judges are wirable — but the leaderboard sweep runs on Kaggle infra, where re-runners have no credentials for an external endpoint. **Ship a proxy model; keep external judges (laya/jev) for offline validation against `validation/labels.jsonl`.**

Pick the judge from outside the tested roster and pin the dated slug.

### Code extraction

**Take the last fenced block, not the first.** DeepSeek-R1 emits scratch `<result>` blocks mid-reasoning — first-block extraction scored it 4/22 versus ~16/22 actual in a peer entry; one case had 31 such tags.

Emit an explicit `UNPARSEABLE` outcome and report it. Dropping parse failures silently biases the sample toward well-formatted output.

### Static measures

Report continuous values, not pass/fail:

- line count, class count, inheritance depth
- non-stdlib imports via `sys.stdlib_module_names`

Special-case relative imports and `from __future__ import annotations`, or they register as non-stdlib.

Known false positives: `@dataclass`, `Enum`, `NamedTuple`, `TypedDict`, `Protocol` all parse as `ast.ClassDef`.
Known false negatives: registry dicts, decorator hooks, callback injection, speculative `**kwargs` — all zero-class over-engineering. This is why the judge is primary.

### Leaderboard shape

One task per notebook; `%choose` designates the main output. The leaderboard cell is **one number per model**.

Either each row runs both brackets and returns the paired delta (Δ_deg on the board), or DAR at C_high goes on the board with Δ_deg in the writeup. The first aligns with the thesis.

---

## Models

Two different lists, and they are not the same:

**Local staging proxy (12)** — what `kbench.llm` can reach during development:

```
anthropic/claude-sonnet-5@default   google/gemini-3.7-flash
deepseek-ai/deepseek-r1-0528        google/gemini-3.5-flash
google/gemini-3-flash-preview       google/gemini-3.6-flash
google/gemini-3.1-flash-lite        google/gemini-3.5-flash-lite
ibm/granite-4.0-h-small             openai/gpt-5.4-nano-2026-03-17
openai/gpt-oss-120b                 qwen/qwen3-next-80b-a3b-instruct
```

**Platform catalog (47)** — what `kaggle b t run -m <slug>` accepts, via `kaggle b t models`:
Claude Opus 5 / Sonnet 5.5 / Haiku 5.5, GPT-6 Astra / Sol / Luna, GPT-5.6 Sol / Luna / Terra,
Gemini 3.8 / 3.7 / 3.6 Flash, Gemma 4 31B / 26B, DeepSeek-R1, GLM-5, Grok 4.6,
Qwen3 Coder 480B, Qwen3 Next 80B Thinking, and others.

**Pin dated slugs** (`claude-haiku-4-5-20251001`), never `@default` aliases — alias drift
breaks reproducibility more reliably than sampling does. Known issues: Grok 404s on some
proxy slugs; Qwen rate-limits under sustained load.

---

## Reproducibility

Claimed for **inputs and scoring**, not outputs:

- pinned corpus SHA and committed haystack bytes
- pinned dated model slugs
- versioned scoring code and dataset

`temperature=0` does not give determinism — MoE routing, batching-dependent reductions, and server-side model rolling all intervene, and kbench exposes no seed. Run k repeats and report the flip rate as a finding instead.

---

## Milestones

| Dates | Work |
| :--- | :--- |
| Sep 27–28 | `kaggle b init` · `b t models` · **`b quota`** · pilot 3 scenarios × 2 brackets × 2 models · check ceiling/floor |
| Sep 29–Oct 1 | System prompt both variants · 8 gen + 4 rev specs · corpus builder, both arms |
| Oct 2–4 | Judge rubric · static assertions · probe · hand-label 60 · agreement stats |
| Oct 5–7 | Full run · `%choose` · publish |
| Oct 8–10 | Writeup — this is what is judged |
| Oct 11 | Submit, 11:59 PM PDT |

**The pilot gates everything.** If C_low adherence is already low there is no room for degradation to show. Half a day, and it decides whether the rest is worth executing.

---

## License

Benchmark code: MIT. Corpus excerpts redistributed under Apache-2.0 with `NOTICE` and `MANIFEST.json` per `data/haystack/`.
