"""AURORA command-line interface."""

from dataclasses import asdict
from pathlib import Path
from typing import Annotated, Callable

import typer
import yaml
from rich.console import Console
from rich.table import Table

from aurora.backtesting.engine import BacktestConfig, SimpleLongOnlyBacktester
from aurora.backtesting.exceptions import AuroraBacktestError
from aurora.backtesting.metrics import metrics_to_dict
from aurora.core.config import load_yaml_config
from aurora.core.engine import AuroraEngine
from aurora.data.base import MarketDataRequest
from aurora.data.cache import cache_key, load_market_data, save_market_data
from aurora.data.quality import DataQualityReport, validate_ohlcv_quality
from aurora.data.yfinance_source import YFinanceDataSource
from aurora.demo.workflow import DemoWorkflowConfig, DemoWorkflowError, run_demo_workflow
from aurora.execution.ledger import PaperLedger
from aurora.execution.models import ORDER_REJECTED, account_to_dict, order_to_dict, position_to_dict
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
from aurora.execution.simulation_broker import SimulationBroker
from aurora.features.build_features import build_features, get_feature_columns
from aurora.models.exceptions import AuroraModelError, ModelRegistryError, ModelTrainingError
from aurora.models.predict import predict_with_model
from aurora.models.registry import list_model_artifacts, load_model_artifact, save_model_artifact
from aurora.models.train import train_baseline_classifier
from aurora.optimization.adaptive_optimizer import AdaptiveOptimizer
from aurora.analysis.paper_performance import PaperPerformanceAnalyzer, save_metrics
from aurora.analysis.monte_carlo import MonteCarloConfig, MonteCarloSimulator, load_trades_from_backtest
from aurora.analysis.scenario_stress import (
    StressTester,
    load_scenario,
    list_built_in_scenarios,
    BUILT_IN_SCENARIOS,
)
from aurora.analysis.sensitivity import (
    SensitivityAnalyzer,
    load_sensitivity_config,
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
from aurora.risk.exceptions import RiskConfigError, RiskEvaluationError
from aurora.risk.models import PortfolioState, RiskConfig, TradeCandidate, risk_decision_to_dict
from aurora.risk.risk_manager import RiskManager
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
    SAFETY_AUDIT_FAIL,
    SafetyAuditConfig,
    SafetyAuditError,
    run_safety_boundary_audit,
)
from aurora.reporting.status_snapshot import (
    ProjectStatusSnapshotConfig,
    create_project_status_snapshot,
)
from aurora.reporting.readiness_report import ReadinessReportGenerator
from aurora.export.strategy_exporter import StrategyExporter, SecretDetectionError
from aurora.research.run import ResearchRunConfig, ResearchRunError, run_research_cycle
from aurora.review.board import ReviewBoardConfig, ReviewBoardError, review_research_run
from aurora.strategies.config import load_strategy_config
from aurora.strategies.exceptions import (
    SignalGenerationError,
    StrategyConfigError,
    StrategyRegistryError,
)
from aurora.strategies.prompt_lab import (
    explain_prompt_lab_result,
    generate_strategy_config_from_prompt,
)
from aurora.strategies.registry import (
    instantiate_strategy,
    list_strategies as list_strategy_artifacts,
    load_strategy_from_registry,
    save_strategy_config,
)
from aurora.strategies.builder import StrategyBuilder, StrategyBuilderError
from aurora.validation.exceptions import AuroraValidationError
from aurora.validation.overfitting import diagnose_backtest_overfitting
from aurora.validation.report import (
    load_validation_report,
    overfitting_report_to_dict,
    save_validation_report,
    walk_forward_result_to_dict,
)
from aurora.validation.walk_forward import WalkForwardConfig, run_walk_forward_validation

app = typer.Typer(help="AURORA Trading Research CLI")
data_app = typer.Typer(help="Market data commands")
features_app = typer.Typer(help="Feature engineering commands")
models_app = typer.Typer(help="Research model commands")
strategies_app = typer.Typer(help="Research strategy commands")
backtest_app = typer.Typer(help="Research backtesting commands")
validation_app = typer.Typer(help="Research validation commands")
risk_app = typer.Typer(help="Risk management commands")
execution_app = typer.Typer(help="Local execution simulation commands")
reports_app = typer.Typer(help="Local reporting commands")
research_app = typer.Typer(help="Local research run orchestration commands")
review_app = typer.Typer(help="Local strategy candidate review commands")
readiness_app = typer.Typer(help="Local readiness gate commands")
demo_app = typer.Typer(help="Synthetic local demo workflow commands")
paper_app = typer.Typer(help="Paper performance analysis commands")
optimize_app = typer.Typer(help="Adaptive optimizer commands")
export_app = typer.Typer(help="Strategy export bundle commands")
analyze_app = typer.Typer(help="Analysis commands")
app.add_typer(data_app, name="data")
app.add_typer(paper_app, name="paper")
app.add_typer(optimize_app, name="optimize")
app.add_typer(export_app, name="export")
app.add_typer(analyze_app, name="analyze")
app.add_typer(features_app, name="features")
app.add_typer(models_app, name="models")
app.add_typer(strategies_app, name="strategies")
app.add_typer(backtest_app, name="backtest")
app.add_typer(validation_app, name="validation")
app.add_typer(risk_app, name="risk")
app.add_typer(execution_app, name="execution")
app.add_typer(reports_app, name="reports")
app.add_typer(research_app, name="research")
app.add_typer(review_app, name="review")
app.add_typer(readiness_app, name="readiness")
app.add_typer(demo_app, name="demo")
console = Console()


@app.command()
def status() -> None:
    """Show current scaffold engine status."""
    config = load_yaml_config("config/settings.example.yaml")
    engine = AuroraEngine(config)
    payload = engine.status()

    table = Table(title="AURORA Status")
    table.add_column("Field")
    table.add_column("Value")
    for key, value in payload.items():
        table.add_row(key, str(value))
    console.print(table)


@app.command("validate-config")
def validate_config(
    config: Annotated[
        Path,
        typer.Option("--config", "-c", help="Path to a YAML configuration file."),
    ] = Path("config/settings.example.yaml"),
) -> None:
    """Validate that a config can load and passes v1 safety checks."""
    loaded_config = load_yaml_config(config)
    AuroraEngine(loaded_config)
    console.print(f"[green]Config is valid for research scaffold:[/green] {config}")


@app.command()
def dashboard() -> None:
    """Print dashboard launch instructions."""
    console.print("Launch the local AURORA dashboard with:")
    console.print("[bold]streamlit run src/aurora/dashboard/streamlit_app.py[/bold]")


@data_app.command("health")
def data_health() -> None:
    """Check market data source health."""
    source = YFinanceDataSource()
    health = source.health_check()

    table = Table(title="Market Data Source Health")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("source_name", health.source_name)
    table.add_row("ok", str(health.ok))
    table.add_row("message", health.message)
    table.add_row("checked_at", health.checked_at)
    console.print(table)


@data_app.command("download")
def data_download(
    symbols: Annotated[
        str,
        typer.Option("--symbols", help="Comma-separated symbols, for example AAPL,MSFT."),
    ],
    start: Annotated[str, typer.Option("--start", help="Start date, for example 2020-01-01.")],
    end: Annotated[str | None, typer.Option("--end", help="Optional end date.")] = None,
    interval: Annotated[str, typer.Option("--interval", help="Data interval.")] = "1d",
    source: Annotated[str, typer.Option("--source", help="Market data source.")] = "yfinance",
    use_cache: Annotated[
        bool,
        typer.Option("--cache/--no-cache", help="Save downloaded data to the local CSV cache."),
    ] = True,
) -> None:
    """Download normalized market data and run quality checks."""
    parsed_symbols = _parse_symbols(symbols)
    if source != "yfinance":
        console.print(f"[red]Unsupported data source:[/red] {source}. Only yfinance is implemented.")
        raise typer.Exit(1)

    request = MarketDataRequest(symbols=parsed_symbols, start=start, end=end, interval=interval)
    data_source = YFinanceDataSource()
    df = data_source.get_bars(request)
    report = validate_ohlcv_quality(df)
    _print_quality_report(report)

    if use_cache:
        key = cache_key(source, parsed_symbols, start, end, interval)
        path = save_market_data(df, key)
        console.print(f"[green]Cached data:[/green] {path}")
        console.print(f"[green]Cache key:[/green] {key}")

    if not report.ok:
        raise typer.Exit(1)


@data_app.command("quality")
def data_quality(
    cache_key_value: Annotated[
        str,
        typer.Option("--cache-key", help="Cache key produced by aurora data download."),
    ],
) -> None:
    """Validate cached market data quality."""
    df = load_market_data(cache_key_value)
    if df is None:
        console.print(f"[red]Cache key not found:[/red] {cache_key_value}")
        raise typer.Exit(1)

    report = validate_ohlcv_quality(df)
    _print_quality_report(report)
    if not report.ok:
        raise typer.Exit(1)


@features_app.command("build")
def features_build(
    cache_key_value: Annotated[
        str,
        typer.Option("--cache-key", help="Input market data cache key."),
    ],
    output_key: Annotated[
        str | None,
        typer.Option("--output-key", help="Optional output feature cache key."),
    ] = None,
    dropna: Annotated[
        bool,
        typer.Option("--dropna/--keepna", help="Drop rows with NaN feature values."),
    ] = False,
) -> None:
    """Build feature columns from cached normalized OHLCV data."""
    df = load_market_data(cache_key_value)
    if df is None:
        console.print(f"[red]Cache key not found:[/red] {cache_key_value}")
        raise typer.Exit(1)

    feature_df = build_features(df, dropna=dropna)
    feature_columns = get_feature_columns(feature_df)
    resolved_output_key = output_key or f"{cache_key_value}_features"
    output_path = save_market_data(feature_df, resolved_output_key)

    table = Table(title="Feature Build")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("input_rows", str(len(df)))
    table.add_row("output_rows", str(len(feature_df)))
    table.add_row("feature_count", str(len(feature_columns)))
    table.add_row("output_cache_path", str(output_path))
    table.add_row("output_cache_key", resolved_output_key)
    console.print(table)


