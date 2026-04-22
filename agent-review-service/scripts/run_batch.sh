#!/usr/bin/env bash
# 一键批量脚本：启动评审服务（后台） + 运行批量任务 + 退出时清理
#
# 用法：
#   ./scripts/run_batch.sh [-i data/sample_dataset.jsonl] [-c 3] [--dry-run]
set -euo pipefail

INPUT="data/sample_dataset.jsonl"
CONCURRENCY="${BATCH_CONCURRENCY:-3}"
DRY_RUN_FLAG=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -i|--input)
      INPUT="$2"; shift 2;;
    -c|--concurrency)
      CONCURRENCY="$2"; shift 2;;
    --dry-run)
      DRY_RUN_FLAG="--dry-run"; shift;;
    -h|--help)
      echo "Usage: $0 [-i INPUT_JSONL] [-c CONCURRENCY] [--dry-run]"; exit 0;;
    *)
      echo "Unknown arg: $1"; exit 2;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

LOG_DIR="${LOG_DIR:-./logs}"
mkdir -p "${LOG_DIR}"
REVIEW_LOG="${LOG_DIR}/review_server.out"

REVIEW_PORT="${REVIEW_PORT:-8100}"
REVIEW_URL="${REVIEW_URL:-http://localhost:${REVIEW_PORT}}"

echo "[run_batch] 启动评审服务 port=${REVIEW_PORT}"
python -m app.main >"${REVIEW_LOG}" 2>&1 &
REVIEW_PID=$!

cleanup() {
  if kill -0 "${REVIEW_PID}" 2>/dev/null; then
    echo "[run_batch] 停止评审服务 pid=${REVIEW_PID}"
    kill "${REVIEW_PID}" 2>/dev/null || true
    wait "${REVIEW_PID}" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

# 等待健康检查就绪
echo "[run_batch] 等待 ${REVIEW_URL}/api/health 就绪..."
for i in $(seq 1 30); do
  if curl -sSf "${REVIEW_URL}/api/health" >/dev/null 2>&1; then
    echo "[run_batch] 评审服务就绪"
    break
  fi
  sleep 1
done

echo "[run_batch] 执行批量 input=${INPUT} concurrency=${CONCURRENCY} ${DRY_RUN_FLAG}"
python -m batch.cli run -i "${INPUT}" -c "${CONCURRENCY}" ${DRY_RUN_FLAG}
