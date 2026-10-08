@echo off
setlocal
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    set "QUANT_WEB_PYTHON=.venv\Scripts\python.exe"
) else (
    set "QUANT_WEB_PYTHON=python"
)
"%QUANT_WEB_PYTHON%" -c "import fastapi, uvicorn, quant_platform.api.main" >nul 2>nul
if errorlevel 1 (
    set "QUANT_WEB_PYTHON=python"
)
"%QUANT_WEB_PYTHON%" -c "import fastapi, uvicorn, quant_platform.api.main" >nul 2>nul
if errorlevel 1 (
    echo API dependencies are missing. Run install_react.bat first.
    pause
    exit /b 1
)
if not exist "frontend\dist\index.html" (
    echo React has not been built. Run install_react.bat first.
    pause
    exit /b 1
)
echo AlphaQuant React: http://127.0.0.1:8000/app
echo Close this window or press Ctrl+C to stop the web service.
"%QUANT_WEB_PYTHON%" -m quant_platform.api.cli --web --open-browser %*
if errorlevel 1 pause