@models_app.command("train")
def models_train(
    features_key: Annotated[
        str,
        typer.Option("--features-key", help="Feature dataframe cache key."),
    ],
    save: Annotated[
        bool,
        typer.Option("--save/--no-save", help="Save the trained model to the local registry."),
    ] = True,
    models_dir: Annotated[
        str,
        typer.Option("--models-dir", help="Local model registry directory."),
    ] = "data/models",
) -> None:
    """Train the baseline supervised research classifier."""
    feature_df = load_market_data(features_key)
    if feature_df is None:
        console.print(f"[red]Features cache key not found:[/red] {features_key}")
        raise typer.Exit(1)

    try:
        model, result = train_baseline_classifier(feature_df)
        model_path = save_model_artifact(model, result, base_dir=models_dir) if save else None
    except ModelTrainingError as exc:
        console.print(f"[red]Model training failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    table = Table(title="Model Training Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("model_id", result.model_id)
    table.add_row("model_type", result.model_type)
    table.add_row("row_count", str(result.row_count))
    table.add_row("feature_count", str(result.feature_count))
    table.add_row("accuracy", f"{result.metrics['accuracy']:.4f}")
    table.add_row("precision", f"{result.metrics['precision']:.4f}")
    table.add_row("recall", f"{result.metrics['recall']:.4f}")
    table.add_row("f1", f"{result.metrics['f1']:.4f}")
    if model_path is not None:
        table.add_row("model_path", str(model_path))
    console.print(table)


@models_app.command("list")
def models_list(
    models_dir: Annotated[
        str,
        typer.Option("--models-dir", help="Local model registry directory."),
    ] = "data/models",
) -> None:
    """List saved research model artifacts."""
    models = list_model_artifacts(base_dir=models_dir)
    table = Table(title="Saved Models")
    table.add_column("model_id")
    table.add_column("trained_at")
    table.add_column("model_type")
    table.add_column("accuracy")
    table.add_column("f1")
    table.add_column("feature_count")

    for metadata in models:
        metrics = metadata.get("metrics", {})
        table.add_row(
            str(metadata.get("model_id", "")),
            str(metadata.get("trained_at", "")),
            str(metadata.get("model_type", "")),
            _format_metric(metrics.get("accuracy")),
            _format_metric(metrics.get("f1")),
            str(metadata.get("feature_count", "")),
        )
    console.print(table)


@models_app.command("predict")
def models_predict(
    features_key: Annotated[
        str,
        typer.Option("--features-key", help="Feature dataframe cache key."),
    ],
    model_id: Annotated[
        str,
        typer.Option("--model-id", help="Saved model identifier."),
    ],
    output_key: Annotated[
        str | None,
        typer.Option("--output-key", help="Optional output prediction cache key."),
    ] = None,
    models_dir: Annotated[
        str,
        typer.Option("--models-dir", help="Local model registry directory."),
    ] = "data/models",
) -> None:
    """Generate predictions from cached features and a saved model."""
    feature_df = load_market_data(features_key)
    if feature_df is None:
        console.print(f"[red]Features cache key not found:[/red] {features_key}")
        raise typer.Exit(1)

    try:
        model, metadata = load_model_artifact(model_id, base_dir=models_dir)
        prediction_df, result = predict_with_model(model, feature_df, metadata["features"])
    except (AuroraModelError, ModelRegistryError, KeyError) as exc:
        console.print(f"[red]Prediction failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    resolved_output_key = output_key or f"{features_key}_{model_id}_predictions"
    output_path = save_market_data(prediction_df, resolved_output_key)

    table = Table(title="Prediction Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("row_count", str(result.row_count))
    table.add_row("prediction_count", str(result.prediction_count))
    table.add_row("positive_signal_count", str(result.positive_signal_count))
    table.add_row("output_cache_path", str(output_path))
    table.add_row("output_cache_key", resolved_output_key)
    console.print(table)


@strategies_app.command("validate")
def strategies_validate(
    config_path: Annotated[
        str,
        typer.Option("--config-path", help="Path to a strategy YAML config."),
    ],
) -> None:
    """Validate a strategy configuration."""
    try:
        config = load_strategy_config(config_path)
    except StrategyConfigError as exc:
        console.print(f"[red]Strategy config invalid:[/red] {exc}")
        raise typer.Exit(1) from exc
    console.print(f"[green]Strategy config is valid:[/green] {config.strategy_id}")


@strategies_app.command("register")
def strategies_register(
    config_path: Annotated[
        str,
        typer.Option("--config-path", help="Path to a strategy YAML config."),
    ],
    strategies_dir: Annotated[
        str,
        typer.Option("--strategies-dir", help="Local strategy registry directory."),
    ] = "data/strategies",
) -> None:
    """Register a strategy config in the local registry."""
    try:
        config = load_strategy_config(config_path)
        path = save_strategy_config(config, base_dir=strategies_dir)
    except (StrategyConfigError, StrategyRegistryError) as exc:
        console.print(f"[red]Strategy registration failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(f"[green]Registered strategy:[/green] {config.strategy_id}")
    console.print(f"[green]Path:[/green] {path}")


@strategies_app.command("list")
def strategies_list(
    strategies_dir: Annotated[
        str,
        typer.Option("--strategies-dir", help="Local strategy registry directory."),
    ] = "data/strategies",
) -> None:
    """List registered strategy configs."""
    strategies = list_strategy_artifacts(base_dir=strategies_dir)
    table = Table(title="Registered Strategies")
    table.add_column("strategy_id")
    table.add_column("name")
    table.add_column("strategy_type")
    table.add_column("status")
    table.add_column("created_at")
    for metadata in strategies:
        table.add_row(
            str(metadata.get("strategy_id", "")),
            str(metadata.get("name", "")),
            str(metadata.get("strategy_type", "")),
            str(metadata.get("status", "")),
            str(metadata.get("created_at", "")),
        )
    console.print(table)


@strategies_app.command("signal")
def strategies_signal(
    strategy_id: Annotated[
        str,
        typer.Option("--strategy-id", help="Registered strategy identifier."),
    ],
    input_key: Annotated[
        str,
        typer.Option("--input-key", help="Input cache key containing features or predictions."),
    ],
    output_key: Annotated[
        str | None,
        typer.Option("--output-key", help="Optional output signal cache key."),
    ] = None,
    strategies_dir: Annotated[
        str,
        typer.Option("--strategies-dir", help="Local strategy registry directory."),
    ] = "data/strategies",
) -> None:
    """Generate research signals from cached data using a registered strategy."""
    df = load_market_data(input_key)
    if df is None:
        console.print(f"[red]Input cache key not found:[/red] {input_key}")
        raise typer.Exit(1)

    try:
        config = load_strategy_from_registry(strategy_id, base_dir=strategies_dir)
        strategy = instantiate_strategy(config)
        signal_df, result = strategy.generate_signals(df)
    except (StrategyConfigError, StrategyRegistryError, SignalGenerationError) as exc:
        console.print(f"[red]Signal generation failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    resolved_output_key = output_key or f"{input_key}_{strategy_id}_signals"
    output_path = save_market_data(signal_df, resolved_output_key)

    table = Table(title="Strategy Signal Result")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("row_count", str(result.row_count))
    table.add_row("signal_count", str(result.signal_count))
    table.add_row("long_count", str(result.long_count))
    table.add_row("output_cache_path", str(output_path))
    table.add_row("output_cache_key", resolved_output_key)
    console.print(table)


@strategies_app.command("prompt")
def strategies_prompt(
    prompt: Annotated[
        str,
        typer.Option("--prompt", help="Plain-English strategy idea."),
    ],
    strategy_id: Annotated[
        str | None,
        typer.Option("--strategy-id", help="Optional strategy identifier."),
    ] = None,
    name: Annotated[
        str | None,
        typer.Option("--name", help="Optional strategy name."),
    ] = None,
    save: Annotated[
        bool,
        typer.Option("--save/--no-save", help="Save generated config to the local registry."),
    ] = False,
    strategies_dir: Annotated[
        str,
        typer.Option("--strategies-dir", help="Local strategy registry directory."),
    ] = "data/strategies",
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional YAML output path for generated config."),
    ] = None,
) -> None:
    """Generate a validated strategy config draft from a simple prompt."""
    try:
        result = generate_strategy_config_from_prompt(prompt, strategy_id=strategy_id, name=name)
    except (StrategyConfigError, ValueError) as exc:
        console.print(f"[red]Prompt Lab generation failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(explain_prompt_lab_result(result))
    if result.warnings:
        console.print("[yellow]Warnings:[/yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")
    if result.unsupported_requests:
        console.print("[yellow]Unsupported requests ignored:[/yellow]")
        for request in result.unsupported_requests:
            console.print(f"- {request}")

    if output_path is not None:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as file:
            yaml.safe_dump(asdict(result.config), file, sort_keys=False)
        console.print(f"[green]Generated config written:[/green] {path}")

    if save:
        path = save_strategy_config(result.config, base_dir=strategies_dir)
        console.print(f"[green]Generated strategy saved:[/green] {path}")


@strategies_app.command("build")
def strategies_build(
    config: Annotated[
        str,
        typer.Option("--config", "-c", help="Path to JSON or YAML config file."),
    ],
    output_strategy_file: Annotated[
        str | None,
        typer.Option("--output-strategy-file", help="Optional path to write generated Python file."),
    ] = None,
) -> None:
    """Build a strategy from a config file using archetype templates.

    This command is research-only. It parses config files and generates
    strategy instances from archetype templates. No live trading, no broker calls.
    """
    console.print("[cyan]Strategy Builder[/cyan]")

    try:
        builder = StrategyBuilder(config_path=config)
        builder.load_config()
        strategy = builder.build()

        console.print(f"\n[green]Built strategy:[/green] {strategy}")

        params = strategy.get_params()
        table = Table(title="Strategy Parameters")
        table.add_column("Parameter")
        table.add_column("Value")
        for key, value in params.items():
            table.add_row(key, str(value))
        console.print(table)

        if output_strategy_file:
            code = builder.generate_code()
            output_path = Path(output_strategy_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(code)
            console.print(f"\n[green]Generated code written:[/green] {output_path}")

        console.print("\n[yellow]Note:[/yellow] This is a research-only strategy. No profitability is claimed.")

    except StrategyBuilderError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@backtest_app.command("run")
def backtest_run(
    signals_key: Annotated[
        str,
        typer.Option("--signals-key", help="Input signal dataframe cache key."),
    ],
    output_prefix: Annotated[
        str | None,
        typer.Option("--output-prefix", help="Optional output cache key prefix."),
    ] = None,
    starting_cash: Annotated[
        float,
        typer.Option("--starting-cash", help="Starting cash for research simulation."),
    ] = 100000.0,
    position_size_pct: Annotated[
        float,
        typer.Option("--position-size-pct", help="Target position size as percent of equity."),
    ] = 0.05,
    max_position_pct: Annotated[
        float,
        typer.Option("--max-position-pct", help="Maximum position size as percent of equity."),
    ] = 0.10,
    commission: Annotated[
        float,
        typer.Option("--commission", help="Commission per simulated entry or exit."),
    ] = 0.0,
    slippage_bps: Annotated[
        float,
        typer.Option("--slippage-bps", help="Simulated slippage in basis points."),
    ] = 5.0,
    price_col: Annotated[
        str,
        typer.Option("--price-col", help="Price column used for fills and marking."),
    ] = "adjusted_close",
) -> None:
    """Run a research-only long/flat signal backtest."""
    signal_df = load_market_data(signals_key)
    if signal_df is None:
        console.print(f"[red]Signals cache key not found:[/red] {signals_key}")
        raise typer.Exit(1)

    config = BacktestConfig(
        starting_cash=starting_cash,
        position_size_pct=position_size_pct,
        max_position_pct=max_position_pct,
        commission_per_trade=commission,
        slippage_bps=slippage_bps,
        price_col=price_col,
    )
    try:
        result = SimpleLongOnlyBacktester(config).run(signal_df)
    except AuroraBacktestError as exc:
        console.print(f"[red]Backtest failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    prefix = output_prefix or f"{signals_key}_backtest"
    equity_path = save_market_data(result.equity_curve, f"{prefix}_equity")
    trades_path = save_market_data(result.trades, f"{prefix}_trades")
    signals_path = save_market_data(result.signals, f"{prefix}_signals")

    metrics = metrics_to_dict(result.metrics)
    table = Table(title="Backtest Metrics")
    table.add_column("Metric")
    table.add_column("Value")
    for key in [
        "total_return",
        "annualized_return",
        "sharpe_ratio",
        "max_drawdown",
        "win_rate",
        "profit_factor",
        "trade_count",
        "exposure_pct",
        "final_equity",
    ]:
        table.add_row(key, _format_metric_or_none(metrics.get(key)))
    table.add_row("equity_cache_path", str(equity_path))
    table.add_row("trades_cache_path", str(trades_path))
    table.add_row("signals_cache_path", str(signals_path))
    console.print(table)


@validation_app.command("walk-forward")
def validation_walk_forward(
    signals_key: Annotated[
        str,
        typer.Option("--signals-key", help="Input signal dataframe cache key."),
    ],
    n_splits: Annotated[int, typer.Option("--n-splits", help="Number of chronological windows.")] = 4,
    min_test_rows: Annotated[
        int,
        typer.Option("--min-test-rows", help="Minimum rows required per test window."),
    ] = 20,
    min_total_return: Annotated[
        float,
        typer.Option("--min-total-return", help="Minimum total return per window."),
    ] = 0.0,
    max_drawdown_limit: Annotated[
        float,
        typer.Option("--max-drawdown-limit", help="Maximum allowed drawdown floor."),
    ] = -0.25,
    min_trade_count: Annotated[
        int,
        typer.Option("--min-trade-count", help="Minimum trade count per window."),
    ] = 3,
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional JSON report output path."),
    ] = None,
) -> None:
    """Run walk-forward validation on cached research signals."""
    signal_df = load_market_data(signals_key)
    if signal_df is None:
        console.print(f"[red]Signals cache key not found:[/red] {signals_key}")
        raise typer.Exit(1)

    config = WalkForwardConfig(
        n_splits=n_splits,
        min_test_rows=min_test_rows,
        min_total_return=min_total_return,
        max_drawdown_limit=max_drawdown_limit,
        min_trade_count=min_trade_count,
    )
    try:
        result = run_walk_forward_validation(signal_df, config)
    except AuroraValidationError as exc:
        console.print(f"[red]Walk-forward validation failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    _print_walk_forward_result(result)
    if output_path is not None:
        path = save_validation_report(walk_forward_result_to_dict(result), output_path)
        console.print(f"[green]Validation report saved:[/green] {path}")

    if not result.passed:
        raise typer.Exit(1)


@validation_app.command("diagnose-backtest")
def validation_diagnose_backtest(
    metrics_json: Annotated[
        str,
        typer.Option("--metrics-json", help="Path to a JSON file containing backtest metrics."),
    ],
    trades_key: Annotated[
        str | None,
        typer.Option("--trades-key", help="Optional trades cache key."),
    ] = None,
    equity_key: Annotated[
        str | None,
        typer.Option("--equity-key", help="Optional equity curve cache key."),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional JSON report output path."),
    ] = None,
) -> None:
    """Run overfitting diagnostics on a backtest metrics JSON file."""
    metrics = load_validation_report(metrics_json)
    trades = load_market_data(trades_key) if trades_key is not None else None
    equity_curve = load_market_data(equity_key) if equity_key is not None else None
    if trades_key is not None and trades is None:
        console.print(f"[red]Trades cache key not found:[/red] {trades_key}")
        raise typer.Exit(1)
    if equity_key is not None and equity_curve is None:
        console.print(f"[red]Equity cache key not found:[/red] {equity_key}")
        raise typer.Exit(1)

    report = diagnose_backtest_overfitting(metrics, trades=trades, equity_curve=equity_curve)
    _print_overfitting_report(report)
    if output_path is not None:
        path = save_validation_report(overfitting_report_to_dict(report), output_path)
        console.print(f"[green]Diagnostic report saved:[/green] {path}")

    if not report.ok:
        raise typer.Exit(1)


@risk_app.command("check")
def risk_check(
    symbol: Annotated[str, typer.Option("--symbol", help="Candidate symbol.")],
    side: Annotated[str, typer.Option("--side", help="Candidate side: buy or sell.")],
    quantity: Annotated[float, typer.Option("--quantity", help="Candidate quantity.")],
    price: Annotated[float, typer.Option("--price", help="Candidate price.")],
    equity: Annotated[float, typer.Option("--equity", help="Current portfolio equity.")] = 100000.0,
    cash: Annotated[float, typer.Option("--cash", help="Current portfolio cash.")] = 100000.0,
    market_value: Annotated[
        float,
        typer.Option("--market-value", help="Current portfolio market value."),
    ] = 0.0,
    daily_pnl: Annotated[float, typer.Option("--daily-pnl", help="Current daily PnL.")] = 0.0,
    weekly_pnl: Annotated[float, typer.Option("--weekly-pnl", help="Current weekly PnL.")] = 0.0,
    trades_today: Annotated[int, typer.Option("--trades-today", help="Trades placed today.")] = 0,
    asset_class: Annotated[str, typer.Option("--asset-class", help="Candidate asset class.")] = "equity",
    max_position_pct: Annotated[
        float,
        typer.Option("--max-position-pct", help="Maximum per-position exposure."),
    ] = 0.05,
    max_total_exposure_pct: Annotated[
        float,
        typer.Option("--max-total-exposure-pct", help="Maximum total exposure."),
    ] = 0.30,
    max_daily_loss_pct: Annotated[
        float,
        typer.Option("--max-daily-loss-pct", help="Maximum daily loss fraction."),
    ] = 0.02,
    max_weekly_loss_pct: Annotated[
        float,
        typer.Option("--max-weekly-loss-pct", help="Maximum weekly loss fraction."),
    ] = 0.05,
    max_open_positions: Annotated[
        int,
        typer.Option("--max-open-positions", help="Maximum open positions."),
    ] = 5,
    max_trades_per_day: Annotated[
        int,
        typer.Option("--max-trades-per-day", help="Maximum trades per day."),
    ] = 10,
    kill_switch: Annotated[
        bool,
        typer.Option("--kill-switch/--no-kill-switch", help="Enable the risk kill switch."),
    ] = False,
) -> None:
    """Evaluate a trade candidate against hard risk limits."""
    config = RiskConfig(
        max_position_pct=max_position_pct,
        max_total_exposure_pct=max_total_exposure_pct,
        max_daily_loss_pct=max_daily_loss_pct,
        max_weekly_loss_pct=max_weekly_loss_pct,
        max_open_positions=max_open_positions,
        max_trades_per_day=max_trades_per_day,
        kill_switch_enabled=kill_switch,
    )
    portfolio = PortfolioState(
        equity=equity,
        cash=cash,
        market_value=market_value,
        daily_pnl=daily_pnl,
        weekly_pnl=weekly_pnl,
        trades_today=trades_today,
    )
    candidate = TradeCandidate(
        symbol=symbol.upper(),
        side=side.lower(),
        quantity=quantity,
        price=price,
        asset_class=asset_class.lower(),
    )

    try:
        decision = RiskManager(config).evaluate(candidate, portfolio)
    except (RiskConfigError, RiskEvaluationError) as exc:
        console.print(f"[red]Risk check failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    payload = risk_decision_to_dict(decision)
    table = Table(title="Risk Decision")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("status", str(payload["status"]))
    table.add_row("approved", str(payload["approved"]))
    table.add_row("original_quantity", str(payload["original_quantity"]))
    table.add_row("final_quantity", str(payload["final_quantity"]))
    table.add_row("reasons", "; ".join(payload["reasons"]))
    console.print(table)

    if not decision.approved:
        raise typer.Exit(1)


@execution_app.command("simulate")
def execution_simulate(
    symbol: Annotated[str, typer.Option("--symbol", help="Candidate symbol.")],
    side: Annotated[str, typer.Option("--side", help="Candidate side: buy or sell.")],
    quantity: Annotated[float, typer.Option("--quantity", help="Candidate quantity.")],
    price: Annotated[float, typer.Option("--price", help="Candidate price.")],
    starting_cash: Annotated[
        float,
        typer.Option("--starting-cash", help="Starting cash if ledger has no account."),
    ] = 100000.0,
    strategy_id: Annotated[
        str | None,
        typer.Option("--strategy-id", help="Optional strategy identifier."),
    ] = None,
    ledger_dir: Annotated[
        str,
        typer.Option("--ledger-dir", help="Local paper ledger directory."),
    ] = "data/ledger",
    slippage_bps: Annotated[
        float,
        typer.Option("--slippage-bps", help="Simulated fill slippage in basis points."),
    ] = 5.0,
    kill_switch: Annotated[
        bool,
        typer.Option("--kill-switch/--no-kill-switch", help="Enable the risk kill switch."),
    ] = False,
) -> None:
    """Submit one local simulation candidate through the risk gate."""
    risk_manager = RiskManager(RiskConfig(kill_switch_enabled=kill_switch))
    ledger = PaperLedger(ledger_dir)
    broker = SimulationBroker(
        starting_cash=starting_cash,
        risk_manager=risk_manager,
        ledger=ledger,
        slippage_bps=slippage_bps,
    )
    candidate = TradeCandidate(
        symbol=symbol.upper(),
        side=side.lower(),
        quantity=quantity,
        price=price,
        strategy_id=strategy_id,
    )
    try:
        order = broker.submit_candidate(candidate)
    except (RiskConfigError, RiskEvaluationError) as exc:
        console.print(f"[red]Simulation failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    account = broker.get_account()
    order_payload = order_to_dict(order)
    table = Table(title="Simulation Order")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("order_id", str(order_payload["order_id"]))
    table.add_row("status", str(order_payload["status"]))
    table.add_row("symbol", str(order_payload["symbol"]))
    table.add_row("side", str(order_payload["side"]))
    table.add_row("requested_quantity", str(order_payload["requested_quantity"]))
    table.add_row("final_quantity", str(order_payload["quantity"]))
    table.add_row("fill_price", str(order_payload["fill_price"]))
    table.add_row("risk_status", str(order_payload["risk_status"]))
    table.add_row("risk_reasons", "; ".join(order_payload["risk_reasons"]))
    table.add_row("account_cash", f"{account.cash:.4f}")
    table.add_row("account_equity", f"{account.equity:.4f}")
    table.add_row("account_market_value", f"{account.market_value:.4f}")
    console.print(table)

    if order.status == ORDER_REJECTED:
        raise typer.Exit(1)


@execution_app.command("account")
def execution_account(
    ledger_dir: Annotated[
        str,
        typer.Option("--ledger-dir", help="Local paper ledger directory."),
    ] = "data/ledger",
) -> None:
    """Show local simulated account and positions from the ledger."""
    ledger = PaperLedger(ledger_dir)
    account = ledger.load_account()
    positions = ledger.load_positions()
    if account is None:
        console.print("[yellow]No simulated account exists in the ledger yet.[/yellow]")
        return

    account_table = Table(title="Simulated Account")
    account_table.add_column("Field")
    account_table.add_column("Value")
    for key, value in account_to_dict(account).items():
        account_table.add_row(key, str(value))
    console.print(account_table)

    position_table = Table(title="Simulated Positions")
    position_table.add_column("symbol")
    position_table.add_column("quantity")
    position_table.add_column("average_price")
    position_table.add_column("market_price")
    for position in positions.values():
        payload = position_to_dict(position)
        position_table.add_row(
            str(payload["symbol"]),
            str(payload["quantity"]),
            str(payload["average_price"]),
            str(payload["market_price"]),
        )
    console.print(position_table)


@execution_app.command("paper-sim-from-plan")
def execution_paper_sim_from_plan(
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Completed research run directory."),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", help="Optional local simulation output directory."),
    ] = None,
    require_plan_ready: Annotated[
        bool,
        typer.Option(
            "--require-plan-ready/--no-require-plan-ready",
            help="Require paper_sim_plan.json status PLAN_READY.",
        ),
    ] = True,
    require_readiness_ready: Annotated[
        bool,
        typer.Option(
            "--require-readiness-ready/--no-require-readiness-ready",
            help="Require paper_sim_readiness.json status READY_FOR_PAPER_SIMULATION.",
        ),
    ] = True,
    require_risk_gate: Annotated[
        bool,
        typer.Option(
            "--require-risk-gate/--no-require-risk-gate",
            help="Require the plan to specify RiskManager hard-gate use.",
        ),
    ] = True,
    initial_cash: Annotated[
        float | None,
        typer.Option("--initial-cash", help="Optional simulation initial cash override."),
    ] = None,
    max_candidates: Annotated[
        int | None,
        typer.Option("--max-candidates", help="Optional maximum signal candidates to process."),
    ] = None,
    dry_run: Annotated[
        bool,
        typer.Option("--dry-run/--no-dry-run", help="Risk-check candidates without writing ledger files."),
    ] = False,
) -> None:
    """Run local paper simulation from a ready plan artifact."""
    config = PaperSimFromPlanConfig(
        run_dir=run_dir,
        output_dir=output_dir,
        require_plan_ready=require_plan_ready,
        require_readiness_ready=require_readiness_ready,
        require_risk_gate=require_risk_gate,
        initial_cash=initial_cash,
        max_candidates=max_candidates,
        dry_run=dry_run,
    )
    try:
        result = run_paper_simulation_from_plan(config)
    except PaperSimFromPlanError as exc:
        console.print(f"[red]Paper simulation from plan failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Paper simulation from plan uses local simulation only. It does not "
        "place real orders, call brokers, or approve live trading.[/yellow]"
    )
    table = Table(title="Paper Simulation From Plan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("status", result.status)
    table.add_row("output_dir", result.output_dir)
    table.add_row("simulation_manifest_path", result.simulation_manifest_path or "")
    table.add_row("orders_path", result.orders_path or "")
    table.add_row("risk_decisions_path", result.risk_decisions_path or "")
    table.add_row("account_path", result.account_path or "")
    table.add_row("positions_path", result.positions_path or "")
    console.print(table)

    summary = Table(title="Paper Simulation Summary")
    summary.add_column("Field")
    summary.add_column("Value")
    for key, value in result.summary.items():
        summary.add_row(str(key), str(value))
    console.print(summary)

    findings = Table(title="Paper Simulation Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Message")
    for finding in result.findings:
        findings.add_row(finding.severity, finding.code, finding.message)
    console.print(findings)


@execution_app.command("review-paper-sim")
def execution_review_paper_sim(
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Completed research run directory."),
    ],
    simulation_dir: Annotated[
        str | None,
        typer.Option("--simulation-dir", help="Optional paper simulation artifact directory."),
    ] = None,
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional paper simulation review output path."),
    ] = None,
    require_simulation_manifest: Annotated[
        bool,
        typer.Option(
            "--require-simulation-manifest/--no-require-simulation-manifest",
            help="Require simulation_manifest.json.",
        ),
    ] = True,
    require_risk_decisions: Annotated[
        bool,
        typer.Option(
            "--require-risk-decisions/--no-require-risk-decisions",
            help="Require the risk decision JSONL artifact.",
        ),
    ] = True,
    require_orders: Annotated[
        bool,
        typer.Option("--require-orders/--no-require-orders", help="Require the order JSONL artifact."),
    ] = True,
    fail_on_kill_switch: Annotated[
        bool,
        typer.Option(
            "--fail-on-kill-switch/--no-fail-on-kill-switch",
            help="Fail the review if kill-switch decisions are present.",
        ),
    ] = True,
    max_rejected_order_ratio: Annotated[
        float,
        typer.Option("--max-rejected-order-ratio", help="Warn above this rejected order ratio."),
    ] = 0.50,
    max_reduced_order_ratio: Annotated[
        float,
        typer.Option("--max-reduced-order-ratio", help="Warn above this reduced order ratio."),
    ] = 0.50,
) -> None:
    """Review local paper simulation artifacts without executing simulation."""
    config = PaperSimReviewConfig(
        run_dir=run_dir,
        simulation_dir=simulation_dir,
        output_path=output_path,
        require_simulation_manifest=require_simulation_manifest,
        require_risk_decisions=require_risk_decisions,
        require_orders=require_orders,
        fail_on_kill_switch=fail_on_kill_switch,
        max_rejected_order_ratio=max_rejected_order_ratio,
        max_reduced_order_ratio=max_reduced_order_ratio,
    )
    try:
        result = review_paper_simulation(config)
    except PaperSimReviewError as exc:
        console.print(f"[red]Paper simulation review failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Paper simulation review analyzes local simulation artifacts only. "
        "It does not trade, place orders, call brokers, or approve live trading.[/yellow]"
    )
    table = Table(title="Paper Simulation Review")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("status", result.status)
    table.add_row("output_path", result.output_path)
    console.print(table)

    summary = Table(title="Paper Simulation Review Summary")
    summary.add_column("Field")
    summary.add_column("Value")
    for key, value in result.summary.items():
        summary.add_row(str(key), str(value))
    console.print(summary)

    findings = Table(title="Paper Simulation Review Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Message")
    for finding in result.findings:
        findings.add_row(finding.severity, finding.code, finding.message)
    console.print(findings)


@reports_app.command("daily")
def reports_daily(
    ledger_dir: Annotated[
        str,
        typer.Option("--ledger-dir", help="Local paper ledger directory."),
    ] = "data/ledger",
    output_json: Annotated[
        str | None,
        typer.Option("--output-json", help="Optional JSON report output path."),
    ] = None,
    output_md: Annotated[
        str | None,
        typer.Option("--output-md", help="Optional Markdown report output path."),
    ] = None,
) -> None:
    """Generate a local daily summary report from ledger files."""
    ledger = PaperLedger(ledger_dir)
    account = ledger.load_account()
    positions = ledger.load_positions()
    report = generate_daily_summary_report(
        account=account_to_dict(account) if account is not None else None,
        positions={symbol: position_to_dict(position) for symbol, position in positions.items()},
        orders=ledger.list_orders(),
        risk_decisions=ledger.list_risk_decisions(),
    )

    console.print_json(data=report)
    if output_json is not None:
        path = save_json_report(report, output_json)
        console.print(f"[green]JSON report saved:[/green] {path}")
    if output_md is not None:
        path = save_markdown_report("AURORA Daily Summary", report, output_md)
        console.print(f"[green]Markdown report saved:[/green] {path}")


@reports_app.command("packet")
def reports_packet(
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Completed research run directory."),
    ],
    output_dir: Annotated[
        str | None,
        typer.Option("--output-dir", help="Optional artifact packet output directory."),
    ] = None,
    copy_artifacts: Annotated[
        bool,
        typer.Option("--copy-artifacts/--no-copy-artifacts", help="Copy artifacts into packet."),
    ] = True,
    require_manifest: Annotated[
        bool,
        typer.Option("--require-manifest/--no-require-manifest", help="Require manifest.json."),
    ] = True,
    require_core_artifacts: Annotated[
        bool,
        typer.Option(
            "--require-core-artifacts/--no-require-core-artifacts",
            help="Require expected core artifacts.",
        ),
    ] = True,
    include_optional_artifacts: Annotated[
        bool,
        typer.Option(
            "--include-optional-artifacts/--no-include-optional-artifacts",
            help="Include optional research artifacts in packet expectations.",
        ),
    ] = True,
    fail_on_missing_core: Annotated[
        bool,
        typer.Option(
            "--fail-on-missing-core/--no-fail-on-missing-core",
            help="Mark packet blocked when core artifacts are missing.",
        ),
    ] = False,
    create_zip: Annotated[
        bool,
        typer.Option("--create-zip/--no-create-zip", help="Create a local ZIP export."),
    ] = False,
    zip_path: Annotated[
        str | None,
        typer.Option("--zip-path", help="Optional ZIP output path."),
    ] = None,
) -> None:
    """Build an audit packet from local research run artifacts."""
    config = ArtifactPacketConfig(
        run_dir=run_dir,
        output_dir=output_dir,
        copy_artifacts=copy_artifacts,
        require_manifest=require_manifest,
        require_core_artifacts=require_core_artifacts,
        include_optional_artifacts=include_optional_artifacts,
        fail_on_missing_core=fail_on_missing_core,
        create_zip=create_zip,
        zip_path=zip_path,
    )
    try:
        result = build_artifact_packet(config)
    except ArtifactPacketError as exc:
        console.print(f"[red]Artifact packet build failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Artifact packet building only copies local research artifacts. "
        "It does not trade, place orders, or approve live trading.[/yellow]"
    )
    table = Table(title="Research Artifact Packet")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("status", result.status)
    table.add_row("packet_manifest_path", result.packet_manifest_path)
    table.add_row("included_artifacts", str(len(result.included_artifacts)))
    table.add_row("missing_artifacts", str(len(result.missing_artifacts)))
    if result.zip_path is not None:
        table.add_row("zip_path", result.zip_path)
        table.add_row("zip_sha256", str(result.zip_sha256))
        table.add_row("zip_size_bytes", str(result.zip_size_bytes))
    console.print(table)
    console.print(f"Packet manifest: {result.packet_manifest_path}")
    console.print(f"Packet manifest filename: {Path(result.packet_manifest_path).name}")
    if result.zip_path is not None:
        console.print(f"Packet ZIP: {result.zip_path}")
        console.print(f"Packet ZIP sha256: {result.zip_sha256}")
        console.print(f"Packet ZIP size bytes: {result.zip_size_bytes}")

    findings = Table(title="Packet Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Message")
    for finding in result.findings:
        findings.add_row(finding.severity, finding.code, finding.message)
    console.print(findings)


@reports_app.command("status")
def reports_status(
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", help="Project status snapshot output directory."),
    ] = "data/status",
    include_recent_research_runs: Annotated[
        bool,
        typer.Option(
            "--include-recent-research-runs/--no-include-recent-research-runs",
            help="Include recent research run summaries.",
        ),
    ] = True,
    research_runs_dir: Annotated[
        str,
        typer.Option("--research-runs-dir", help="Research runs directory to inspect."),
    ] = "data/research_runs",
    max_recent_runs: Annotated[
        int,
        typer.Option("--max-recent-runs", help="Maximum recent research runs to summarize."),
    ] = 5,
    latest_test_count: Annotated[
        int | None,
        typer.Option("--latest-test-count", help="Optional latest passing test count."),
    ] = None,
) -> None:
    """Create a documentation-only project status snapshot."""
    result = create_project_status_snapshot(
        ProjectStatusSnapshotConfig(
            output_dir=output_dir,
            include_recent_research_runs=include_recent_research_runs,
            research_runs_dir=research_runs_dir,
            max_recent_runs=max_recent_runs,
            latest_test_count=latest_test_count,
        )
    )

    console.print(
        "[yellow]Status snapshot is documentation-only. It does not trade, place orders, "
        "or approve live trading.[/yellow]"
    )
    table = Table(title="Project Status Snapshot")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("json_path", result.json_path)
    table.add_row("markdown_path", result.markdown_path)
    table.add_row("capabilities_count", str(len(result.capabilities)))
    table.add_row("recent_research_run_count", str(len(result.recent_research_runs)))
    console.print(table)
    console.print(f"JSON snapshot: {result.json_path}")
    console.print(f"Markdown snapshot: {result.markdown_path}")


@reports_app.command("safety-audit")
def reports_safety_audit(
    source_dir: Annotated[
        str,
        typer.Option("--source-dir", help="Source directory to scan."),
    ] = "src/aurora",
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", help="Safety audit output directory."),
    ] = "data/status",
    include_tests: Annotated[
        bool,
        typer.Option("--include-tests/--no-include-tests", help="Include tests in scan."),
    ] = False,
    fail_on_critical: Annotated[
        bool,
        typer.Option(
            "--fail-on-critical/--no-fail-on-critical",
            help="Return FAIL when critical findings are present.",
        ),
    ] = True,
    allowlisted_path: Annotated[
        list[str] | None,
        typer.Option(
            "--allowlisted-path",
            help="Repeatable path where critical findings are downgraded to warnings.",
        ),
    ] = None,
) -> None:
    """Run a static safety boundary audit."""
    try:
        result = run_safety_boundary_audit(
            SafetyAuditConfig(
                source_dir=source_dir,
                output_dir=output_dir,
                include_tests=include_tests,
                fail_on_critical=fail_on_critical,
                allowlisted_paths=allowlisted_path,
            )
        )
    except SafetyAuditError as exc:
        console.print(f"[red]Safety audit failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Safety audit is static analysis only. It does not trade, place orders, "
        "call brokers, or approve live trading.[/yellow]"
    )
    table = Table(title="Safety Boundary Audit")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("status", result.status)
    table.add_row("json_path", result.json_path)
    table.add_row("markdown_path", result.markdown_path)
    table.add_row("files_scanned", str(result.files_scanned))
    table.add_row("finding_count", str(len(result.findings)))
    console.print(table)
    console.print(f"Safety audit JSON: {result.json_path}")
    console.print(f"Safety audit Markdown: {result.markdown_path}")

    findings = Table(title="Safety Audit Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Location")
    findings.add_column("Message")
    for finding in result.findings:
        location = finding.file_path
        if finding.line_number is not None:
            location = f"{location}:{finding.line_number}"
        findings.add_row(finding.severity, finding.code, location, finding.message)
    console.print(findings)

    if result.status == SAFETY_AUDIT_FAIL and fail_on_critical:
        raise typer.Exit(1)


@reports_app.command("readiness")
def reports_readiness(
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Strategy name to generate report for."),
    ],
    artifact_dir: Annotated[
        str,
        typer.Option(
            "--artifact-dir",
            help="Directory containing research run artifacts.",
        ),
    ] = "data/demo/research_runs",
    paper_metrics: Annotated[
        str | None,
        typer.Option(
            "--paper-metrics",
            help="Optional path to paper performance metrics JSON file.",
        ),
    ] = "data/paper_analysis/paper_performance.json",
    proposal: Annotated[
        str | None,
        typer.Option(
            "--proposal",
            help="Optional path to optimization proposal JSON file.",
        ),
    ] = "data/optimization/optimization_proposal.json",
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output path for the readiness report JSON.",
        ),
    ] = "data/reports/readiness_report.json",
) -> None:
    """Generate a comprehensive readiness report for a strategy.

    This command is research-only. It aggregates backtest, walk-forward
    diagnostics, paper-trading performance, and optimization proposals.
    No live trading, no broker calls, no profitability claims.
    """
    console.print("[cyan]Readiness Report Generator[/cyan]")

    try:
        generator = ReadinessReportGenerator(
            artifact_directory=artifact_dir,
            strategy_name=strategy,
            paper_metrics_path=paper_metrics,
            proposal_path=proposal,
        )

        readiness_report = generator.generate()
        output_path = generator.save_report(readiness_report, output)

        console.print(f"\n[green]Report saved to:[/green] {output_path}")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@research_app.command("run")
