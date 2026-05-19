"""Configuration helpers for AURORA."""

from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv


def get_project_root() -> Path:
    """Return the repository root for the installed source tree."""
    return Path(__file__).resolve().parents[3]


def load_env() -> None:
    """Load local environment variables from a .env file if present."""
    load_dotenv()


def load_yaml_config(path: str | Path) -> dict[str, Any]:
    """Load a YAML configuration file."""
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = get_project_root() / config_path

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}

    if not isinstance(config, dict):
        raise ValueError(f"Config file must contain a YAML mapping: {config_path}")

    return config
