"""Project configuration management for AURORA.

This module provides YAML-based configuration for research runs.
All secrets must use environment variable placeholders.
No live trading, no real-money, no broker execution without RiskManager.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml


SECRET_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",
    r"sk-[a-zA-Z0-9]{20,}",
    r"xox[baprs]-[0-9a-zA-Z]{10,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"gho_[a-zA-Z0-9]{36}",
    r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}",
]


@dataclass
class ProjectSection:
    """Base section for project config."""


@dataclass
class DataSection(ProjectSection):
    """Data source configuration."""

    source: str = "yfinance"
    symbols: list[str] = field(default_factory=lambda: ["SPY"])
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    interval: str = "1d"


@dataclass
class StrategySection(ProjectSection):
    """Strategy configuration."""

    archetype: Optional[str] = None
    parameters: dict[str, Any] = field(default_factory=dict)
    signal_key: Optional[str] = None
    config_path: Optional[str] = None


@dataclass
class BacktestSection(ProjectSection):
    """Backtesting configuration."""

    walk_forward_method: Optional[str] = None
    purge_days: Optional[int] = None
    embargo_days: Optional[int] = None
    initial_capital: float = 100000.0
    slippage_bps: int = 10
    commission_bps: int = 0


@dataclass
class PaperTradingSection(ProjectSection):
    """Paper trading configuration."""

    broker: str = "fake"
    env_vars: dict[str, str] = field(default_factory=dict)
    latency_ms: int = 100
    fill_model: str = "market"
    position_sizing_type: str = "fixed_fraction"
    position_sizing_params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RiskSection(ProjectSection):
    """Risk configuration."""

    max_portfolio_drawdown: Optional[float] = None
    max_daily_loss: Optional[float] = None
    max_position_size: Optional[float] = None
    max_leverage: float = 1.0
    kill_switch_max_drawdown: Optional[float] = None
    kill_switch_max_daily_loss: Optional[float] = None
    kill_switch_min_sharpe: Optional[float] = None
    kill_switch_max_consecutive_losses: Optional[int] = None
    kill_switch_emergency_kill: bool = False


@dataclass
class OptimizationSection(ProjectSection):
    """Optimization configuration."""

    method: str = "bayesian"
    param_space_path: Optional[str] = None
    metric: str = "sharpe"
    max_iterations: int = 50


@dataclass
class ExportSection(ProjectSection):
    """Export bundle configuration."""

    include_artifacts: list[str] = field(default_factory=lambda: ["all"])
    compress: bool = True


@dataclass
class ProjectInfo(ProjectSection):
    """Project metadata."""

    name: str = "aurora-project"
    version: str = "1.0.0"
    description: str = ""


@dataclass
class ProjectConfig:
    """Complete project configuration."""

    project: ProjectInfo = field(default_factory=ProjectInfo)
    data: DataSection = field(default_factory=DataSection)
    strategy: StrategySection = field(default_factory=StrategySection)
    backtesting: BacktestSection = field(default_factory=BacktestSection)
    paper_trading: PaperTradingSection = field(default_factory=PaperTradingSection)
    risk: RiskSection = field(default_factory=RiskSection)
    optimization: OptimizationSection = field(default_factory=OptimizationSection)
    export: ExportSection = field(default_factory=ExportSection)

    @classmethod
    def from_yaml(cls, path: str) -> "ProjectConfig":
        """Load configuration from YAML file.

        Args:
            path: Path to YAML config file.

        Returns:
            ProjectConfig instance.

        Raises:
            FileNotFoundError: If config file doesn't exist.
            ValueError: If secrets detected in config.
        """
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        with config_path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        cls._check_for_secrets(data, path)

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict[str, Any]) -> "ProjectConfig":
        """Create config from dictionary."""
        config = cls()

        if "project" in data:
            config.project = cls._filter_kwargs(ProjectInfo, data["project"])

        if "data" in data:
            config.data = cls._filter_kwargs(DataSection, data["data"])

        if "strategy" in data:
            config.strategy = cls._filter_kwargs(StrategySection, data["strategy"])

        if "backtesting" in data:
            config.backtesting = cls._filter_kwargs(BacktestSection, data["backtesting"])

        if "paper_trading" in data:
            config.paper_trading = cls._filter_kwargs(PaperTradingSection, data["paper_trading"])

        if "risk" in data:
            config.risk = cls._filter_kwargs(RiskSection, data["risk"])

        if "optimization" in data:
            config.optimization = cls._filter_kwargs(OptimizationSection, data["optimization"])

        if "export" in data:
            config.export = cls._filter_kwargs(ExportSection, data["export"])

        return config

    @staticmethod
    def _filter_kwargs(cls, data: dict[str, Any]) -> Any:
        """Filter dict to only include known fields for a dataclass."""
        import dataclasses

        field_names = {f.name for f in dataclasses.fields(cls)}
        filtered = {k: v for k, v in data.items() if k in field_names}
        return cls(**filtered)

    @staticmethod
    def _check_for_secrets(data: dict[str, Any], path: str) -> None:
        """Check for suspicious secret-like values in config.

        Args:
            data: Configuration dictionary.
            path: Path to config file (for error message).

        Raises:
            ValueError: If secrets detected.
        """
        for key, value in _flatten_dict(data).items():
            if value is None:
                continue
            value_str = str(value)
            for pattern in SECRET_PATTERNS:
                if re.search(pattern, value_str):
                    raise ValueError(
                        f"Potential secret detected in {path} at key '{key}'. "
                        f"Use environment variable placeholders like ${{API_KEY}} instead."
                    )

    def to_yaml(self, path: str) -> None:
        """Write configuration to YAML file.

        Args:
            path: Path to save YAML config.
        """
        output_path = Path(path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with output_path.open("w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, default_flow_style=False, sort_keys=False)

    def to_dict(self) -> dict[str, Any]:
        """Convert config to dictionary."""
        return {
            "project": {
                "name": self.project.name,
                "version": self.project.version,
                "description": self.project.description,
            },
            "data": {
                "source": self.data.source,
                "symbols": self.data.symbols,
                "start_date": self.data.start_date,
                "end_date": self.data.end_date,
                "interval": self.data.interval,
            },
            "strategy": {
                "archetype": self.strategy.archetype,
                "parameters": self.strategy.parameters,
                "signal_key": self.strategy.signal_key,
                "config_path": self.strategy.config_path,
            },
            "backtesting": {
                "walk_forward_method": self.backtesting.walk_forward_method,
                "purge_days": self.backtesting.purge_days,
                "embargo_days": self.backtesting.embargo_days,
                "initial_capital": self.backtesting.initial_capital,
                "slippage_bps": self.backtesting.slippage_bps,
                "commission_bps": self.backtesting.commission_bps,
            },
            "paper_trading": {
                "broker": self.paper_trading.broker,
                "env_vars": self.paper_trading.env_vars,
                "latency_ms": self.paper_trading.latency_ms,
                "fill_model": self.paper_trading.fill_model,
                "position_sizing_type": self.paper_trading.position_sizing_type,
                "position_sizing_params": self.paper_trading.position_sizing_params,
            },
            "risk": {
                "max_portfolio_drawdown": self.risk.max_portfolio_drawdown,
                "max_daily_loss": self.risk.max_daily_loss,
                "max_position_size": self.risk.max_position_size,
                "max_leverage": self.risk.max_leverage,
                "kill_switch_max_drawdown": self.risk.kill_switch_max_drawdown,
                "kill_switch_max_daily_loss": self.risk.kill_switch_max_daily_loss,
                "kill_switch_min_sharpe": self.risk.kill_switch_min_sharpe,
                "kill_switch_max_consecutive_losses": self.risk.kill_switch_max_consecutive_losses,
                "kill_switch_emergency_kill": self.risk.kill_switch_emergency_kill,
            },
            "optimization": {
                "method": self.optimization.method,
                "param_space_path": self.optimization.param_space_path,
                "metric": self.optimization.metric,
                "max_iterations": self.optimization.max_iterations,
            },
            "export": {
                "include_artifacts": self.export.include_artifacts,
                "compress": self.export.compress,
            },
        }

    def merge_with_cli_args(self, args: Any) -> "ProjectConfig":
        """Merge config with CLI arguments.

        CLI arguments take precedence over config file values.

        Args:
            args: argparse.Namespace with CLI arguments.

        Returns:
            New ProjectConfig with CLI overrides applied.
        """
        config = ProjectConfig()

        if hasattr(args, "symbols") and args.symbols:
            config.data.symbols = args.symbols
        if hasattr(args, "initial_capital") and args.initial_capital:
            config.backtesting.initial_capital = args.initial_capital
        if hasattr(args, "source") and args.source:
            config.data.source = args.source

        return config


def _flatten_dict(d: dict, parent_key: str = "") -> dict[str, Any]:
    """Flatten nested dict for secret scanning."""
    items = []
    for k, v in d.items():
        new_key = f"{parent_key}.{k}" if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_dict(v, new_key).items())
        else:
            items.append((new_key, v))
    return dict(items)


DEFAULT_CONFIG_TEMPLATE = """# AURORA Project Configuration
# This file defines the complete research run parameters.
# All secrets should use environment variable placeholders: ${VAR_NAME}

