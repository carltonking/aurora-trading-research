"""Local Streamlit dashboard for AURORA research artifacts."""

from dataclasses import asdict
import json
from pathlib import Path
import sys

import pandas as pd
import streamlit as st

SRC_ROOT = Path(__file__).resolve().parents[2]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from aurora.data.normalize import STANDARD_OHLCV_COLUMNS
from aurora.data.quality import validate_ohlcv_quality
from aurora.demo.workflow import DemoWorkflowConfig, DemoWorkflowError, run_demo_workflow
from aurora.execution.ledger import PaperLedger
from aurora.execution.models import account_to_dict, position_to_dict
from aurora.execution.paper_sim_from_plan import (
    PaperSimFromPlanConfig,
    PaperSimFromPlanError,
    run_paper_simulation_from_plan,
)
from aurora.execution.paper_sim_review import (
    PaperSimReviewConfig,
    PaperSimReviewError,
    review_paper_simulation,
)
from aurora.models.registry import list_model_artifacts
from aurora.reporting.charts import (
    drawdown_chart_data,
    equity_curve_chart_data,
    trade_pnl_chart_data,
)
from aurora.reporting.artifact_packet import (
    ArtifactPacketConfig,
    ArtifactPacketError,
    build_artifact_packet,
)
from aurora.reporting.reports import (
    generate_daily_summary_report,
    save_json_report,
    save_markdown_report,
)
from aurora.reporting.safety_audit import (
    SafetyAuditConfig,
    SafetyAuditError,
    run_safety_boundary_audit,
)
from aurora.reporting.status_snapshot import (
    ProjectStatusSnapshotConfig,
    create_project_status_snapshot,
)
from aurora.reporting.summaries import (
    summarize_dataframe,
    summarize_orders,
    summarize_positions,
    summarize_risk_decisions,
)
from aurora.readiness.paper_sim import (
    PaperSimReadinessConfig,
    PaperSimReadinessError,
    evaluate_paper_sim_readiness,
)
from aurora.readiness.paper_sim_plan import (
    PaperSimPlanConfig,
    PaperSimPlanError,
    create_paper_sim_plan,
)
from aurora.research.run import ResearchRunConfig, ResearchRunError, run_research_cycle
from aurora.review.board import ReviewBoardConfig, ReviewBoardError, review_research_run
from aurora.strategies.prompt_lab import (
    explain_prompt_lab_result,
    generate_strategy_config_from_prompt,
    prompt_lab_result_to_dict,
)
from aurora.strategies.registry import list_strategies, save_strategy_config


def _list_csv_files(directory: Path) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(directory.glob("*.csv"))


def _safe_read_csv(path: Path) -> pd.DataFrame | None:
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        st.error(f"Could not read {path}: {exc}")
        return None
    if "timestamp" in df.columns:
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df


def _display_dict(title: str, data: dict) -> None:
    st.write(title)
    if data:
        st.json(data)
    else:
        st.info("No data available.")


def _safe_read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        st.warning(f"Could not read JSON file {path}: {exc}")
        return None


def _parse_symbols(value: str) -> list[str]:
    return [symbol.strip().upper() for symbol in value.split(",") if symbol.strip()]


def _remember_guided_artifact(name: str, path: str | None) -> None:
    if not path:
        return
    artifacts = st.session_state.setdefault("guided_artifact_paths", {})
    artifacts[name] = path


st.set_page_config(page_title="AURORA Trading Research", layout="wide")

st.sidebar.title("AURORA Trading Research")
st.sidebar.caption("Research / local simulation only")
cache_dir = Path(st.sidebar.text_input("Cache directory", "data/cache"))
ledger_dir = Path(st.sidebar.text_input("Ledger directory", "data/ledger"))
models_dir = Path(st.sidebar.text_input("Models directory", "data/models"))
strategies_dir = Path(st.sidebar.text_input("Strategies directory", "data/strategies"))

st.title("AURORA Trading Research")
st.warning("No live trading. No Alpaca connection in this dashboard.")

ledger = PaperLedger(ledger_dir)
account = ledger.load_account()
positions = ledger.load_positions()
orders = ledger.list_orders()
risk_decisions = ledger.list_risk_decisions()

tabs = st.tabs(
    [
        "Overview",
        "Data Health",
        "Models",
        "Strategies",
        "Prompt Lab",
        "Research Runs",
        "Review Board",
        "Paper Sim Readiness",
        "Paper Sim Plan",
        "Backtests",
        "Risk & Ledger",
        "Reports",
        "Guided Workflow",
        "Demo Workflow",
        "Paper Simulation From Plan",
        "Paper Simulation Review",
    ]
)

with tabs[0]:
    st.subheader("Overview")
    st.write(
        "AURORA is a research-first platform for local strategy research, validation, "
        "risk checks, and simulation ledger review."
    )
    if account is not None:
        metrics = account_to_dict(account)
        col1, col2, col3 = st.columns(3)
        col1.metric("Equity", f"{metrics['equity']:,.2f}")
        col2.metric("Cash", f"{metrics['cash']:,.2f}")
        col3.metric("Market Value", f"{metrics['market_value']:,.2f}")
    else:
        st.info("No simulated account found in the selected ledger directory.")

    if positions:
        st.dataframe(pd.DataFrame([position_to_dict(position) for position in positions.values()]))
    else:
        st.info("No simulated positions found.")

