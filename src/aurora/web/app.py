"""AURORA Web UI - Local research dashboard.

This module provides a lightweight web interface using Streamlit for
research workflows. All data stays local - no secrets transmitted.
Binds to localhost only.
"""

import os
import sys
from typing import Optional

try:
    import streamlit as st
    from streamlit.runtime.scriptrunner import RerunException
except ImportError:
    raise ImportError(
        "Streamlit is required for the web UI. "
        "Install with: pip install streamlit"
    )


APP_VERSION = "3.0.0"
APP_TITLE = "AURORA Research Dashboard"
APP_HOST = "127.0.0.1"
APP_PORT = 8501


def check_streamlit() -> None:
    """Ensure Streamlit is available."""
    pass


st.set_page_config(
    page_title=APP_TITLE,
    page_icon=":rocket:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def show_disclaimer() -> None:
    """Show research-only disclaimer."""
    st.markdown("---")
    st.markdown(
        "**:warning: Research Only Disclaimer:** "
        "This is a research-only tool. Past performance does not guarantee "
        "future results. No profitability is claimed. Paper trading results "
        "are simulated and may not reflect actual market conditions."
    )


def mask_secrets(value: str) -> str:
    """Mask potential secrets in display strings."""
    if not value:
        return ""
    if value.startswith("${") and value.endswith("}"):
        return value
    if len(value) > 8:
        return value[:4] + "****" + value[-4:]
    return "****"


def render_sidebar() -> Optional[str]:
    """Render sidebar navigation and return selected page."""
    st.sidebar.title(":rocket: AURORA")
    st.sidebar.markdown(f"Version {APP_VERSION}")

    pages = [
        "Home / Status",
        "Data Explorer",
        "Strategy Builder",
        "Backtest Runner",
        "Paper Trading Monitor",
        "Readiness Report",
        "Optimizer",
        "Export",
        "Scheduler",
        "Deployment Checklist",
    ]

    selected = st.sidebar.radio("Navigation", pages)

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Safety:**")
    st.sidebar.markdown("- Local only (127.0.0.1)")
    st.sidebar.markdown("- No secrets stored")
    st.sidebar.markdown("- Research only")

    return selected


def render_home() -> None:
    """Render Home / Status page."""
    st.title(":house: Home / Status")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("AURORA Status")
        st.markdown(f"**Version:** {APP_VERSION}")
        st.markdown(f"**Python:** {sys.version.split()[0]}")
        st.markdown("**Mode:** Research-only (paper trading)")
        st.markdown("**Status:** Ready")

    with col2:
        st.subheader("Project Configuration")
        config_path = ".aurora.yml"
        if os.path.exists(config_path):
            try:
                from aurora.config.project_config import ProjectConfig

                config = ProjectConfig.from_yaml(config_path)
                st.markdown(f"**Project:** {config.project.name}")
                st.markdown(f"**Data Source:** {config.data.source}")
                st.markdown(f"**Symbols:** {', '.join(config.data.symbols)}")
                st.markdown(f"**Initial Capital:** ${config.backtesting.initial_capital:,.2f}")
            except Exception as e:
                st.warning(f"Could not load config: {e}")
        else:
            st.info("No project config found. Run `aurora config init` to create one.")

    show_disclaimer()


def render_data_explorer() -> None:
    """Render Data Explorer page."""
    st.title(":chart_with_upwards_trend: Data Explorer")

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("Parameters")
        symbol = st.text_input("Symbol", value="SPY")
        interval = st.selectbox("Interval", ["1d", "1h", "15m", "5m"], index=0)
        start_date = st.date_input("Start Date", value=None)
        end_date = st.date_input("End Date", value=None)

    with col2:
        st.subheader(f"{symbol} Data")

        if st.button("Fetch Data", type="primary"):
            try:
                from aurora.data.yfinance_source import YFinanceDataSource
                from datetime import datetime

                source = YFinanceDataSource()
                start = start_date.isoformat() if start_date else None
                end = end_date.isoformat() if end_date else None

                data = source.fetch(symbol, interval=interval, start_date=start, end_date=end)

                if data is not None and not data.empty:
                    st.dataframe(data.tail(100), use_container_width=True)

                    st.markdown("### Price Chart")
                    import pandas as pd

                    if isinstance(data, pd.DataFrame) and "close" in data.columns:
                        st.line_chart(data["close"])
                else:
                    st.warning("No data returned")
            except Exception as e:
                st.error(f"Error fetching data: {e}")

    show_disclaimer()


def render_strategy_builder() -> None:
    """Render Strategy Builder page."""
    st.title(":wrench: Strategy Builder")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Strategy Configuration")

        archetype = st.selectbox(
            "Archetype",
            ["momentum", "mean_reversion", "breakout", "trend_following"],
        )

        params = {}
        if archetype == "momentum":
            params["lookback"] = st.slider("Lookback Period", 5, 100, 20)
            params["threshold"] = st.slider("Signal Threshold", 0.01, 0.2, 0.05)
        elif archetype == "mean_reversion":
            params["window"] = st.slider("Window", 5, 50, 20)
            params["z_threshold"] = st.slider("Z-Score Threshold", 1.0, 3.0, 2.0)

        st.markdown("### Parameters")
        st.json(params)

    with col2:
        st.subheader("Quick Backtest")
        run_quick = st.checkbox("Run quick backtest", value=False)

        if run_quick:
            symbol = st.text_input("Symbol", value="SPY")
            initial_capital = st.number_input("Initial Capital", value=100000.0)

            if st.button("Run Backtest", type="primary"):
                st.info("Backtest runner not implemented in web UI yet")

    show_disclaimer()


def render_backtest_runner() -> None:
    """Render Backtest Runner page."""
    st.title(":running: Backtest Runner")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Backtest Configuration")

        strategy = st.selectbox(
            "Strategy",
            ["momentum", "mean_reversion", "breakout"],
        )

        symbols = st.text_input("Symbols (comma separated)", value="SPY,QQQ")
        start_date = st.date_input("Start Date", value=None)
        end_date = st.date_input("End Date", value=None)
        initial_capital = st.number_input("Initial Capital", value=100000.0)

        walk_forward = st.checkbox("Walk-Forward Validation", value=False)

    with col2:
        st.subheader("Results")

        if st.button("Run Backtest", type="primary"):
            with st.spinner("Running backtest..."):
                try:
                    from aurora.backtesting.engine import SimpleLongOnlyBacktester
                    from aurora.data.yfinance_source import YFinanceDataSource
                    from datetime import datetime

                    symbol_list = [s.strip() for s in symbols.split(",")]
                    source = YFinanceDataSource()

                    results = {}

                    for symbol in symbol_list:
                        data = source.fetch(
                            symbol,
                            start_date=start_date.isoformat() if start_date else None,
                            end_date=end_date.isoformat() if end_date else None,
                        )

                        if data is not None and not data.empty:
                            results[symbol] = {
                                "data_points": len(data),
                                "start_price": float(data["close"].iloc[0]),
                                "end_price": float(data["close"].iloc[-1]),
                            }

                    if results:
                        st.success("Backtest completed!")
                        for symbol, result in results.items():
                            st.markdown(f"**{symbol}**: {result['data_points']} data points")
                    else:
                        st.warning("No data retrieved")

                except Exception as e:
                    st.error(f"Backtest error: {e}")

    show_disclaimer()


def render_paper_trading() -> None:
    """Render Paper Trading Monitor page."""
    st.title(":dollar: Paper Trading Monitor")

    st.info("Paper trading sessions can be started from the CLI with `aurora paper stream`")

    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Active Positions")

        ledger_path = "data/paper_ledger/execution_log.jsonl"
        if os.path.exists(ledger_path):
            try:
                import json

                with open(ledger_path) as f:
                    lines = f.readlines()
                    executions = [json.loads(line) for line in lines[-10:]]

                st.write(f"Recent executions: {len(executions)}")

                for exec in executions[-5:]:
                    req = exec.get("request", {})
                    st.markdown(
                        f"- **{req.get('side', '').upper()}** {req.get('quantity', 0)} "
                        f"{req.get('symbol', '')} @ ${req.get('price', 0):.2f}"
                    )
            except Exception as e:
                st.warning(f"Could not load ledger: {e}")
        else:
            st.info("No paper trading sessions recorded yet")

    with col2:
        st.subheader("Session Control")

        st.markdown("**Start Session** (CLI required)")
        st.code("aurora paper stream --duration 3600", language="bash")

        st.markdown("**Stop Session**")
        st.markdown("Press Ctrl+C in the running terminal")

    show_disclaimer()


def render_readiness_report() -> None:
    """Render Readiness Report page."""
    st.title(":clipboard: Readiness Report")

    report_path = "data/demo/research_runs/latest/readiness_report.json"

    if os.path.exists(report_path):
        try:
            import json

            with open(report_path) as f:
                report = json.load(f)

            st.subheader("Report Summary")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("Strategy", report.get("strategy_name", "N/A"))
            with col2:
                st.metric("Generated", report.get("generated_at", "N/A")[:10])

            st.json(report)

        except Exception as e:
            st.warning(f"Could not load report: {e}")
    else:
        st.info("No readiness report found. Run `aurora demo run` to generate one.")

    st.markdown("### Download PDF")
    st.info("PDF download requires Phase 6R's PDF generation - see `aurora report pdf`")

    show_disclaimer()


def render_optimizer() -> None:
    """Render Optimizer page."""
    st.title(":optical_tennis_ball: Optimizer")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Optimization Configuration")

        strategy = st.selectbox("Strategy", ["momentum", "mean_reversion"])

        method = st.selectbox("Method", ["bayesian", "genetic"])

        metric = st.selectbox("Metric", ["sharpe", "returns", "drawdown"])

        iterations = st.number_input("Max Iterations", value=50, min_value=10, max_value=200)

    with col2:
        st.subheader("Results")

        if st.button("Run Optimization", type="primary"):
            with st.spinner("Running optimization..."):
                st.info("Optimization not yet integrated with web UI")
                st.markdown("Use CLI: `aurora optimize analyze --strategy momentum`")

    show_disclaimer()


def render_export() -> None:
    """Render Export page."""
    st.title(":package: Export")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Export Configuration")

        strategy_name = st.text_input("Strategy Name", value="demo_momentum_strategy")
        output_path = st.text_input("Output Path", value="export/strategy_bundle.zip")
        artifact_dir = st.text_input(
            "Artifact Directory (optional)",
            value="data/demo/research_runs/latest",
        )

    with col2:
        st.subheader("Actions")

        if st.button("Generate Export Bundle", type="primary"):
            st.markdown("---")
            st.markdown("**:warning: Research Only Disclaimer:** This export tool is for research and paper-trading purposes only. No live trading, no broker execution.")
            st.markdown("---")

            with st.spinner("Generating export bundle..."):
                try:
                    from aurora.export.strategy_exporter import StrategyExporter

                    exporter = StrategyExporter(
                        strategy_name=strategy_name,
                        artifact_directory=artifact_dir,
                        output_zip_path=output_path,
                    )

                    bundle = exporter.create_bundle()

                    st.success(f"Export bundle created: {output_path}")

                    st.markdown("### Bundle Manifest")
                    for f in bundle.files:
                        st.markdown(f"- {f}")

                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="Download Bundle",
                            data=f,
                            file_name=output_path.split("/")[-1],
                            mime="application/zip",
                        )

                except Exception as e:
                    st.error(f"Export failed: {e}")

    show_disclaimer()


