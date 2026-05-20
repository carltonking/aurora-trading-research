"""Tests for project configuration."""

import os
import pytest
import tempfile
from pathlib import Path

from aurora.config.project_config import (
    ProjectConfig,
    write_default_config,
    _flatten_dict,
)


def test_default_config() -> None:
    """Test default configuration values."""
    config = ProjectConfig()

    assert config.project.name == "aurora-project"
    assert config.data.symbols == ["SPY"]
    assert config.backtesting.initial_capital == 100000.0
    assert config.paper_trading.broker == "fake"


def test_full_config_from_dict() -> None:
    """Test creating config from full dictionary."""
    data = {
        "project": {"name": "test-project", "version": "2.0.0"},
        "data": {"source": "lseg", "symbols": ["AAPL", "MSFT"]},
        "backtesting": {"initial_capital": 50000.0},
    }

    config = ProjectConfig._from_dict(data)

    assert config.project.name == "test-project"
    assert config.project.version == "2.0.0"
    assert config.data.source == "lseg"
    assert config.data.symbols == ["AAPL", "MSFT"]
    assert config.backtesting.initial_capital == 50000.0


def test_load_minimal_yaml() -> None:
    """Test loading minimal YAML config."""
    yaml_content = """
project:
  name: minimal-project
data:
  symbols:
    - SPY
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        config = ProjectConfig.from_yaml(tmppath)
        assert config.project.name == "minimal-project"
        assert config.data.symbols == ["SPY"]
    finally:
        Path(tmppath).unlink()


def test_load_full_yaml() -> None:
    """Test loading full YAML config."""
    yaml_content = """
project:
  name: full-project
  version: "1.0.0"
  description: "A complete project"
data:
  source: yfinance
  symbols:
    - SPY
    - QQQ
    - DIA
  start_date: "2020-01-01"
  end_date: "2023-12-31"
  interval: 1d
strategy:
  archetype: momentum
  parameters:
    lookback: 20
    threshold: 0.01
backtesting:
  walk_forward_method: rolling
  purge_days: 30
  embargo_days: 5
  initial_capital: 200000.0
  slippage_bps: 15
  commission_bps: 5
paper_trading:
  broker: alpaca_paper
  latency_ms: 200
  fill_model: limit
  position_sizing_type: kelly
  position_sizing_params:
    multiplier: 0.5
risk:
  max_portfolio_drawdown: 0.2
  max_daily_loss: 5000.0
  max_leverage: 1.5
  kill_switch_max_drawdown: 0.3
  kill_switch_emergency_kill: false
optimization:
  method: genetic
  metric: sharpe
  max_iterations: 100
export:
  include_artifacts:
    - backtest
    - trades
  compress: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        config = ProjectConfig.from_yaml(tmppath)

        assert config.project.name == "full-project"
        assert config.data.source == "yfinance"
        assert config.data.symbols == ["SPY", "QQQ", "DIA"]
        assert config.data.start_date == "2020-01-01"
        assert config.backtesting.initial_capital == 200000.0
        assert config.paper_trading.broker == "alpaca_paper"
        assert config.risk.max_portfolio_drawdown == 0.2
        assert config.optimization.method == "genetic"
    finally:
        Path(tmppath).unlink()