with tabs[1]:
    st.subheader("Data Health")
    csv_files = _list_csv_files(cache_dir)
    if not csv_files:
        st.info("No cached CSV files found.")
    else:
        selected = st.selectbox("Cached CSV", csv_files, format_func=lambda path: path.name)
        df = _safe_read_csv(selected)
        if df is not None:
            _display_dict("Data Summary", summarize_dataframe(df))
            if set(STANDARD_OHLCV_COLUMNS).issubset(df.columns):
                quality = validate_ohlcv_quality(df)
                st.write(f"Quality OK: `{quality.ok}`")
                if quality.issues:
                    st.dataframe(pd.DataFrame([asdict(issue) for issue in quality.issues]))
                else:
                    st.success("No OHLCV quality issues found.")
            st.dataframe(df.head(100))

with tabs[2]:
    st.subheader("Models")
    models = list_model_artifacts(models_dir)
    if models:
        st.dataframe(pd.DataFrame(models))
    else:
        st.info("No saved model artifacts found.")

with tabs[3]:
    st.subheader("Strategies")
    strategies = list_strategies(strategies_dir)
    if strategies:
        st.dataframe(pd.DataFrame(strategies))
    else:
        st.info("No registered strategies found.")

with tabs[4]:
    st.subheader("Strategy Prompt Lab")
    st.warning("Prompt Lab creates strategy configs only. It does not trade or place orders.")
    prompt = st.text_area(
        "Strategy idea",
        "Create a conservative 20 and 50 day moving average crossover strategy for SPY and QQQ.",
    )
    strategy_id = st.text_input("Optional strategy_id", "")
    name = st.text_input("Optional name", "")

    if st.button("Generate Strategy Draft"):
        try:
            result = generate_strategy_config_from_prompt(
                prompt,
                strategy_id=strategy_id or None,
                name=name or None,
            )
            st.session_state["prompt_lab_result"] = result
        except Exception as exc:
            st.error(f"Could not generate strategy draft: {exc}")

    result = st.session_state.get("prompt_lab_result")
    if result is not None:
        st.text(explain_prompt_lab_result(result))
        if result.warnings:
            st.warning("\n".join(result.warnings))
        if result.unsupported_requests:
            st.info("Unsupported requests ignored: " + ", ".join(result.unsupported_requests))
        st.json(prompt_lab_result_to_dict(result)["config"])
        if st.button("Save Draft To Strategy Registry"):
            path = save_strategy_config(result.config, base_dir=strategies_dir)
            st.success(f"Saved strategy config to {path}")

with tabs[5]:
    st.subheader("Research Runs")
    st.warning(
        "Research runs generate signals, backtests, diagnostics, and reports only. "
        "They do not trade or place orders."
    )
    registered_strategies = list_strategies(strategies_dir)
    strategy_ids = [
        item["strategy_id"]
        for item in registered_strategies
        if item.get("strategy_id")
    ]
    if strategy_ids:
        research_strategy_id = st.selectbox("strategy_id", strategy_ids)
    else:
        research_strategy_id = st.text_input("strategy_id")
    research_symbols = st.text_input(
        "Optional symbols",
        help="Comma-separated, for example SPY,QQQ",
    )
    research_start = st.text_input("Optional start date", "")
    research_end = st.text_input("Optional end date", "")
    research_data_mode = st.selectbox(
        "Data mode",
        ["cache_only", "download_if_missing"],
        help=(
            "cache_only never downloads data. download_if_missing may use yfinance "
            "for research data if no local cache exists."
        ),
    )
    research_data_dir = st.text_input(
        "Data directory",
        str(cache_dir.parent if cache_dir.name == "cache" else Path("data")),
    )
    research_output_dir = st.text_input("Research run output directory", "data/research_runs")

    if st.button("Run Research Cycle"):
        symbols = [
            symbol.strip().upper()
            for symbol in research_symbols.split(",")
            if symbol.strip()
        ]
        config = ResearchRunConfig(
            strategy_id=research_strategy_id,
            symbols=symbols or None,
            start_date=research_start or None,
            end_date=research_end or None,
            data_mode=research_data_mode,
            data_dir=research_data_dir,
            strategies_dir=str(strategies_dir),
            output_dir=research_output_dir,
        )
        try:
            result = run_research_cycle(config)
            st.session_state["research_run_result"] = result
        except ResearchRunError as exc:
            st.error(f"Research run failed: {exc}")

    research_result = st.session_state.get("research_run_result")
    if research_result is not None:
        st.write(f"Run ID: `{research_result.run_id}`")
        st.write("Artifact paths")
        st.json(
            {
                "output_dir": research_result.output_dir,
                "config_path": research_result.config_path,
                "signals_path": research_result.signals_path,
                "backtest_path": research_result.backtest_path,
                "diagnostics_path": research_result.diagnostics_path,
                "manifest_path": research_result.manifest_path,
                "report_path": research_result.report_path,
            }
        )
        if research_result.manifest_path:
            manifest = _safe_read_json(Path(research_result.manifest_path))
            if manifest:
                st.write("Safety flags")
                st.json(manifest.get("safety_flags", {}))
        st.write("Metrics")
        st.json(research_result.metrics)
        st.write("Diagnostics")
        st.json(research_result.diagnostics)
        if research_result.warnings:
            st.warning("\n".join(research_result.warnings))