def research_run(
    strategy_id: Annotated[
        str,
        typer.Option("--strategy-id", help="Registered strategy identifier."),
    ],
    symbols: Annotated[
        str | None,
        typer.Option("--symbols", help="Optional comma-separated symbols, for example SPY,QQQ."),
    ] = None,
    start_date: Annotated[
        str | None,
        typer.Option("--start-date", help="Optional market data start date."),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option("--end-date", help="Optional market data end date."),
    ] = None,
    data_mode: Annotated[
        str,
        typer.Option(
            "--data-mode",
            help="cache_only avoids network downloads; download_if_missing may use yfinance.",
        ),
    ] = "cache_only",
    data_dir: Annotated[
        str,
        typer.Option("--data-dir", help="Local data directory."),
    ] = "data",
    strategies_dir: Annotated[
        str,
        typer.Option("--strategies-dir", help="Local strategy registry directory."),
    ] = "data/strategies",
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", help="Research run artifact directory."),
    ] = "data/research_runs",
    initial_cash: Annotated[
        float,
        typer.Option("--initial-cash", help="Initial cash for research backtest."),
    ] = 100000.0,
    commission_bps: Annotated[
        float,
        typer.Option("--commission-bps", help="Commission basis points for run config."),
    ] = 1.0,
    slippage_bps: Annotated[
        float,
        typer.Option("--slippage-bps", help="Slippage basis points for backtest fills."),
    ] = 5.0,
    max_position_pct: Annotated[
        float | None,
        typer.Option("--max-position-pct", help="Optional max position size override."),
    ] = None,
    build_features_flag: Annotated[
        bool,
        typer.Option("--build-features/--no-build-features", help="Build features before signals."),
    ] = True,
    write_report: Annotated[
        bool,
        typer.Option("--write-report/--no-write-report", help="Write a Markdown summary report."),
    ] = True,
) -> None:
    """Run a local research-only strategy cycle."""
    config = ResearchRunConfig(
        strategy_id=strategy_id,
        symbols=_parse_symbols(symbols) if symbols else None,
        start_date=start_date,
        end_date=end_date,
        data_mode=data_mode,
        data_dir=data_dir,
        strategies_dir=strategies_dir,
        output_dir=output_dir,
        initial_cash=initial_cash,
        commission_bps=commission_bps,
        slippage_bps=slippage_bps,
        max_position_pct=max_position_pct,
        build_features=build_features_flag,
        write_report=write_report,
    )
    try:
        result = run_research_cycle(config)
    except ResearchRunError as exc:
        console.print(f"[red]Research run failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Research run completed without placing orders or using a broker.[/yellow]"
    )
    table = Table(title="Research Run")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("symbols", ", ".join(result.symbols))
    table.add_row("output_dir", result.output_dir)
    table.add_row("config_path", result.config_path)
    table.add_row("signals_path", result.signals_path or "")
    table.add_row("backtest_path", result.backtest_path or "")
    table.add_row("diagnostics_path", result.diagnostics_path or "")
    table.add_row("manifest_path", result.manifest_path or "")
    table.add_row("report_path", result.report_path or "")
    console.print(table)

    metrics = Table(title="Research Metrics")
    metrics.add_column("Metric")
    metrics.add_column("Value")
    for key in ["total_return", "max_drawdown", "sharpe_ratio", "trade_count", "final_equity"]:
        if key in result.metrics:
            metrics.add_row(key, str(result.metrics[key]))
    console.print(metrics)

    diagnostics_summary = result.diagnostics.get("summary", {})
    diagnostics = Table(title="Diagnostics Summary")
    diagnostics.add_column("Field")
    diagnostics.add_column("Value")
    diagnostics.add_row("ok", str(result.diagnostics.get("ok")))
    diagnostics.add_row("issue_count", str(len(result.diagnostics.get("issues", []))))
    for key, value in diagnostics_summary.items():
        diagnostics.add_row(str(key), str(value))
    console.print(diagnostics)

    if result.warnings:
        console.print("[yellow]Warnings / diagnostics:[/yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")


