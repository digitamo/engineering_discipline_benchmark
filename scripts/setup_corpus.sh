#!/usr/bin/env bash
# Pinned shallow clone of the corpus repo.
#
# The corpus is a BUILD-TIME input only. Nothing here runs on Kaggle.
# Pinned so the haystack is byte-reproducible.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO_PATH="${TARGET_REPO_PATH:-$ROOT/target_repo}"
TARGET_REPO_URL="${TARGET_REPO_URL:-https://github.com/dlt-hub/dlt.git}"
TARGET_REPO_COMMIT="${TARGET_REPO_COMMIT:-c3215e99163eedda925726ab10be23399651727d}"

if [ -d "$TARGET_REPO_PATH/.git" ]; then
  echo "[setup_corpus] target_repo already exists, verifying commit"
  git -C "$TARGET_REPO_PATH" rev-parse HEAD
  exit 0
fi

echo "[setup_corpus] cloning $TARGET_REPO_URL"
echo "[setup_corpus] pinned commit: $TARGET_REPO_COMMIT"

git init -q "$TARGET_REPO_PATH"
git -C "$TARGET_REPO_PATH" remote add origin "$TARGET_REPO_URL"
git -C "$TARGET_REPO_PATH" fetch --depth 300 origin "$TARGET_REPO_COMMIT"
git -C "$TARGET_REPO_PATH" checkout -q FETCH_HEAD

echo "[setup_corpus] done at $(git -C "$TARGET_REPO_PATH" rev-parse HEAD)"
