#!/usr/bin/env bash
# adbs 服务器后台启动：释放端口 → PATH/GOPROXY → nohup go run .（脚本立即退出，进程常驻）
# 用法：
#   ./scripts/start-server.sh
#   ADBS_PORT=8080 ./scripts/start-server.sh
# 日志：../logs/adbs.log   PID：../run/adbs.pid
# 停止：kill "$(cat run/adbs.pid)"  或再次运行前由 free_port 占用端口时会释放

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

# macOS Homebrew + 官方包常见安装路径；Linux 常见 /usr/local/go、snap、用户 GOPATH/bin
export PATH="/opt/homebrew/bin:/usr/local/go/bin:/snap/bin:${HOME}/go/bin:${PATH:-}"
export GOPROXY="${GOPROXY:-https://goproxy.cn,direct}"
export U2_AUTO_START="${U2_AUTO_START:-1}"
export ADBS_PORT="${ADBS_PORT:-18081}"

LOG_DIR="${ROOT}/logs"
RUN_DIR="${ROOT}/run"
mkdir -p "$LOG_DIR" "$RUN_DIR"
PID_FILE="${RUN_DIR}/adbs.pid"
LOG_FILE="${LOG_DIR}/adbs.log"

echo "[adbs] 目录: $ROOT"
echo "[adbs] U2_AUTO_START=$U2_AUTO_START  ADBS_PORT=$ADBS_PORT  GOPROXY=$GOPROXY"

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

if [[ -f "$PID_FILE" ]]; then
  old_pid="$(cat "$PID_FILE" 2>/dev/null || true)"
  if [[ -n "${old_pid:-}" ]] && kill -0 "$old_pid" 2>/dev/null; then
    echo "[adbs] 警告: 记录中的进程仍在运行 pid=$old_pid，已先释放端口；若异常请手动 kill。" >&2
  fi
  rm -f "$PID_FILE"
fi

# 后台运行；分离终端 SIGHUP
nohup go run . >>"$LOG_FILE" 2>&1 &
echo $! >"$PID_FILE"

echo "[adbs] 已后台启动 pid=$(cat "$PID_FILE")"
echo "[adbs] 日志: $LOG_FILE"
echo "[adbs] 访问: http://127.0.0.1:${ADBS_PORT}"
echo "[adbs] 停止: kill \"\$(cat run/adbs.pid)\""
