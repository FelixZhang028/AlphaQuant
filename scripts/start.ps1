param(
    [ValidateRange(1, 65535)][int]$BackendPort = 8000,
    [ValidateRange(1, 65535)][int]$FrontendPort = 5273,
    [ValidateRange(0, 3600)][int]$StopAfterSeconds = 0,
    [string]$LogDirectory = '',
    [switch]$NoBrowser
)
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$backendRoot = Join-Path $projectRoot 'dashboard\backend'
$frontendRoot = Join-Path $projectRoot 'landing'
$logRoot = if ($LogDirectory) { [IO.Path]::GetFullPath($LogDirectory) } else { Join-Path $backendRoot 'data\runtime\logs' }
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
$backend = $null
$frontend = $null
$processGroup = $null
$startupExitCode = 0
try {
    if ($BackendPort -eq $FrontendPort) { throw '前后端端口不能相同。' }
    if (-not ('FellowQuant.Launcher.ProcessGroup' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'ProcessGroup.cs')
    }
    Write-Host '============================================'
    Write-Host '  智投引擎 FellowQuant - 一键启动'
    Write-Host '============================================'
    Write-Host ''
    Write-Host "[启动] 后端服务  http://127.0.0.1:$BackendPort  （API 文档 /docs）"
    Write-Host "[启动] 前端页面  http://localhost:$FrontendPort"
    Write-Host '服务在后台运行，回到此启动窗口按任意键停止前后端。'
    Write-Host '后台数据任务（每天自动更新、补历史数据）不随窗口关闭，会继续运行；需要时在数据更新页停止。'
    Write-Host ''

    # 清理上次会话遗留的本平台进程（直接关闭启动窗口时子进程会存活并占住端口）。
    # 只清理命令行可识别为本平台的进程；外来进程仍按端口冲突报错。
    foreach ($port in @($BackendPort, $FrontendPort)) {
        $listeners = Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue
        foreach ($listener in $listeners) {
            $stale = Get-CimInstance Win32_Process -Filter "ProcessId=$($listener.OwningProcess)" -ErrorAction SilentlyContinue
            $commandLine = if ($stale) { [string]$stale.CommandLine } else { '' }
            $ours = $commandLine.IndexOf($projectRoot, [StringComparison]::OrdinalIgnoreCase) -ge 0
            if ($ours) {
                Write-Host "[清理] 发现上次遗留的进程（端口 $port，PID $($listener.OwningProcess)），已自动停止。"
                $savedPreference = $ErrorActionPreference
                try {
                    $ErrorActionPreference = 'Continue'
                    & taskkill.exe /PID $listener.OwningProcess /T /F 2>$null | Out-Null
                } finally { $ErrorActionPreference = $savedPreference }
            }
        }
    }
    Start-Sleep -Milliseconds 500

    foreach ($port in @($BackendPort, $FrontendPort)) {
        if (Get-NetTCPConnection -State Listen -LocalPort $port -ErrorAction SilentlyContinue) {
            throw "端口 $port 已被其他程序占用（非本平台进程），请先停止该程序再启动。"
        }
    }
    $pythonPath = (Get-Command python -ErrorAction Stop).Source
    $nodePath = (Get-Command node -ErrorAction Stop).Source
    $processGroup = New-Object FellowQuant.Launcher.ProcessGroup
    $backend = $processGroup.Start($pythonPath,
        [string[]]@('-m', 'uvicorn', 'app.main:app', '--app-dir', $backendRoot, '--host', '127.0.0.1', '--port', "$BackendPort"),
        $backendRoot, (Join-Path $logRoot 'backend.stdout.log'), (Join-Path $logRoot 'backend.stderr.log'))
    # Direct Vite entry avoids cmd/npm intermediary processes.
    $frontend = $processGroup.Start($nodePath,
        [string[]]@((Join-Path $frontendRoot 'node_modules\vite\bin\vite.js'), '--host', '127.0.0.1', '--port', "$FrontendPort", '--strictPort'),
        $frontendRoot, (Join-Path $logRoot 'frontend.stdout.log'), (Join-Path $logRoot 'frontend.stderr.log'))
    $ready = $false
    for ($attempt = 0; $attempt -lt 45; $attempt++) {
        if ($backend.HasExited -or $frontend.HasExited) { throw "服务启动失败，请查看 $logRoot 中的日志。" }
        try {
            $apiCheck = Invoke-WebRequest "http://127.0.0.1:$BackendPort/" -UseBasicParsing -TimeoutSec 1
            $pageCheck = Invoke-WebRequest "http://127.0.0.1:$FrontendPort/" -UseBasicParsing -TimeoutSec 1
            if ($apiCheck.StatusCode -eq 200 -and $pageCheck.StatusCode -eq 200) { $ready = $true; break }
        } catch { }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { throw "服务启动超时，请查看 $logRoot 中的日志。" }
    if (-not $NoBrowser) { Start-Process "http://127.0.0.1:$FrontendPort/" }
    Write-Host '服务已启动。回到此窗口按任意键停止前后端；日志保存在 dashboard/backend/data/runtime/logs。'
    if ($StopAfterSeconds -gt 0) {
        Start-Sleep -Seconds $StopAfterSeconds
    } elseif ([Console]::IsInputRedirected) {
        Write-Host '当前输入已被重定向，请按 Enter 停止。'
        [void][Console]::ReadLine()
    } else {
        [void][Console]::ReadKey($true)
    }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    $startupExitCode = 1
} finally {
    # Stop the whole job even if a root already exited. Closing the console also
    # closes the job's last handle, so descendants cannot outlive the launcher.
    if ($null -ne $processGroup) {
        Write-Host '[停止] 正在关闭前后端…（正在运行的后台数据任务会继续，完成后自动结束）'
        try { $processGroup.Stop() }
        catch {
            $startupExitCode = 1
            Write-Host "[停止失败] $($_.Exception.Message)" -ForegroundColor Red
        } finally { $processGroup.Dispose() }
    }
    foreach ($child in @($frontend, $backend)) {
        if ($null -ne $child) { $child.Dispose() }
    }
}
exit $startupExitCode
