"""AURORA Terminal User Interface (TUI).

A keyboard-navigable terminal application for all major AURORA workflows.
Requires Textual: pip install .[tui]
"""

from aurora.tui.app import AuroraTUI

__all__ = ["AuroraTUI"]