project:
  name: aurora-project
  version: "1.0.0"
  description: "AURORA research project"

# Data source configuration
data:
  source: yfinance  # yfinance, lseg
  symbols:
    - SPY
    - QQQ
  start_date: null  # null means use default (earliest available)
  end_date: null
  interval: 1d

# Strategy configuration
strategy:
  archetype: null  # e.g., momentum, mean_reversion, breakout
  parameters: {}
  signal_key: null
  config_path: null

# Backtesting configuration
backtesting:
  walk_forward_method: null  # null, expanding, rolling
  purge_days: null
  embargo_days: null
  initial_capital: 100000.0
  slippage_bps: 10
  commission_bps: 0

# Paper trading configuration
paper_trading:
  broker: fake  # fake, alpaca_paper
  env_vars: {}  # API keys via env vars: ${ALPACA_API_KEY}
  latency_ms: 100
  fill_model: market
  position_sizing_type: fixed_fraction
  position_sizing_params:
    fraction: 0.1

# Risk configuration
risk:
  max_portfolio_drawdown: null  # 0.2 = 20%
  max_daily_loss: null  # dollar amount
  max_position_size: null  # fraction of portfolio
  max_leverage: 1.0
  kill_switch_max_drawdown: null
  kill_switch_max_daily_loss: null
  kill_switch_min_sharpe: null
  kill_switch_max_consecutive_losses: null
  kill_switch_emergency_kill: false

# Optimization configuration
optimization:
  method: bayesian  # bayesian, genetic
  param_space_path: null
  metric: sharpe
  max_iterations: 50

# Export configuration
export:
  include_artifacts:
    - all
  compress: true

# Disclaimer: This is a research-only configuration.
# No live trading, no real-money execution.
"""


def write_default_config(path: str) -> None:
    """Write a default config template to file.

    Args:
        path: Path to save the config template.
    """
    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)

    with config_path.open("w", encoding="utf-8") as f:
        f.write(DEFAULT_CONFIG_TEMPLATE)