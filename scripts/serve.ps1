param(
    [ValidateRange(1, 65535)][int]$Port = 8000,
    [string]$ListenHost = '127.0.0.1',
    [switch]$SkipBuild
)
# 正式部署：打包官网/功能台，由后端直接提供网页和接口，整个网站只有一个地址。
# 前面再放 Cloudflare Tunnel 或 Nginx 提供 https；只监听本机地址，不直接暴露端口。
# 配置写在 dashboard\backend\.env（参考 .env.example）。本机开发请用 scripts\start.ps1。
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'dashboard\backend'
$siteRoot = Join-Path $projectRoot 'landing'
$siteDist = Join-Path $siteRoot 'dist'

if (-not $SkipBuild) {
    Write-Host '[打包] 官网和功能台 ...'
    Push-Location $siteRoot
    try {
        if (-not (Test-Path (Join-Path $siteRoot 'node_modules'))) { & npm ci; if ($LASTEXITCODE) { throw 'npm ci 失败' } }
        & npm run build; if ($LASTEXITCODE) { throw '前端打包失败' }
    } finally { Pop-Location }
}
if (-not (Test-Path (Join-Path $siteDist 'index.html'))) { throw "没有找到打包好的网页：$siteDist" }

$env:FELLOWQUANT_STATIC_DIR = $siteDist
Remove-Item Env:FELLOWQUANT_API_DOCS -ErrorAction SilentlyContinue
Write-Host "[启动] FellowQuant  http://${ListenHost}:$Port  （按 Ctrl+C 停止）"
# 只开一个进程：次数限制和后台任务都记在这个进程里。
& python -m uvicorn app.main:app --app-dir $backendRoot --host $ListenHost --port $Port --no-server-header
exit $LASTEXITCODE
