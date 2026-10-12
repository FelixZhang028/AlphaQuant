$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'dashboard\backend'
$frontendRoot = Join-Path $projectRoot 'landing'
$logRoot = Join-Path $backendRoot 'data\runtime\logs'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$backend = $null
$frontend = $null
try {
    Write-Host '============================================'
    Write-Host '  智投引擎 FellowQuant - 一键启动'
    Write-Host '============================================'
    Write-Host ''
    Write-Host '[启动] 后端服务  http://127.0.0.1:8000  （API 文档 /docs）'
    Write-Host '[启动] 前端页面  http://localhost:5273'
    Write-Host '服务在后台运行，按任意键停止全部服务。'
    Write-Host ''

    # 清理上次会话遗留的本平台进程（直接关闭启动窗口时子进程会存活并占住端口）。
    # 只清理命令行可识别为本平台的进程；外来进程仍按端口冲突报错。
    foreach ($port in @(8000, 5273)) {
        $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $stale = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
            $commandLine = if ($stale) { [string]$stale.CommandLine } else { '' }
            $ours = $commandLine.Contains($projectRoot) -or
                ($port -eq 8000 -and $commandLine -match 'uvicorn') -or
                ($port -eq 5273 -and $commandLine -match 'vite')
            if ($ours) {
                Write-Host "[清理] 发现上次遗留的进程（端口 $port，PID $($listener.OwningProcess)），已自动停止。"
                & taskkill.exe /PID $listener.OwningProcess /T /F | Out-Null
            }
        }
    }
    Start-Sleep -Milliseconds 500

    foreach ($port in @(8000, 5273)) {
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
            throw "端口 $port 已被其他程序占用（非本平台进程），请先停止该程序再启动。"
        }
    }
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $backend = Start-Process -FilePath $pythonPath -ArgumentList @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000') -WorkingDirectory $backendRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'backend.stdout.log') -RedirectStandardError (Join-Path $logRoot 'backend.stderr.log')
    $frontend = Start-Process -FilePath $env:ComSpec -ArgumentList '/d /c npm.cmd run dev -- --host 127.0.0.1' -WorkingDirectory $frontendRoot -PassThru -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logRoot 'frontend.stdout.log') -RedirectStandardError (Join-Path $logRoot 'frontend.stderr.log')
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($backend.HasExited -or $frontend.HasExited) { throw "服务启动失败，请查看 $logRoot 中的日志。" }
        try {
            $apiCheck = Invoke-WebRequest 'http://127.0.0.1:8000/' -UseBasicParsing -TimeoutSec 1
            $pageCheck = Invoke-WebRequest 'http://127.0.0.1:5273/' -UseBasicParsing -TimeoutSec 1
            if ($apiCheck.StatusCode -eq 200 -and $pageCheck.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "服务启动超时，请查看 $logRoot 中的日志。" }
    Start-Process 'http://127.0.0.1:5273'
    Write-Host '服务已启动。按任意键停止前后端；日志保存在 dashboard/backend/data/runtime/logs。'
    [void][Console]::ReadKey($true)
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
} finally {
    foreach ($child in @($frontend, $backend)) {
        if ($child -and -not $child.HasExited) { & taskkill.exe /PID $child.Id /T /F | Out-Null }
    }
}
