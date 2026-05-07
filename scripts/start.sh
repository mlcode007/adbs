#!/usr/bin/env bash
# adbs 一键启动：释放 ADBS_PORT（默认 18081）→ PATH/GOPROXY →（可选）自动起 u2 bridge → go run .
# 用法：在终端执行
#   ./scripts/start.sh
# 或：
#   bash scripts/start.sh

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# macOS Homebrew + 官方包常见安装路径；Linux 常见 /usr/local/go、snap、用户 GOPATH/bin
export PATH="/opt/homebrew/bin:/usr/local/go/bin:/snap/bin:${HOME}/go/bin:${PATH:-}"
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
# 设为 0 可禁用自动启动 python_u2_bridge（仅 Go + /u2 反向代理需你先手动起 uvicorn）
export U2_AUTO_START="${U2_AUTO_START:-1}"
export ADBS_PORT="${ADBS_PORT:-18081}"

echo "[adbs] 目录: $ROOT"
echo "[adbs] U2_AUTO_START=$U2_AUTO_START  GOPROXY=$GOPROXY"

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

if ! command -v go >/dev/null 2>&1; then
  echo "[adbs] 错误: 未找到 go，请安装 Go 或把 go 加入 PATH。" >&2
  echo "[adbs] 示例: Debian/Ubuntu: sudo apt install -y golang-go  或从 https://go.dev/dl/ 安装到 /usr/local/go 后 export PATH=/usr/local/go/bin:\$PATH" >&2
  exit 1
fi

echo "[adbs] 启动中（本机: http://127.0.0.1:${ADBS_PORT}  按 Ctrl+C 停止）"
exec go run .
