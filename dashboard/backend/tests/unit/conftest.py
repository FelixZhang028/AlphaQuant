import pytest

from app.quant import compute


@pytest.fixture(autouse=True)
def fresh_compute_cache():
    """Computation results are remembered per process; each test starts without any."""

    compute.clear_cache()
    yield
    compute.clear_cache()