with tabs[6]:
    st.subheader("Strategy Candidate Review Board")
    st.warning(
        "Review Board evaluates research artifacts only. "
        "It does not trade, place orders, or approve live trading."
    )
    review_run_dir = st.text_input("Research run directory", "data/research_runs/<run_id>")
    if st.button("Review Research Run"):
        try:
            review_result = review_research_run(ReviewBoardConfig(run_dir=review_run_dir))
            st.session_state["review_board_result"] = review_result
        except ReviewBoardError as exc:
            st.error(f"Review failed: {exc}")

    review_result = st.session_state.get("review_board_result")
    if review_result is not None:
        st.write(f"Status: `{review_result.status}`")
        st.write(f"Review artifact: `{review_result.output_path}`")
        st.write("Safety flags")
        st.json(review_result.safety_flags)
        st.write("Findings")
        if review_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in review_result.findings]))
        else:
            st.success("No review findings.")

with tabs[7]:
    st.subheader("Paper Simulation Readiness")
    st.warning(
        "Paper simulation readiness checks artifacts only. "
        "It does not trade, place orders, or approve live trading."
    )
    readiness_run_dir = st.text_input(
        "Readiness research run directory",
        "data/research_runs/<run_id>",
    )
    if st.button("Evaluate Paper Simulation Readiness"):
        try:
            readiness_result = evaluate_paper_sim_readiness(
                PaperSimReadinessConfig(run_dir=readiness_run_dir)
            )
            st.session_state["paper_sim_readiness_result"] = readiness_result
        except PaperSimReadinessError as exc:
            st.error(f"Readiness evaluation failed: {exc}")

    readiness_result = st.session_state.get("paper_sim_readiness_result")
    if readiness_result is not None:
        st.write(f"Readiness status: `{readiness_result.status}`")
        st.write(f"Review status: `{readiness_result.review_status}`")
        st.write(f"Readiness artifact: `{readiness_result.output_path}`")
        st.write("Safety flags")
        st.json(readiness_result.safety_flags)
        st.write("Metrics")
        st.json(readiness_result.metrics)
        st.write("Findings")
        if readiness_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in readiness_result.findings]))
        else:
            st.success("No readiness findings.")

with tabs[8]:
    st.subheader("Paper Simulation Plan")
    st.warning(
        "Paper simulation planning creates a plan artifact only. "
        "It does not trade, place orders, or approve live trading."
    )
    plan_run_dir = st.text_input(
        "Plan research run directory",
        "data/research_runs/<run_id>",
    )
    if st.button("Create Paper Simulation Plan"):
        try:
            plan_result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=plan_run_dir))
            st.session_state["paper_sim_plan_result"] = plan_result
        except PaperSimPlanError as exc:
            st.error(f"Plan creation failed: {exc}")

    plan_result = st.session_state.get("paper_sim_plan_result")
    if plan_result is not None:
        st.write(f"Plan status: `{plan_result.status}`")
        st.write(f"Readiness status: `{plan_result.readiness_status}`")
        st.write(f"Plan artifact: `{plan_result.output_path}`")
        st.write("Safety flags")
        st.json(plan_result.safety_flags)
        st.write("Plan details")
        st.json(plan_result.plan)
        st.write("Findings")
        if plan_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in plan_result.findings]))
        else:
            st.success("No plan findings.")

with tabs[9]:
    st.subheader("Backtests")
    backtest_files = [
        path
        for path in _list_csv_files(cache_dir)
        if any(token in path.stem.lower() for token in ["equity", "trades", "signal"])
    ]
    if not backtest_files:
        st.info("No backtest-like cached files found.")
    else:
        equity_file = st.selectbox(
            "Equity curve CSV",
            [None, *backtest_files],
            format_func=lambda path: "None" if path is None else path.name,
        )
        trades_file = st.selectbox(
            "Trades CSV",
            [None, *backtest_files],
            format_func=lambda path: "None" if path is None else path.name,
        )

        if equity_file is not None:
            equity_df = _safe_read_csv(equity_file)
            if equity_df is not None and {"timestamp", "equity"}.issubset(equity_df.columns):
                equity_chart = equity_curve_chart_data(equity_df).set_index("timestamp")
                st.line_chart(equity_chart["equity"])
                drawdown_chart = drawdown_chart_data(equity_df).set_index("timestamp")
                st.line_chart(drawdown_chart["drawdown"])
            elif equity_df is not None:
                st.warning("Selected equity file does not contain timestamp and equity columns.")

        if trades_file is not None:
            trades_df = _safe_read_csv(trades_file)
            if trades_df is not None:
                st.dataframe(trades_df)
                pnl_data = trade_pnl_chart_data(trades_df)
                if not pnl_data.empty:
                    st.bar_chart(pnl_data.set_index("trade_id")["net_pnl"])

with tabs[10]:
    st.subheader("Risk & Ledger")
    if account is not None:
        _display_dict("Account", account_to_dict(account))
    else:
        st.info("No simulated account found.")

    _display_dict("Positions Summary", summarize_positions(positions))
    _display_dict("Orders Summary", summarize_orders(orders))
    _display_dict("Risk Decisions Summary", summarize_risk_decisions(risk_decisions))

    if orders:
        st.write("Orders")
        st.dataframe(pd.DataFrame(orders))
    if risk_decisions:
        st.write("Risk Decisions")
        st.dataframe(pd.DataFrame(risk_decisions))

