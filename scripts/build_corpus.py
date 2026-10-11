#!/usr/bin/env python3
"""Build the context fillers as fixed-size chunks.

BUILD-TIME ONLY. Nothing here runs on Kaggle. Output is uploaded once as a
Kaggle Dataset and attached to the task with `-d`.

    python3 scripts/build_corpus.py

Produces:

    data/haystack/prose/chunk_000.txt ...   RFCs
    data/haystack/code/chunk_000.txt ...    the pinned dlt clone
    data/haystack/MANIFEST.json             what went in, from where

Two fillers exist because the content of the context is a separate variable from
its size. A code corpus demonstrates coding conventions and primes the model
toward them; RFCs do not. Comparing the two separates "the model lost the rules"
from "the model imitated what it just read".

Token counts use a chars/4 estimate. It is an estimate, not a tokenizer, and it
runs about 20% low. The run artifact reports actual input tokens, and
scripts/analyze.py compares the two so the error stays visible.
"""

import json
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "haystack"
RFC_CACHE = ROOT / ".rfc-cache"

CHARS_PER_TOKEN = 4
CHUNK_TOKENS = 32_000
CHUNK_CHARS = CHUNK_TOKENS * CHARS_PER_TOKEN

# The corpus is a build-time input only. Prefer an existing clone; fall back to
# the one scripts/setup_corpus.sh creates.
_CORPUS_CANDIDATES = (
    str(ROOT / "target_repo"),
    str(Path.home() / "workspace" / "playground" / "dlt"),
)
REPO = next((Path(p) for p in _CORPUS_CANDIDATES if (Path(p) / ".git").exists()), None)

# Never let agent guidance into a filler. The corpus repo ships coding-style
# rules, review skills, and a whole documentation tree for its AI harness.
# Unfiltered, the context would coach the model on the exact axis under test.
CORPUS_EXCLUDE = (
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
    "CONTRIBUTING.md",
    ".agents/",
    ".claude/",
    ".cursor/",
    ".codex/",
    ".continue/",
    "/hub/ai-harness/",
    "/hub/agents/",
    "/hub/getting-started/agents.md",
    ".github/PULL_REQUEST_TEMPLATE.md",
)

# Second line of defence. Path rules miss files whose name gives nothing away.
CONTAMINATION_PHRASES = (
    "no black boxes",
    "dry and yagni",
    "keep diffs as minimal",
    "ai harness",
    "agent definition",
    "coding style guide",
)

# Large, protocol-focused RFCs. Chosen for size and because they describe wire
# behaviour rather than how to write software, so they are neutral with respect
# to the standards under test. PEPs were rejected for this role: PEP 20 is a
# simplicity manifesto and PEP 8 is a style guide, both of which would prime the
# measured axis.
RFCS = [
    791, 793, 821, 822, 959, 1034, 1035, 1122, 1738, 1866,
    1939, 2045, 2109, 2131, 2181, 2246, 2328, 2459, 2616, 2617,
    2818, 2822, 2965, 3261, 3315, 3449, 3493, 3550, 3711, 3986,
    4180, 4251, 4253, 4254, 4291, 4301, 4302, 4303, 4366, 4443,
    4505, 4880, 4960, 5034, 5246, 5280, 5321, 5322, 5346, 5769,
    6066, 6120, 6151, 6265, 6455, 6749, 6750, 7159, 7230, 7231,
    7232, 7233, 7234, 7235, 7540, 7541, 7515, 7519, 8010, 8259,
    8446, 8484, 8555, 8621, 8898, 9000, 9001, 9002, 9110, 9111,
    9112, 9113, 9114, 9147, 9204, 9221, 9293, 9309, 9457, 9553,
]

MAX_PATCH_CHARS = 40_000


def tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def is_excluded(path: str) -> bool:
    return any(marker in path for marker in CORPUS_EXCLUDE)


def is_contaminated(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in CONTAMINATION_PHRASES)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args], capture_output=True, text=True, check=True
    ).stdout


# --------------------------------------------------------------------------
# Chunking
# --------------------------------------------------------------------------


def chunk(text: str, limit_chars: int = CHUNK_CHARS) -> list[str]:
    """Split on blank lines so chunks break at paragraph boundaries."""
    chunks, current, size = [], [], 0
    for paragraph in text.split("\n\n"):
        block = paragraph + "\n\n"
        if size + len(block) > limit_chars and current:
            chunks.append("".join(current))
            current, size = [], 0
        current.append(block)
        size += len(block)
    if current:
        chunks.append("".join(current))
    return chunks


def write_chunks(filler: str, chunks: list[str]) -> list[dict]:
    """Flat files with a filler prefix.

    Kaggle's dataset uploader skips subdirectories unless you tar or zip them,
    and a tarball would need unpacking at run time. Flat is simpler.
    """
    for stale in OUT.glob(f"{filler}_chunk_*.txt"):
        stale.unlink()

    manifest = []
    for i, text in enumerate(chunks):
        name = f"{filler}_chunk_{i:03d}.txt"
        (OUT / name).write_text(text, encoding="utf-8")
        manifest.append({"file": name, "chars": len(text), "tokens_estimate": tokens(text)})
    return manifest