@review_app.command("run")
def review_run(
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Completed research run directory."),
    ],
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional output path for review.json."),
    ] = None,
    min_trades: Annotated[
        int,
        typer.Option("--min-trades", help="Minimum acceptable closed trade count."),
    ] = 50,
    max_drawdown_pct: Annotated[
        float,
        typer.Option("--max-drawdown-pct", help="Maximum tolerated drawdown as a decimal."),
    ] = 0.25,
    min_walk_forward_windows: Annotated[
        int,
        typer.Option("--min-walk-forward-windows", help="Minimum walk-forward windows if present."),
    ] = 3,
    require_diagnostics: Annotated[
        bool,
        typer.Option(
            "--require-diagnostics/--no-require-diagnostics",
            help="Require diagnostics.json to be present.",
        ),
    ] = True,
    allow_paper_simulation_approval: Annotated[
        bool,
        typer.Option(
            "--allow-paper-simulation-approval/--no-allow-paper-simulation-approval",
            help="Allow the best possible review status to be paper simulation approval.",
        ),
    ] = True,
) -> None:
    """Review a completed research run without trading or approving live trading."""
    config = ReviewBoardConfig(
        run_dir=run_dir,
        output_path=output_path,
        min_trades=min_trades,
        max_drawdown_pct=max_drawdown_pct,
        min_walk_forward_windows=min_walk_forward_windows,
        require_diagnostics=require_diagnostics,
        allow_paper_simulation_approval=allow_paper_simulation_approval,
    )
    try:
        result = review_research_run(config)
    except ReviewBoardError as exc:
        console.print(f"[red]Review Board failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Review Board does not trade, place orders, or approve live trading.[/yellow]"
    )
    table = Table(title="Strategy Candidate Review")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("status", result.status)
    table.add_row("output_path", result.output_path or "")
    console.print(table)
    console.print(f"Review artifact: {result.output_path}")

    findings = Table(title="Review Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Message")
    for finding in result.findings:
        findings.add_row(finding.severity, finding.code, finding.message)
    console.print(findings)