with tabs[11]:
    st.subheader("Reports")
    st.warning(
        "Safety audits are static analysis only. "
        "They do not trade, place orders, call brokers, or approve live trading."
    )
    audit_source_dir = st.text_input("Safety audit source directory", "src/aurora")
    audit_output_dir = st.text_input("Safety audit output directory", "data/status")
    audit_include_tests = st.checkbox("Include tests in safety audit", value=False)
    if st.button("Run Safety Boundary Audit"):
        try:
            audit_result = run_safety_boundary_audit(
                SafetyAuditConfig(
                    source_dir=audit_source_dir,
                    output_dir=audit_output_dir,
                    include_tests=audit_include_tests,
                )
            )
            st.session_state["safety_audit_result"] = audit_result
        except SafetyAuditError as exc:
            st.error(f"Safety audit failed: {exc}")

    audit_result = st.session_state.get("safety_audit_result")
    if audit_result is not None:
        st.write(f"Audit status: `{audit_result.status}`")
        st.write(f"JSON report: `{audit_result.json_path}`")
        st.write(f"Markdown report: `{audit_result.markdown_path}`")
        st.write(f"Files scanned: `{audit_result.files_scanned}`")
        st.write("Safety flags")
        st.json(audit_result.safety_flags)
        st.write("Findings")
        if audit_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in audit_result.findings]))
        else:
            st.success("No safety audit findings.")

    st.warning(
        "Project status snapshots are documentation-only. "
        "They do not trade, place orders, or approve live trading."
    )
    status_output_dir = st.text_input("Status snapshot output directory", "data/status")
    status_latest_count_raw = st.text_input("Latest test count (optional)", "")
    if st.button("Create Project Status Snapshot"):
        try:
            status_latest_count = (
                int(status_latest_count_raw.strip()) if status_latest_count_raw.strip() else None
            )
            status_result = create_project_status_snapshot(
                ProjectStatusSnapshotConfig(
                    output_dir=status_output_dir,
                    latest_test_count=status_latest_count,
                )
            )
            st.session_state["project_status_snapshot_result"] = status_result
        except ValueError:
            st.error("Latest test count must be an integer when provided.")

    status_result = st.session_state.get("project_status_snapshot_result")
    if status_result is not None:
        st.write(f"JSON path: `{status_result.json_path}`")
        st.write(f"Markdown path: `{status_result.markdown_path}`")
        st.write("Capabilities")
        st.json(status_result.capabilities)
        st.write("Safety boundaries")
        st.json(status_result.safety_boundaries)
        st.write("Recent research runs")
        if status_result.recent_research_runs:
            st.dataframe(pd.DataFrame(status_result.recent_research_runs))
        else:
            st.info("No recent research runs found.")

    st.warning(
        "Artifact packets copy local research files only. "
        "They do not trade, place orders, or approve live trading."
    )
    st.caption(
        "When present, paper_simulation/paper_sim_review.json is included as an optional "
        "packet artifact."
    )
    packet_run_dir = st.text_input("Packet research run directory", "data/research_runs/<run_id>")
    packet_copy_artifacts = st.checkbox("Copy artifacts", value=True)
    packet_include_optional = st.checkbox("Include optional artifacts", value=True)
    packet_create_zip = st.checkbox("Create artifact ZIP", value=False)
    packet_zip_path_raw = st.text_input("Optional packet ZIP path", "")
    if st.button("Build Artifact Packet"):
        try:
            packet_zip_path = packet_zip_path_raw.strip() or None
            packet_result = build_artifact_packet(
                ArtifactPacketConfig(
                    run_dir=packet_run_dir,
                    copy_artifacts=packet_copy_artifacts,
                    include_optional_artifacts=packet_include_optional,
                    create_zip=packet_create_zip,
                    zip_path=packet_zip_path,
                )
            )
            st.session_state["artifact_packet_result"] = packet_result
        except ArtifactPacketError as exc:
            st.error(f"Artifact packet build failed: {exc}")

    packet_result = st.session_state.get("artifact_packet_result")
    if packet_result is not None:
        st.write(f"Packet status: `{packet_result.status}`")
        st.write(f"Packet manifest: `{packet_result.packet_manifest_path}`")
        if packet_result.zip_path is not None:
            st.write(f"Packet ZIP: `{packet_result.zip_path}`")
            st.write(f"Packet ZIP sha256: `{packet_result.zip_sha256}`")
            st.write(f"Packet ZIP size bytes: `{packet_result.zip_size_bytes}`")
        st.write("Safety flags")
        st.json(packet_result.safety_flags)
        st.write("Included artifacts")
        st.dataframe(pd.DataFrame(packet_result.included_artifacts))
        st.write("Missing artifacts")
        st.json(packet_result.missing_artifacts)
        st.write("Findings")
        if packet_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in packet_result.findings]))
        else:
            st.success("No packet findings.")

    report_json_path = Path(st.text_input("JSON report path", "data/reports/daily_summary.json"))
    report_md_path = Path(st.text_input("Markdown report path", "data/reports/daily_summary.md"))
    report = generate_daily_summary_report(
        account=account_to_dict(account) if account is not None else None,
        positions={symbol: position_to_dict(position) for symbol, position in positions.items()},
        orders=orders,
        risk_decisions=risk_decisions,
    )

    if st.button("Generate Daily Summary"):
        st.json(report)

    col1, col2 = st.columns(2)
    if col1.button("Save JSON Report"):
        path = save_json_report(report, report_json_path)
        st.success(f"Saved JSON report to {path}")
    if col2.button("Save Markdown Report"):
        path = save_markdown_report("AURORA Daily Summary", report, report_md_path)
        st.success(f"Saved Markdown report to {path}")

