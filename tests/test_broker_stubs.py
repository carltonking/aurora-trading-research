import ast
from dataclasses import asdict
import json
from pathlib import Path

import pytest

from aurora.brokers import (
    AlpacaPaperBrokerAdapter,
    BrokerAdapterConfig,
    BrokerAdapterError,
    BrokerOrderRequest,
    BrokerOrderResult,
    assert_no_live_trading,
)


def test_default_broker_adapter_config_is_disabled_and_safe() -> None:
    config = BrokerAdapterConfig()

    assert config.enabled is False
    assert config.paper_only is True
    assert config.allow_live_trading is False
    assert config.dry_run is True
    assert config.require_risk_approval is True


def test_live_trading_config_is_rejected() -> None:
    with pytest.raises(BrokerAdapterError, match="allow_live_trading"):
        assert_no_live_trading(BrokerAdapterConfig(allow_live_trading=True))


def test_non_paper_config_is_rejected() -> None:
    with pytest.raises(BrokerAdapterError, match="paper_only"):
        assert_no_live_trading(BrokerAdapterConfig(paper_only=False))


def test_alpaca_paper_stub_does_not_import_broker_or_network_libraries() -> None:
    imports = _top_level_imports(Path("src/aurora/brokers/alpaca_paper.py"))

    assert "alpaca" not in imports
    assert "requests" not in imports
    assert "httpx" not in imports
    assert "urllib" not in imports


def test_alpaca_paper_stub_submit_order_never_places_order() -> None:
    adapter = AlpacaPaperBrokerAdapter()

    result = adapter.submit_order(_request(), risk_approved=True)

    assert result.accepted is False
    assert result.broker_order_id is None
    assert result.status == "DRY_RUN_REJECTED"
    assert "non-network stub" in result.message
    assert "submitted" in result.message


def test_risk_approval_is_required_by_default() -> None:
    adapter = AlpacaPaperBrokerAdapter()

    result = adapter.submit_order(_request(), risk_approved=False)

    assert result.accepted is False
    assert result.status == "REJECTED"
    assert "RiskManager approval is required" in result.message


def test_enabled_non_dry_run_stub_config_is_rejected() -> None:
    adapter = AlpacaPaperBrokerAdapter(BrokerAdapterConfig(enabled=True, dry_run=False))

    with pytest.raises(BrokerAdapterError, match="dry_run"):
        adapter.validate_config()


def test_stub_account_and_positions_are_empty_dry_run_structures() -> None:
    adapter = AlpacaPaperBrokerAdapter()

    assert adapter.get_account() == {
        "adapter": "alpaca_paper_stub",
        "dry_run": True,
        "account": None,
    }
    assert adapter.get_positions() == []


def test_broker_dataclasses_are_json_serializable() -> None:
    request = _request()
    result = BrokerOrderResult(
        accepted=False,
        broker_order_id=None,
        status="DRY_RUN_REJECTED",
        message="stub",
        raw_response={"dry_run": True},
    )

    json.dumps(asdict(request))
    json.dumps(asdict(result))


def test_broker_stubs_do_not_write_ledger_files(tmp_path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    adapter = AlpacaPaperBrokerAdapter()

    adapter.submit_order(_request(), risk_approved=True)

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _request() -> BrokerOrderRequest:
    return BrokerOrderRequest(symbol="SPY", side="buy", quantity=1.0)


def _top_level_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    return imports