@readiness_app.command("paper-sim")
def readiness_paper_sim(
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Completed research run directory."),
    ],
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional output path for readiness JSON."),
    ] = None,
    require_review_approval: Annotated[
        bool,
        typer.Option(
            "--require-review-approval/--no-require-review-approval",
            help="Require review status to meet the configured minimum.",
        ),
    ] = True,
    require_research_only_manifest: Annotated[
        bool,
        typer.Option(
            "--require-research-only-manifest/--no-require-research-only-manifest",
            help="Require safe research-only manifest safety flags.",
        ),
    ] = True,
    require_no_critical_review_findings: Annotated[
        bool,
        typer.Option(
            "--require-no-critical-review-findings/--no-require-no-critical-review-findings",
            help="Block when review.json contains critical findings.",
        ),
    ] = True,
    require_no_ledger_writes: Annotated[
        bool,
        typer.Option(
            "--require-no-ledger-writes/--no-require-no-ledger-writes",
            help="Block when ledger artifacts are detected near the run.",
        ),
    ] = True,
    min_trades: Annotated[
        int,
        typer.Option("--min-trades", help="Minimum acceptable closed trade count."),
    ] = 50,
    max_drawdown_pct: Annotated[
        float,
        typer.Option("--max-drawdown-pct", help="Maximum tolerated drawdown as a decimal."),
    ] = 0.25,
) -> None:
    """Evaluate artifact-only readiness for future local paper simulation."""
    config = PaperSimReadinessConfig(
        run_dir=run_dir,
        output_path=output_path,
        require_review_approval=require_review_approval,
        require_research_only_manifest=require_research_only_manifest,
        require_no_critical_review_findings=require_no_critical_review_findings,
        require_no_ledger_writes=require_no_ledger_writes,
        min_trades=min_trades,
        max_drawdown_pct=max_drawdown_pct,
    )
    try:
        result = evaluate_paper_sim_readiness(config)
    except PaperSimReadinessError as exc:
        console.print(f"[red]Paper simulation readiness failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Paper simulation readiness does not trade, place orders, "
        "or approve live trading.[/yellow]"
    )
    table = Table(title="Paper Simulation Readiness")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("review_status", result.review_status or "")
    table.add_row("readiness_status", result.status)
    table.add_row("output_path", result.output_path)
    console.print(table)
    console.print(f"Readiness artifact: {result.output_path}")
    console.print(f"Readiness artifact filename: {Path(result.output_path).name}")

    findings = Table(title="Readiness Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Message")
    for finding in result.findings:
        findings.add_row(finding.severity, finding.code, finding.message)
    console.print(findings)


