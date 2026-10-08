@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "QUANT_API_PYTHON=.venv\Scripts\python.exe"
) else (
    set "QUANT_API_PYTHON=python"
)

"%QUANT_API_PYTHON%" -c "import fastapi, uvicorn, quant_platform.api.main" >nul 2>nul
if errorlevel 1 (
    set "QUANT_API_PYTHON=python"
)
"%QUANT_API_PYTHON%" -c "import fastapi, uvicorn, quant_platform.api.main" >nul 2>nul
if errorlevel 1 (
    echo API dependencies are missing. Install them with:
    echo "%QUANT_API_PYTHON%" -m pip install -e ".[api]"
    pause
    exit /b 1
)

echo AlphaQuant API: http://127.0.0.1:8000/docs
echo Close this window or press Ctrl+C to stop the API.
"%QUANT_API_PYTHON%" -m quant_platform.api.cli %*
if errorlevel 1 pause
