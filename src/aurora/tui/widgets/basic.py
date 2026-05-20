"""Basic TUI widgets."""

from textual.app import ComposeResult
from textual.containers import Horizontal, Container
from textual.widgets import Static, Footer


class MetricCard(Static):
    """A small bordered panel showing a label and value."""

    def __init__(self, label: str, value: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._label = label
        self._value = value

    def compose(self) -> ComposeResult:
        yield Static(f"[b]{self._label}[/b]\n{self._value}", id="metric")


class DisclaimerFooter(Footer):
    """Footer bar that always shows the mandatory disclaimer."""

    def compose(self) -> ComposeResult:
        yield Static(
            "DISCLAIMER: Research-only. No profitability. User bears all responsibility. | "
            "F1-Home F2-Data F3-Strategy F4-Backtest F5-Paper F6-Optimize F7-Ready F8-Export | Ctrl+Q Quit"
        )


class SparklineChart(Static):
    """Widget that renders a simple ASCII sparkline from numeric values."""

    def __init__(self, values: list[float] | None = None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._values = values or []

    def update(self, values: list[float]) -> None:
        """Update the sparkline with new values."""
        self._values = values
        self.refresh()

    def render(self) -> str:
        """Render the sparkline as ASCII art."""
        if not self._values:
            return "No data"

        min_val = min(self._values)
        max_val = max(self._values)
        range_val = max_val - min_val if max_val != min_val else 1

        chars = " ▁▂▃▄▅▆▇█"
        result = ""
        for v in self._values:
            idx = int(((v - min_val) / range_val) * (len(chars) - 1))
            result += chars[idx]
        return result