import os

# 在导入后端之前设置：测试里的密码只做少量加密轮次（真实部署是 60 万次），
# 频率限制默认关闭（很多测试会连续注册、登录），专门的测试会自己打开。
os.environ.setdefault("FELLOWQUANT_PASSWORD_ITERATIONS", "1000")
os.environ["FELLOWQUANT_RATE_LIMITS"] = "off"

import pytest  # noqa: E402

from app.quant import compute  # noqa: E402
from app.quant import rate_limit  # noqa: E402


@pytest.fixture(autouse=True)
def fresh_compute_cache():
    """Computation results are remembered per process; each test starts without any."""

    compute.clear_cache()
    yield
    compute.clear_cache()


@pytest.fixture(autouse=True)
def isolate_native_jev_credentials(monkeypatch):
    # Local .env credentials must never turn unit tests into paid external calls.
    for name in ("TYPESAFE_API_KEY", "JEV_API_KEY", "FELLOWQUANT_JEV_URL", "FELLOWQUANT_JEV_MODEL"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def fresh_rate_limits(monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_RATE_LIMITS", "off")
    rate_limit.reset()
    yield
    rate_limit.reset()
