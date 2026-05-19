from aurora.execution.models import (
    ORDER_FILLED,
    SimulatedAccount,
    SimulatedOrder,
    SimulatedPosition,
    account_to_dict,
    order_to_dict,
    position_to_dict,
)


def test_order_position_account_helpers_return_expected_keys() -> None:
    order = SimulatedOrder(
        order_id="sim_000001",
        symbol="AAPL",
        side="buy",
        quantity=10.0,
        requested_quantity=10.0,
        price=100.0,
        fill_price=100.0,
        status=ORDER_FILLED,
        timestamp="2024-01-01T00:00:00+00:00",
        strategy_id="strategy",
        risk_status="APPROVED",
        risk_reasons=["approved"],
    )
    position = SimulatedPosition(symbol="AAPL", quantity=10.0, average_price=100.0)
    account = SimulatedAccount(equity=100000.0, cash=99000.0, market_value=1000.0)

    assert set(order_to_dict(order)) == set(SimulatedOrder.__dataclass_fields__)
    assert set(position_to_dict(position)) == set(SimulatedPosition.__dataclass_fields__)
    assert set(account_to_dict(account)) == set(SimulatedAccount.__dataclass_fields__)
