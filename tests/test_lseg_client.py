import pytest

from aurora.data.exceptions import DataSourceError
from aurora.data.lseg_client import (
    LSEGClient,
    LSEGClientProtocol,
    LSEGConnectionError,
)
from aurora.data.lseg_source import LSEGDataSourceConfig


def test_lseg_client_protocol_exists() -> None:
    assert hasattr(LSEGClientProtocol, "health_check")
    assert hasattr(LSEGClientProtocol, "get_ohlcv")


def test_real_client_fails_without_app_key() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key=None,
        username="test-user",
        password="test-pass",
    )

    with pytest.raises(ValueError, match="app_key"):
        LSEGClient(config)


def test_real_client_fails_without_username() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="test-key",
        username=None,
        password="test-pass",
    )

    with pytest.raises(ValueError, match="username"):
        LSEGClient(config)


def test_real_client_fails_without_password() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="test-key",
        username="test-user",
        password=None,
    )

    with pytest.raises(ValueError, match="password"):
        LSEGClient(config)


def test_real_client_repr_does_not_expose_secrets() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="secret-key",
        username="secret-user",
        password="secret-pass",
    )

    with pytest.raises(ImportError):
        client = LSEGClient(config)

    repr_str = repr(config)
    assert "secret-key" not in repr_str
    assert "secret-user" not in repr_str
    assert "secret-pass" not in repr_str
    assert "***" in repr_str


def test_real_client_str_does_not_expose_secrets() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="secret-key",
        username="secret-user",
        password="secret-pass",
    )

    with pytest.raises(ImportError):
        client = LSEGClient(config)

    str_str = str(config)
    assert "secret-key" not in str_str
    assert "secret-user" not in str_str
    assert "secret-pass" not in str_str


def test_real_client_fails_when_sdk_not_installed(monkeypatch) -> None:
    monkeypatch.setitem(__import__("sys").modules, "lseg", None)

    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="test-key",
        username="test-user",
        password="test-pass",
    )

    with pytest.raises(ImportError, match="not installed"):
        LSEGClient(config)


def test_client_health_check_returns_expected_structure() -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="test-key",
        username="test-user",
        password="test-pass",
    )

    try:
        client = LSEGClient(config)
    except ImportError:
        pytest.skip("LSEG SDK not installed")

    health = client.health_check()

    assert isinstance(health, dict)
    assert "ok" in health
    assert "message" in health
    assert isinstance(health["ok"], bool)
    assert isinstance(health["message"], str)


def test_client_get_ohlcv_raises_connection_error_on_failure(monkeypatch) -> None:
    config = LSEGDataSourceConfig(
        enabled=True,
        app_key="test-key",
        username="test-user",
        password="test-pass",
    )

    try:
        client = LSEGClient(config)
    except ImportError:
        pytest.skip("LSEG SDK not installed")

    with pytest.raises(LSEGConnectionError):
        client.get_ohlcv(
            symbols=["SPY.N"],
            start="2024-01-01",
            end="2024-01-02",
            interval="1d",
            adjusted=True,
        )


def test_protocol_is_duck_typed() -> None:
    class MockClient:
        def health_check(self) -> dict:
            return {"ok": True, "message": "ok"}

        def get_ohlcv(
            self, *, symbols: list, start: str, end: str | None, interval: str, adjusted: bool
        ):
            return []

    mock = MockClient()
    assert isinstance(mock, LSEGClientProtocol)