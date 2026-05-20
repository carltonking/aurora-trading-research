"""Strategy sandboxing for safe strategy execution.

This module provides sandboxing for user-built strategies to prevent
dangerous operations like filesystem writes, network access, and
import of dangerous modules.
"""

from __future__ import annotations

import ast
import os
import sys
from typing import Any, Optional

import pandas as pd


DISALLOWED_IMPORTS = {
    "os",
    "sys",
    "subprocess",
    "socket",
    "requests",
    "urllib",
    "http",
    "ftplib",
    "telnetlib",
    "shutil",
    "ctypes",
    "multiprocessing",
    "threading",
    "signal",
    "boto3",
    "boto",
    "botocore",
    "alpaca",
    "lseg",
    "interactive",
    "ib",
    "ccxt",
}

DISALLOWED_BUILTINS = {
    "exec",
    "eval",
    "compile",
    "open",
    "__import__",
}

DISALLOWED_ATTRIBUTES = {
    "__subclasses__",
    "__bases__",
    "__globals__",
    "__code__",
    "__closure__",
}

FORBIDDEN_FILE_WRITES = {"write", "w", "a", "r+"}


class SandboxViolationError(Exception):
    """Raised when a strategy violates sandbox rules."""

    pass


def is_sandbox_enabled() -> bool:
    """Check if sandbox mode is enabled.

    Returns:
        True if AURORA_SANDBOX environment variable is set to 'true'.
    """
    return os.getenv("AURORA_SANDBOX", "false").lower() == "true"


class SandboxVisitor(ast.NodeVisitor):
    """AST visitor to detect dangerous patterns in strategy code."""

    def __init__(self) -> None:
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import) -> None:
        """Check import statements."""
        for alias in node.names:
            name = alias.name.split(".")[0].lower()
            if name in DISALLOWED_IMPORTS:
                self.violations.append(f"Disallowed import: '{alias.name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from...import statements."""
        if node.module:
            name = node.module.split(".")[0].lower()
            if name in DISALLOWED_IMPORTS:
                self.violations.append(f"Disallowed import: 'from {node.module} ...'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Check for dangerous function calls."""
        if isinstance(node.func, ast.Name):
            if node.func.id in DISALLOWED_BUILTINS:
                self.violations.append(f"Disallowed builtin: '{node.func.id}()'")
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in DISALLOWED_BUILTINS:
                self.violations.append(f"Disallowed method: '{node.func.attr}()'")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Check for dangerous attribute access."""
        if node.attr in DISALLOWED_ATTRIBUTES:
            self.violations.append(f"Disallowed attribute: '__*{node.attr}*__'")
        self.generic_visit(node)


class SandboxValidator:
    """Validates strategy source code against sandbox rules."""

    def __init__(self) -> None:
        self._visitor = SandboxVisitor()

    def validate_source(self, code: str) -> bool:
        """Validate strategy source code.

        Args:
            code: Python source code string.

        Returns:
            True if code is safe.

        Raises:
            SandboxViolationError: If code contains dangerous patterns.
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SandboxViolationError(f"Syntax error in strategy code: {e}")

        self._visitor = SandboxVisitor()
        self._visitor.visit(tree)

        if self._visitor.violations:
            raise SandboxViolationError(
                f"Sandbox violation(s) detected: {'; '.join(self._visitor.violations)}"
            )

        return True


class SandboxedStrategy:
    """Wrapper that runs strategies in sandboxed mode."""

    def __init__(
        self,
        strategy_instance: Any,
        source_code: Optional[str] = None,
    ) -> None:
        """Initialize sandboxed strategy.

        Args:
            strategy_instance: The strategy object to wrap.
            source_code: Optional source code for validation.
        """
        self._strategy = strategy_instance
        self._source_code = source_code

        if is_sandbox_enabled():
            self._validate()

    def _validate(self) -> None:
        """Validate the strategy code if sandbox is enabled."""
        if self._source_code:
            validator = SandboxValidator()
            validator.validate_source(self._source_code)

    def generate_signal(self, data: pd.DataFrame) -> pd.Series:
        """Generate trading signal from strategy.

        Args:
            data: Market data DataFrame.

        Returns:
            Series of trading signals.
        """
        return self._strategy.generate_signal(data)

    @property
    def strategy(self) -> Any:
        """Get the underlying strategy."""
        return self._strategy


def create_sandboxed_strategy(
    strategy_instance: Any,
    source_code: Optional[str] = None,
) -> SandboxedStrategy | Any:
    """Create a sandboxed strategy if sandbox is enabled.

    Args:
        strategy_instance: The strategy object.
        source_code: Optional source code.

    Returns:
        SandboxedStrategy if enabled, otherwise the original strategy.
    """
    if is_sandbox_enabled():
        return SandboxedStrategy(strategy_instance, source_code)
    return strategy_instance