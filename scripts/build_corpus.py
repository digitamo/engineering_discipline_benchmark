#!/usr/bin/env python3
"""Build the context haystack from the pinned corpus clone.

BUILD-TIME ONLY. Nothing here runs on Kaggle. The output is uploaded once as a
Kaggle Dataset and attached to the task with `-d`.

    python3 scripts/build_corpus.py

Outputs data/haystack/code_high.txt plus a MANIFEST.json recording exactly
which bytes came from where, so the artifact is reproducible and auditable.

Token counts use a chars/4 heuristic. It is an estimate, not a tokenizer; it is
used consistently across all arms, so relative comparisons hold.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "haystack"

# The corpus is a build-time input only. Prefer an existing clone; fall back to
# the one scripts/setup_corpus.sh creates. The commit actually used is recorded
# in MANIFEST.json, which is the source of truth for reproducibility.
_CORPUS_CANDIDATES = (
    os.environ.get("CORPUS_REPO_PATH"),
    str(ROOT / "target_repo"),
    str(Path.home() / "workspace" / "playground" / "dlt"),
)
REPO = next(
    (Path(p) for p in _CORPUS_CANDIDATES if p and (Path(p) / ".git").exists()),
    Path(ROOT / "target_repo"),
)

TARGET_TOKENS = 100_000
DOC_SHARE = 0.40
DIFF_SHARE = 0.60
CHARS_PER_TOKEN = 4

# Never let agent guidance into the haystack. The corpus repo ships coding-style
# rules, review skills, and a whole documentation tree for its AI harness.
# Unfiltered, the haystack would coach the model on the exact axis under test.
# See DESIGN.md section 3.7.
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

# Second line of defence. Path rules miss files whose name gives nothing away,
# so anything carrying agent-instruction or coding-standards language is dropped
# regardless of where it lives.
CONTAMINATION_PHRASES = (
    "no black boxes",
    "dry and yagni",
    "keep diffs as minimal",
    "ai harness",
    "agent definition",
    "coding style guide",
)

# A single commit patch longer than this is a generated file, a lockfile, or a
# vendored dump. Not representative of a real session.
MAX_PATCH_CHARS = 12_000


def tokens(text: str) -> int:
    return len(text) // CHARS_PER_TOKEN


def is_excluded(path: str) -> bool:
    return any(marker in path for marker in CORPUS_EXCLUDE)


def is_contaminated(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in CONTAMINATION_PHRASES)


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(REPO), *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def collect_docs(budget_tokens: int) -> tuple[str, list[dict]]:
    """Markdown from the docs tree, deterministic order, agent paths excluded."""
    files = sorted(
        p for p in (REPO / "docs").rglob("*.md")
        if not is_excluded(str(p.relative_to(REPO)))
    )

    parts: list[str] = []
    manifest: list[dict] = []
    used = 0
    skipped = 0

    for path in files:
        if used >= budget_tokens:
            break
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.strip():
            continue
        if is_contaminated(text):
            skipped += 1
            continue

        rel = str(path.relative_to(REPO))
        parts.append(f"\n===== FILE: {rel} =====\n{text}")
        manifest.append({"source": rel, "chars": len(text)})
        used += tokens(text)

    if skipped:
        print(f"  skipped {skipped} doc(s) carrying agent-instruction language")
    return "".join(parts), manifest


def collect_diffs(budget_tokens: int) -> tuple[str, list[dict]]:
    """Real commit patches, newest first, agent-touching commits skipped."""
    log = git("log", "--no-merges", "--format=%H%x00%ad%x00%s", "--date=short")
    entries = [line.split("\x00") for line in log.splitlines() if line.strip()]

    parts: list[str] = []
    manifest: list[dict] = []
    used = 0
    skipped = 0

    for sha, date, subject in entries:
        if used >= budget_tokens:
            break

        changed = git("show", "--name-only", "--format=", sha).splitlines()
        if any(is_excluded(f) for f in changed if f.strip()):
            continue

        patch = git("show", "--format=%ncommit %h%nAuthor: %an%nDate: %ad%n%n    %s", "--date=short", sha)
        if len(patch) > MAX_PATCH_CHARS:
            continue
        if is_contaminated(patch):
            skipped += 1
            continue

        parts.append(f"\n===== COMMIT {sha[:8]} ({date}) =====\n{patch}")
        manifest.append({"source": sha[:12], "subject": subject, "chars": len(patch)})
        used += tokens(patch)

    if skipped:
        print(f"  skipped {skipped} commit(s) carrying agent-instruction language")
    return "".join(parts), manifest


def main() -> int:
    if not (REPO / ".git").exists():
        print("error: no corpus clone found. Set CORPUS_REPO_PATH or run scripts/setup_corpus.sh.", file=sys.stderr)
        return 1

    commit = git("rev-parse", "HEAD").strip()
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"corpus repo: {REPO}")

    doc_budget = int(TARGET_TOKENS * DOC_SHARE)
    diff_budget = int(TARGET_TOKENS * DIFF_SHARE)

    print(f"collecting docs (budget ~{doc_budget} tokens)")
    docs, doc_manifest = collect_docs(doc_budget)
    print(f"  {len(doc_manifest)} files, {tokens(docs)} tokens")

    print(f"collecting diffs (budget ~{diff_budget} tokens)")
    diffs, diff_manifest = collect_diffs(diff_budget)
    print(f"  {len(diff_manifest)} commits, {tokens(diffs)} tokens")

    # Diffs first: they read as session history, docs read as reference material.
    haystack = diffs + docs
    total = tokens(haystack)

    out_file = OUT / "code_high.txt"
    out_file.write_text(haystack, encoding="utf-8")

    manifest = {
        "corpus_repo": "https://github.com/dlt-hub/dlt.git",
        "corpus_commit": commit,
        "token_estimate": total,
        "chars_per_token_heuristic": CHARS_PER_TOKEN,
        "excluded_patterns": list(CORPUS_EXCLUDE),
        "composition": {
            "diff_tokens": tokens(diffs),
            "doc_tokens": tokens(docs),
            "diff_share": round(tokens(diffs) / max(total, 1), 3),
        },
        "diff_sources": diff_manifest,
        "doc_sources": doc_manifest,
    }
    (OUT / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print(f"\nwrote {out_file.relative_to(ROOT)}  ({len(haystack):,} chars, ~{total:,} tokens)")
    print(f"diff/doc split: {manifest['composition']['diff_share']:.0%} / {1 - manifest['composition']['diff_share']:.0%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
