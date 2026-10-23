param(
    [ValidateRange(1, 65535)][int]$Port = 8100,
    [switch]$SkipBuild,
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Stop,
    [switch]$Status,
    [string]$Tunnel = '',
    [string]$Hostname = '',
    [switch]$Detached
)
# 在自己的电脑上公开网站：用 scripts\serve.ps1 打包网页并启动后端，再用 Cloudflare Tunnel 给它一个 https 网址。
#   -Tunnel 名字 -Hostname 域名   用正式 Tunnel，网址固定（例如 -Tunnel prismind -Hostname getprismind.com）。
#                               先在这台电脑上运行一次 cloudflared tunnel login、tunnel create、tunnel route dns。
#   不带这两个参数                用临时 Tunnel：网址形如 https://xxx.trycloudflare.com，不需要账号，但每次重新启动都会变。
# 当前网址写在 dashboard\backend\data\runtime\public-url.txt，也可以用 -Status 查看。
# 后端或 Tunnel 意外退出时自动重启。默认用 8100 端口，和本机开发（scripts\start.ps1，8000）分开。
#   -Install    登录 Windows 后自动在后台启动（放进“启动”文件夹，不需要管理员权限），带上 -Tunnel、-Hostname 等设置
#   -Uninstall  取消自动启动
#   -Stop       停止正在运行的公开网站
#   -Status     查看是否在运行和当前网址
# 从编辑器、自动化工具的终端里启动时，会自动转到后台运行，关掉那个终端也不会停。
# 需要先安装 cloudflared：winget install --id Cloudflare.cloudflared
$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtimeRoot = Join-Path $projectRoot 'dashboard\backend\data\runtime'
$logRoot = Join-Path $runtimeRoot 'logs'
$urlFile = Join-Path $runtimeRoot 'public-url.txt'
$pidFile = Join-Path $runtimeRoot 'public-site.pid'
$logFile = Join-Path $logRoot 'public-site.log'
$tunnelLog = Join-Path $logRoot 'public-tunnel.log'
$shortcut = Join-Path ([Environment]::GetFolderPath('Startup')) 'FellowQuant Public Site.lnk'
$powerShellPath = Join-Path $env:SystemRoot 'System32\WindowsPowerShell\v1.0\powershell.exe'
New-Item -ItemType Directory -Force -Path $logRoot | Out-Null
if ($Tunnel -and -not $Hostname) { throw '用正式 Tunnel 时要同时给出 -Hostname（例如 getprismind.com）。' }
# 自动启动、转到后台重新启动时，都带上同样的设置。
$launchArguments = "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`" -Port $Port"
if ($Tunnel) { $launchArguments += " -Tunnel `"$Tunnel`" -Hostname `"$Hostname`"" }

function Get-Supervisor {
    if (-not (Test-Path $pidFile)) { return $null }
    $id = 0
    if (-not [int]::TryParse((Get-Content $pidFile -Raw).Trim(), [ref]$id)) { return $null }
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$id" -ErrorAction SilentlyContinue
    # 进程号可能已经被别的程序重新使用：只认命令行里有本脚本的进程。
    if ($process -and ([string]$process.CommandLine).IndexOf('tunnel.ps1', [StringComparison]::OrdinalIgnoreCase) -ge 0) { return $process }
    return $null
}

function Write-Log([string]$message) {
    $line = "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') $message"
    Write-Host $line
    # 日志文件被别的程序占用时只少记一行，不能影响网站运行。
    try { Add-Content -Path $logFile -Value $line -Encoding UTF8 } catch { }
}

if ($Install) {
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut($shortcut)
    $link.TargetPath = $powerShellPath
    $link.Arguments = $launchArguments
    $link.WorkingDirectory = $projectRoot
    $link.WindowStyle = 7
    $link.Save()
    Write-Host "已设置：登录 Windows 后自动启动公开网站（$shortcut）。"
    Write-Host '现在就启动：去掉 -Install 再运行一次（其他参数不变）。'
    Write-Host '腾讯电脑管家、360 等安全软件可能会删掉这个快捷方式；之后用 -Status 确认“自动启动：已设置”。'
    exit 0
}
if ($Uninstall) {
    Remove-Item $shortcut -ErrorAction SilentlyContinue
    Write-Host '已取消自动启动。正在运行的公开网站不受影响，需要时用 -Stop 停止。'
    exit 0
}
if ($Status) {
    $supervisor = Get-Supervisor
    Write-Host ("自动启动：" + $(if (Test-Path $shortcut) { '已设置' } else { '未设置' }))
    if (-not $supervisor) { Write-Host '公开网站：没有运行'; exit 1 }
    Write-Host "公开网站：正在运行（进程 $($supervisor.ProcessId)），本机地址 http://127.0.0.1:$Port"
    Write-Host ("公开网址：" + $(if (Test-Path $urlFile) { (Get-Content $urlFile -Raw).Trim() } else { '还没拿到，请稍等或查看 ' + $logFile }))
    exit 0
}
if ($Stop) {
    $supervisor = Get-Supervisor
    if (-not $supervisor) { Write-Host '公开网站没有在运行。'; exit 0 }
    # 结束守护进程后，它的进程组关闭，后端和 Tunnel 一起停止；正在运行的后台数据任务会继续，完成后自动结束。
    Stop-Process -Id $supervisor.ProcessId -Force
    Remove-Item $pidFile, $urlFile -ErrorAction SilentlyContinue
    Write-Log '[停止] 公开网站已停止。'
    exit 0
}

if (Get-Supervisor) { Write-Host '公开网站已经在运行，用 -Status 查看网址。'; exit 0 }
# 从别的程序里启动时，本进程可能在那个程序的进程组（Windows job）里：那个程序一结束，
# 整个网站会被一起强制关掉，来不及留下任何日志。这种情况下在进程组外面重新启动自己。
if (-not $Detached) {
    Add-Type -Namespace FellowQuant.Launcher -Name JobCheck -MemberDefinition @'
[DllImport("kernel32.dll")] public static extern bool IsProcessInJob(IntPtr process, IntPtr job, out bool result);
'@
    $inJob = $false
    [void][FellowQuant.Launcher.JobCheck]::IsProcessInJob([Diagnostics.Process]::GetCurrentProcess().Handle, [IntPtr]::Zero, [ref]$inJob)
    if ($inJob) {
        $arguments = "$launchArguments -Detached" + $(if ($SkipBuild) { ' -SkipBuild' } else { '' })
        $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{ ShowWindow = [uint16]0 }
        # 通过 WMI 启动：新进程由系统服务创建，不属于当前的进程组。
        $created = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine = "`"$powerShellPath`" $arguments"; CurrentDirectory = $projectRoot; ProcessStartupInformation = $startup
        }
        if ($created.ReturnValue -ne 0) { throw "转到后台启动失败（WMI 返回 $($created.ReturnValue)）。" }
        Write-Host "已转到后台启动公开网站（关掉当前窗口也不会停）。一两分钟后用 -Status 查看网址，日志在 $logFile"
        exit 0
    }
}

$mutex = New-Object Threading.Mutex($false, 'Local\FellowQuantPublicSite')
try { $owned = $mutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $owned = $true }
if (-not $owned) { Write-Host '公开网站已经在运行，用 -Status 查看网址。'; exit 0 }

$group = $null
$exitCode = 0
try {
    $cloudflared = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
    if (-not $cloudflared) {
        $cloudflared = @("$env:ProgramFiles\cloudflared\cloudflared.exe", "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe") |
            Where-Object { Test-Path $_ } | Select-Object -First 1
    }
    if (-not $cloudflared) { throw '没有找到 cloudflared，请先运行：winget install --id Cloudflare.cloudflared' }
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) {
        throw "端口 $Port 已被占用，请先停止占用它的程序，或用 -Port 换一个端口。"
    }
    if (-not ('FellowQuant.Launcher.ProcessGroup' -as [type])) {
        Add-Type -Path (Join-Path $PSScriptRoot 'ProcessGroup.cs')
    }
    Set-Content -Path $pidFile -Value $PID -Encoding ASCII
    Remove-Item $urlFile -ErrorAction SilentlyContinue
    # 访问都经过 Cloudflare，用户的真实地址在 CF-Connecting-IP 里（登录、注册的频率限制要用）。
    $env:FELLOWQUANT_CLIENT_IP_HEADER = 'CF-Connecting-IP'
    # 守护进程退出时（包括被 -Stop 结束），进程组里的后端和 Tunnel 一起停止。
    $group = New-Object FellowQuant.Launcher.ProcessGroup

    function Start-Backend([bool]$build) {
        $arguments = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'serve.ps1'), '-Port', "$Port")
        if (-not $build) { $arguments += '-SkipBuild' }
        Write-Log $(if ($build) { '[启动] 打包网页并启动后端…' } else { '[启动] 启动后端…' })
        $process = $group.Start($powerShellPath, [string[]]$arguments, $projectRoot,
            (Join-Path $logRoot 'public-backend.stdout.log'), (Join-Path $logRoot 'public-backend.stderr.log'))
        # 打包网页要一两分钟，最多等 10 分钟。
        $deadline = (Get-Date).AddMinutes(10)
        while ((Get-Date) -lt $deadline -and -not $process.HasExited) {
            $ready = $false
            try { $ready = (Invoke-WebRequest "http://127.0.0.1:$Port/api/health" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 } catch { }
            if ($ready) {
                Write-Log "[启动] 后端已就绪：http://127.0.0.1:$Port"
                return $process
            }
            Start-Sleep -Seconds 2
        }
        Write-Log "[出错] 后端没有启动成功，请查看 $logRoot 里的 public-backend.*.log"
        return $process
    }

    function Start-Tunnel {
        Remove-Item $urlFile -ErrorAction SilentlyContinue
        if ($Tunnel) {
            Write-Log "[启动] 正在连接正式 Tunnel $Tunnel …"
            $arguments = @('tunnel', '--no-autoupdate', 'run', '--url', "http://127.0.0.1:$Port", $Tunnel)
        } else {
            Write-Log '[启动] 正在向 Cloudflare 申请临时网址…'
            $arguments = @('tunnel', '--no-autoupdate', '--url', "http://127.0.0.1:$Port")
        }
        $process = $group.Start($cloudflared, [string[]]$arguments,
            $projectRoot, (Join-Path $logRoot 'public-tunnel.stdout.log'), $tunnelLog)
        for ($attempt = 0; $attempt -lt 60 -and -not $process.HasExited; $attempt++) {
            Start-Sleep -Seconds 1
            # cloudflared 把日志写在 stderr。
            $text = Get-Content $tunnelLog -Raw -ErrorAction SilentlyContinue
            if ($Tunnel) {
                # 正式 Tunnel 的网址固定，有一条连接连上 Cloudflare 就能访问。
                if ([string]$text -match 'Registered tunnel connection') {
                    Set-Content -Path $urlFile -Value "https://$Hostname" -Encoding ASCII
                    Write-Log "[启动] 已连上 Cloudflare，网址：https://$Hostname"
                    return $process
                }
                continue
            }
            # 临时网址出现在一个文字框里。api.trycloudflare.com 是申请网址的接口，不是网址本身。
            $match = [regex]::Match([string]$text, 'https://(?!api\.)[a-z0-9-]+\.trycloudflare\.com')
            if ($match.Success) {
                Set-Content -Path $urlFile -Value $match.Value -Encoding ASCII
                Write-Log "[启动] 公开网址：$($match.Value)"
                return $process
            }
        }
        Write-Log $(if ($Tunnel) { "[出错] 没有连上 Cloudflare，请查看 $tunnelLog" } else { "[出错] 没有拿到临时网址，请查看 $tunnelLog" })
        return $process
    }

    # PowerShell 变量名不分大小写：进程不能叫 $tunnel，否则会覆盖参数 $Tunnel。
    $backendProcess = Start-Backend (-not $SkipBuild)
    $tunnelProcess = Start-Tunnel
    while ($true) {
        Start-Sleep -Seconds 5
        if ($backendProcess.HasExited) {
            Write-Log '[重启] 后端已退出，15 秒后重新启动。'
            Start-Sleep -Seconds 15
            $backendProcess = Start-Backend $false
        }
        if ($tunnelProcess.HasExited) {
            Write-Log $(if ($Tunnel) { '[重启] Tunnel 已退出，15 秒后重新连接（网址不变）。' } else { '[重启] Tunnel 已退出，15 秒后重新申请（网址会变）。' })
            Remove-Item $urlFile -ErrorAction SilentlyContinue
            Start-Sleep -Seconds 15
            $tunnelProcess = Start-Tunnel
        }
    }
} catch {
    Write-Log "[出错] $($_.Exception.Message)"
    $exitCode = 1
} finally {
    if ($null -ne $group) {
        try { $group.Stop() } catch { } finally { $group.Dispose() }
    }
    Remove-Item $pidFile, $urlFile -ErrorAction SilentlyContinue
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
exit $exitCode