@readiness_app.command("paper-sim-plan")
def readiness_paper_sim_plan(
    run_dir: Annotated[
        str,
        typer.Option("--run-dir", help="Completed research run directory."),
    ],
    output_path: Annotated[
        str | None,
        typer.Option("--output-path", help="Optional output path for plan JSON."),
    ] = None,
    require_ready_status: Annotated[
        bool,
        typer.Option(
            "--require-ready-status/--no-require-ready-status",
            help="Require readiness status READY_FOR_PAPER_SIMULATION.",
        ),
    ] = True,
    default_initial_cash: Annotated[
        float,
        typer.Option("--default-initial-cash", help="Planned initial cash."),
    ] = 100000.0,
    default_max_position_pct: Annotated[
        float,
        typer.Option("--default-max-position-pct", help="Planned max position size."),
    ] = 0.05,
    default_slippage_bps: Annotated[
        float,
        typer.Option("--default-slippage-bps", help="Planned slippage basis points."),
    ] = 5.0,
    default_commission_bps: Annotated[
        float,
        typer.Option("--default-commission-bps", help="Planned commission basis points."),
    ] = 1.0,
    require_signals_artifact: Annotated[
        bool,
        typer.Option(
            "--require-signals-artifact/--no-require-signals-artifact",
            help="Require signals.csv to exist before creating a ready plan.",
        ),
    ] = True,
    require_risk_gate: Annotated[
        bool,
        typer.Option(
            "--require-risk-gate/--no-require-risk-gate",
            help="Record whether future simulation must use the risk gate.",
        ),
    ] = True,
) -> None:
    """Create a non-executing future paper simulation plan."""
    config = PaperSimPlanConfig(
        run_dir=run_dir,
        output_path=output_path,
        require_ready_status=require_ready_status,
        default_initial_cash=default_initial_cash,
        default_max_position_pct=default_max_position_pct,
        default_slippage_bps=default_slippage_bps,
        default_commission_bps=default_commission_bps,
        require_signals_artifact=require_signals_artifact,
        require_risk_gate=require_risk_gate,
    )
    try:
        result = create_paper_sim_plan(config)
    except PaperSimPlanError as exc:
        console.print(f"[red]Paper simulation planning failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Paper simulation planning does not trade, place orders, "
        "or approve live trading.[/yellow]"
    )
    table = Table(title="Paper Simulation Plan")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("run_id", result.run_id)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("readiness_status", result.readiness_status or "")
    table.add_row("plan_status", result.status)
    table.add_row("output_path", result.output_path)
    console.print(table)
    console.print(f"Plan artifact: {result.output_path}")
    console.print(f"Plan artifact filename: {Path(result.output_path).name}")

    findings = Table(title="Plan Findings")
    findings.add_column("Severity")
    findings.add_column("Code")
    findings.add_column("Message")
    for finding in result.findings:
        findings.add_row(finding.severity, finding.code, finding.message)
    console.print(findings)


@demo_app.command("run")
def demo_run(
    output_root: Annotated[
        str,
        typer.Option("--output-root", help="Demo-specific output root."),
    ] = "data/demo",
    strategy_id: Annotated[
        str,
        typer.Option("--strategy-id", help="Demo strategy identifier."),
    ] = "demo_momentum_strategy",
    symbols: Annotated[
        str | None,
        typer.Option("--symbols", help="Optional comma-separated symbols."),
    ] = None,
    rows: Annotated[
        int,
        typer.Option("--rows", help="Synthetic OHLCV rows per symbol."),
    ] = 260,
    latest_test_count: Annotated[
        int | None,
        typer.Option("--latest-test-count", help="Optional latest passing test count."),
    ] = None,
    create_packet_zip: Annotated[
        bool,
        typer.Option(
            "--create-packet-zip/--no-create-packet-zip",
            help="Create a local artifact packet ZIP.",
        ),
    ] = True,
    run_safety_audit_flag: Annotated[
        bool,
        typer.Option(
            "--run-safety-audit/--no-run-safety-audit",
            help="Run the static safety audit as part of the demo.",
        ),
    ] = True,
) -> None:
    """Run the deterministic synthetic local demo workflow."""
    config = DemoWorkflowConfig(
        output_root=output_root,
        strategy_id=strategy_id,
        symbols=_parse_symbols(symbols) if symbols else None,
        rows=rows,
        latest_test_count=latest_test_count,
        create_packet_zip=create_packet_zip,
        run_safety_audit=run_safety_audit_flag,
    )
    try:
        result = run_demo_workflow(config)
    except DemoWorkflowError as exc:
        console.print(f"[red]Demo workflow failed:[/red] {exc}")
        raise typer.Exit(1) from exc

    console.print(
        "[yellow]Demo workflow uses synthetic local data only. It does not trade, "
        "place orders, call brokers, or approve live trading.[/yellow]"
    )
    table = Table(title="Local Demo Workflow")
    table.add_column("Field")
    table.add_column("Value")
    table.add_row("output_root", result.output_root)
    table.add_row("strategy_id", result.strategy_id)
    table.add_row("symbols", ", ".join(result.symbols))
    table.add_row("research_run_dir", result.research_run_dir)
    table.add_row("manifest_path", result.manifest_path)
    table.add_row("review_path", result.review_path)
    table.add_row("readiness_path", result.readiness_path)
    table.add_row("plan_path", result.plan_path)
    table.add_row("packet_manifest_path", result.packet_manifest_path)
    if result.packet_zip_path is not None:
        table.add_row("packet_zip_path", result.packet_zip_path)
    table.add_row("status_json_path", result.status_json_path)
    table.add_row("status_markdown_path", result.status_markdown_path)
    if result.safety_audit_json_path is not None:
        table.add_row("safety_audit_json_path", result.safety_audit_json_path)
    if result.safety_audit_markdown_path is not None:
        table.add_row("safety_audit_markdown_path", result.safety_audit_markdown_path)
    console.print(table)

    if result.warnings:
        console.print("[yellow]Demo warnings / review notes:[/yellow]")
        for warning in result.warnings:
            console.print(f"- {warning}")