with tabs[12]:
    st.subheader("Guided Workflow")
    st.warning(
        "Guided Workflow runs local research and artifact steps only. "
        "It does not trade, place orders, call brokers, or approve live trading."
    )
    st.write(
        "Follow the local artifact pipeline: Strategy Prompt Lab, Research Run, Review Board, "
        "Paper Simulation Readiness, Paper Simulation Plan, Artifact Packet, Project Status "
        "Snapshot, and Safety Boundary Audit."
    )
    st.markdown(
        "1. Strategy Prompt Lab\n"
        "2. Research Run\n"
        "3. Review Board\n"
        "4. Paper Simulation Readiness\n"
        "5. Paper Simulation Plan\n"
        "6. Artifact Packet\n"
        "7. Project Status Snapshot\n"
        "8. Safety Boundary Audit"
    )

    guided_prompt = st.text_area(
        "Guided strategy idea",
        "Create a conservative 20 and 50 day moving average crossover strategy for SPY and QQQ.",
        key="guided_prompt",
    )
    guided_strategy_id = st.text_input(
        "Guided strategy_id",
        st.session_state.get("guided_strategy_id", ""),
        key="guided_strategy_id_input",
    )
    guided_strategy_name = st.text_input(
        "Guided strategy name",
        st.session_state.get("guided_strategy_name", ""),
        key="guided_strategy_name_input",
    )
    guided_symbols = st.text_input(
        "Guided symbols",
        st.session_state.get("guided_symbols", "SPY,QQQ"),
        key="guided_symbols_input",
    )
    col_start, col_end, col_mode = st.columns(3)
    guided_start_date = col_start.text_input("Guided start date", "", key="guided_start_date")
    guided_end_date = col_end.text_input("Guided end date", "", key="guided_end_date")
    guided_data_mode = col_mode.selectbox(
        "Guided data mode",
        ["cache_only", "download_if_missing"],
        index=0,
        help="cache_only never downloads data. download_if_missing may use yfinance.",
        key="guided_data_mode",
    )
    guided_data_dir = st.text_input(
        "Guided data directory",
        str(cache_dir.parent if cache_dir.name == "cache" else Path("data")),
        key="guided_data_dir",
    )
    guided_output_dir = st.text_input(
        "Guided research output directory",
        "data/research_runs",
        key="guided_output_dir",
    )
    guided_run_dir_input = st.text_input(
        "Guided run directory",
        st.session_state.get("guided_run_dir", "data/research_runs/<run_id>"),
        key="guided_run_dir_display",
    )
    guided_run_dir = st.session_state.get("guided_run_dir") or guided_run_dir_input

    st.divider()
    st.write("Step 1: Strategy Prompt Lab")
    if st.button("Guided: Generate Strategy Draft"):
        try:
            prompt_result = generate_strategy_config_from_prompt(
                guided_prompt,
                strategy_id=guided_strategy_id or None,
                name=guided_strategy_name or None,
            )
            st.session_state["guided_prompt_result"] = prompt_result
            st.session_state["guided_strategy_id"] = prompt_result.config.strategy_id
            st.session_state["guided_strategy_name"] = prompt_result.config.name
            symbols = prompt_result.config.universe.get("symbols", [])
            if symbols:
                st.session_state["guided_symbols"] = ",".join(symbols)
        except Exception as exc:
            st.error(f"Could not generate strategy draft: {exc}")

    guided_prompt_result = st.session_state.get("guided_prompt_result")
    if guided_prompt_result is not None:
        st.text(explain_prompt_lab_result(guided_prompt_result))
        if guided_prompt_result.warnings:
            st.warning("\n".join(guided_prompt_result.warnings))
        if guided_prompt_result.unsupported_requests:
            st.info(
                "Unsupported requests ignored: "
                + ", ".join(guided_prompt_result.unsupported_requests)
            )
        st.json(prompt_lab_result_to_dict(guided_prompt_result)["config"])
        if st.button("Guided: Save Strategy Config"):
            path = save_strategy_config(guided_prompt_result.config, base_dir=strategies_dir)
            st.session_state["guided_strategy_id"] = guided_prompt_result.config.strategy_id
            st.success(f"Saved strategy config to {path}")

    st.divider()
    st.write("Step 2: Research Run")
    if st.button("Guided: Run Research Cycle"):
        strategy_id_for_run = guided_strategy_id or st.session_state.get("guided_strategy_id", "")
        try:
            research_result = run_research_cycle(
                ResearchRunConfig(
                    strategy_id=strategy_id_for_run,
                    symbols=_parse_symbols(guided_symbols) or None,
                    start_date=guided_start_date or None,
                    end_date=guided_end_date or None,
                    data_mode=guided_data_mode,
                    data_dir=guided_data_dir,
                    strategies_dir=str(strategies_dir),
                    output_dir=guided_output_dir,
                )
            )
            st.session_state["guided_research_result"] = research_result
            st.session_state["guided_run_dir"] = research_result.output_dir
            _remember_guided_artifact("research_output_dir", research_result.output_dir)
            _remember_guided_artifact("manifest", research_result.manifest_path)
            _remember_guided_artifact("signals", research_result.signals_path)
            _remember_guided_artifact("backtest", research_result.backtest_path)
            _remember_guided_artifact("diagnostics", research_result.diagnostics_path)
            _remember_guided_artifact("report", research_result.report_path)
        except ResearchRunError as exc:
            st.error(f"Research run failed: {exc}")

    guided_research_result = st.session_state.get("guided_research_result")
    if guided_research_result is not None:
        st.write(f"Run ID: `{guided_research_result.run_id}`")
        st.write(f"Output directory: `{guided_research_result.output_dir}`")
        st.write(f"Manifest path: `{guided_research_result.manifest_path}`")
        st.write("Metrics")
        st.json(guided_research_result.metrics)
        st.write("Diagnostics")
        st.json(guided_research_result.diagnostics)
        if guided_research_result.warnings:
            st.warning("\n".join(guided_research_result.warnings))

    st.divider()
    st.write("Step 3: Review Board")
    if st.button("Guided: Run Review Board"):
        try:
            review_result = review_research_run(ReviewBoardConfig(run_dir=guided_run_dir))
            st.session_state["guided_review_result"] = review_result
            _remember_guided_artifact("review", review_result.output_path)
        except ReviewBoardError as exc:
            st.error(f"Review failed: {exc}")

    guided_review_result = st.session_state.get("guided_review_result")
    if guided_review_result is not None:
        st.write(f"Review status: `{guided_review_result.status}`")
        st.write(f"Review artifact: `{guided_review_result.output_path}`")
        st.write("Safety flags")
        st.json(guided_review_result.safety_flags)
        if guided_review_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in guided_review_result.findings]))
        else:
            st.success("No review findings.")

    st.divider()
    st.write("Step 4: Paper Simulation Readiness")
    if st.button("Guided: Evaluate Readiness"):
        try:
            readiness_result = evaluate_paper_sim_readiness(
                PaperSimReadinessConfig(run_dir=guided_run_dir)
            )
            st.session_state["guided_readiness_result"] = readiness_result
            _remember_guided_artifact("paper_sim_readiness", readiness_result.output_path)
        except PaperSimReadinessError as exc:
            st.error(f"Readiness evaluation failed: {exc}")

    guided_readiness_result = st.session_state.get("guided_readiness_result")
    if guided_readiness_result is not None:
        st.write(f"Readiness status: `{guided_readiness_result.status}`")
        st.write(f"Review status: `{guided_readiness_result.review_status}`")
        st.write(f"Readiness artifact: `{guided_readiness_result.output_path}`")
        st.write("Safety flags")
        st.json(guided_readiness_result.safety_flags)
        st.write("Metrics")
        st.json(guided_readiness_result.metrics)
        if guided_readiness_result.findings:
            st.dataframe(
                pd.DataFrame([asdict(finding) for finding in guided_readiness_result.findings])
            )
        else:
            st.success("No readiness findings.")

    st.divider()
    st.write("Step 5: Paper Simulation Plan")
    st.caption("This creates a non-executing plan artifact only. It does not execute simulation.")
    if st.button("Guided: Create Paper Simulation Plan"):
        try:
            plan_result = create_paper_sim_plan(PaperSimPlanConfig(run_dir=guided_run_dir))
            st.session_state["guided_plan_result"] = plan_result
            _remember_guided_artifact("paper_sim_plan", plan_result.output_path)
        except PaperSimPlanError as exc:
            st.error(f"Plan creation failed: {exc}")

    guided_plan_result = st.session_state.get("guided_plan_result")
    if guided_plan_result is not None:
        st.write(f"Plan status: `{guided_plan_result.status}`")
        st.write(f"Readiness status: `{guided_plan_result.readiness_status}`")
        st.write(f"Plan artifact: `{guided_plan_result.output_path}`")
        st.write("Plan summary")
        st.json(guided_plan_result.plan)
        if guided_plan_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in guided_plan_result.findings]))
        else:
            st.success("No plan findings.")

    st.divider()
    st.write("Step 6: Artifact Packet")
    guided_packet_copy = st.checkbox("Guided copy artifacts", value=True)
    guided_packet_zip = st.checkbox("Guided create ZIP", value=False)
    if st.button("Guided: Build Artifact Packet"):
        try:
            packet_result = build_artifact_packet(
                ArtifactPacketConfig(
                    run_dir=guided_run_dir,
                    copy_artifacts=guided_packet_copy,
                    create_zip=guided_packet_zip,
                )
            )
            st.session_state["guided_packet_result"] = packet_result
            _remember_guided_artifact("packet_manifest", packet_result.packet_manifest_path)
            _remember_guided_artifact("packet_zip", packet_result.zip_path)
        except ArtifactPacketError as exc:
            st.error(f"Artifact packet build failed: {exc}")

    guided_packet_result = st.session_state.get("guided_packet_result")
    if guided_packet_result is not None:
        st.write(f"Packet status: `{guided_packet_result.status}`")
        st.write(f"Packet manifest: `{guided_packet_result.packet_manifest_path}`")
        if guided_packet_result.zip_path:
            st.write(f"Packet ZIP: `{guided_packet_result.zip_path}`")
            st.write(f"Packet ZIP sha256: `{guided_packet_result.zip_sha256}`")
            st.write(f"Packet ZIP size bytes: `{guided_packet_result.zip_size_bytes}`")
        st.write("Missing artifacts")
        st.json(guided_packet_result.missing_artifacts)
        if guided_packet_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in guided_packet_result.findings]))
        else:
            st.success("No packet findings.")

    st.divider()
    st.write("Step 7: Project Status Snapshot")
    guided_status_count_raw = st.text_input("Guided latest test count (optional)", "")
    if st.button("Guided: Create Project Status Snapshot"):
        try:
            latest_count = (
                int(guided_status_count_raw.strip()) if guided_status_count_raw.strip() else None
            )
            status_result = create_project_status_snapshot(
                ProjectStatusSnapshotConfig(
                    output_dir="data/status",
                    research_runs_dir=guided_output_dir,
                    latest_test_count=latest_count,
                )
            )
            st.session_state["guided_status_result"] = status_result
            _remember_guided_artifact("project_status_json", status_result.json_path)
            _remember_guided_artifact("project_status_markdown", status_result.markdown_path)
        except ValueError:
            st.error("Latest test count must be an integer when provided.")

    guided_status_result = st.session_state.get("guided_status_result")
    if guided_status_result is not None:
        st.write(f"JSON path: `{guided_status_result.json_path}`")
        st.write(f"Markdown path: `{guided_status_result.markdown_path}`")
        st.write(f"Capabilities count: `{len(guided_status_result.capabilities)}`")
        st.write(f"Recent research run count: `{len(guided_status_result.recent_research_runs)}`")

    st.divider()
    st.write("Step 8: Safety Boundary Audit")
    guided_audit_source = st.text_input("Guided audit source directory", "src/aurora")
    guided_audit_output = st.text_input("Guided audit output directory", "data/status")
    if st.button("Guided: Run Safety Boundary Audit"):
        try:
            audit_result = run_safety_boundary_audit(
                SafetyAuditConfig(
                    source_dir=guided_audit_source,
                    output_dir=guided_audit_output,
                    fail_on_critical=False,
                )
            )
            st.session_state["guided_audit_result"] = audit_result
            _remember_guided_artifact("safety_audit_json", audit_result.json_path)
            _remember_guided_artifact("safety_audit_markdown", audit_result.markdown_path)
        except SafetyAuditError as exc:
            st.error(f"Safety audit failed: {exc}")

    guided_audit_result = st.session_state.get("guided_audit_result")
    if guided_audit_result is not None:
        st.write(f"Audit status: `{guided_audit_result.status}`")
        st.write(f"JSON report: `{guided_audit_result.json_path}`")
        st.write(f"Markdown report: `{guided_audit_result.markdown_path}`")
        st.write(f"Files scanned: `{guided_audit_result.files_scanned}`")
        st.write(f"Findings count: `{len(guided_audit_result.findings)}`")
        if guided_audit_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in guided_audit_result.findings]))
        else:
            st.success("No safety audit findings.")

    if guided_run_dir:
        guided_paper_sim_review_path = Path(guided_run_dir) / "paper_simulation" / (
            "paper_sim_review.json"
        )
        if guided_paper_sim_review_path.exists():
            _remember_guided_artifact("paper_sim_review", str(guided_paper_sim_review_path))

    guided_artifacts = st.session_state.get("guided_artifact_paths", {})
    if guided_artifacts:
        st.divider()
        st.write("Guided artifact path summary")
        st.json(guided_artifacts)

