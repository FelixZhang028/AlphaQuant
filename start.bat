@echo off
setlocal
cd /d "%~dp0"
title FellowQuant Platform

if exist ".venv\Scripts\python.exe" (
    set "PYTHON_EXE=.venv\Scripts\python.exe"
) else (
    python -c "import streamlit, quant_platform" >nul 2>nul
    if errorlevel 1 (
        call "%~dp0install_and_start.bat"
        exit /b
    )
    set "PYTHON_EXE=python"
)

echo Starting FellowQuant Platform...
echo The browser will open automatically. Close this window to stop the platform.
"%PYTHON_EXE%" -m streamlit run "src\quant_platform\web\app.py" --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo Startup failed. Keep this window open and check the error above.
    pause
)