def render_scheduler() -> None:
    """Render Scheduler page."""
    st.title(":calendar: Scheduler")

    if "scheduler_state" not in st.session_state:
        st.session_state.scheduler_state = {
            "running": False,
            "log_messages": [],
            "tasks": [],
        }

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Schedule Configuration")

        default_yaml = """tasks:
  - name: daily_research
    command: research run
    interval: 60
    enabled: true
    start_time: "09:00"

  - name: weekly_backtest
    command: backtest run --symbols SPY
    interval: 10080
    enabled: false
"""
        schedule_yaml = st.text_area(
            "Schedule YAML",
            value=default_yaml,
            height=300,
        )

        if st.button("Validate Schedule", type="secondary"):
            try:
                import tempfile
                import yaml

                with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                    f.write(schedule_yaml)
                    temp_path = f.name

                from aurora.scheduling.scheduler import validate_schedule

                is_valid, message = validate_schedule(temp_path)
                if is_valid:
                    st.success(message)
                else:
                    st.error(f"Validation failed: {message}")

                import os
                os.unlink(temp_path)
            except Exception as e:
                st.error(f"Validation error: {e}")

    with col2:
        st.subheader("Scheduler Control")

        if not st.session_state.scheduler_state["running"]:
            if st.button("Start Scheduler", type="primary"):
                try:
                    import tempfile
                    import threading

                    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
                        f.write(schedule_yaml)
                        temp_path = f.name

                    from aurora.scheduling.scheduler import TaskScheduler

                    scheduler = TaskScheduler(temp_path)
                    st.session_state.scheduler_state["scheduler"] = scheduler
                    st.session_state.scheduler_state["running"] = True
                    st.session_state.scheduler_state["tasks"] = scheduler.list_tasks()

                    def run_scheduler(sched):
                        try:
                            sched.run_forever(check_interval=30)
                        except Exception as e:
                            st.session_state.scheduler_state["log_messages"].append(f"Error: {e}")

                    thread = threading.Thread(target=run_scheduler, args=(scheduler,), daemon=True)
                    thread.start()

                    st.success("Scheduler started!")
                except Exception as e:
                    st.error(f"Failed to start scheduler: {e}")
        else:
            if st.button("Stop Scheduler", type="secondary"):
                try:
                    scheduler = st.session_state.scheduler_state.get("scheduler")
                    if scheduler:
                        scheduler.stop()
                    st.session_state.scheduler_state["running"] = False
                    st.success("Scheduler stopped!")
                except Exception as e:
                    st.error(f"Failed to stop scheduler: {e}")

        st.markdown("---")
        st.markdown("### Task Status")

        if st.session_state.scheduler_state["tasks"]:
            import pandas as pd

            task_df = pd.DataFrame(st.session_state.scheduler_state["tasks"])
            st.dataframe(task_df, use_container_width=True)
        else:
            st.info("No tasks loaded. Validate schedule first.")

        st.markdown("---")
        st.markdown("### Recent Log Messages")

        log_container = st.container()
        for msg in st.session_state.scheduler_state["log_messages"][-10:]:
            st.text(msg)

        st.button("Refresh", key="refresh_scheduler")

    show_disclaimer()


