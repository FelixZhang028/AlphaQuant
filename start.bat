@echo off
setlocal
title FellowQuant Launcher
cd /d "%~dp0"

rem This file is intentionally ASCII-only.
rem cmd.exe mis-parses batch files that combine "chcp 65001" with multi-byte
rem characters (line fragments get executed as commands), so every
rem user-facing message lives in scripts\start.ps1 instead (UTF-8 with BOM).

rem Resolve Windows PowerShell directly; its directory may be absent from PATH.
set "startupPowerShell=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"
if not exist "%startupPowerShell%" (
  echo [ERROR] Windows PowerShell not found.
  pause
  exit /b 1
)

where python >nul 2>nul
if errorlevel 1 (
  echo [ERROR] python not found. Install Python 3.11+ first.
  pause
  exit /b 1
)
where node >nul 2>nul
if errorlevel 1 (
  echo [ERROR] node not found. Install Node.js 18+ first.
  pause
  exit /b 1
)

rem ---- Backend dependencies (auto-install on first run) ----
if not exist "dashboard\backend\quant_platform\__init__.py" (
  echo [ERROR] backend code not found: dashboard\backend
  pause
  exit /b 1
)
python -c "import fastapi, uvicorn, pandas, pyarrow, requests, yaml, dotenv, scipy, rich, akshare, baostock" >nul 2>nul
if errorlevel 1 (
  echo [INFO] First run: installing backend dependencies...
  python -m pip install -r dashboard\backend\requirements.txt
  if errorlevel 1 exit /b 1
)

rem ---- Frontend dependencies (auto-install on first run) ----
node -e "require.resolve('vite',{paths:['./landing']}); require.resolve('three',{paths:['./landing']})" >nul 2>nul
if errorlevel 1 (
  echo [INFO] First run: installing frontend dependencies...
  where npm >nul 2>nul
  if errorlevel 1 (
    echo [ERROR] npm not found. Install Node.js 18+ first.
    pause
    exit /b 1
  )
  call npm install --prefix landing
  if errorlevel 1 exit /b 1
)

"%startupPowerShell%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start.ps1"
set "startupExitCode=%errorlevel%"
if not "%startupExitCode%"=="0" (
  pause
)
exit /b %startupExitCode%
