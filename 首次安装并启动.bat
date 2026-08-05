@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
title 首次安装 A股量化工作台

where python >nul 2>nul
if errorlevel 1 (
    echo 未找到 Python。
    echo 请先安装 Python 3.11 或 3.12，并在安装时勾选“Add Python to PATH”。
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo 正在创建独立运行环境……
    python -m venv .venv
    if errorlevel 1 (
        echo 创建运行环境失败，请确认 Python 版本为 3.11 或 3.12。
        pause
        exit /b 1
    )
)

echo 正在安装平台依赖，首次安装可能需要几分钟……
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
    echo.
    echo 安装失败，请检查网络连接后重新双击本文件。
    pause
    exit /b 1
)

echo 安装完成，正在启动平台……
echo 浏览器会自动打开；以后只需双击“启动量化平台.bat”。
".venv\Scripts\python.exe" -m streamlit run "src\quant_platform\web\app.py" --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo 平台启动失败。请保留本窗口中的提示信息。
    pause
)
