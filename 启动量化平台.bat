@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title A股量化工作台

if not exist ".venv\Scripts\python.exe" (
    echo 首次运行需要准备独立环境，正在进入自动安装程序……
    call "%~dp0首次安装并启动.bat"
    exit /b %errorlevel%
)

echo 正在启动 A股量化工作台，请稍候……
echo 浏览器会自动打开；关闭本窗口即可停止平台。
".venv\Scripts\python.exe" -m streamlit run "src\quant_platform\web\app.py" --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo 平台启动失败。请保留本窗口中的提示信息。
    pause
)
