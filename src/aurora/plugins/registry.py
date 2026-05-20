"""Plugin registry for AURORA plugin system.

This module provides a registry that scans plugin directories,
discovers plugins, validates them, and makes them available.
"""

from __future__ import annotations

import importlib.util
import importlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Optional

from aurora.plugins.base import BrokerPlugin, DataSourcePlugin, OptimizerPlugin

logger = logging.getLogger(__name__)

SECRET_PATTERNS = [
    r"AKIA[0-9A-Z]{16}",
    r"sk-[a-zA-Z0-9]{20,}",
    r"xox[baprs]-[0-9a-zA-Z]{10,}",
    r"ghp_[a-zA-Z0-9]{36}",
    r"SG\.[a-zA-Z0-9_-]{22}\.[a-zA-Z0-9_-]{43}",
]

DEFAULT_PLUGIN_DIR = os.path.expanduser("~/aurora/plugins")


class PluginInfo:
    """Information about a discovered plugin."""

    def __init__(
        self,
        name: str,
        plugin_type: str,
        path: Path,
        instance: Any = None,
        version: Optional[str] = None,
        error: Optional[str] = None,
    ) -> None:
        self.name = name
        self.plugin_type = plugin_type
        self.path = path
        self.instance = instance
        self.version = version
        self.error = error