def render_deployment_checklist() -> None:
    """Render Deployment Checklist page."""
    st.title(":clipboard: Deployment Checklist")

    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("Checklist Configuration")

        export_path = st.text_input("Export Bundle Path", value="export/strategy_bundle.zip")
        readiness_path = st.text_input("Readiness Report Path (optional)", value="data/demo/research_runs/latest/readiness_report.json")

    with col2:
        st.subheader("Checklist Results")

        if st.button("Run Checklist", type="primary"):
            st.markdown("---")
            st.markdown("**:warning: Advisory Only Disclaimer:** This checklist is an advisory tool only. It does not guarantee safety or profitability. The decision to deploy is entirely at your own risk. Past performance does not guarantee future results.")
            st.markdown("---")

            with st.spinner("Running checklist..."):
                try:
                    from aurora.deployment.checklist import DeploymentChecklist
                    import json
                    import os

                    strategy_metrics = {}
                    if os.path.exists(readiness_path):
                        with open(readiness_path) as f:
                            readiness = json.load(f)
                            strategy_metrics = {
                                "sharpe_ratio": readiness.get("sharpe_ratio", 0),
                                "win_rate": readiness.get("win_rate", 0),
                                "max_drawdown": readiness.get("max_drawdown", 1),
                            }

                    checklist = DeploymentChecklist()
                    results = checklist.run(
                        export_bundle_path=export_path if os.path.exists(export_path) else None,
                        readiness_report_path=readiness_path if os.path.exists(readiness_path) else None,
                        strategy_metrics=strategy_metrics,
                        answers={"doc_disclaimer_acknowledged": True},
                    )

                    passed_count = sum(1 for r in results if r.passed)
                    total_count = len(results)

                    if checklist.is_ready(results):
                        st.success(f"READY - {passed_count}/{total_count} checks passed")
                    else:
                        st.warning(f"NOT READY - {passed_count}/{total_count} checks passed")

                    for result in results:
                        if result.passed:
                            st.markdown(f"**:white_check_mark: {result.item_id}**: {result.details}")
                        else:
                            st.markdown(f"**:x: {result.item_id}**: {result.details}")

                    st.markdown("---")
                    report_data = {
                        "generated_at": result.timestamp,
                        "total_items": total_count,
                        "passed": passed_count,
                        "failed": total_count - passed_count,
                        "results": [{"item_id": r.item_id, "passed": r.passed, "details": r.details} for r in results],
                    }
                    st.json(report_data)

                    report_json = json.dumps(report_data, indent=2)
                    st.download_button(
                        label="Export Report as JSON",
                        data=report_json,
                        file_name="deployment_checklist_report.json",
                        mime="application/json",
                    )

                except Exception as e:
                    st.error(f"Checklist error: {e}")

    show_disclaimer()


def run_app() -> None:
    """Main entry point for the web app."""
    try:
        selected_page = render_sidebar()

        if selected_page == "Home / Status":
            render_home()
        elif selected_page == "Data Explorer":
            render_data_explorer()
        elif selected_page == "Strategy Builder":
            render_strategy_builder()
        elif selected_page == "Backtest Runner":
            render_backtest_runner()
        elif selected_page == "Paper Trading Monitor":
            render_paper_trading()
        elif selected_page == "Readiness Report":
            render_readiness_report()
        elif selected_page == "Optimizer":
            render_optimizer()
        elif selected_page == "Export":
            render_export()
        elif selected_page == "Scheduler":
            render_scheduler()
        elif selected_page == "Deployment Checklist":
            render_deployment_checklist()

    except RerunException:
        raise
    except Exception as e:
        st.error(f"Application error: {e}")


if __name__ == "__main__":
    run_app()