#!/usr/bin/env bash
# Run the benchmark locally against LiteLLM, bypassing the Kaggle model proxy.
#
# The Kaggle proxy reserves quota per request and refuses a request before
# sending it when the reservation exceeds the balance. A baseline cell needs
# more than the balance has had for some time, so local runs are the way to get
# measurements while quota is short.
#
# LiteLLM must already be running (default http://127.0.0.1:4000/v1). This
# starts the path bridge the library needs, points it at LiteLLM, and runs.
#
#   ./scripts/run_local.sh baseline        # all nine scenarios, no context
#   ./scripts/run_local.sh deep            # three scenarios at 30% of the window
#   ./scripts/run_local.sh full            # both
#
# Override the models with SUBJECT= and JUDGE=.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:-baseline}"
SUBJECT="${SUBJECT:-gemini/gemini-3.7-flash-medium}"
JUDGE="${JUDGE:-gemini/claude-opus-5-5-medium}"
BRIDGE_PORT="${BRIDGE_PORT:-4001}"
LITELLM="${LITELLM:-http://127.0.0.1:4000/v1}"

if ! curl -s --max-time 5 "${LITELLM}/models" >/dev/null 2>&1; then
  echo "error: LiteLLM not reachable at ${LITELLM}" >&2
  echo "       start it first (the config lives at ~/.config/litellm/config.yaml)" >&2
  exit 1
fi

mkdir -p runs/local

if ! curl -s --max-time 5 "http://127.0.0.1:${BRIDGE_PORT}/openapi/models" >/dev/null 2>&1; then
  echo "[run_local] starting bridge on ${BRIDGE_PORT}"
  nohup python3 scripts/litellm_bridge.py --port "$BRIDGE_PORT" --upstream "$LITELLM" \
    > runs/local/bridge.log 2>&1 &
  sleep 2
fi

export MODEL_PROXY_URL="http://127.0.0.1:${BRIDGE_PORT}"
export MODEL_PROXY_API_KEY="sk-local"
export LLM_DEFAULT="$SUBJECT"
export LLM_DEFAULT_JUDGE="$JUDGE"
export LLMS_AVAILABLE="${SUBJECT},${JUDGE}"

case "$MODE" in
  baseline) LEVELS='[{"fill": 0.0, "scenarios": null}]' ;;
  # deep and full use the task's configured FILL_LEVELS, so the script cannot
  # drift from what the published task actually runs.
  deep)     LEVELS="" ;;
  full)     LEVELS="" ;;
  *) echo "unknown mode: $MODE (baseline|deep|full)" >&2; exit 1 ;;
esac

echo "[run_local] subject=$SUBJECT judge=$JUDGE mode=$MODE"

python3 - "$LEVELS" > "runs/local/${MODE}.log" 2>&1 <<'PY'
import json, sys
sys.path.insert(0, "tasks")
import engineering_discipline as benchmark
import kaggle_benchmarks as kbench

override = sys.argv[1] if len(sys.argv) > 1 else ""
if override:
    benchmark.FILL_LEVELS = json.loads(override)
print(f"[run_local] fills: {[int(l['fill'] * 100) for l in benchmark.FILL_LEVELS]}")
benchmark.engineering_discipline.run(llm=kbench.llm, judge_llm=kbench.judge_llm)
PY

echo "[run_local] done, results in runs/local/${MODE}.log"
grep -E 'pass rate' "runs/local/${MODE}.log" || true
