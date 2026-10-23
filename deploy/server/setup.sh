#!/usr/bin/env bash
# 第一次准备云服务器（Ubuntu 24.04，用 root 运行一次）：装软件、加交换空间、建运行网站的用户和目录、
# 只允许用钥匙登录 SSH、装 Nginx 配置。重复运行不会出问题。
# 用法：sudo bash setup.sh   （和 nginx-prismind.conf 放在同一个目录）
set -euo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
base=/opt/prismind
export DEBIAN_FRONTEND=noninteractive

apt-get update -qq
apt-get install -y -qq nginx nodejs npm python3-venv certbot python3-certbot-nginx

# 每天的全市场更新最多用约 5 GB 内存，和后端同时运行时 8 GB 内存偏紧：再加 4 GB 交换空间。
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap -q /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

id prismind >/dev/null 2>&1 || useradd --system --create-home --home-dir "$base" --shell /usr/sbin/nologin prismind
mkdir -p "$base/releases" "$base/data" "$base/shared"
[ -d "$base/venv" ] || python3 -m venv "$base/venv"
chown -R prismind:prismind "$base"
chmod 750 "$base"

# 只允许用钥匙登录（腾讯云、阿里云控制台里的网页登录不受影响）。
cat > /etc/ssh/sshd_config.d/00-prismind-hardening.conf <<'EOF'
# 镜思 Prismind：只允许用钥匙登录
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
EOF
sshd -t && systemctl reload ssh

if [ ! -f /etc/nginx/sites-available/prismind ]; then
  cp "$here/nginx-prismind.conf" /etc/nginx/sites-available/prismind
fi
ln -sfn /etc/nginx/sites-available/prismind /etc/nginx/sites-enabled/prismind
rm -f /etc/nginx/sites-enabled/default
nginx -t
# 刚装好时 Nginx 可能没在运行（例如 80 端口当时被占用）。
systemctl enable -q nginx
systemctl is-active -q nginx && systemctl reload nginx || systemctl start nginx
echo "服务器准备好了。接下来：把数据和 .env 放到 $base/data、$base/shared/.env，再在本机运行 scripts/deploy.sh。"
