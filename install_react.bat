@echo off
setlocal
cd /d "%~dp0"
where npm >nul 2>nul
if errorlevel 1 (
    echo Install Node.js LTS first, then run this script again.
    pause
    exit /b 1
)
if exist ".venv\Scripts\python.exe" (
    set "QUANT_WEB_PYTHON=.venv\Scripts\python.exe"
) else (
    set "QUANT_WEB_PYTHON=python"
)
"%QUANT_WEB_PYTHON%" -m pip install -e ".[api]"
if errorlevel 1 goto failed
pushd frontend
call npm ci --cache .npm-cache --no-audit --no-fund
if errorlevel 1 (
    popd
    goto failed
)
call npm run build
if errorlevel 1 (
    popd
    goto failed
)
popd
echo Ready. Double-click start_react.bat to open the new workspace.
pause
exit /b 0
:failed
echo Installation failed. See the error above.
pause
exit /b 1