with tabs[13]:
    st.subheader("Demo Workflow")
    st.warning(
        "Demo workflow uses synthetic local data only. It does not trade, place orders, "
        "call brokers, or approve live trading."
    )
    st.write(
        "Run a deterministic local demo that generates synthetic OHLCV data, registers a "
        "safe demo strategy, runs the research artifact workflow in cache-only mode, and "
        "writes review, readiness, plan, packet, status, and optional safety audit artifacts."
    )
    demo_output_root = st.text_input("Demo output root", "data/demo")
    demo_strategy_id = st.text_input("Demo strategy_id", "demo_momentum_strategy")
    demo_symbols_raw = st.text_input("Demo symbols", "SPY,QQQ,DIA")
    demo_rows = st.number_input("Synthetic rows per symbol", min_value=60, value=260, step=10)
    demo_latest_test_count_raw = st.text_input("Demo latest test count (optional)", "")
    demo_create_zip = st.checkbox("Create demo packet ZIP", value=True)
    demo_run_audit = st.checkbox("Run demo safety audit", value=True)

    if st.button("Run Local Demo Workflow"):
        try:
            latest_test_count = (
                int(demo_latest_test_count_raw.strip())
                if demo_latest_test_count_raw.strip()
                else None
            )
            demo_result = run_demo_workflow(
                DemoWorkflowConfig(
                    output_root=demo_output_root,
                    strategy_id=demo_strategy_id,
                    symbols=_parse_symbols(demo_symbols_raw),
                    rows=int(demo_rows),
                    latest_test_count=latest_test_count,
                    create_packet_zip=demo_create_zip,
                    run_safety_audit=demo_run_audit,
                )
            )
            st.session_state["demo_workflow_result"] = demo_result
        except ValueError:
            st.error("Latest test count must be an integer when provided.")
        except DemoWorkflowError as exc:
            st.error(f"Demo workflow failed: {exc}")

    demo_result = st.session_state.get("demo_workflow_result")
    if demo_result is not None:
        st.write("Demo result paths")
        st.json(
            {
                "output_root": demo_result.output_root,
                "strategy_id": demo_result.strategy_id,
                "symbols": demo_result.symbols,
                "research_run_dir": demo_result.research_run_dir,
                "manifest_path": demo_result.manifest_path,
                "review_path": demo_result.review_path,
                "readiness_path": demo_result.readiness_path,
                "plan_path": demo_result.plan_path,
                "packet_manifest_path": demo_result.packet_manifest_path,
                "packet_zip_path": demo_result.packet_zip_path,
                "status_json_path": demo_result.status_json_path,
                "status_markdown_path": demo_result.status_markdown_path,
                "safety_audit_json_path": demo_result.safety_audit_json_path,
                "safety_audit_markdown_path": demo_result.safety_audit_markdown_path,
            }
        )
        st.write("Safety flags")
        st.json(demo_result.safety_flags)
        if demo_result.warnings:
            st.warning("\n".join(demo_result.warnings))
        else:
            st.success("Demo completed without workflow warnings.")

