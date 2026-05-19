import json

from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.strategies.config import validate_strategy_config
from aurora.strategies.prompt_lab import (
    DEFAULT_SYMBOLS,
    explain_prompt_lab_result,
    generate_strategy_config_from_prompt,
    prompt_lab_result_to_dict,
)


def test_momentum_prompt_generates_momentum_config() -> None:
    result = generate_strategy_config_from_prompt("Build a momentum strategy for AAPL.")

    assert result.config.strategy_type == "momentum"
    assert result.config.entry_rules[0]["return_col"] == "return_20d"
    assert result.config.universe["symbols"] == ["AAPL"]
    validate_strategy_config(result.config)


def test_moving_average_prompt_generates_crossover_config() -> None:
    result = generate_strategy_config_from_prompt(
        "Create a moving average crossover using 50 and 200 day averages for SPY."
    )

    assert result.config.strategy_type == "moving_average_crossover"
    assert result.config.entry_rules[0] == {"fast_ma": "ma_50", "slow_ma": "ma_200"}
    validate_strategy_config(result.config)


def test_ml_model_prompt_generates_ml_signal_config() -> None:
    result = generate_strategy_config_from_prompt("Use an ML model prediction strategy for MSFT.")

    assert result.config.strategy_type == "ml_signal"
    assert result.config.entry_rules[0]["prediction_col"] == "prediction"
    assert result.config.entry_rules[0]["min_probability"] == 0.55
    validate_strategy_config(result.config)


def test_default_prompt_uses_safe_defaults() -> None:
    result = generate_strategy_config_from_prompt("Build a simple strategy.")

    assert result.config.strategy_type == "momentum"
    assert result.config.asset_class == "etf"
    assert result.config.universe["symbols"] == DEFAULT_SYMBOLS
    assert result.config.direction == "long_only"
    assert result.config.risk["max_position_pct"] == 0.05
    validate_strategy_config(result.config)


def test_conservative_prompt_lowers_risk_or_increases_threshold() -> None:
    momentum = generate_strategy_config_from_prompt("Conservative low risk momentum for AAPL.")
    ml_signal = generate_strategy_config_from_prompt("Conservative machine learning model for AAPL.")

    assert momentum.config.risk["max_position_pct"] == 0.03
    assert momentum.config.entry_rules[0]["min_return"] == 0.05
    assert ml_signal.config.entry_rules[0]["min_probability"] == 0.60


def test_aggressive_prompt_does_not_exceed_safety_cap_and_warns() -> None:
    result = generate_strategy_config_from_prompt("Aggressive momentum strategy for AAPL.")

    assert result.config.risk["max_position_pct"] == 0.05
    assert any("Aggressive" in warning for warning in result.warnings)


def test_unsupported_high_risk_requests_are_reported_and_not_enabled() -> None:
    result = generate_strategy_config_from_prompt(
        "Use shorting, margin, leverage, options, crypto, scalping, HFT, live trading, "
        "and real money trading for AAPL."
    )
    expected_requests = {
        "shorting",
        "margin",
        "leverage",
        "options",
        "crypto",
        "scalping",
        "high frequency trading",
        "live trading",
        "real money trading",
    }

    assert expected_requests.issubset(set(result.unsupported_requests))
    warnings_text = " ".join(result.warnings).lower()
    for request in expected_requests:
        assert request in warnings_text
    assert result.config.direction == "long_only"
    assert result.config.asset_class == "equity"
    assert result.config.risk["allow_shorting"] is False
    assert result.config.risk["allow_margin"] is False
    validate_strategy_config(result.config)


def test_ticker_extraction_works_and_ignores_common_uppercase_terms() -> None:
    result = generate_strategy_config_from_prompt(
        "Use AI ML RSI SMA EMA ETF ETFS HFT API CEO USD filters for SPY QQQ DIA AAPL MSFT NVDA."
    )

    assert result.config.universe["symbols"] == ["SPY", "QQQ", "DIA", "AAPL", "MSFT", "NVDA"]
    for token in ["AI", "ML", "RSI", "SMA", "EMA", "ETF", "ETFS", "HFT", "API", "CEO", "USD"]:
        assert token not in result.config.universe["symbols"]


def test_duplicate_tickers_are_removed_preserving_prompt_order() -> None:
    result = generate_strategy_config_from_prompt("Momentum for SPY QQQ SPY AAPL QQQ MSFT NVDA DIA.")

    assert result.config.universe["symbols"] == ["SPY", "QQQ", "AAPL", "MSFT", "NVDA", "DIA"]


def test_generated_config_passes_validation() -> None:
    result = generate_strategy_config_from_prompt("5-day momentum strategy for SPY.")

    validate_strategy_config(result.config)
    assert result.config.entry_rules[0]["return_col"] == "return_5d"


def test_explain_prompt_lab_result_returns_readable_text() -> None:
    result = generate_strategy_config_from_prompt("Momentum strategy for AAPL.")

    explanation = explain_prompt_lab_result(result)

    assert "Strategy type: momentum" in explanation
    assert "Symbols: AAPL" in explanation
    assert "configs only" in explanation
    assert "does not trade" in explanation
    assert "long-only" in explanation
    assert "Risk:" in explanation


def test_prompt_lab_result_to_dict_is_json_serializable() -> None:
    result = generate_strategy_config_from_prompt("Momentum strategy for AAPL.")
    payload = prompt_lab_result_to_dict(result)

    encoded = json.dumps(payload)

    assert "momentum" in encoded
    assert payload["config"]["strategy_id"] == result.config.strategy_id


def test_cli_prompt_command_writes_output_yaml(tmp_path) -> None:
    runner = CliRunner()
    output_path = tmp_path / "strategy.yaml"

    result = runner.invoke(
        app,
        [
            "strategies",
            "prompt",
            "--prompt",
            "Momentum strategy for AAPL.",
            "--output-path",
            str(output_path),
        ],
    )

    assert result.exit_code == 0, result.output
    assert output_path.exists()
    content = output_path.read_text(encoding="utf-8")
    assert "strategy_type: momentum" in content
    assert "AAPL" in content
