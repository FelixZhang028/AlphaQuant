import pytest

from app.quant import compute


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
