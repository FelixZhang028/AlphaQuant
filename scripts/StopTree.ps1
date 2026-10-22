# 停掉一个本平台的旧进程（例如占着端口的旧后端）和它启动的子进程，但不停后台数据任务。
# 数据任务（quant_platform.application.data_jobs）是后端启动的子进程，用 taskkill /T 会把它一起停掉，
# 正在下载的数据就中断了；它自己会接着运行，需要时在数据更新页停止。
function Stop-PlatformTree([int]$Id) {
    $all = @(Get-CimInstance Win32_Process)
    $order = New-Object System.Collections.Generic.List[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    $queue.Enqueue($Id)
    while ($queue.Count -gt 0) {
        $current = $queue.Dequeue()
        $order.Add($current)
        foreach ($child in $all) {
            if ($child.ParentProcessId -ne $current -or $child.ProcessId -eq $current) { continue }
            if (([string]$child.CommandLine).IndexOf('quant_platform.application.data_jobs', [StringComparison]::OrdinalIgnoreCase) -ge 0) { continue }
            $queue.Enqueue([int]$child.ProcessId)
        }
    }
    # 先停子进程，再停父进程
    for ($i = $order.Count - 1; $i -ge 0; $i--) {
        Stop-Process -Id $order[$i] -Force -ErrorAction SilentlyContinue
    }
}
