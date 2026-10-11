#!/usr/bin/env bash
# Wait for model-proxy quota to return, then push and run the benchmark.
#
# The proxy reserves quota per request from input tokens plus maximum output,
# and refuses a request BEFORE sending it when the reservation exceeds the
# remaining balance. While the balance is low every cell fails with a 403.
#
# Two things this has to get right:
#   1. Probe with a request shaped like a real cell. A tiny probe succeeds on a
#      balance far too small to run anything, which makes the watcher act early.
#   2. Wait for the task build to finish. Task creation executes the task, so a
#      run started too soon is refused with "task is not ready to run".
#
#   nohup scripts/wait_for_quota.sh > quota-watch.log 2>&1 &

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

POLL_SECONDS="${POLL_SECONDS:-1800}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
MODEL="${MODEL:-gemini-3.7-flash}"

probe() {
  # Shaped like a baseline cell: a few thousand input tokens and a full output
  # reservation. If this is refused, real cells would be refused too.
  python3 - <<'PY' >/dev/null 2>&1
import kaggle_benchmarks as kbench
filler = "x " * 2000
with kbench.chats.new("quota-probe"):
    kbench.llm.prompt(filler + "\n\nReply with one word: ok",
                      extra_api_params={"max_tokens": 4096})
PY
}

wait_for_build() {
  for _ in $(seq 1 60); do
    local status
    status="$(kaggle b t status engineering-discipline 2>&1 | grep -i '^Status:' | head -1 | awk '{print $2}')"
    case "$status" in
      Completed) return 0 ;;
      Errored|Failed) echo "[quota-watch] build ended: $status"; return 1 ;;
    esac
    sleep 20
  done
  return 1
}

echo "[quota-watch] started $(date -u +%H:%M:%S)"
for attempt in $(seq 1 "$MAX_ATTEMPTS"); do
  source scripts/kbench-env.sh >/dev/null 2>&1

  if probe; then
    echo "[quota-watch] quota looks sufficient at $(date -u +%H:%M:%S)"

    echo "[quota-watch] pushing"
    kaggle b t push engineering-discipline \
      -f tasks/engineering_discipline.py \
      -d digitamo/engineering-discipline-haystack 2>&1 | tail -2

    if wait_for_build; then
      echo "[quota-watch] running against $MODEL"
      kaggle b t run engineering-discipline -m "$MODEL" --wait 2>&1 | tail -6
      kaggle b t download engineering-discipline -o ./runs 2>&1 | tail -2
      echo "[quota-watch] finished $(date -u +%H:%M:%S)"
      python3 scripts/analyze.py runs/engineering-discipline/**/*.run.json 2>&1 | head -70
      exit 0
    fi
    echo "[quota-watch] build did not complete, retrying later"
  else
    echo "[quota-watch] attempt $attempt: quota still short at $(date -u +%H:%M:%S)"
  fi

  sleep "$POLL_SECONDS"
done

echo "[quota-watch] gave up after $MAX_ATTEMPTS attempts"
exit 1