def _parse_symbols(symbols: str) -> list[str]:
    parsed = [symbol.strip().upper() for symbol in symbols.split(",") if symbol.strip()]
    if not parsed:
        console.print("[red]At least one symbol is required.[/red]")
        raise typer.Exit(1)
    return parsed


def _print_quality_report(report: DataQualityReport) -> None:
    summary = Table(title="Data Quality Report")
    summary.add_column("Metric")
    summary.add_column("Value")
    summary.add_row("ok", str(report.ok))
    summary.add_row("row_count", str(report.row_count))
    summary.add_row("symbol_count", str(report.symbol_count))
    summary.add_row("issue_count", str(len(report.issues)))
    console.print(summary)

    if not report.issues:
        return

    issues = Table(title="Data Quality Issues")
    issues.add_column("Severity")
    issues.add_column("Code")
    issues.add_column("Symbol")
    issues.add_column("Message")
    for issue in report.issues:
        issues.add_row(issue.severity, issue.code, issue.symbol or "", issue.message)
    console.print(issues)


def _format_metric(value: object) -> str:
    if isinstance(value, int | float):
        return f"{value:.4f}"
    return ""


def _format_metric_or_none(value: object) -> str:
    if value is None:
        return "None"
    return _format_metric(value)


def _print_walk_forward_result(result) -> None:
    summary = result.summary
    table = Table(title="Walk-Forward Validation")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("passed", str(result.passed))
    table.add_row("window_count", str(summary["window_count"]))
    table.add_row("passed_window_count", str(summary["passed_window_count"]))
    table.add_row("failed_window_count", str(summary["failed_window_count"]))
    table.add_row("average_total_return", _format_metric_or_none(summary["average_total_return"]))
    table.add_row("average_max_drawdown", _format_metric_or_none(summary["average_max_drawdown"]))
    table.add_row("total_trade_count", str(summary["total_trade_count"]))
    console.print(table)

    windows = Table(title="Walk-Forward Windows")
    windows.add_column("window_id")
    windows.add_column("passed")
    windows.add_column("total_return")
    windows.add_column("max_drawdown")
    windows.add_column("trade_count")
    windows.add_column("issues")
    for window_result in result.windows:
        metrics = window_result.metrics
        windows.add_row(
            window_result.window.window_id,
            str(window_result.passed),
            _format_metric_or_none(metrics.get("total_return")),
            _format_metric_or_none(metrics.get("max_drawdown")),
            str(metrics.get("trade_count", "")),
            "; ".join(window_result.issues),
        )
    console.print(windows)


def _print_overfitting_report(report) -> None:
    table = Table(title="Overfitting Diagnostics")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("ok", str(report.ok))
    table.add_row("issue_count", str(len(report.issues)))
    console.print(table)

    if not report.issues:
        return

    issues = Table(title="Diagnostic Issues")
    issues.add_column("Severity")
    issues.add_column("Code")
    issues.add_column("Message")
    for issue in report.issues:
        issues.add_row(issue.severity, issue.code, issue.message)
    console.print(issues)


@paper_app.command("performance")
def paper_performance(
    strategy: Annotated[
        str | None,
        typer.Option("--strategy", help="Strategy name to analyze. If not provided, analyzes all strategies."),
    ] = None,
    ledger_path: Annotated[
        str,
        typer.Option("--ledger-path", help="Path to paper execution ledger."),
    ] = "data/paper_ledger/execution_log.jsonl",
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", help="Output directory for metrics."),
    ] = "data/paper_analysis",
) -> None:
    """Analyze paper trading performance metrics.

    This command is research-only. It analyzes the paper execution ledger
    to compute performance metrics. No live trading, no broker calls.
    """
    console.print("[cyan]Paper Performance Analyzer[/cyan]")

    analyzer = PaperPerformanceAnalyzer(ledger_path=ledger_path)
    metrics = analyzer.compute_metrics(strategy_name=strategy)

    output_path = save_metrics(metrics, output_dir)
    console.print(f"\n[green]Metrics saved to:[/green] {output_path}")

    table = Table(title="Paper Performance Metrics")
    table.add_column("Metric")
    table.add_column("Value")

    table.add_row("Strategy", metrics.strategy_name)
    table.add_row("Total Trades", str(metrics.total_trades))
    table.add_row("Win Count", str(metrics.win_count))
    table.add_row("Loss Count", str(metrics.loss_count))
    table.add_row("Win Rate", f"{metrics.win_rate:.2%}")
    table.add_row("Total P&L", f"${metrics.total_pnl:.2f}")
    table.add_row("Avg P&L/Trade", f"${metrics.avg_pnl_per_trade:.2f}")
    table.add_row("Max Drawdown", f"${metrics.max_drawdown:.2f}")
    table.add_row("Sharpe Ratio", f"{metrics.sharpe_ratio:.3f}")
    table.add_row("Profit Factor", f"{metrics.profit_factor:.3f}")

    console.print(table)

    console.print("\n[yellow]Disclaimer:[/yellow] Past paper performance does not guarantee future results.")


@optimize_app.command("analyze")
def optimize_analyze(
    strategy: Annotated[
        str,
        typer.Argument(help="Strategy name to analyze."),
    ],
    artifact_directory: Annotated[
        str,
        typer.Option(
            "--artifact-directory",
            help="Directory containing research artifacts.",
        ),
    ] = "data/research",
    paper_metrics: Annotated[
        str | None,
        typer.Option(
            "--paper-metrics",
            help="Path to paper performance metrics JSON file.",
        ),
    ] = "data/paper_analysis/paper_performance.json",
    output_dir: Annotated[
        str,
        typer.Option(
            "--output-dir",
            help="Output directory for optimization proposal.",
        ),
    ] = "data/optimization",
) -> None:
    """Analyze strategy and produce an optimization proposal.

    This command is research-only. It reads research artifacts and optionally
    paper trading performance to propose parameter adjustments. No live trading,
    no broker calls, no profitability claims.
    """
    console.print("[cyan]Adaptive Optimizer[/cyan]")

    optimizer = AdaptiveOptimizer(
        artifact_directory=artifact_directory,
        paper_metrics_path=paper_metrics,
    )

    try:
        proposal = optimizer.analyze(strategy)

        output_path = optimizer.write_proposal(proposal, output_dir)
        console.print(f"\n[green]Proposal saved to:[/green] {output_path}")

        table = Table(title=f"Optimization Proposal: {strategy}")
        table.add_column("Field")
        table.add_column("Value")

        table.add_row("Status", proposal.status)
        table.add_row("Rationale", proposal.rationale[:100] + "..." if len(proposal.rationale) > 100 else proposal.rationale)

        console.print(table)

        if proposal.parameter_changes:
            changes_table = Table(title="Proposed Parameter Changes")
            changes_table.add_column("Parameter")
            changes_table.add_column("Change")
            for param, change in proposal.parameter_changes.items():
                changes_table.add_row(param, change)
            console.print(changes_table)

        console.print("\n[yellow]Disclaimer:[/yellow] This is research-only proposal. No profitability is claimed.")

    except FileNotFoundError as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@export_app.command("strategy")
def export_strategy(
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Strategy name to export."),
    ],
    artifact_dir: Annotated[
        str,
        typer.Option(
            "--artifact-dir",
            help="Directory containing research artifacts.",
        ),
    ] = "data/demo/research_runs",
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output path for the export bundle zip file.",
        ),
    ] = "data/exports/strategy_bundle.zip",
    strategy_file: Annotated[
        str | None,
        typer.Option(
            "--strategy-file",
            help="Optional path to strategy Python file.",
        ),
    ] = None,
    model_file: Annotated[
        str | None,
        typer.Option(
            "--model-file",
            help="Optional path to serialized model file.",
        ),
    ] = None,
    feature_config: Annotated[
        str | None,
        typer.Option(
            "--feature-config",
            help="Optional path to feature configuration JSON.",
        ),
    ] = None,
    readiness_report: Annotated[
        str | None,
        typer.Option(
            "--readiness-report",
            help="Optional path to readiness report JSON.",
        ),
    ] = None,
) -> None:
    """Export a strategy bundle for external deployment.

    This command is research-only. It packages strategy code, configuration,
    and readiness report into a zip file. No live trading, no broker calls.
    """
    console.print("[cyan]Strategy Exporter[/cyan]")

    try:
        exporter = StrategyExporter(
            strategy_name=strategy,
            artifact_directory=artifact_dir,
            output_zip_path=output,
            strategy_file_path=strategy_file,
            model_path=model_file,
            feature_config_path=feature_config,
            readiness_report_path=readiness_report,
        )

        bundle = exporter.create_bundle()

        console.print(f"\n[green]Export bundle created:[/green] {output}")

        table = Table(title=f"Bundle Contents: {bundle.strategy_name}")
        table.add_column("File")
        table.add_column("Description")
        for file_info in bundle.manifest.get("files", []):
            table.add_row(file_info["path"], file_info["description"])
        console.print(table)

        console.print(f"\n[yellow]Disclaimer:[/yellow] {bundle.disclaimer}")

        if exporter.verify_bundle():
            console.print("\n[green]Bundle verification: PASSED[/green]")
        else:
            console.print("\n[yellow]Bundle verification: FAILED (bundle may still be usable)[/yellow]")

    except SecretDetectionError as e:
        console.print(f"[red]Secret detected:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@analyze_app.command("monte-carlo")
def analyze_monte_carlo(
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Strategy name."),
    ],
    backtest_file: Annotated[
        str,
        typer.Option(
            "--backtest-file",
            help="Path to backtest JSON file.",
        ),
    ],
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output path for Monte Carlo results.",
        ),
    ] = "data/analysis/monte_carlo_result.json",
    simulations: Annotated[
        int,
        typer.Option(
            "--simulations",
            help="Number of Monte Carlo simulations.",
        ),
    ] = 1000,
    seed: Annotated[
        int | None,
        typer.Option(
            "--seed",
            help="Random seed for reproducibility.",
        ),
    ] = None,
) -> None:
    """Run Monte Carlo simulation on backtest results.

    This command is research-only. It generates distributions of possible
    strategy outcomes by resampling trade sequences. No live trading, no broker calls.
    """
    console.print("[cyan]Monte Carlo Simulation[/cyan]")

    try:
        config = MonteCarloConfig(
            num_simulations=simulations,
            method="trade_reshuffle",
            random_seed=seed,
        )

        console.print(f"Loading trades from: {backtest_file}")
        trades = load_trades_from_backtest(backtest_file)

        if not trades:
            console.print("[red]No trades found in backtest file.[/red]")
            raise typer.Exit(code=1)

        console.print(f"Loaded {len(trades)} trades")

        simulator = MonteCarloSimulator(config)
        console.print(f"Running {simulations} simulations...")

        result = simulator.run(trades, strategy_name=strategy)

        output_path = simulator.save_result(result, output)
        console.print(f"\n[green]Results saved to:[/green] {output_path}")

        table = Table(title=f"Monte Carlo Results: {strategy}")
        table.add_column("Metric")
        table.add_column("Mean")
        table.add_column("Median")
        table.add_column("Std")
        table.add_column("5th Percentile")
        table.add_column("95th Percentile")

        for metric, stats in result.summary_stats.items():
            table.add_row(
                metric,
                f"{stats['mean']:.4f}",
                f"{stats['median']:.4f}",
                f"{stats['std']:.4f}",
                f"{stats['p5']:.4f}",
                f"{stats['p95']:.4f}",
            )

        console.print(table)

        console.print("\n[yellow]Disclaimer:[/yellow] This is research-only simulation. Past performance does not guarantee future results.")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@analyze_app.command("stress-test")
