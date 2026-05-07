#!/usr/bin/env bash
# 启动 python_u2_bridge（uvicorn），监听 127.0.0.1:U2_INTERNAL_PORT（默认 18082）。
# Go 通过 /u2 反代到该端口；与 u2start.go 二选一：由 start.sh / start-server.sh 调用本脚本时应设置 U2_AUTO_START=0。
#
# 环境变量：
#   U2_DISABLE          非空则跳过（退出 0）
#   U2_INTERNAL_PORT    默认 18082
#   U2_PIP_INSTALL=1    启动前执行 pip install -r requirements.txt
#   U2_BRIDGE_FOREGROUND=1  前台运行（不写 pid / 不用 nohup，便于调试）
#
# 后台模式：日志 logs/u2_bridge.log，PID run/u2_bridge.pid

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRIDGE="${ROOT}/python_u2_bridge"
export U2_INTERNAL_PORT="${U2_INTERNAL_PORT:-18082}"

if [[ -n "${U2_DISABLE:-}" ]]; then
  echo "[u2-bridge] U2_DISABLE 已设置，跳过启动"
  exit 0
fi

if [[ ! -f "${BRIDGE}/app.py" ]]; then
  echo "[u2-bridge] 错误: 未找到 ${BRIDGE}/app.py" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "[u2-bridge] 错误: 未找到 python3" >&2
  exit 1
fi

free_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti ":${port}" 2>/dev/null || true)"
    if [[ -n "${pids:-}" ]]; then
      echo "[u2-bridge] 释放端口 ${port} …"
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
      sleep 0.3
    fi
  fi
}

free_port "$U2_INTERNAL_PORT"

if [[ "${U2_PIP_INSTALL:-}" == "1" ]]; then
  echo "[u2-bridge] pip install -r requirements.txt …"
  python3 -m pip install -r "${BRIDGE}/requirements.txt"
fi

cd "$BRIDGE"

if [[ "${U2_BRIDGE_FOREGROUND:-}" == "1" ]]; then
  echo "[u2-bridge] 前台: http://127.0.0.1:${U2_INTERNAL_PORT}/"
  exec python3 -m uvicorn app:app --host 127.0.0.1 --port "$U2_INTERNAL_PORT"
fi

LOG_DIR="${ROOT}/logs"
RUN_DIR="${ROOT}/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"
U2_PID_FILE="${RUN_DIR}/u2_bridge.pid"
U2_LOG_FILE="${LOG_DIR}/u2_bridge.log"

rm -f "$U2_PID_FILE"
nohup python3 -m uvicorn app:app --host 127.0.0.1 --port "$U2_INTERNAL_PORT" >>"$U2_LOG_FILE" 2>&1 &
echo $! >"$U2_PID_FILE"
echo "[u2-bridge] 已后台启动 pid=$(cat "$U2_PID_FILE")  http://127.0.0.1:${U2_INTERNAL_PORT}/"
echo "[u2-bridge] 日志: $U2_LOG_FILE"
