from aurora.core.config import load_yaml_config


def test_example_config_loads() -> None:
    config = load_yaml_config("config/settings.example.yaml")

    assert config["mode"] == "research"
    assert config["broker"] == "simulation"
    assert config["execution"]["live_trading_enabled"] is False
    assert config["risk_limits"]["allow_shorting"] is False
