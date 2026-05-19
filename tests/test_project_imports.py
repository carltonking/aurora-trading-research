from aurora.backtesting.engine import BacktestEngine
from aurora.core.engine import AuroraEngine
from aurora.data.quality import DataQualityChecker
from aurora.models.registry import ModelRegistry
from aurora.risk.risk_manager import RiskManager
from aurora.strategies.registry import StrategyRegistry


def test_key_modules_import_and_engine_status(tmp_path) -> None:
    engine = AuroraEngine({"mode": "research", "execution": {"live_trading_enabled": False}})
    status = engine.status()

    assert status["project"] == "AURORA Trading Research"
    assert status["mode"] == "research"
    assert status["live_trading_enabled"] is False
    assert StrategyRegistry().list_strategies() == []
    assert ModelRegistry(base_dir=tmp_path).list_models() == []
    assert RiskManager().describe()
    assert BacktestEngine().describe()
    assert DataQualityChecker().describe()