class PluginRegistry:
    """Registry for discovering and managing AURORA plugins."""

    def __init__(self, plugin_dir: Optional[str] = None) -> None:
        """Initialize the plugin registry.

        Args:
            plugin_dir: Directory to scan for plugins. Defaults to ~/aurora/plugins.
        """
        self._plugin_dir = Path(plugin_dir) if plugin_dir else Path(DEFAULT_PLUGIN_DIR)
        self._data_sources: dict[str, DataSourcePlugin] = {}
        self._brokers: dict[str, BrokerPlugin] = {}
        self._optimizers: dict[str, OptimizerPlugin] = {}
        self._discovered: list[PluginInfo] = []

    @property
    def plugin_dir(self) -> Path:
        """Get plugin directory path."""
        return self._plugin_dir

    def discover(self) -> list[PluginInfo]:
        """Scan plugin directory and discover plugins.

        Returns:
            List of PluginInfo objects for discovered plugins.
        """
        self._data_sources.clear()
        self._brokers.clear()
        self._optimizers.clear()
        self._discovered.clear()

        if not self._plugin_dir.exists():
            logger.warning(f"Plugin directory does not exist: {self._plugin_dir}")
            return []

        logger.info(f"Scanning plugin directory: {self._plugin_dir}")

        for entry in sorted(self._plugin_dir.iterdir()):
            if not entry.is_dir():
                continue

            plugin_info = self._load_plugin(entry)
            if plugin_info:
                self._discovered.append(plugin_info)

                if plugin_info.instance:
                    if isinstance(plugin_info.instance, DataSourcePlugin):
                        self._data_sources[plugin_info.name] = plugin_info.instance
                    elif isinstance(plugin_info.instance, BrokerPlugin):
                        self._brokers[plugin_info.name] = plugin_info.instance
                    elif isinstance(plugin_info.instance, OptimizerPlugin):
                        self._optimizers[plugin_info.name] = plugin_info.instance

        logger.info(f"Discovered {len(self._discovered)} plugin(s)")
        return self._discovered

    def _check_for_secrets(self, plugin_path: Path) -> Optional[str]:
        """Check plugin files for hardcoded secrets.

        Args:
            plugin_path: Path to plugin directory.

        Returns:
            Error message if secrets found, None otherwise.
        """
        python_files = list(plugin_path.glob("*.py"))

        for py_file in python_files:
            try:
                content = py_file.read_text(encoding="utf-8")
                for pattern in SECRET_PATTERNS:
                    if re.search(pattern, content):
                        return f"Potential secret detected in {py_file.name}"
            except Exception:
                pass

        return None

    def _load_plugin(self, plugin_path: Path) -> Optional[PluginInfo]:
        """Load a single plugin from a directory.

        Args:
            plugin_path: Path to plugin directory.

        Returns:
            PluginInfo if loaded successfully, None otherwise.
        """
        name = plugin_path.name

        secret_error = self._check_for_secrets(plugin_path)
        if secret_error:
            logger.warning(f"Plugin {name} rejected: {secret_error}")
            return PluginInfo(name, "unknown", plugin_path, error=secret_error)

        init_file = plugin_path / "__init__.py"
        plugin_file = plugin_path / "plugin.py"

        module_path = None
        if init_file.exists():
            module_path = init_file
        elif plugin_file.exists():
            module_path = plugin_file

        if not module_path:
            logger.debug(f"No plugin file found in {plugin_path}")
            return None

        try:
            spec = importlib.util.spec_from_file_location(f"aurora_plugin_{name}", module_path)
            if spec is None or spec.loader is None:
                return None

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            instance = None
            plugin_type = "unknown"

            if hasattr(module, "create_plugin"):
                instance = module.create_plugin()
            elif hasattr(module, "plugin"):
                instance = module.plugin

            if instance is None:
                logger.warning(f"Plugin {name} has no create_plugin() or plugin attribute")
                return PluginInfo(name, plugin_type, plugin_path, error="No plugin instance")

            if isinstance(instance, DataSourcePlugin):
                plugin_type = "data_source"
            elif isinstance(instance, BrokerPlugin):
                plugin_type = "broker"
            elif isinstance(instance, OptimizerPlugin):
                plugin_type = "optimizer"
            else:
                logger.warning(f"Plugin {name} doesn't implement required ABC")
                return PluginInfo(name, plugin_type, plugin_path, error="Invalid plugin type")

            version = getattr(instance, "version", None) or getattr(module, "__version__", None)

            logger.info(f"Loaded plugin: {name} ({plugin_type})")
            return PluginInfo(name, plugin_type, plugin_path, instance, version)

        except Exception as e:
            logger.warning(f"Failed to load plugin {name}: {e}")
            return PluginInfo(name, "unknown", plugin_path, error=str(e))

    def get_data_source(self, name: str) -> Optional[DataSourcePlugin]:
        """Get a data source plugin by name.

        Args:
            name: Plugin name.

        Returns:
            DataSourcePlugin instance or None.
        """
        if not self._data_sources and not self._discovered:
            self.discover()
        return self._data_sources.get(name)

    def get_broker(self, name: str) -> Optional[BrokerPlugin]:
        """Get a broker plugin by name.

        Args:
            name: Plugin name.

        Returns:
            BrokerPlugin instance or None.
        """
        if not self._brokers and not self._discovered:
            self.discover()
        return self._brokers.get(name)

    def get_optimizer(self, name: str) -> Optional[OptimizerPlugin]:
        """Get an optimizer plugin by name.

        Args:
            name: Plugin name.

        Returns:
            OptimizerPlugin instance or None.
        """
        if not self._optimizers and not self._discovered:
            self.discover()
        return self._optimizers.get(name)

    def list_plugins(self) -> list[dict[str, Any]]:
        """Get list of all discovered plugins.

        Returns:
            List of plugin info dictionaries.
        """
        if not self._discovered:
            self.discover()

        result = []
        for plugin in self._discovered:
            result.append({
                "name": plugin.name,
                "type": plugin.plugin_type,
                "version": plugin.version,
                "path": str(plugin.path),
                "error": plugin.error,
            })
        return result

    def validate_plugins(self) -> dict[str, Any]:
        """Validate all plugins in the registry.

        Returns:
            Validation result dictionary.
        """
        if not self._discovered:
            self.discover()

        valid = 0
        errors = []

        for plugin in self._discovered:
            if plugin.error:
                errors.append({"name": plugin.name, "error": plugin.error})
            else:
                valid += 1

        return {
            "total": len(self._discovered),
            "valid": valid,
            "errors": errors,
        }