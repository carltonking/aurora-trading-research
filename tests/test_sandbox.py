"""Tests for sandbox system."""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from aurora.security.sandbox import (
    SandboxViolationError,
    SandboxValidator,
    SandboxedStrategy,
    is_sandbox_enabled,
    create_sandboxed_strategy,
    DISALLOWED_IMPORTS,
    DISALLOWED_BUILTINS,
)


def test_is_sandbox_enabled_default() -> None:
    """Test sandbox is disabled by default."""
    original = os.environ.get("AURORA_SANDBOX")
    try:
        if "AURORA_SANDBOX" in os.environ:
            del os.environ["AURORA_SANDBOX"]

        assert is_sandbox_enabled() is False
    finally:
        if original:
            os.environ["AURORA_SANDBOX"] = original


def test_is_sandbox_enabled_true() -> None:
    """Test sandbox can be enabled via env var."""
    original = os.environ.get("AURORA_SANDBOX")
    try:
        os.environ["AURORA_SANDBOX"] = "true"

        assert is_sandbox_enabled() is True
    finally:
        if original:
            os.environ["AURORA_SANDBOX"] = original
        else:
            del os.environ["AURORA_SANDBOX"]


def test_disallowed_imports_defined() -> None:
    """Test that disallowed imports are defined."""
    assert "os" in DISALLOWED_IMPORTS
    assert "sys" in DISALLOWED_IMPORTS
    assert "subprocess" in DISALLOWED_IMPORTS
    assert "requests" in DISALLOWED_IMPORTS


def test_disallowed_builtins_defined() -> None:
    """Test that disallowed builtins are defined."""
    assert "exec" in DISALLOWED_BUILTINS
    assert "eval" in DISALLOWED_BUILTINS


def test_safe_code_passes() -> None:
    """Test that safe code passes validation."""
    code = """
import pandas as pd
import numpy as np

def generate_signal(data):
    return pd.Series([1, -1, 0], index=data.index)
"""
    validator = SandboxValidator()
    result = validator.validate_source(code)
    assert result is True


def test_import_os_raises() -> None:
    """Test that importing os raises violation."""
    code = """
import os
def generate_signal(data):
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed import"):
        validator.validate_source(code)


def test_import_sys_raises() -> None:
    """Test that importing sys raises violation."""
    code = """
import sys
def generate_signal(data):
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed import"):
        validator.validate_source(code)


def test_import_subprocess_raises() -> None:
    """Test that importing subprocess raises violation."""
    code = """
import subprocess
def generate_signal(data):
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed import"):
        validator.validate_source(code)


def test_from_import_raises() -> None:
    """Test that from...import raises violation for disallowed module."""
    code = """
from os import path
def generate_signal(data):
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed import"):
        validator.validate_source(code)


def test_eval_raises() -> None:
    """Test that eval() raises violation."""
    code = """
def generate_signal(data):
    return eval("1 + 1")
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed builtin"):
        validator.validate_source(code)


def test_exec_raises() -> None:
    """Test that exec() raises violation."""
    code = """
def generate_signal(data):
    exec("print('hello')")
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed builtin"):
        validator.validate_source(code)


def test_open_write_raises() -> None:
    """Test that open() for writing raises violation."""
    code = """
def generate_signal(data):
    f = open("test.txt", "w")
    f.write("test")
    f.close()
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed builtin"):
        validator.validate_source(code)


def test_sandboxed_strategy_calls_underlying() -> None:
    """Test that SandboxedStrategy calls underlying strategy."""
    import pandas as pd

    mock_strategy = MagicMock()
    mock_strategy.generate_signal.return_value = pd.Series([1, -1])

    sandboxed = SandboxedStrategy(mock_strategy, "def generate_signal(data): pass")

    data = pd.DataFrame({"close": [100, 101, 100]})
    result = sandboxed.generate_signal(data)

    mock_strategy.generate_signal.assert_called_once_with(data)
    assert len(result) == 2


def test_sandboxed_strategy_validates_source() -> None:
    """Test that SandboxedStrategy validates source."""
    mock_strategy = MagicMock()

    with patch("aurora.security.sandbox.is_sandbox_enabled", return_value=True):
        with pytest.raises(SandboxViolationError):
            SandboxedStrategy(mock_strategy, "import os")


def test_sandbox_skipped_when_disabled() -> None:
    """Test that validation is skipped when sandbox is disabled."""
    mock_strategy = MagicMock()

    with patch("aurora.security.sandbox.is_sandbox_enabled", return_value=False):
        sandboxed = SandboxedStrategy(mock_strategy, "import os")

    assert sandboxed is not None


def test_create_sandboxed_strategy_enabled() -> None:
    """Test create returns SandboxedStrategy when enabled."""
    mock_strategy = MagicMock()

    with patch("aurora.security.sandbox.is_sandbox_enabled", return_value=True):
        result = create_sandboxed_strategy(mock_strategy, "def generate_signal(data): pass")

    assert isinstance(result, SandboxedStrategy)


def test_create_sandboxed_strategy_disabled() -> None:
    """Test create returns original strategy when disabled."""
    mock_strategy = MagicMock()

    with patch("aurora.security.sandbox.is_sandbox_enabled", return_value=False):
        result = create_sandboxed_strategy(mock_strategy, "def generate_signal(data): pass")

    assert result is mock_strategy


def test_syntax_error_raises() -> None:
    """Test that syntax errors in code raise violation."""
    code = """
def generate_signal(data)
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Syntax error"):
        validator.validate_source(code)


def test_disallowed_module_attributes() -> None:
    """Test that access to dangerous module attributes raises."""
    code = """
def generate_signal(data):
    return data.__class__.__subclasses__()
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed attribute"):
        validator.validate_source(code)


def test_requests_import_raises() -> None:
    """Test that importing requests raises violation."""
    code = """
import requests
def generate_signal(data):
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed import"):
        validator.validate_source(code)


def test_threading_import_raises() -> None:
    """Test that importing threading raises violation."""
    code = """
import threading
def generate_signal(data):
    return data
"""
    validator = SandboxValidator()

    with pytest.raises(SandboxViolationError, match="Disallowed import"):
        validator.validate_source(code)