"""Local JSON/JSONL paper ledger."""

import json
from pathlib import Path

from aurora.execution.exceptions import LedgerError
from aurora.execution.models import (
    SimulatedAccount,
    SimulatedOrder,
    SimulatedPosition,
    account_to_dict,
    order_to_dict,
    position_to_dict,
)
from aurora.risk.models import RiskDecision, risk_decision_to_dict


class PaperLedger:
    """Append-only order/risk ledger plus latest paper account state."""

    def __init__(self, base_dir: str | Path = "data/ledger") -> None:
        self.base_dir = Path(base_dir)

    @property
    def ledger_dir(self) -> Path:
        """Return the ledger directory, creating it if needed."""
        self.base_dir.mkdir(parents=True, exist_ok=True)
        return self.base_dir

    def record_order(self, order: SimulatedOrder) -> Path:
        """Append an order record to orders.jsonl."""
        return self._append_jsonl(self.ledger_dir / "orders.jsonl", order_to_dict(order))

    def record_risk_decision(self, decision: RiskDecision) -> Path:
        """Append a risk decision record to risk_decisions.jsonl."""
        return self._append_jsonl(self.ledger_dir / "risk_decisions.jsonl", risk_decision_to_dict(decision))

    def list_orders(self) -> list[dict]:
        """List recorded simulated orders."""
        return self._read_jsonl(self.ledger_dir / "orders.jsonl")

    def list_risk_decisions(self) -> list[dict]:
        """List recorded risk decisions."""
        return self._read_jsonl(self.ledger_dir / "risk_decisions.jsonl")

    def save_account(self, account: SimulatedAccount) -> Path:
        """Save latest simulated account state."""
        path = self.ledger_dir / "account.json"
        self._write_json(path, account_to_dict(account))
        return path

    def load_account(self) -> SimulatedAccount | None:
        """Load latest simulated account state."""
        path = self.ledger_dir / "account.json"
        if not path.exists():
            return None
        try:
            return SimulatedAccount(**self._read_json(path))
        except (TypeError, json.JSONDecodeError) as exc:
            raise LedgerError(f"Invalid account file: {path}") from exc

    def save_positions(self, positions: dict[str, SimulatedPosition]) -> Path:
        """Save latest simulated positions."""
        path = self.ledger_dir / "positions.json"
        payload = {symbol: position_to_dict(position) for symbol, position in positions.items()}
        self._write_json(path, payload)
        return path

    def load_positions(self) -> dict[str, SimulatedPosition]:
        """Load latest simulated positions."""
        path = self.ledger_dir / "positions.json"
        if not path.exists():
            return {}
        try:
            data = self._read_json(path)
            return {
                symbol: SimulatedPosition(**position_data)
                for symbol, position_data in data.items()
            }
        except (AttributeError, TypeError, json.JSONDecodeError) as exc:
            raise LedgerError(f"Invalid positions file: {path}") from exc

    def _append_jsonl(self, path: Path, payload: dict) -> Path:
        try:
            with path.open("a", encoding="utf-8") as file:
                file.write(json.dumps(payload, sort_keys=True) + "\n")
        except OSError as exc:
            raise LedgerError(f"Could not write ledger file: {path}") from exc
        return path

    def _read_jsonl(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            with path.open("r", encoding="utf-8") as file:
                return [json.loads(line) for line in file if line.strip()]
        except (OSError, json.JSONDecodeError) as exc:
            raise LedgerError(f"Invalid JSONL ledger file: {path}") from exc

    def _write_json(self, path: Path, payload: dict) -> None:
        try:
            with path.open("w", encoding="utf-8") as file:
                json.dump(payload, file, indent=2, sort_keys=True)
        except OSError as exc:
            raise LedgerError(f"Could not write ledger file: {path}") from exc

    def _read_json(self, path: Path) -> dict:
        try:
            with path.open("r", encoding="utf-8") as file:
                return json.load(file)
        except OSError as exc:
            raise LedgerError(f"Could not read ledger file: {path}") from exc


class ResearchLedger:
    """Compatibility wrapper around PaperLedger."""

    def __init__(self, base_dir: str | Path = "data/ledger") -> None:
        self.ledger = PaperLedger(base_dir)

    def list_entries(self) -> list[dict[str, object]]:
        """Return recorded order entries."""
        return self.ledger.list_orders()
