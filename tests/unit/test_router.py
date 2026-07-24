import pandas as pd

from quant_platform.data.router import DataRouter


class EmptyProvider:
    def fetch(self) -> pd.DataFrame:
        return pd.DataFrame()


def test_router_can_accept_valid_empty_event_dataset() -> None:
    router = DataRouter({"primary": EmptyProvider()}, {"suspensions": ["primary"]})  # type: ignore[arg-type]

    frame, provider = router.fetch("suspensions", "fetch", allow_empty=True)

    assert frame.empty
    assert provider == "primary"
