@echo off
setlocal
cd /d "%~dp0"
title Install AlphaQuant Platform

where python >nul 2>nul
if errorlevel 1 (
    echo Python was not found.
    echo Install Python 3.11 or 3.12 and select "Add Python to PATH" during installation.
    pause
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo Creating an isolated Python environment...
    python -m venv .venv
    if errorlevel 1 (
        echo Failed to create the Python environment.
        pause
        exit /b 1
    )
)

echo Installing project dependencies. The first installation may take a few minutes...
".venv\Scripts\python.exe" -m pip install -e .
if errorlevel 1 (
    echo.
    echo Installation failed. Check the network connection and run this file again.
    pause
    exit /b 1
)

echo Installation completed. Starting AlphaQuant Platform...
".venv\Scripts\python.exe" -m streamlit run "src\quant_platform\web\app.py" --server.headless false --browser.gatherUsageStats false

if errorlevel 1 (
    echo.
    echo Startup failed. Keep this window open and check the error above.
    pause
)
