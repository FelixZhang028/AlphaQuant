from datetime import date

from quant_platform.execution.models import Order, OrderSide, OrderStatus


def test_order_tracks_partial_and_full_fill_quantities() -> None:
    order = Order.create(
        "strategy", "000001.SZ", OrderSide.BUY, 1_000, date(2024, 1, 2), date(2024, 1, 3)
    )

    partial = order.with_fill(300)
    completed = partial.with_fill(700)

    assert partial.status == OrderStatus.PARTIALLY_FILLED
    assert partial.filled_quantity == 300
    assert partial.remaining_quantity == 700
    assert completed.status == OrderStatus.FILLED
    assert completed.remaining_quantity == 0
