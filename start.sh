#!/usr/bin/env bash
# FellowQuant — Linux/macOS 启动脚本（与 start.bat 等效）
set -e
cd "$(dirname "$0")"

if [ -x ".venv/Scripts/python.exe" ]; then
    PYTHON_EXE=".venv/Scripts/python.exe"
elif [ -x ".venv/bin/python" ]; then
    PYTHON_EXE=".venv/bin/python"
else
    PYTHON_EXE="python3"
fi

echo "Starting FellowQuant Platform..."
echo "The browser will open automatically. Press Ctrl+C to stop."
exec "$PYTHON_EXE" -m streamlit run "src/quant_platform/web/app.py" \
    --server.headless false --browser.gatherUsageStats false
