#!/usr/bin/env bash
# 前端打包：frontend → ../static（与 vue.config.js outputDir 一致）
# 由 start.sh / start-server.sh 调用；也可单独执行：./scripts/build-frontend.sh
# 跳过：ADBS_SKIP_FRONTEND_BUILD=1
# 未安装 npm 时仅警告并退出 0（沿用已有 static/），避免无 Node 环境无法启动服务。

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FE="${ROOT}/frontend"

if [[ -n "${ADBS_SKIP_FRONTEND_BUILD:-}" ]]; then
  echo "[adbs] 跳过前端构建（已设置 ADBS_SKIP_FRONTEND_BUILD）"
  exit 0
fi

if [[ ! -f "${FE}/package.json" ]]; then
  echo "[adbs] 警告: 未找到 frontend/package.json，跳过前端构建" >&2
  exit 0
fi

if ! command -v npm >/dev/null 2>&1; then
  echo "[adbs] 警告: 未找到 npm，跳过前端构建（将使用已有 static/）" >&2
  exit 0
fi

echo "[adbs] 前端构建: ${FE} → ${ROOT}/static"
cd "$FE"
if [[ -f package-lock.json ]]; then
  npm ci
else
  npm install
fi
npm run build
echo "[adbs] 前端构建完成"