with tabs[14]:
    st.subheader("Paper Simulation From Plan")
    st.warning(
        "Paper simulation from plan uses local simulation only. It does not place real "
        "orders, call brokers, or approve live trading."
    )
    sim_run_dir = st.text_input(
        "Simulation research run directory",
        st.session_state.get("guided_run_dir", "data/research_runs/<run_id>"),
    )
    sim_dry_run = st.checkbox("Dry run only", value=True)
    sim_max_candidates_raw = st.text_input("Max candidates (optional)", "")
    if st.button("Run Local Paper Simulation From Plan"):
        try:
            sim_max_candidates = (
                int(sim_max_candidates_raw.strip())
                if sim_max_candidates_raw.strip()
                else None
            )
            sim_result = run_paper_simulation_from_plan(
                PaperSimFromPlanConfig(
                    run_dir=sim_run_dir,
                    max_candidates=sim_max_candidates,
                    dry_run=sim_dry_run,
                )
            )
            st.session_state["paper_sim_from_plan_result"] = sim_result
        except ValueError:
            st.error("Max candidates must be an integer when provided.")
        except PaperSimFromPlanError as exc:
            st.error(f"Paper simulation from plan failed: {exc}")

    sim_result = st.session_state.get("paper_sim_from_plan_result")
    if sim_result is not None:
        st.write(f"Status: `{sim_result.status}`")
        st.write(f"Output directory: `{sim_result.output_dir}`")
        st.write(f"Simulation manifest: `{sim_result.simulation_manifest_path}`")
        st.write("Local ledger paths")
        st.json(
            {
                "orders_path": sim_result.orders_path,
                "risk_decisions_path": sim_result.risk_decisions_path,
                "account_path": sim_result.account_path,
                "positions_path": sim_result.positions_path,
            }
        )
        st.write("Summary")
        st.json(sim_result.summary)
        st.write("Safety flags")
        st.json(sim_result.safety_flags)
        st.write("Findings")
        if sim_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in sim_result.findings]))
        else:
            st.success("No paper simulation findings.")

