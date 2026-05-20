"""Tests for position sizing models."""

import pytest

from aurora.risk.position_sizing import (
    FixedFractionSizer,
    KellySizer,
    VolatilityAdjustedSizer,
    EqualRiskContributionSizer,
    get_sizer_from_config,
)


def test_fixed_fraction_sizer() -> None:
    """Test fixed fraction position sizing."""
    sizer = FixedFractionSizer(fraction=0.1)
    shares = sizer.calculate(portfolio_value=100000, price=100)
    assert shares == 100


def test_fixed_fraction_sizer_zero_values() -> None:
    """Test with zero portfolio or price."""
    sizer = FixedFractionSizer(fraction=0.1)
    assert sizer.calculate(portfolio_value=0, price=100) == 0
    assert sizer.calculate(portfolio_value=100000, price=0) == 0


def test_fixed_fraction_sizer_fraction() -> None:
    """Test different fractions."""
    sizer = FixedFractionSizer(fraction=0.05)
    shares = sizer.calculate(portfolio_value=100000, price=100)
    assert shares == 50


def test_kelly_sizer() -> None:
    """Test Kelly criterion position sizing."""
    sizer = KellySizer(multiplier=1.0, win_rate=0.6, avg_win=1.5, avg_loss=1.0)
    shares = sizer.calculate(portfolio_value=100000, price=100, strategy_edge=0.05)
    assert shares > 0


def test_kelly_sizer_zero_values() -> None:
    """Test Kelly with zero values."""
    sizer = KellySizer()
    assert sizer.calculate(portfolio_value=0, price=100) == 0
    assert sizer.calculate(portfolio_value=100000, price=0) == 0


def test_kelly_sizer_invalid_multiplier() -> None:
    """Test Kelly rejects invalid multiplier."""
    with pytest.raises(ValueError):
        KellySizer(multiplier=1.5)


def test_volatility_adjusted_sizer() -> None:
    """Test volatility-adjusted position sizing."""
    sizer = VolatilityAdjustedSizer(target_volatility=0.02)
    shares = sizer.calculate(portfolio_value=100000, price=100, volatility=0.02)
    assert shares > 0


def test_volatility_adjusted_sizer_zero_values() -> None:
    """Test volatility sizer with zero values."""
    sizer = VolatilityAdjustedSizer()
    assert sizer.calculate(portfolio_value=0, price=100) == 0
    assert sizer.calculate(portfolio_value=100000, price=0) == 0


def test_volatility_adjusted_sizer_target() -> None:
    """Test different target volatility."""
    sizer = VolatilityAdjustedSizer(target_volatility=0.01)
    shares = sizer.calculate(portfolio_value=100000, price=100, volatility=0.02)
    assert shares == 500


def test_equal_risk_sizer() -> None:
    """Test equal risk contribution sizing."""
    sizer = EqualRiskContributionSizer(risk_per_trade=0.01, stop_loss_pct=0.02)
    shares = sizer.calculate(portfolio_value=100000, price=100)
    assert shares == 500


def test_equal_risk_sizer_zero_values() -> None:
    """Test equal risk sizer with zero values."""
    sizer = EqualRiskContributionSizer()
    assert sizer.calculate(portfolio_value=0, price=100) == 0
    assert sizer.calculate(portfolio_value=100000, price=0) == 0


def test_equal_risk_sizer_custom_risk() -> None:
    """Test different risk per trade."""
    sizer = EqualRiskContributionSizer(risk_per_trade=0.02, stop_loss_pct=0.04)
    shares = sizer.calculate(portfolio_value=100000, price=100)
    assert shares == 500


def test_equal_risk_sizer_invalid_params() -> None:
    """Test invalid parameters."""
    with pytest.raises(ValueError):
        EqualRiskContributionSizer(risk_per_trade=0)
    with pytest.raises(ValueError):
        EqualRiskContributionSizer(stop_loss_pct=0)


def test_get_sizer_from_config_fixed() -> None:
    """Test getting fixed fraction sizer from config."""
    sizer = get_sizer_from_config("fixed_fraction", fraction=0.2)
    assert isinstance(sizer, FixedFractionSizer)
    assert sizer.fraction == 0.2


def test_get_sizer_from_config_kelly() -> None:
    """Test getting Kelly sizer from config."""
    sizer = get_sizer_from_config("kelly", multiplier=0.3)
    assert isinstance(sizer, KellySizer)
    assert sizer.multiplier == 0.3


def test_get_sizer_from_config_volatility() -> None:
    """Test getting volatility sizer from config."""
    sizer = get_sizer_from_config("volatility", target_volatility=0.03)
    assert isinstance(sizer, VolatilityAdjustedSizer)
    assert sizer.target_volatility == 0.03


def test_get_sizer_from_config_equal_risk() -> None:
    """Test getting equal risk sizer from config."""
    sizer = get_sizer_from_config("equal_risk", risk_per_trade=0.02)
    assert isinstance(sizer, EqualRiskContributionSizer)
    assert sizer.risk_per_trade == 0.02


def test_get_sizer_from_config_unknown() -> None:
    """Test unknown sizer type returns default."""
    sizer = get_sizer_from_config("unknown_type")
    assert isinstance(sizer, FixedFractionSizer)