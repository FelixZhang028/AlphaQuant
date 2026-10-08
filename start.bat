@echo off
chcp 65001 >nul
title 智投引擎 - 一键启动
cd /d "%~dp0"

echo ============================================
echo   智投引擎 FellowQuant - 一键启动
echo ============================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 python，请先安装 Python 3.11+
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo [错误] 未找到 node，请先安装 Node.js 18+
  pause
  exit /b 1
)

rem ---- 后端依赖检查（首次自动安装）----
if not exist "dashboard\backend\quant_platform\__init__.py" (
  echo [错误] 未找到后端代码目录 dashboard\backend
  pause
  exit /b 1
)
python -c "import fastapi, uvicorn, pandas, pyarrow, requests, yaml, dotenv, scipy, rich, akshare, baostock" >nul 2>nul
if errorlevel 1 (
  echo [提示] 首次运行：安装后端依赖...
  python -m pip install -r dashboard\backend\requirements.txt
  if errorlevel 1 exit /b 1
)

rem ---- 前端依赖检查（首次自动安装）----
node -e "require.resolve('vite',{paths:['./landing']}); require.resolve('three',{paths:['./landing']})" >nul 2>nul
if errorlevel 1 (
  echo [提示] 首次运行：安装前端依赖...
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [错误] 未找到 npm，请先安装 Node.js 18+
    pause
    exit /b 1
  )
  call npm install --prefix landing
  if errorlevel 1 exit /b 1
)

echo.
echo [启动] 后端服务  http://127.0.0.1:8000  （API 文档 /docs）
echo [启动] 前端页面  http://localhost:5273
echo 服务在后台运行，按任意键停止全部服务。

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
set "startupExitCode=%errorlevel%"
if not "%startupExitCode%"=="0" (
  echo [错误] 启动失败，请查看以上提示。
  pause
)
exit /b %startupExitCode%
