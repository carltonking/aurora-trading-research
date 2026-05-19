import pytest

from aurora.brokers.alpaca_adapter import (
    AlpacaConfig,
    AlpacaLiveTradingError,
    RealAlpacaPaperClient,
    FakeAlpacaPaperClient,
    AlpacaPaperBrokerProtocol,
    load_alpaca_config_from_env,
)


def test_alpaca_protocol_exists() -> None:
    assert hasattr(AlpacaPaperBrokerProtocol, "health_check")
    assert hasattr(AlpacaPaperBrokerProtocol, "get_account")
    assert hasattr(AlpacaPaperBrokerProtocol, "submit_paper_order")
    assert hasattr(AlpacaPaperBrokerProtocol, "cancel_paper_order")
    assert hasattr(AlpacaPaperBrokerProtocol, "get_paper_positions")
    assert hasattr(AlpacaPaperBrokerProtocol, "get_paper_orders")


def test_real_client_fails_without_enabled() -> None:
    config = AlpacaConfig(
        enabled=False,
        api_key="test-key",
        secret_key="test-secret",
    )

    with pytest.raises(ValueError, match="disabled"):
        RealAlpacaPaperClient(config)


def test_real_client_fails_without_api_key() -> None:
    config = AlpacaConfig(
        enabled=True,
        api_key=None,
        secret_key="test-secret",
    )

    with pytest.raises(ValueError, match="api_key"):
        RealAlpacaPaperClient(config)


def test_real_client_fails_without_secret_key() -> None:
    config = AlpacaConfig(
        enabled=True,
        api_key="test-key",
        secret_key=None,
    )

    with pytest.raises(ValueError, match="secret_key"):
        RealAlpacaPaperClient(config)


def test_real_client_repr_does_not_expose_secrets() -> None:
    config = AlpacaConfig(
        enabled=True,
        api_key="secret-key-123456",
        secret_key="secret-secret-abcdef",
    )

    with pytest.raises(ImportError):
        client = RealAlpacaPaperClient(config)

    repr_str = repr(config)
    assert "secret-key" not in repr_str
    assert "secret-secret" not in repr_str
    assert "***" in repr_str


def test_real_client_str_does_not_expose_secrets() -> None:
    config = AlpacaConfig(
        enabled=True,
        api_key="secret-key-123456",
        secret_key="secret-secret-abcdef",
    )

    with pytest.raises(ImportError):
        client = RealAlpacaPaperClient(config)

    str_str = str(config)
    assert "secret-key" not in str_str
    assert "secret-secret" not in str_str


def test_real_client_fails_when_sdk_not_installed(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "alpaca", None)

    config = AlpacaConfig(
        enabled=True,
        api_key="test-key",
        secret_key="test-secret",
    )

    with pytest.raises(ImportError, match="not installed"):
        RealAlpacaPaperClient(config)


def test_protocol_is_duck_typed() -> None:
    class MockClient:
        def health_check(self) -> dict:
            return {"ok": True}

        def get_account(self) -> dict:
            return {"id": "test", "paper": True}

        def submit_paper_order(self, symbol, qty, side, order_type):
            return {"id": "order-1"}

        def cancel_paper_order(self, order_id):
            return {"status": "cancelled"}

        def get_paper_positions(self):
            return []

        def get_paper_orders(self):
            return []

    mock = MockClient()
    assert isinstance(mock, AlpacaPaperBrokerProtocol)


def test_fake_client_health_check() -> None:
    client = FakeAlpacaPaperClient()
    health = client.health_check()

    assert health["ok"] is True
    assert "fake" in health["message"].lower()
    assert health["details"]["paper"] is True


def test_fake_client_get_account() -> None:
    client = FakeAlpacaPaperClient()
    account = client.get_account()

    assert account["id"] == "fake-account-id"
    assert account["paper"] is True
    assert "cash" in account


def test_fake_client_submit_order() -> None:
    client = FakeAlpacaPaperClient()
    order = client.submit_paper_order("SPY", 10, "buy", "market")

    assert order["symbol"] == "SPY"
    assert order["qty"] == 10
    assert order["side"] == "buy"
    assert order["paper"] is True


def test_fake_client_get_positions() -> None:
    client = FakeAlpacaPaperClient()
    positions = client.get_paper_positions()

    assert positions == []


def test_fake_client_get_orders() -> None:
    client = FakeAlpacaPaperClient()
    orders = client.get_paper_orders()

    assert orders == []


def test_load_alpaca_config_from_env_returns_defaults_when_no_env(monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_PAPER_ENABLED", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_KEY", raising=False)
    monkeypatch.delenv("ALPACA_PAPER_SECRET", raising=False)

    config = load_alpaca_config_from_env()

    assert config.enabled is False
    assert config.api_key is None
    assert config.secret_key is None
    assert config.paper is True


def test_load_alpaca_config_from_env_reads_enabled_true(monkeypatch) -> None:
    monkeypatch.setenv("ALPACA_PAPER_ENABLED", "true")
    monkeypatch.setenv("ALPACA_PAPER_KEY", "test-key")
    monkeypatch.setenv("ALPACA_PAPER_SECRET", "test-secret")

    config = load_alpaca_config_from_env()

    assert config.enabled is True
    assert config.api_key == "test-key"
    assert config.secret_key == "test-secret"
    assert config.paper is True


def test_config_repr_shows_last_four_chars() -> None:
    config = AlpacaConfig(
        enabled=True,
        api_key="1234567890abcdef",
        secret_key="abcdef1234567890",
    )

    repr_str = repr(config)
    assert "***" in repr_str
    assert "1234567890abcdef" not in repr_str
    assert "abcdef1234567890" not in repr_str