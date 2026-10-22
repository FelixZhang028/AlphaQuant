#!/usr/bin/env bash
# 正式部署（Linux）：打包官网/功能台，由后端直接提供网页和接口，整个网站只有一个地址。
# 前面再放 Cloudflare Tunnel 或 Nginx 提供 https；只监听本机地址，不直接暴露端口。
# 配置写在 dashboard/backend/.env（参考 .env.example）。
# 用法：scripts/serve.sh [端口，默认 8000]；设 SKIP_BUILD=1 跳过打包。
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
port="${1:-8000}"
host="${LISTEN_HOST:-127.0.0.1}"

if [ "${SKIP_BUILD:-0}" != "1" ]; then
  for part in landing admin; do
    echo "[打包] $part ..."
    (cd "$root/$part" && { [ -d node_modules ] || npm ci; } && npm run build)
  done
fi
for part in landing admin; do
  [ -f "$root/$part/dist/index.html" ] || { echo "没有找到打包好的网页：$root/$part/dist" >&2; exit 1; }
done

export FELLOWQUANT_STATIC_DIR="$root/landing/dist"
export FELLOWQUANT_ADMIN_DIR="$root/admin/dist"
unset FELLOWQUANT_API_DOCS
echo "[启动] 镜思 Prismind  http://$host:$port  管理后台 /admin/  （按 Ctrl+C 停止）"
# 只开一个进程：次数限制和后台任务都记在这个进程里。
exec python3 -m uvicorn app.main:app --app-dir "$root/dashboard/backend" --host "$host" --port "$port" --no-server-header
