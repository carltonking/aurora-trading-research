from aurora.backtesting.trades import Trade, trade_to_dict, trades_to_dataframe


def _trade() -> Trade:
    return Trade(
        trade_id="trade_1",
        symbol="AAPL",
        entry_timestamp="2024-01-01",
        exit_timestamp="2024-01-03",
        side="long",
        quantity=10.0,
        entry_price=100.0,
        exit_price=105.0,
        gross_pnl=50.0,
        net_pnl=48.0,
        return_pct=0.05,
        bars_held=2,
        exit_reason="signal_flat",
    )


def test_trade_to_dict_returns_expected_keys() -> None:
    result = trade_to_dict(_trade())

    assert result["trade_id"] == "trade_1"
    assert result["symbol"] == "AAPL"
    assert result["net_pnl"] == 48.0
    assert set(result) == set(Trade.__dataclass_fields__)


def test_trades_to_dataframe_works_for_empty_and_non_empty_lists() -> None:
    empty = trades_to_dataframe([])
    non_empty = trades_to_dataframe([_trade()])

    assert empty.empty
    assert list(empty.columns) == list(Trade.__dataclass_fields__)
    assert len(non_empty) == 1
    assert non_empty.loc[0, "trade_id"] == "trade_1"
