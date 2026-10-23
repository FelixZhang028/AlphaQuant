# 部署到云服务器

网站跑在一台 Linux 云服务器上（现在是腾讯云香港轻量服务器，Ubuntu 24.04，2 核 8 GB），由 Nginx 提供 https，域名 `getprismind.com` 在 Cloudflare 上只做 DNS（灰色云朵，不经过 Cloudflare 代理），国内访问直接连到服务器。

```
访问者 ──https──▶ Nginx（80/443）──▶ 后端 127.0.0.1:8000（systemd 服务 prismind）
                                         └─ 启动的数据任务（每日更新等）
```

## 服务器上的目录

| 位置 | 内容 |
|---|---|
| `/opt/prismind/releases/时间-提交/` | 每次部署的代码，保留最近 5 个 |
| `/opt/prismind/current` | 指向正在用的版本 |
| `/opt/prismind/data/` | 账户数据库、行情数据、回测结果、`runtime/app-secret.key`（所有版本共用） |
| `/opt/prismind/shared/.env` | 配置（所有版本共用） |
| `/opt/prismind/venv/` | Python 环境 |
| `/etc/systemd/system/prismind.service` | 后端服务，每次部署时从 `deploy/server/prismind.service` 更新 |
| `/etc/nginx/sites-available/prismind` | Nginx 配置，只在第一次准备时安装，之后由 certbot 加上 https |

`runtime/app-secret.key` 是登录令牌和后台保存的密钥（AI 接口、邮箱密码）的加密钥匙，**丢了所有人都要重新登录、后台密钥要重新填写**，换服务器时一定要一起搬。

## 第一次准备服务器

1. 买一台 Ubuntu 22.04/24.04、至少 8 GB 内存的服务器，防火墙放开 22、80、443。
2. 本机生成钥匙：`ssh-keygen -t ed25519 -f ~/.ssh/prismind_hk_ed25519 -N ""`，在云服务器控制台的网页终端里把 `~/.ssh/prismind_hk_ed25519.pub` 的内容追加到 `~/.ssh/authorized_keys`。
3. 把 `deploy/server/setup.sh` 和 `nginx-prismind.conf` 传上去，`sudo bash setup.sh`：装 Nginx、Node.js、Python 环境、certbot，加 4 GB 交换空间，建 `prismind` 用户和目录，SSH 只允许用钥匙登录。

## 搬数据

在本机（Git Bash）把数据打包：账户数据库用 SQLite 在线备份导出一份一致的副本，其余直接打包；日志和 `runtime/data_jobs`（里面是本机的进程号）不带。

```bash
cd dashboard/backend/data
python -c "import sqlite3; s=sqlite3.connect('app.db'); d=sqlite3.connect('/tmp/app.db'); s.backup(d)"
tar -cf /tmp/data.tar --exclude=runtime/logs --exclude=runtime/data_jobs market runtime backups -C /tmp app.db
scp -i ~/.ssh/prismind_hk_ed25519 /tmp/data.tar ../.env ubuntu@服务器:/tmp/
```

在服务器上：

```bash
sudo tar -xf /tmp/data.tar -C /opt/prismind/data
sudo install -o prismind -g prismind -m 600 /tmp/.env /opt/prismind/shared/.env
sudo chown -R prismind:prismind /opt/prismind/data
rm /tmp/data.tar /tmp/.env
```

## 部署和更新

PR 合并后，在本机项目目录（Git Bash）运行：

```bash
scripts/deploy.sh                 # 部署 origin/main
scripts/deploy.sh 某个分支或提交   # 部署别的版本
```

脚本把代码打包传到服务器，装依赖、打包网页、切换 `current`、重启后端并检查 `/api/health`；新版本没启动成功会自动切回上一个版本。重启网站时，正在运行的数据下载任务会继续。

回退到上一个版本：

```bash
ls -1dt /opt/prismind/releases/*/                      # 找到上一个版本
sudo ln -sfn /opt/prismind/releases/上一个版本 /opt/prismind/current
sudo systemctl restart prismind
```

## 切换域名（从本机 Tunnel 换到服务器）

1. 本机停止公开网站：`scripts\tunnel.ps1 -Stop`，并在管理后台确认没有数据任务在跑。
2. 按“搬数据”再同步一次账户数据库和 `runtime`（行情数据如果当天更新过也要同步）。
3. 在 Cloudflare 的 DNS 里，把 `getprismind.com` 和 `www` 两条 CNAME（指向 Tunnel）删掉，换成指向服务器 IP 的 A 记录，**代理状态选“仅 DNS”（灰色云朵）**。
4. 服务器上申请证书：`sudo certbot --nginx -d getprismind.com -d www.getprismind.com`，选择把 http 自动跳转到 https。证书会自动续期。
5. 本机取消开机自动启动：`scripts\tunnel.ps1 -Uninstall`（腾讯电脑管家可能要先放行），先保留几天作为备用。

## 日常查看

```bash
systemctl status prismind                 # 后端是否在运行
journalctl -u prismind -n 100 --no-pager   # 最近的后端日志
sudo tail -f /var/log/nginx/access.log     # 访问记录
free -h; df -h /                           # 内存、硬盘
```

## 注意

- 只开一个后端进程，不要加 `--workers`：次数限制、计算排队都记在这个进程里。
- 每天的全市场更新最多用约 5 GB 内存，8 GB 内存加 6 GB 交换空间够用；如果以后更新失败或网站在更新时变卡，先看 `free -h`。
- 备份默认在 `/opt/prismind/data/backups`，和网站在同一块硬盘上，还应该定期复制到别处。
