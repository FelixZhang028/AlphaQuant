#!/usr/bin/env bash
# 把代码部署到云服务器：打包一个提交 → 传到服务器 → 装依赖、打包网页 → 切换版本 → 重启后端。
# 新版本启动失败时服务器自动切回上一个版本。第一次部署前先按 docs/DEPLOY_SERVER.md 准备服务器。
# 用法（在 Git Bash 或 Linux/macOS 终端里）：scripts/deploy.sh [提交，默认 origin/main]
#   PRISMIND_HOST  服务器，默认 ubuntu@43.161.200.13
#   PRISMIND_KEY   SSH 钥匙，默认 ~/.ssh/prismind_hk_ed25519
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
host="${PRISMIND_HOST:-ubuntu@43.161.200.13}"
key="${PRISMIND_KEY:-$HOME/.ssh/prismind_hk_ed25519}"
ref="${1:-origin/main}"
ssh_opts=(-i "$key" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=15)

git -C "$root" fetch -q origin
sha="$(git -C "$root" rev-parse --short "$ref")"
release="$(date +%Y%m%d-%H%M%S)-$sha"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

echo "[打包] $ref（$sha）"
git -C "$root" archive --format=tar.gz -o "$tmp/release.tar.gz" "$ref"
echo "[上传] $host"
scp -q "${ssh_opts[@]}" "$tmp/release.tar.gz" "$host:/tmp/prismind-release.tar.gz"
ssh "${ssh_opts[@]}" "$host" "set -e
  sudo mkdir -p /opt/prismind/releases/$release
  sudo tar -xzf /tmp/prismind-release.tar.gz -C /opt/prismind/releases/$release
  rm -f /tmp/prismind-release.tar.gz
  sudo bash /opt/prismind/releases/$release/deploy/server/install-release.sh $release"
