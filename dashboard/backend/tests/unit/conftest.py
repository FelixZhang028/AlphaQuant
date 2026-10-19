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
def isolate_local_account_settings(monkeypatch):
    # The local .env may create an administrator or choose how people sign up; tests set these themselves.
    for name in ("FELLOWQUANT_ADMIN_EMAIL", "FELLOWQUANT_ADMIN_PASSWORD", "FELLOWQUANT_INVITE_CODES", "FELLOWQUANT_REGISTRATION"):
        monkeypatch.delenv(name, raising=False)


@pytest.fixture(autouse=True)
def isolated_factor_profiles(tmp_path, monkeypatch):
    # AI 研究员的因子画像：算在临时目录里，不开后台线程，也不沿用别的测试算过的结果。
    from quant_platform.ai_research import report

    monkeypatch.setattr(report, "COMPUTE_IN_BACKGROUND", False)
    monkeypatch.setattr(report, "_STORE", tmp_path / "factor_profiles")
    report._FACTOR_CACHE.clear()
    report._PENDING.clear()
    yield
    report._FACTOR_CACHE.clear()


@pytest.fixture(autouse=True)
def fresh_rate_limits(monkeypatch):
    monkeypatch.setenv("FELLOWQUANT_RATE_LIMITS", "off")
    rate_limit.reset()
    yield
    rate_limit.reset()
