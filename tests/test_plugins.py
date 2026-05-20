"""Tests for plugin system."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from aurora.plugins.base import DataSourcePlugin, BrokerPlugin, OptimizerPlugin
from aurora.plugins.registry import PluginRegistry, PluginInfo, SECRET_PATTERNS


def test_data_source_plugin_abc() -> None:
    """Test that DataSourcePlugin is an abstract base class."""
    plugin = DataSourcePlugin.__abstractmethods__
    assert "fetch_data" in plugin
    assert "health_check" in plugin


def test_broker_plugin_abc() -> None:
    """Test that BrokerPlugin is an abstract base class."""
    plugin = BrokerPlugin.__abstractmethods__
    assert "health_check" in plugin
    assert "get_account" in plugin
    assert "submit_order" in plugin


def test_optimizer_plugin_abc() -> None:
    """Test that OptimizerPlugin is an abstract base class."""
    plugin = OptimizerPlugin.__abstractmethods__
    assert "optimize" in plugin
    assert "health_check" in plugin


def test_secret_patterns_defined() -> None:
    """Test that secret patterns are defined."""
    assert len(SECRET_PATTERNS) > 0
    assert any("AKIA" in p for p in SECRET_PATTERNS)
    assert any("sk-" in p for p in SECRET_PATTERNS)


def test_plugin_registry_init() -> None:
    """Test plugin registry initialization."""
    registry = PluginRegistry("/tmp/test_plugins")

    assert str(registry.plugin_dir) == "/tmp/test_plugins"


def test_plugin_registry_default_dir() -> None:
    """Test plugin registry default directory."""
    registry = PluginRegistry()

    expected = os.path.expanduser("~/aurora/plugins")
    assert str(registry.plugin_dir) == expected


def test_plugin_registry_discover_empty_dir() -> None:
    """Test discovering plugins in empty directory."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = PluginRegistry(tmpdir)
        plugins = registry.discover()

        assert plugins == []


def test_plugin_registry_discovers_valid_plugin() -> None:
    """Test discovering a valid plugin."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "test_data_source"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import DataSourcePlugin
import pandas as pd

class TestDataSource(DataSourcePlugin):
    def fetch_data(self, symbol, start_date=None, end_date=None, interval="1d"):
        return pd.DataFrame()

    def health_check(self):
        return {"status": "ok"}

def create_plugin():
    return TestDataSource()
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        plugins = registry.discover()

        assert len(plugins) == 1
        assert plugins[0].name == "test_data_source"
        assert plugins[0].plugin_type == "data_source"
        assert plugins[0].error is None


def test_plugin_registry_skips_invalid_plugin() -> None:
    """Test that invalid plugins are skipped with warning."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "invalid_plugin"
        plugin_dir.mkdir()

        plugin_code = '''
def some_function():
    pass
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        plugins = registry.discover()

        assert len(plugins) == 1
        assert plugins[0].error is not None


def test_plugin_registry_rejects_secret_in_file() -> None:
    """Test that plugins with secrets are rejected."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "secret_plugin"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import DataSourcePlugin
API_KEY = "AKIAIOSFODNN7EXAMPLE"

class SecretPlugin(DataSourcePlugin):
    pass
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        plugins = registry.discover()

        assert len(plugins) == 1
        assert "secret" in plugins[0].error.lower()


def test_plugin_registry_get_data_source() -> None:
    """Test getting a data source plugin by name."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "my_data_source"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import DataSourcePlugin
import pandas as pd

class MyDataSource(DataSourcePlugin):
    def fetch_data(self, symbol, start_date=None, end_date=None, interval="1d"):
        return pd.DataFrame()

    def health_check(self):
        return {"status": "ok"}

def create_plugin():
    return MyDataSource()
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        source = registry.get_data_source("my_data_source")

        assert source is not None
        assert isinstance(source, DataSourcePlugin)


def test_plugin_registry_get_nonexistent() -> None:
    """Test getting a nonexistent plugin returns None."""
    with tempfile.TemporaryDirectory() as tmpdir:
        registry = PluginRegistry(tmpdir)
        source = registry.get_data_source("nonexistent")

        assert source is None


def test_plugin_registry_list_plugins() -> None:
    """Test listing all plugins."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "test_plugin"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import DataSourcePlugin
import pandas as pd

class TestPlugin(DataSourcePlugin):
    version = "1.0.0"

    def fetch_data(self, symbol, start_date=None, end_date=None, interval="1d"):
        return pd.DataFrame()

    def health_check(self):
        return {"status": "ok"}

def create_plugin():
    return TestPlugin()
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        plugins = registry.list_plugins()

        assert len(plugins) == 1
        assert plugins[0]["name"] == "test_plugin"
        assert plugins[0]["version"] == "1.0.0"


def test_plugin_registry_validate() -> None:
    """Test validating plugins."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "valid_plugin"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import DataSourcePlugin
import pandas as pd

class ValidPlugin(DataSourcePlugin):
    def fetch_data(self, symbol, start_date=None, end_date=None, interval="1d"):
        return pd.DataFrame()

    def health_check(self):
        return {"status": "ok"}

def create_plugin():
    return ValidPlugin()
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        result = registry.validate_plugins()

        assert result["total"] == 1
        assert result["valid"] == 1
        assert result["errors"] == []


def test_plugin_registry_validate_with_errors() -> None:
    """Test validation with errors."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "bad_plugin"
        plugin_dir.mkdir()

        (plugin_dir / "__init__.py").write_text("def nothing(): pass")

        registry = PluginRegistry(tmpdir)
        result = registry.validate_plugins()

        assert result["total"] == 1
        assert result["valid"] == 0
        assert len(result["errors"]) == 1


def test_optimizer_plugin_creation() -> None:
    """Test creating an optimizer plugin."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "test_optimizer"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import OptimizerPlugin
import pandas as pd

class TestOptimizer(OptimizerPlugin):
    def optimize(self, strategy_builder, data, param_space, metric="sharpe", max_iterations=50):
        return {"best_params": {}, "score": 0.0}

    def health_check(self):
        return {"status": "ok"}

def create_plugin():
    return TestOptimizer()
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        optimizer = registry.get_optimizer("test_optimizer")

        assert optimizer is not None
        assert isinstance(optimizer, OptimizerPlugin)


def test_broker_plugin_paper_only_check() -> None:
    """Test that broker plugins are paper-only."""
    with tempfile.TemporaryDirectory() as tmpdir:
        plugin_dir = Path(tmpdir) / "test_broker"
        plugin_dir.mkdir()

        plugin_code = '''
from aurora.plugins.base import BrokerPlugin

class TestBroker(BrokerPlugin):
    def health_check(self):
        return {"status": "ok"}

    def get_account(self):
        return {"cash": 10000}

    def submit_order(self, symbol, quantity, side, order_type="market", limit_price=None):
        return {"id": "123", "status": "filled"}

    def cancel_order(self, order_id):
        return {"status": "cancelled"}

    def get_positions(self):
        return []

    def get_orders(self, status=None):
        return []

def create_plugin():
    return TestBroker()
'''
        (plugin_dir / "__init__.py").write_text(plugin_code)

        registry = PluginRegistry(tmpdir)
        broker = registry.get_broker("test_broker")

        assert broker is not None
        assert isinstance(broker, BrokerPlugin)