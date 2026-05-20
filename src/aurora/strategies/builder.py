"""Strategy builder - generates strategy classes from config files.

This module is research-only. It parses configuration files and produces
strategy instances from archetype templates. No live trading, no broker calls.
"""

import json
from pathlib import Path
from typing import Any

import yaml

from aurora.strategies import archetypes


class StrategyBuilderError(Exception):
    """Error raised by StrategyBuilder."""
    pass


class StrategyBuilder:
    """Builds strategy instances from configuration files.

    This is a research-only builder. It parses config files and instantiates
    strategies from archetype templates. No live trading, no broker calls.
    """

    VALID_ARCHETYPES = {
        "trend_following",
        "mean_reversion",
        "breakout",
        "grid_trading",
        "pairs_trading",
        "dca",
    }

    def __init__(self, config_path: str | Path | None = None):
        """Initialize builder with optional config path.

        Args:
            config_path: Path to JSON or YAML config file.
        """
        self.config_path = Path(config_path) if config_path else None
        self.config: dict[str, Any] = {}

    def load_config(self, config_path: str | Path | None = None) -> dict[str, Any]:
        """Load configuration from file.

        Args:
            config_path: Path to config file. Uses self.config_path if not provided.

        Returns:
            Loaded configuration dictionary.

        Raises:
            StrategyBuilderError: If file not found or invalid format.
        """
        path = Path(config_path or self.config_path)
        if not path.exists():
            raise StrategyBuilderError(f"Config file not found: {path}")

        try:
            with path.open() as f:
                if path.suffix in (".yaml", ".yml"):
                    self.config = yaml.safe_load(f)
                else:
                    self.config = json.load(f)
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            raise StrategyBuilderError(f"Invalid config file format: {e}")

        return self.config

    def validate_config(self) -> None:
        """Validate loaded configuration.

        Raises:
            StrategyBuilderError: If required fields are missing or invalid.
        """
        if not self.config:
            raise StrategyBuilderError("No configuration loaded")

        required_fields = ["strategy_name", "archetype", "parameters"]
        for field in required_fields:
            if field not in self.config:
                raise StrategyBuilderError(f"Missing required field: {field}")

        archetype = self.config.get("archetype")
        if archetype not in self.VALID_ARCHETYPES:
            available = ", ".join(sorted(self.VALID_ARCHETYPES))
            raise StrategyBuilderError(
                f"Invalid archetype: {archetype}. Available: {available}"
            )

    def build(self) -> Any:
        """Build strategy instance from configuration.

        Returns:
            Instantiated strategy object from the appropriate archetype.

        Raises:
            StrategyBuilderError: If configuration is invalid.
        """
        self.validate_config()

        archetype_name = self.config["archetype"]
        parameters = self.config["parameters"]
        strategy_name = self.config["strategy_name"]

        archetype_class = archetypes.get_archetype(archetype_name)

        try:
            strategy = archetype_class(**parameters)
            strategy.strategy_name = strategy_name
            return strategy
        except TypeError as e:
            raise StrategyBuilderError(f"Invalid parameters for {archetype_name}: {e}")
        except ValueError as e:
            raise StrategyBuilderError(f"Parameter validation failed: {e}")

    def generate_code(self) -> str:
        """Generate Python source code for the strategy.

        Returns:
            String containing complete Python class definition.

        Raises:
            StrategyBuilderError: If configuration is invalid.
        """
        self.validate_config()

        archetype_name = self.config["archetype"]
        parameters = self.config["parameters"]
        strategy_name = self.config["strategy_name"]

        if archetype_name == "trend_following":
            return self._generate_trend_following_code(strategy_name, parameters)
        elif archetype_name == "mean_reversion":
            return self._generate_mean_reversion_code(strategy_name, parameters)
        elif archetype_name == "breakout":
            return self._generate_breakout_code(strategy_name, parameters)

        return ""

    def _generate_trend_following_code(self, name: str, params: dict) -> str:
        """Generate code for trend following strategy."""
        lines = [
            '"""Auto-generated trend following strategy."""',
            "",
            "import pandas as pd",
            "",
            "from aurora.strategies.archetypes.trend_following import TrendFollowingStrategy",
            "",
            "",
            f"class {self._class_name(name)}(TrendFollowingStrategy):",
            '    """Auto-generated trend following strategy."""',
            "",
            "    def __init__(self):",
            f"        super().__init__(",
            f"            fast_window={params.get('fast_window', 10)},",
            f"            slow_window={params.get('slow_window', 30)},",
            f'            price_column="{params.get("price_column", "close")}",',
            "        )",
        ]
        return "\n".join(lines)

    def _generate_mean_reversion_code(self, name: str, params: dict) -> str:
        """Generate code for mean reversion strategy."""
        method = params.get("method", "bollinger")
        lines = [
            '"""Auto-generated mean reversion strategy."""',
            "",
            "import pandas as pd",
            "",
            "from aurora.strategies.archetypes.mean_reversion import MeanReversionStrategy",
            "",
            "",
            f"class {self._class_name(name)}(MeanReversionStrategy):",
            '    """Auto-generated mean reversion strategy."""',
            "",
            "    def __init__(self):",
            f"        super().__init__(",
            f"            window={params.get('window', 20)},",
            f"            num_std={params.get('num_std', 2.0)},",
            f'            price_column="{params.get("price_column", "close")}",',
            f'            method="{method}",',
        ]
        if method == "rsi":
            lines.append(f"            rsi_period={params.get('rsi_period', 14)},")
            lines.append(f"            rsi_oversold={params.get('rsi_oversold', 30)},")
            lines.append(f"            rsi_overbought={params.get('rsi_overbought', 70)},")
        lines.append("        )")
        return "\n".join(lines)

    def _generate_breakout_code(self, name: str, params: dict) -> str:
        """Generate code for breakout strategy."""
        lines = [
            '"""Auto-generated breakout strategy."""',
            "",
            "import pandas as pd",
            "",
            "from aurora.strategies.archetypes.breakout import BreakoutStrategy",
            "",
            "",
            f"class {self._class_name(name)}(BreakoutStrategy):",
            '    """Auto-generated breakout strategy."""',
            "",
            "    def __init__(self):",
            f"        super().__init__(",
            f"            lookback_period={params.get('lookback_period', 20)},",
            f'            price_column="{params.get("price_column", "close")}",',
            f'            high_column="{params.get("high_column", "high")}",',
            "        )",
        ]
        return "\n".join(lines)

    def _class_name(self, strategy_name: str) -> str:
        """Convert strategy name to valid Python class name."""
        parts = strategy_name.replace("-", "_").replace(" ", "_").split("_")
        return "".join(part.capitalize() for part in parts if part)