"""FellowQuant 适配层：桥接 vendored quant_platform 与 FastAPI 路由。"""

from __future__ import annotations

import sys
from pathlib import Path

# 确保无论从哪个 CWD 启动，vendored quant_platform 都可导入。
_BACKEND_ROOT = str(Path(__file__).resolve().parents[2])
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)
