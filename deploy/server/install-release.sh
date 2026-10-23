#!/usr/bin/env bash
# 在服务器上装好一个新版本并切换过去（由本机的 scripts/deploy.sh 调用，用 root 运行）：
# 链接数据和 .env → 装 Python 依赖 → 打包网页 → 切换 current → 重启后端 → 检查。
# 新版本启动失败时自动切回上一个版本。
# 用法：install-release.sh 版本目录名（代码已经解压在 /opt/prismind/releases/版本目录名）
set -euo pipefail
base=/opt/prismind
release="$1"
dir="$base/releases/$release"
[ -d "$dir/dashboard/backend" ] || { echo "没有找到 $dir" >&2; exit 1; }

# 数据和 .env 放在版本目录外面，换版本时不动它们。
ln -sfn "$base/data" "$dir/dashboard/backend/data"
ln -sfn "$base/shared/.env" "$dir/dashboard/backend/.env"
chown -R prismind:prismind "$dir"
as_app() { sudo -u prismind -H "$@"; }

echo "[依赖] Python …"
as_app "$base/venv/bin/pip" install -q --disable-pip-version-check \
  -r "$dir/dashboard/backend/requirements.txt" -c "$dir/dashboard/backend/requirements.lock"
for part in landing admin; do
  echo "[打包] $part …"
  (cd "$dir/$part" && as_app npm ci --no-audit --no-fund --loglevel=error && as_app npm run build --silent)
done

install -m 644 "$dir/deploy/server/prismind.service" /etc/systemd/system/prismind.service
systemctl daemon-reload
systemctl enable -q prismind

previous="$(readlink -f "$base/current" 2>/dev/null || true)"
ln -sfn "$dir" "$base/current"
systemctl restart prismind
healthy() {
  for _ in $(seq 1 45); do
    curl -fsS -o /dev/null http://127.0.0.1:8000/api/health && return 0
    sleep 2
  done
  return 1
}
if healthy; then
  echo "[完成] 已切换到 $release"
else
  echo "[出错] 新版本没有启动成功，切回上一个版本。日志：journalctl -u prismind -n 100" >&2
  if [ -n "$previous" ] && [ "$previous" != "$dir" ]; then
    ln -sfn "$previous" "$base/current"
    systemctl restart prismind
  fi
  exit 1
fi

# 只保留最近 5 个版本，方便回退。
ls -1dt "$base"/releases/*/ | tail -n +6 | xargs -r rm -rf
