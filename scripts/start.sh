#!/usr/bin/env bash
# adbs 一键启动：前端打包 → 释放端口 → start-u2-bridge.sh（18082）→ go run .（U2_AUTO_START=0 避免重复起 uvicorn）
# 用法：在终端执行
#   ./scripts/start.sh
#   ADBS_SKIP_FRONTEND_BUILD=1 ./scripts/start.sh   # 跳过 npm 构建

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# macOS Homebrew + 官方包常见安装路径；Linux 常见 /usr/local/go、snap、用户 GOPATH/bin
export PATH="/opt/homebrew/bin:/usr/local/go/bin:/snap/bin:${HOME}/go/bin:${PATH:-}"
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
# 先由 scripts/start-u2-bridge.sh 起 127.0.0.1:18082（U2_INTERNAL_PORT），再禁 Go 内重复拉起
export U2_AUTO_START="${U2_AUTO_START:-1}"
export ADBS_PORT="${ADBS_PORT:-18081}"

echo "[adbs] 目录: $ROOT"
echo "[adbs] U2_AUTO_START=$U2_AUTO_START  U2_INTERNAL_PORT=${U2_INTERNAL_PORT:-18082}  GOPROXY=$GOPROXY"

free_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti ":${port}" 2>/dev/null || true)"
    if [[ -n "${pids:-}" ]]; then
      echo "[adbs] 释放端口 ${port} …"
      # shellcheck disable=SC2086
      kill -9 ${pids} 2>/dev/null || true
      sleep 0.3
    fi
  fi
}

free_port "$ADBS_PORT"

if [[ -z "${U2_DISABLE:-}" ]]; then
  bash "${ROOT}/scripts/start-u2-bridge.sh"
  export U2_AUTO_START=0
  _adbs_cleanup_u2() {
    if [[ -f "${ROOT}/run/u2_bridge.pid" ]]; then
      kill "$(cat "${ROOT}/run/u2_bridge.pid")" 2>/dev/null || true
      rm -f "${ROOT}/run/u2_bridge.pid"
    fi
  }
  trap _adbs_cleanup_u2 EXIT INT TERM
fi

if ! command -v go >/dev/null 2>&1; then
  echo "[adbs] 错误: 未找到 go，请安装 Go 或把 go 加入 PATH。" >&2
  echo "[adbs] 示例: Debian/Ubuntu: sudo apt install -y golang-go  或从 https://go.dev/dl/ 安装到 /usr/local/go 后 export PATH=/usr/local/go/bin:\$PATH" >&2
  exit 1
fi

bash "${ROOT}/scripts/build-frontend.sh"

echo "[adbs] 启动中（本机: http://127.0.0.1:${ADBS_PORT}  按 Ctrl+C 停止）"
# 不用 exec，以便退出时 trap 能结束 start-u2-bridge 拉起的 uvicorn
go run .
