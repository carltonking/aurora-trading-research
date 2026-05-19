"""Run local paper simulation from an approved non-executing plan."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
import json

import pandas as pd

from aurora.execution.exceptions import AuroraExecutionError
from aurora.execution.ledger import PaperLedger
from aurora.execution.models import ORDER_FILLED, ORDER_REJECTED, account_to_dict
from aurora.execution.simulation_broker import SimulationBroker
from aurora.readiness.paper_sim import PAPER_SIM_READY
from aurora.readiness.paper_sim_plan import PAPER_SIM_PLAN_READY
from aurora.reporting.reports import save_json_report
from aurora.risk.models import (
    RISK_APPROVED,
    RISK_REDUCED_SIZE,
    PortfolioState,
    RiskConfig,
    TradeCandidate,
)
from aurora.risk.risk_manager import RiskManager

PAPER_SIM_FROM_PLAN_BLOCKED = "BLOCKED"
PAPER_SIM_FROM_PLAN_COMPLETED = "COMPLETED"

PAPER_SIM_INFO = "INFO"
PAPER_SIM_WARNING = "WARNING"
PAPER_SIM_CRITICAL = "CRITICAL"

SIMULATION_SAFETY_FLAG_FALSE_KEYS = [
    "placed_orders",
    "used_broker",
    "wrote_ledger",
    "external_llm_calls",
]


@dataclass(frozen=True)
class PaperSimFromPlanFinding:
    """Single deterministic local paper simulation finding."""

    code: str
    severity: str
    message: str


@dataclass(frozen=True)
class PaperSimFromPlanConfig:
    """Configuration for local paper simulation from a saved plan."""

    run_dir: str
    output_dir: str | None = None
    require_plan_ready: bool = True
    require_readiness_ready: bool = True
    require_risk_gate: bool = True
    initial_cash: float | None = None
    max_candidates: int | None = None
    dry_run: bool = False


@dataclass(frozen=True)
class PaperSimFromPlanResult:
    """Result from running local paper simulation from a plan."""

    run_id: str
    strategy_id: str
    status: str
    simulated_at: str
    findings: list[PaperSimFromPlanFinding]
    run_dir: str
    output_dir: str
    manifest_path: str
    readiness_path: str
    plan_path: str
    signals_path: str | None
    simulation_manifest_path: str | None
    orders_path: str | None
    risk_decisions_path: str | None
    account_path: str | None
    positions_path: str | None
    safety_flags: dict[str, Any]
    summary: dict[str, Any]


class PaperSimFromPlanError(AuroraExecutionError):
    """Raised when local paper simulation from plan cannot be evaluated."""


def run_paper_simulation_from_plan(
    config: PaperSimFromPlanConfig,
) -> PaperSimFromPlanResult:
    """Run local-only simulation from an approved paper simulation plan."""
    _validate_config(config)
    run_dir = Path(config.run_dir)
    manifest_path = run_dir / "manifest.json"
    readiness_path = run_dir / "paper_sim_readiness.json"
    plan_path = run_dir / "paper_sim_plan.json"
    if not manifest_path.exists():
        raise PaperSimFromPlanError(f"Research run manifest not found: {manifest_path}")
    if not readiness_path.exists():
        raise PaperSimFromPlanError(f"Readiness artifact not found: {readiness_path}")
    if not plan_path.exists():
        raise PaperSimFromPlanError(f"Plan artifact not found: {plan_path}")

    manifest = _load_json(manifest_path)
    readiness = _load_json(readiness_path)
    plan_artifact = _load_json(plan_path)
    output_dir = Path(config.output_dir) if config.output_dir else run_dir / "paper_simulation"
    output_dir.mkdir(parents=True, exist_ok=True)
    simulation_manifest_path = output_dir / "simulation_manifest.json"
    simulated_at = datetime.now(UTC).isoformat()

    findings: list[PaperSimFromPlanFinding] = []
    findings.extend(_safety_flag_findings("manifest", manifest.get("safety_flags")))
    findings.extend(_safety_flag_findings("readiness", readiness.get("safety_flags")))
    findings.extend(_safety_flag_findings("plan", plan_artifact.get("safety_flags")))
    findings.extend(_readiness_findings(readiness, config))
    findings.extend(_plan_findings(plan_artifact, config))

    signals_path = _resolve_signals_path(run_dir, plan_artifact)
    if signals_path is None or not signals_path.exists():
        findings.append(
            PaperSimFromPlanFinding(
                code="missing_signals_artifact",
                severity=PAPER_SIM_CRITICAL,
                message=f"Signals artifact is missing: {signals_path}.",
            )
        )

    run_id = str(manifest.get("run_id", run_dir.name))
    strategy_id = str(manifest.get("strategy_id", ""))
    safety_flags = _simulation_safety_flags(config)

    if _has_critical(findings):
        result = _result(
            run_id=run_id,
            strategy_id=strategy_id,
            status=PAPER_SIM_FROM_PLAN_BLOCKED,
            simulated_at=simulated_at,
            findings=findings,
            run_dir=run_dir,
            output_dir=output_dir,
            manifest_path=manifest_path,
            readiness_path=readiness_path,
            plan_path=plan_path,
            signals_path=signals_path,
            simulation_manifest_path=simulation_manifest_path,
            safety_flags=safety_flags,
            summary={"blocked": True, "candidate_count": 0},
        )
        save_paper_sim_from_plan_result(result, simulation_manifest_path)
        return result

    candidates, conversion_findings = _load_candidates(
        signals_path=signals_path,
        strategy_id=strategy_id,
        max_candidates=config.max_candidates,
    )
    findings.extend(conversion_findings)
    if not candidates:
        findings.append(
            PaperSimFromPlanFinding(
                code="no_valid_candidates",
                severity=PAPER_SIM_WARNING,
                message="No valid long-only candidates were produced from signals.",
            )
        )

    plan = _safe_dict(plan_artifact.get("plan"))
    risk_config = _risk_config_from_plan(plan)
    initial_cash = _initial_cash(config, plan)
    slippage_bps = float(plan.get("slippage_bps", 5.0) or 0.0)

    if config.dry_run:
        summary = _dry_run_candidates(candidates, risk_config, initial_cash)
        ledger_paths = _empty_ledger_paths()
    elif candidates:
        summary, ledger_paths = _simulate_candidates(
            candidates=candidates,
            output_dir=output_dir,
            risk_config=risk_config,
            initial_cash=initial_cash,
            slippage_bps=slippage_bps,
        )
    else:
        summary = _base_summary(candidate_count=0)
        ledger_paths = _empty_ledger_paths()

    result = _result(
        run_id=run_id,
        strategy_id=strategy_id,
        status=PAPER_SIM_FROM_PLAN_COMPLETED,
        simulated_at=simulated_at,
        findings=findings,
        run_dir=run_dir,
        output_dir=output_dir,
        manifest_path=manifest_path,
        readiness_path=readiness_path,
        plan_path=plan_path,
        signals_path=signals_path,
        simulation_manifest_path=simulation_manifest_path,
        safety_flags=safety_flags,
        summary=summary,
        ledger_paths=ledger_paths,
    )
    save_paper_sim_from_plan_result(result, simulation_manifest_path)
    return result


def paper_sim_from_plan_result_to_dict(
    result: PaperSimFromPlanResult,
) -> dict[str, Any]:
    """Convert a paper simulation result to a JSON-serializable dictionary."""
    return asdict(result)


def save_paper_sim_from_plan_result(
    result: PaperSimFromPlanResult,
    path: str | Path,
) -> Path:
    """Save the local paper simulation manifest."""
    return save_json_report(paper_sim_from_plan_result_to_dict(result), path)


def _validate_config(config: PaperSimFromPlanConfig) -> None:
    if config.initial_cash is not None and config.initial_cash <= 0:
        raise PaperSimFromPlanError("initial_cash must be greater than 0 when supplied.")
    if config.max_candidates is not None and config.max_candidates < 0:
        raise PaperSimFromPlanError("max_candidates must be non-negative when supplied.")


def _safety_flag_findings(
    source_name: str,
    safety_flags: object,
) -> list[PaperSimFromPlanFinding]:
    if not isinstance(safety_flags, dict):
        return [
            PaperSimFromPlanFinding(
                code="missing_safety_flags",
                severity=PAPER_SIM_CRITICAL,
                message=f"{source_name} safety flags are missing or malformed.",
            )
        ]
    findings = []
    has_safe_posture = bool(
        safety_flags.get("research_only")
        or safety_flags.get("artifact_only")
        or safety_flags.get("status_snapshot_only")
    )
    if not has_safe_posture:
        findings.append(
            PaperSimFromPlanFinding(
                code="missing_research_or_artifact_flag",
                severity=PAPER_SIM_CRITICAL,
                message=f"{source_name} does not declare research-only or artifact-only posture.",
            )
        )

    for key in SIMULATION_SAFETY_FLAG_FALSE_KEYS:
        if safety_flags.get(key) is not False:
            findings.append(
                PaperSimFromPlanFinding(
                    code="unsafe_prior_safety_flag",
                    severity=PAPER_SIM_CRITICAL,
                    message=f"{source_name} safety flag {key} expected False, found {safety_flags.get(key)}.",
                )
            )
    return findings


def _readiness_findings(
    readiness: dict[str, Any],
    config: PaperSimFromPlanConfig,
) -> list[PaperSimFromPlanFinding]:
    if config.require_readiness_ready and readiness.get("status") != PAPER_SIM_READY:
        return [
            PaperSimFromPlanFinding(
                code="readiness_not_ready",
                severity=PAPER_SIM_CRITICAL,
                message=f"Readiness status is {readiness.get('status')}; expected {PAPER_SIM_READY}.",
            )
        ]
    return []


def _plan_findings(
    plan_artifact: dict[str, Any],
    config: PaperSimFromPlanConfig,
) -> list[PaperSimFromPlanFinding]:
    findings: list[PaperSimFromPlanFinding] = []
    if config.require_plan_ready and plan_artifact.get("status") != PAPER_SIM_PLAN_READY:
        findings.append(
            PaperSimFromPlanFinding(
                code="plan_not_ready",
                severity=PAPER_SIM_CRITICAL,
                message=f"Plan status is {plan_artifact.get('status')}; expected {PAPER_SIM_PLAN_READY}.",
            )
        )

    plan = _safe_dict(plan_artifact.get("plan"))
    if config.require_risk_gate and plan.get("require_risk_gate") is not True:
        findings.append(
            PaperSimFromPlanFinding(
                code="risk_gate_not_required_by_plan",
                severity=PAPER_SIM_CRITICAL,
                message="Plan does not require the RiskManager hard gate.",
            )
        )
    return findings


def _resolve_signals_path(run_dir: Path, plan_artifact: dict[str, Any]) -> Path | None:
    plan = _safe_dict(plan_artifact.get("plan"))
    artifacts = _safe_dict(plan.get("proposed_input_artifacts"))
    signal_value = artifacts.get("signals_path")
    candidates: list[Path] = []
    if isinstance(signal_value, str) and signal_value.strip():
        raw_path = Path(signal_value)
        candidates.append(raw_path)
        if not raw_path.is_absolute():
            candidates.append(run_dir / raw_path)
    candidates.append(run_dir / "signals.csv")
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0] if candidates else None


def _load_candidates(
    signals_path: Path,
    strategy_id: str,
    max_candidates: int | None,
) -> tuple[list[TradeCandidate], list[PaperSimFromPlanFinding]]:
    findings: list[PaperSimFromPlanFinding] = []
    try:
        signals = pd.read_csv(signals_path)
    except Exception as exc:
        raise PaperSimFromPlanError(f"Could not read signals artifact: {signals_path}") from exc

    required = {"timestamp", "symbol", "signal"}
    missing = sorted(required - set(signals.columns))
    if missing:
        raise PaperSimFromPlanError(f"Signals artifact missing required columns: {', '.join(missing)}")
    price_col = "adjusted_close" if "adjusted_close" in signals.columns else "close"
    if price_col not in signals.columns:
        raise PaperSimFromPlanError("Signals artifact must contain adjusted_close or close.")

    signals = signals.copy()
    signals["timestamp"] = pd.to_datetime(signals["timestamp"], errors="coerce")
    signals = signals.sort_values(["timestamp", "symbol"]).reset_index(drop=True)
    candidates: list[TradeCandidate] = []
    ignored_non_long = 0
    skipped_missing_price = 0
    for _, row in signals.iterrows():
        signal = float(row.get("signal", 0.0) or 0.0)
        if signal <= 0:
            ignored_non_long += 1
            continue
        price = pd.to_numeric(pd.Series([row.get(price_col)]), errors="coerce").iloc[0]
        if pd.isna(price) or float(price) <= 0:
            skipped_missing_price += 1
            continue
        symbol = str(row["symbol"]).strip().upper()
        if not symbol:
            skipped_missing_price += 1
            continue
        asset_class = str(row.get("asset_type", "equity") or "equity").lower()
        if asset_class not in {"equity", "etf"}:
            asset_class = "equity"
        quantity = 1.0
        candidates.append(
            TradeCandidate(
                symbol=symbol,
                side="buy",
                quantity=quantity,
                price=float(price),
                asset_class=asset_class,
                strategy_id=strategy_id,
                timestamp=row["timestamp"].isoformat() if not pd.isna(row["timestamp"]) else None,
            )
        )
        if max_candidates is not None and len(candidates) >= max_candidates:
            break

    if ignored_non_long:
        findings.append(
            PaperSimFromPlanFinding(
                code="non_long_signals_ignored",
                severity=PAPER_SIM_INFO,
                message=f"Ignored {ignored_non_long} flat or non-long signal rows.",
            )
        )
    if skipped_missing_price:
        findings.append(
            PaperSimFromPlanFinding(
                code="candidate_rows_skipped_missing_price",
                severity=PAPER_SIM_WARNING,
                message=f"Skipped {skipped_missing_price} long signal rows with missing or invalid prices.",
            )
        )
    if max_candidates is not None and len(candidates) >= max_candidates:
        findings.append(
            PaperSimFromPlanFinding(
                code="max_candidates_reached",
                severity=PAPER_SIM_INFO,
                message=f"Processed max_candidates limit: {max_candidates}.",
            )
        )
    return candidates, findings


def _dry_run_candidates(
    candidates: list[TradeCandidate],
    risk_config: RiskConfig,
    initial_cash: float,
) -> dict[str, Any]:
    risk_manager = RiskManager(risk_config)
    cash = float(initial_cash)
    market_value = 0.0
    open_positions: dict[str, float] = {}
    latest_prices: dict[str, float] = {}
    counts = _base_summary(candidate_count=len(candidates))
    for candidate in candidates:
        latest_prices[candidate.symbol] = candidate.price
        portfolio = PortfolioState(
            equity=cash + market_value,
            cash=cash,
            market_value=market_value,
            open_positions=dict(open_positions),
            trades_today=int(counts["approved_count"]) + int(counts["reduced_count"]),
        )
        decision = risk_manager.evaluate(candidate, portfolio)
        _count_risk_decision(counts, decision.status, decision.approved)
        if decision.approved:
            quantity = decision.final_quantity
            cash -= quantity * candidate.price
            open_positions[candidate.symbol] = open_positions.get(candidate.symbol, 0.0) + quantity
            market_value = sum(
                quantity_value * latest_prices.get(symbol, candidate.price)
                for symbol, quantity_value in open_positions.items()
            )
    counts["dry_run"] = True
    counts["final_cash"] = cash
    counts["final_market_value"] = market_value
    counts["final_equity"] = cash + market_value
    return counts


def _simulate_candidates(
    candidates: list[TradeCandidate],
    output_dir: Path,
    risk_config: RiskConfig,
    initial_cash: float,
    slippage_bps: float,
) -> tuple[dict[str, Any], dict[str, str | None]]:
    ledger = PaperLedger(output_dir)
    broker = SimulationBroker(
        starting_cash=initial_cash,
        risk_manager=RiskManager(risk_config),
        ledger=ledger,
        slippage_bps=slippage_bps,
    )
    for candidate in candidates:
        broker.submit_candidate(candidate)

    ledger.save_account(broker.get_account())
    ledger.save_positions(broker.get_positions())
    orders = ledger.list_orders()
    risk_decisions = ledger.list_risk_decisions()
    summary = _base_summary(candidate_count=len(candidates))
    summary.update(
        {
            "dry_run": False,
            "order_count": len(orders),
            "risk_decision_count": len(risk_decisions),
            "filled_count": sum(1 for order in orders if order.get("status") == ORDER_FILLED),
            "rejected_count": sum(1 for order in orders if order.get("status") == ORDER_REJECTED),
            "approved_count": sum(
                1 for decision in risk_decisions if decision.get("status") == RISK_APPROVED
            ),
            "reduced_count": sum(
                1 for decision in risk_decisions if decision.get("status") == RISK_REDUCED_SIZE
            ),
            "final_account": account_to_dict(broker.get_account()),
        }
    )
    return summary, _ledger_paths(output_dir)


def _risk_config_from_plan(plan: dict[str, Any]) -> RiskConfig:
    max_position_pct = float(plan.get("max_position_pct", 0.05) or 0.05)
    return RiskConfig(max_position_pct=max_position_pct)


def _initial_cash(config: PaperSimFromPlanConfig, plan: dict[str, Any]) -> float:
    if config.initial_cash is not None:
        return float(config.initial_cash)
    return float(plan.get("initial_cash", 100000.0) or 100000.0)


def _base_summary(candidate_count: int) -> dict[str, Any]:
    return {
        "candidate_count": candidate_count,
        "order_count": 0,
        "risk_decision_count": 0,
        "approved_count": 0,
        "reduced_count": 0,
        "rejected_count": 0,
        "filled_count": 0,
        "dry_run": False,
    }


def _count_risk_decision(summary: dict[str, Any], status: str, approved: bool) -> None:
    summary["risk_decision_count"] += 1
    if status == RISK_REDUCED_SIZE:
        summary["reduced_count"] += 1
    elif approved:
        summary["approved_count"] += 1
    else:
        summary["rejected_count"] += 1


def _result(
    run_id: str,
    strategy_id: str,
    status: str,
    simulated_at: str,
    findings: list[PaperSimFromPlanFinding],
    run_dir: Path,
    output_dir: Path,
    manifest_path: Path,
    readiness_path: Path,
    plan_path: Path,
    signals_path: Path | None,
    simulation_manifest_path: Path,
    safety_flags: dict[str, Any],
    summary: dict[str, Any],
    ledger_paths: dict[str, str | None] | None = None,
) -> PaperSimFromPlanResult:
    resolved_ledger_paths = ledger_paths or _empty_ledger_paths()
    return PaperSimFromPlanResult(
        run_id=run_id,
        strategy_id=strategy_id,
        status=status,
        simulated_at=simulated_at,
        findings=findings,
        run_dir=str(run_dir),
        output_dir=str(output_dir),
        manifest_path=str(manifest_path),
        readiness_path=str(readiness_path),
        plan_path=str(plan_path),
        signals_path=str(signals_path) if signals_path is not None else None,
        simulation_manifest_path=str(simulation_manifest_path),
        orders_path=resolved_ledger_paths["orders_path"],
        risk_decisions_path=resolved_ledger_paths["risk_decisions_path"],
        account_path=resolved_ledger_paths["account_path"],
        positions_path=resolved_ledger_paths["positions_path"],
        safety_flags=safety_flags,
        summary=summary,
    )


def _ledger_paths(output_dir: Path) -> dict[str, str | None]:
    return {
        "orders_path": str(output_dir / "orders.jsonl"),
        "risk_decisions_path": str(output_dir / "risk_decisions.jsonl"),
        "account_path": str(output_dir / "account.json"),
        "positions_path": str(output_dir / "positions.json"),
    }


def _empty_ledger_paths() -> dict[str, None]:
    return {
        "orders_path": None,
        "risk_decisions_path": None,
        "account_path": None,
        "positions_path": None,
    }


def _simulation_safety_flags(config: PaperSimFromPlanConfig) -> dict[str, Any]:
    return {
        "local_paper_simulation_only": True,
        "live_trading": False,
        "real_broker_used": False,
        "placed_real_orders": False,
        "external_llm_calls": False,
        "risk_gate_required": config.require_risk_gate,
        "dry_run": config.dry_run,
    }


def _safe_dict(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _has_critical(findings: list[PaperSimFromPlanFinding]) -> bool:
    return any(finding.severity == PAPER_SIM_CRITICAL for finding in findings)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaperSimFromPlanError(f"Could not load JSON artifact: {path}") from exc
    if not isinstance(data, dict):
        raise PaperSimFromPlanError(f"JSON artifact must contain an object: {path}")
    return data