with tabs[15]:
    st.subheader("Paper Simulation Review")
    st.warning(
        "Paper simulation review analyzes local simulation artifacts only. It does not "
        "trade, place orders, call brokers, or approve live trading."
    )
    review_sim_run_dir = st.text_input(
        "Paper simulation review run directory",
        st.session_state.get("guided_run_dir", "data/research_runs/<run_id>"),
    )
    review_sim_dir = st.text_input("Optional simulation directory", "")
    if st.button("Review Local Paper Simulation"):
        try:
            review_sim_result = review_paper_simulation(
                PaperSimReviewConfig(
                    run_dir=review_sim_run_dir,
                    simulation_dir=review_sim_dir.strip() or None,
                )
            )
            st.session_state["paper_sim_review_result"] = review_sim_result
        except PaperSimReviewError as exc:
            st.error(f"Paper simulation review failed: {exc}")

    review_sim_result = st.session_state.get("paper_sim_review_result")
    if review_sim_result is not None:
        st.write(f"Status: `{review_sim_result.status}`")
        st.write(f"Output path: `{review_sim_result.output_path}`")
        st.write("Summary")
        st.json(review_sim_result.summary)
        st.write("Safety flags")
        st.json(review_sim_result.safety_flags)
        st.write("Findings")
        if review_sim_result.findings:
            st.dataframe(pd.DataFrame([asdict(finding) for finding in review_sim_result.findings]))
        else:
            st.success("No paper simulation review findings.")
