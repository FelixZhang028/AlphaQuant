"""Exercise real Windows job ownership, including orphan and abrupt-exit cases."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'win32', reason='Windows job objects')
ROOT = Path(__file__).resolve().parents[4]
POWERSHELL = Path(os.environ.get('SystemRoot', 'C:/Windows')) / 'System32/WindowsPowerShell/v1.0/powershell.exe'


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def listening(port):
    with socket.socket() as sock:
        sock.settimeout(.2)
        return sock.connect_ex(('127.0.0.1', port)) == 0


def wait_for(check, message):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if check():
            return
        time.sleep(.1)
    raise AssertionError(message)


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


ORPHAN_PARENT = (
    "import subprocess,sys,time\n"
    "subprocess.Popen([sys.executable, '-m', 'http.server', sys.argv[1], '--bind', '127.0.0.1'], "
    "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)\n"
    "time.sleep(.5)\n")


def orphan_launcher(tmp_path, port, parent_code=ORPHAN_PARENT):
    # A space/non-ASCII path also verifies argv/path handling under Windows PowerShell 5.1.
    folder = tmp_path / 'process logs 测试'
    folder.mkdir()
    parent = folder / 'temporary parent.py'
    parent.write_text(parent_code, encoding='utf-8')
    ready = folder / 'ready.txt'
    script = folder / 'launcher.ps1'
    script.write_text(
        "$ErrorActionPreference='Stop'\n"
        f"Add-Type -Path {literal(ROOT / 'scripts/ProcessGroup.cs')}\n"
        "$group=New-Object FellowQuant.Launcher.ProcessGroup\n"
        "try {\n"
        f" $root=$group.Start({literal(sys.executable)}, [string[]]@({literal(parent)}, '{port}'), "
        f"{literal(folder)}, {literal(folder / 'out.log')}, {literal(folder / 'err.log')})\n"
        " if (-not $root.WaitForExit(5000)) { throw 'Intermediate parent did not exit' }\n"
        f" [IO.File]::WriteAllText({literal(ready)}, 'parent has exited')\n"
        " [void][Console]::ReadLine()\n"
        "} finally { $group.Stop(); $group.Dispose() }\n", encoding='utf-8-sig')
    proc = subprocess.Popen([str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script)],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return proc, ready


def cleanup(proc):
    if proc.poll() is None:
        proc.kill()  # Only the isolated test launcher we created; its job owns its children.
    proc.communicate(timeout=10)


def test_normal_stop_kills_descendant_even_after_intermediate_parent_exits(tmp_path):
    port = free_port()
    proc, ready = orphan_launcher(tmp_path, port)
    try:
        wait_for(lambda: ready.exists() and listening(port), 'Orphan test server did not start')
        _, errors = proc.communicate(input='stop\n', timeout=15)
        assert proc.returncode == 0, errors
        wait_for(lambda: not listening(port), 'Descendant still listens after normal cleanup')
    finally:
        cleanup(proc)


def test_abrupt_launcher_exit_kills_its_descendants_but_not_unrelated_server(tmp_path):
    port, unrelated_port = free_port(), free_port()
    unrelated = subprocess.Popen([sys.executable, '-m', 'http.server', str(unrelated_port), '--bind', '127.0.0.1'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
    proc, ready = orphan_launcher(tmp_path, port)
    try:
        wait_for(lambda: ready.exists() and listening(port) and listening(unrelated_port), 'Test servers did not start')
        proc.kill()  # Simulate closing/killing the launcher before its finally block can execute.
        proc.communicate(timeout=10)
        wait_for(lambda: not listening(port), 'Descendant survived launcher exit')
        assert unrelated.poll() is None and listening(unrelated_port)
    finally:
        cleanup(proc)
        unrelated.terminate()
        unrelated.wait(timeout=10)


def test_a_data_job_started_by_the_backend_outlives_the_launcher(tmp_path):
    # 服务器进程跟着启动窗口一起结束；后端启动的数据下载（补财务数据可能要十几个小时）继续运行。
    server_port, job_port = free_port(), free_port()
    pid_file = tmp_path / 'job.pid'
    parent = (
        "import subprocess,sys,time\n"
        f"sys.path.insert(0, {str(ROOT / 'dashboard/backend')!r})\n"
        "from quant_platform.application.data_jobs import launch_detached\n"
        "subprocess.Popen([sys.executable, '-m', 'http.server', sys.argv[1], '--bind', '127.0.0.1'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW)\n"
        f"job = launch_detached([sys.executable, '-m', 'http.server', '{job_port}', '--bind', '127.0.0.1'], "
        "stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)\n"
        f"open({str(pid_file)!r}, 'w').write(str(job.pid))\n"
        "time.sleep(.5)\n")
    proc, ready = orphan_launcher(tmp_path, server_port, parent)
    try:
        wait_for(lambda: ready.exists() and listening(server_port) and listening(job_port), 'Test servers did not start')
        _, errors = proc.communicate(input='stop\n', timeout=15)
        assert proc.returncode == 0, errors
        wait_for(lambda: not listening(server_port), 'Server survived the launcher')
        time.sleep(.5)
        assert listening(job_port), 'The data job was stopped with the launcher'
    finally:
        cleanup(proc)
        if pid_file.exists():
            subprocess.run(['taskkill', '/PID', pid_file.read_text(), '/T', '/F'], capture_output=True)


def test_restarting_stops_the_old_backend_but_not_a_running_data_job(tmp_path):
    # 启动器清理占着端口的旧后端时，旧后端启动的数据任务要继续下载，普通子进程一起停掉。
    pids = tmp_path / 'pids.txt'
    backend = subprocess.Popen([sys.executable, '-c', (
        "import subprocess, sys, time\n"
        "sleep = 'import time; time.sleep(60)'\n"
        "worker = subprocess.Popen([sys.executable, '-c', sleep])\n"
        # 拼出来：在虚拟环境里，这个“后端”是 python.exe 启动器下面的真正 Python，它的命令行里不能出现数据任务的名字
        "job = subprocess.Popen([sys.executable, '-c', sleep, 'quant_platform.application.' + 'data_jobs'])\n"
        f"open({str(pids)!r}, 'w').write(f'{{worker.pid}} {{job.pid}}')\n"
        "time.sleep(60)\n")])
    try:
        wait_for(lambda: pids.exists() and pids.read_text().strip(), 'Test processes did not start')
        worker, job = (int(value) for value in pids.read_text().split())
        command = f". {literal(ROOT / 'scripts' / 'StopTree.ps1')}; Stop-PlatformTree -Id {backend.pid}"
        subprocess.run([str(POWERSHELL), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', command],
                       check=True, capture_output=True, timeout=60)
        wait_for(lambda: backend.poll() is not None, 'The old backend survived')
        alive = lambda pid: str(pid) in subprocess.run(['tasklist', '/FI', f'PID eq {pid}', '/NH'],
                                                       capture_output=True, text=True).stdout
        wait_for(lambda: not alive(worker), 'An ordinary child process survived')
        assert alive(job), 'The data job was stopped with the old backend'
    finally:
        backend.kill()
        if pids.exists() and pids.read_text().strip():
            for pid in pids.read_text().split():
                subprocess.run(['taskkill', '/PID', pid, '/F'], capture_output=True)