def test_unknown_keys_ignored() -> None:
    """Test that unknown keys are ignored gracefully."""
    yaml_content = """
project:
  name: test-project
  unknown_field: should_be_ignored
data:
  source: yfinance
  unknown_nested:
    key: value
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        config = ProjectConfig.from_yaml(tmppath)
        assert config.project.name == "test-project"
    finally:
        Path(tmppath).unlink()


def test_write_and_reload_config() -> None:
    """Test writing config to file and reloading produces identical config."""
    config = ProjectConfig()
    config.project.name = "test-reload"
    config.data.symbols = ["AAPL", "GOOG"]
    config.backtesting.initial_capital = 150000.0
    config.risk.max_portfolio_drawdown = 0.15

    with tempfile.NamedTemporaryFile(suffix=".yml", delete=False) as f:
        tmppath = f.name

    try:
        config.to_yaml(tmppath)
        loaded = ProjectConfig.from_yaml(tmppath)

        assert loaded.project.name == "test-reload"
        assert loaded.data.symbols == ["AAPL", "GOOG"]
        assert loaded.backtesting.initial_capital == 150000.0
        assert loaded.risk.max_portfolio_drawdown == 0.15
    finally:
        Path(tmppath).unlink()


def test_merge_with_cli_args() -> None:
    """Test merging config with CLI arguments."""
    from argparse import Namespace

    config = ProjectConfig()
    config.data.symbols = ["SPY", "QQQ"]
    config.backtesting.initial_capital = 100000.0
    config.data.source = "yfinance"

    args = Namespace(
        symbols=["AAPL", "MSFT", "GOOG"],
        initial_capital=250000.0,
        source="lseg",
        other_arg="ignored",
    )

    merged = config.merge_with_cli_args(args)

    assert merged.data.symbols == ["AAPL", "MSFT", "GOOG"]
    assert merged.backtesting.initial_capital == 250000.0
    assert merged.data.source == "lseg"


def test_secrets_detection_aws_key() -> None:
    """Test detection of AWS access key."""
    yaml_content = """
project:
  name: test
paper_trading:
  env_vars:
    AWS_KEY: AKIAIOSFODNN7EXAMPLE
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        with pytest.raises(ValueError, match="Potential secret detected"):
            ProjectConfig.from_yaml(tmppath)
    finally:
        Path(tmppath).unlink()


def test_secrets_detection_sk_key() -> None:
    """Test detection of secret key."""
    yaml_content = """
project:
  name: test
paper_trading:
  env_vars:
    API_SECRET: sk-abcdefghijklmnopqrstuvwxyz
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        with pytest.raises(ValueError, match="Potential secret detected"):
            ProjectConfig.from_yaml(tmppath)
    finally:
        Path(tmppath).unlink()


def test_secrets_detection_github_token() -> None:
    """Test detection of GitHub token."""
    yaml_content = """
project:
  name: test
data:
  api_token: ghp_abcdefghijklmnopqrstuvwxyz1234567890
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        with pytest.raises(ValueError, match="Potential secret detected"):
            ProjectConfig.from_yaml(tmppath)
    finally:
        Path(tmppath).unlink()


def test_safe_env_var_placeholder() -> None:
    """Test that env var placeholders are allowed."""
    yaml_content = """
project:
  name: test
paper_trading:
  env_vars:
    API_KEY: ${ALPACA_API_KEY}
    SECRET: ${ALPACA_SECRET_KEY}
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yml", delete=False) as f:
        f.write(yaml_content)
        tmppath = f.name

    try:
        config = ProjectConfig.from_yaml(tmppath)
        assert config.paper_trading.env_vars["API_KEY"] == "${ALPACA_API_KEY}"
    finally:
        Path(tmppath).unlink()


def test_file_not_found() -> None:
    """Test that missing file raises FileNotFoundError."""
    with pytest.raises(FileNotFoundError):
        ProjectConfig.from_yaml("/nonexistent/path/config.yml")


def test_flatten_dict() -> None:
    """Test flattening nested dictionary."""
    nested = {
        "project": {"name": "test", "version": "1.0"},
        "data": {"source": "yfinance"},
    }

    flat = _flatten_dict(nested)

    assert "project.name" in flat
    assert flat["project.name"] == "test"
    assert "project.version" in flat
    assert "data.source" in flat


def test_write_default_config() -> None:
    """Test writing default config template."""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "default.yml"
        write_default_config(str(config_path))

        assert config_path.exists()

        config = ProjectConfig.from_yaml(str(config_path))
        assert config.project.name == "aurora-project"
        assert config.data.source == "yfinance"


def test_to_dict() -> None:
    """Test converting config to dictionary."""
    config = ProjectConfig()
    config.project.name = "dict-test"
    config.data.symbols = ["AAPL"]

    d = config.to_dict()

    assert d["project"]["name"] == "dict-test"
    assert d["data"]["symbols"] == ["AAPL"]
    assert "backtesting" in d
    assert "risk" in d