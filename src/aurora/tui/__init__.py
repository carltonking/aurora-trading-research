"""AURORA Terminal User Interface (TUI).

A keyboard-navigable terminal application for all major AURORA workflows.
Requires Textual: pip install .[tui]

``AuroraTUI`` is exposed lazily via module ``__getattr__`` so that simply
importing :mod:`aurora.tui` (and, transitively, the CLI) does not require the
optional ``textual`` dependency. The hard import only happens when ``AuroraTUI``
is actually accessed.
"""

from typing import Any

__all__ = ["AuroraTUI"]


def __getattr__(name: str) -> Any:
    if name == "AuroraTUI":
        from aurora.tui.app import AuroraTUI

        return AuroraTUI
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