def analyze_stress_test(
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Strategy name."),
    ],
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Symbol to test (e.g., SPY)."),
    ],
    start_date: Annotated[
        str,
        typer.Option("--start", help="Start date (YYYY-MM-DD)."),
    ],
    end_date: Annotated[
        str,
        typer.Option("--end", help="End date (YYYY-MM-DD)."),
    ],
    scenario: Annotated[
        str | None,
        typer.Option(
            "--scenario",
            help="Scenario name (e.g., 2008_financial_crisis) or path to JSON file.",
        ),
    ] = None,
    all_scenarios: Annotated[
        bool,
        typer.Option(
            "--all-scenarios",
            help="Run all built-in scenarios.",
        ),
    ] = False,
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output path for stress test results.",
        ),
    ] = "data/analysis/stress_test_result.json",
) -> None:
    """Run stress test on strategy under adverse market scenarios.

    This command is research-only. It applies scenario shocks to market
    data and evaluates strategy performance. No live trading, no broker calls.
    """
    console.print("[cyan]Stress Test Analysis[/cyan]")

    try:
        from aurora.data.yfinance_source import YFinanceDataSource

        console.print(f"Fetching data for {symbol} from {start_date} to {end_date}...")
        data_source = YFinanceDataSource()
        data = data_source.fetch(
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
        )

        if data.empty:
            console.print(f"[red]No data fetched for {symbol}.[/red]")
            raise typer.Exit(code=1)

        console.print(f"Loaded {len(data)} rows of data")

        def simple_strategy(df: pd.DataFrame) -> pd.Series:
            """Simple moving average crossover strategy."""
            signals = pd.Series(0, index=df.index, dtype=int)
            if "close" in df.columns:
                ma_fast = df["close"].rolling(window=5).mean()
                ma_slow = df["close"].rolling(window=20).mean()
                signals[df["close"] > ma_slow] = 1
            return signals

        import pandas as pd

        tester = StressTester(strategy_fn=simple_strategy)

        if all_scenarios:
            console.print("Running all built-in scenarios...")
            results = tester.run_all_scenarios(data)

            output_path = tester.save_results(results, output)
            console.print(f"\n[green]Results saved to:[/green] {output_path}")

            table = Table(title=f"Stress Test Results: {strategy}")
            table.add_column("Scenario")
            table.add_column("Original Return")
            table.add_column("Stressed Return")
            table.add_column("Original DD")
            table.add_column("Stressed DD")
            table.add_column("Original Sharpe")
            table.add_column("Stressed Sharpe")

            for result in results:
                table.add_row(
                    result.scenario_name,
                    f"{result.original_metrics.get('total_return', 0):.2f}",
                    f"{result.stressed_metrics.get('total_return', 0):.2f}",
                    f"{result.original_metrics.get('max_drawdown', 0):.2%}",
                    f"{result.stressed_metrics.get('max_drawdown', 0):.2%}",
                    f"{result.original_metrics.get('sharpe_ratio', 0):.2f}",
                    f"{result.stressed_metrics.get('sharpe_ratio', 0):.2f}",
                )

            console.print(table)

        elif scenario:
            if Path(scenario).exists():
                loaded_scenario = load_scenario(scenario)
                console.print(f"Loaded scenario from: {scenario}")
            elif scenario in BUILT_IN_SCENARIOS:
                loaded_scenario = BUILT_IN_SCENARIOS[scenario]
                console.print(f"Using built-in scenario: {scenario}")
            else:
                console.print(f"[red]Unknown scenario: {scenario}[/red]")
                console.print(f"Available: {', '.join(BUILT_IN_SCENARIOS.keys())}")
                raise typer.Exit(code=1)

            result = tester.run_scenario(data, loaded_scenario, strategy_name=strategy)

            output_path = tester.save_result(result, output)
            console.print(f"\n[green]Results saved to:[/green] {output_path}")

            table = Table(title=f"Stress Test: {strategy} - {result.scenario_name}")
            table.add_column("Metric")
            table.add_column("Original")
            table.add_column("Stressed")
            table.add_column("Change")

            for metric in ["total_return", "max_drawdown", "win_rate", "sharpe_ratio", "trade_count"]:
                orig = result.original_metrics.get(metric, 0)
                stressed = result.stressed_metrics.get(metric, 0)
                change = stressed - orig
                table.add_row(
                    metric,
                    f"{orig:.4f}",
                    f"{stressed:.4f}",
                    f"{change:+.4f}",
                )

            console.print(table)

        else:
            console.print("[red]Please specify --scenario or --all-scenarios.[/red]")
            console.print(f"Available scenarios: {', '.join(BUILT_IN_SCENARIOS.keys())}")
            raise typer.Exit(code=1)

        console.print("\n[yellow]Disclaimer:[/yellow] This is research-only stress test. Past performance does not guarantee future results.")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


@analyze_app.command("sensitivity")
def analyze_sensitivity(
    strategy: Annotated[
        str,
        typer.Option("--strategy", help="Strategy name."),
    ],
    config: Annotated[
        str,
        typer.Option(
            "--config",
            help="Path to JSON config defining parameter ranges.",
        ),
    ],
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Symbol to test (e.g., SPY)."),
    ],
    start_date: Annotated[
        str,
        typer.Option("--start", help="Start date (YYYY-MM-DD)."),
    ],
    end_date: Annotated[
        str,
        typer.Option("--end", help="End date (YYYY-MM-DD)."),
    ],
    metric: Annotated[
        str,
        typer.Option(
            "--metric",
            help="Metric to analyze (sharpe_ratio, total_return, max_drawdown, win_rate).",
        ),
    ] = "sharpe_ratio",
    output: Annotated[
        str,
        typer.Option(
            "--output",
            help="Output path for sensitivity results.",
        ),
    ] = "data/analysis/sensitivity_result.json",
) -> None:
    """Run sensitivity analysis on strategy parameters.

    This command is research-only. It varies strategy parameters and
    measures metric changes to identify fragile parameters. No live trading, no broker calls.
    """
    console.print("[cyan]Sensitivity Analysis[/cyan]")

    try:
        console.print(f"Loading parameter config from: {config}")
        sensitivity_config = load_sensitivity_config(config)

        if not sensitivity_config.parameters:
            console.print("[red]No parameters defined in config.[/red]")
            raise typer.Exit(code=1)

        console.print(f"Parameters to test: {', '.join(sensitivity_config.parameters.keys())}")

        from aurora.data.yfinance_source import YFinanceDataSource
        import pandas as pd

        console.print(f"Fetching data for {symbol} from {start_date} to {end_date}...")
        data_source = YFinanceDataSource()
        data = data_source.fetch(
            symbols=[symbol],
            start_date=start_date,
            end_date=end_date,
        )

        if data.empty:
            console.print(f"[red]No data fetched for {symbol}.[/red]")
            raise typer.Exit(code=1)

        console.print(f"Loaded {len(data)} rows of data")

        def moving_average_strategy_builder(params: dict) -> Callable[[pd.DataFrame], pd.Series]:
            """Build a moving average strategy with configurable parameters."""
            fast_window = params.get("fast_window", 5)
            slow_window = params.get("slow_window", 20)

            def strategy_fn(df: pd.DataFrame) -> pd.Series:
                signals = pd.Series(0, index=df.index, dtype=int)
                if "close" in df.columns:
                    ma_fast = df["close"].rolling(window=fast_window).mean()
                    ma_slow = df["close"].rolling(window=slow_window).mean()
                    signals[df["close"] > ma_slow] = 1
                return signals

            return strategy_fn

        analyzer = SensitivityAnalyzer(
            strategy_builder=moving_average_strategy_builder,
            base_data=data,
        )

        console.print(f"Running sensitivity analysis for metric: {metric}")
        result = analyzer.analyze(sensitivity_config, metric=metric)

        output_path = analyzer.save_result(result, output)
        console.print(f"\n[green]Results saved to:[/green] {output_path}")

        analyzer.print_tornado(result)

        if result.most_sensitive:
            console.print(f"\n[yellow]Most sensitive parameter:[/yellow] {result.most_sensitive[0]}")
            console.print("[yellow]Disclaimer:[/yellow] This is research-only sensitivity analysis. Past performance does not guarantee future results.")

    except FileNotFoundError as e:
        console.print(f"[red]File not found:[/red] {e}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