# --------------------------------------------------------------------------
# Prose filler: RFCs
# --------------------------------------------------------------------------


def download_rfcs() -> list[Path]:
    RFC_CACHE.mkdir(exist_ok=True)
    paths = []
    for number in RFCS:
        path = RFC_CACHE / f"rfc{number}.txt"
        if not path.exists():
            url = f"https://www.rfc-editor.org/rfc/rfc{number}.txt"
            try:
                with urllib.request.urlopen(url, timeout=60) as response:
                    path.write_bytes(response.read())
            except Exception as error:  # noqa: BLE001 - report and continue
                print(f"  skipped RFC {number}: {error}")
                continue
        paths.append(path)
    return paths


def build_prose() -> list[dict]:
    print("prose filler: downloading RFCs")
    paths = download_rfcs()
    print(f"  {len(paths)} RFCs available")

    parts = []
    for path in sorted(paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        if is_contaminated(text):
            continue
        parts.append(f"\n\n===== {path.stem.upper()} =====\n\n{text}")

    combined = "".join(parts)
    chunks = chunk(combined)
    print(f"  {tokens(combined):,} tokens -> {len(chunks)} chunks")
    return write_chunks("prose", chunks)


# --------------------------------------------------------------------------
# Code filler: the pinned clone
# --------------------------------------------------------------------------


def collect_docs(budget_tokens: int) -> list[str]:
    files = sorted(
        p for p in (REPO / "docs").rglob("*.md")
        if not is_excluded(str(p.relative_to(REPO)))
    )
    parts, used = [], 0
    for path in files:
        if used >= budget_tokens:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip() or is_contaminated(text):
            continue
        parts.append(f"\n\n===== FILE: {path.relative_to(REPO)} =====\n\n{text}")
        used += tokens(text)
    return parts


def collect_diffs(budget_tokens: int) -> list[str]:
    log = git("log", "--no-merges", "--format=%H%x00%ad%x00%s", "--date=short")
    entries = [line.split("\x00") for line in log.splitlines() if line.strip()]

    parts, used = [], 0
    for sha, _date, _subject in entries:
        if used >= budget_tokens:
            break
        changed = git("show", "--name-only", "--format=", sha).splitlines()
        if any(is_excluded(f) for f in changed if f.strip()):
            continue
        patch = git(
            "show", "--format=%ncommit %h%nAuthor: %an%nDate: %ad%n%n    %s", "--date=short", sha
        )
        if len(patch) > MAX_PATCH_CHARS or is_contaminated(patch):
            continue
        parts.append(f"\n\n===== COMMIT {sha[:8]} =====\n\n{patch}")
        used += tokens(patch)
    return parts


def build_code() -> list[dict]:
    if REPO is None:
        print("code filler: no clone found, skipping. Run scripts/setup_corpus.sh.", file=sys.stderr)
        return []

    print(f"code filler: {REPO}")
    commit = git("rev-parse", "HEAD").strip()

    parts = collect_diffs(1_200_000) + collect_docs(600_000)
    combined = "".join(parts)
    chunks = chunk(combined)
    print(f"  commit {commit[:12]}, {tokens(combined):,} tokens -> {len(chunks)} chunks")
    return write_chunks("code", chunks)


# --------------------------------------------------------------------------


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    prose_manifest = build_prose()
    code_manifest = build_code()

    manifest = {
        "chars_per_token_heuristic": CHARS_PER_TOKEN,
        "chunk_tokens_estimate": CHUNK_TOKENS,
        "fillers": {
            "prose": {
                "source": "IETF RFCs (rfc-editor.org)",
                "licence": "IETF Trust Legal Provisions; redistribution permitted with notice",
                "rfc_numbers": RFCS,
                "chunks": prose_manifest,
                "tokens_estimate": sum(c["tokens_estimate"] for c in prose_manifest),
            },
            "code": {
                "source": "https://github.com/dlt-hub/dlt.git",
                "commit": git("rev-parse", "HEAD").strip() if REPO else None,
                "licence": "Apache-2.0",
                "excluded_patterns": list(CORPUS_EXCLUDE),
                "chunks": code_manifest,
                "tokens_estimate": sum(c["tokens_estimate"] for c in code_manifest),
            },
        },
        "note": (
            "Token counts are chars/4 estimates and run ~20% low. Actual input "
            "tokens are reported in the run artifact and compared by "
            "scripts/analyze.py. Excluded items are not enumerated here; the "
            "rules above are what was applied."
        ),
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\nsummary")
    for name, entry in manifest["fillers"].items():
        print(f"  {name:<6} {len(entry['chunks']):>3} chunks  ~{entry['tokens_estimate']:,} tokens")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
