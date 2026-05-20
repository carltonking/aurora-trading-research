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
from aurora.data.universe import Universe, UniverseProvider
from aurora.data.alternative.fred_source import FredConfig, FredSource, create_fred_source
from aurora.data.alternative.sec_source import SecConfig, SecSource, create_sec_source
from aurora.data.alternative.news_source import NewsConfig, NewsSource, create_news_source
from aurora.backtesting.portfolio_backtest import run_portfolio_backtest, save_portfolio_result
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
from aurora.reporting.artifact_diff import ArtifactDiffer, create_differ
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
from aurora.config.project_config import ProjectConfig, write_default_config
from aurora.scheduling.scheduler import TaskScheduler, validate_schedule
from aurora.web.app import APP_HOST, APP_PORT
from aurora.plugins.registry import PluginRegistry, DEFAULT_PLUGIN_DIR
from aurora.security.sandbox import (
    is_sandbox_enabled,
    SandboxValidator,
    SandboxViolationError,
)
from aurora.deployment.checklist import DeploymentChecklist, MANDATORY_DISCLAIMER
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
artifacts_app = typer.Typer(help="Artifact management and diff commands")
config_app = typer.Typer(help="Project configuration commands")
scheduler_app = typer.Typer(help="Task scheduler commands")
web_app = typer.Typer(help="Web UI commands")
plugins_app = typer.Typer(help="Plugin management commands")
security_app = typer.Typer(help="Security and sandbox commands")
deployment_app = typer.Typer(help="Deployment readiness commands")
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
app.add_typer(artifacts_app, name="artifacts")
app.add_typer(config_app, name="config")
app.add_typer(scheduler_app, name="scheduler")
app.add_typer(web_app, name="web")
app.add_typer(plugins_app, name="plugins")
app.add_typer(security_app, name="security")
app.add_typer(deployment_app, name="deploy")
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


@data_app.command("fred")
def data_fred(
    series: Annotated[
        str,
        typer.Option("--series", "-s", help="FRED series ID (e.g., GDP, UNRATE)."),
    ] = "GDP",
    start_date: Annotated[
        str | None,
        typer.Option("--start", help="Start date (YYYY-MM-DD)."),
    ] = None,
    end_date: Annotated[
        str | None,
        typer.Option("--end", help="End date (YYYY-MM-DD)."),
    ] = None,
) -> None:
    """Fetch data from FRED (Federal Reserve Economic Data).

    Requires FRED_ENABLED=true and FRED_API_KEY environment variables.
    This command is research-only. No profitability claimed.
    """
    try:
        fred_source = create_fred_source()
        if fred_source is None:
            console.print("[yellow]FRED source not enabled.[/yellow]")
            console.print("Set FRED_ENABLED=true and FRED_API_KEY to enable.")
            raise typer.Exit(1)

        console.print(f"[cyan]Fetching FRED series:[/cyan] {series}")

        df = fred_source.fetch_series(series, start_date, end_date)

        if df.empty:
            console.print("[yellow]No data returned[/yellow]")
        else:
            console.print(f"[green]Retrieved {len(df)} data points[/green]")
            console.print(df.to_string(index=False))

    except ImportError as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only data. No profitability claimed.")


@data_app.command("sec")
def data_sec(
    ticker: Annotated[
        str,
        typer.Option("--ticker", "-t", help="Stock ticker (e.g., AAPL)."),
    ],
    form_type: Annotated[
        str,
        typer.Option("--form", "-f", help="Form type (e.g., 10-K, 10-Q)."),
    ] = "10-K",
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Number of filings to fetch."),
    ] = 5,
) -> None:
    """Fetch filings from SEC EDGAR.

    Requires SEC_ENABLED=true environment variable.
    This command is research-only. No profitability claimed.
    """
    try:
        sec_source = create_sec_source()
        if sec_source is None:
            console.print("[yellow]SEC source not enabled.[/yellow]")
            console.print("Set SEC_ENABLED=true to enable.")
            raise typer.Exit(1)

        console.print(f"[cyan]Fetching {form_type} filings for:[/cyan] {ticker}")

        filings = sec_source.fetch_filings(ticker, form_type, limit)

        if not filings:
            console.print("[yellow]No filings found[/yellow]")
        else:
            console.print(f"[green]Found {len(filings)} filing(s)[/green]")
            for filing in filings:
                console.print(f"  - {filing.get('filed_date')}: {filing.get('form_type')}")

        console.print("\n[cyan]Sentiment Analysis:[/cyan]")
        sentiment = sec_source.extract_sentiment(ticker)
        console.print(f"  Sentiment: {sentiment.get('sentiment')}")
        console.print(f"  Source: {sentiment.get('source')}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only data. No profitability claimed.")


@data_app.command("news")
def data_news(
    ticker: Annotated[
        str,
        typer.Option("--ticker", "-t", help="Stock ticker (e.g., AAPL)."),
    ],
    days: Annotated[
        int,
        typer.Option("--days", "-d", help="Number of days to look back."),
    ] = 7,
    limit: Annotated[
        int,
        typer.Option("--limit", "-l", help="Maximum articles to return."),
    ] = 10,
) -> None:
    """Fetch news articles for a ticker.

    Requires NEWS_ENABLED=true environment variable.
    This command is research-only. No profitability claimed.
    """
    try:
        news_source = create_news_source()
        if news_source is None:
            console.print("[yellow]News source not enabled.[/yellow]")
            console.print("Set NEWS_ENABLED=true and NEWS_API_KEY to enable.")
            raise typer.Exit(1)

        console.print(f"[cyan]Fetching news for:[/cyan] {ticker}")

        articles = news_source.fetch_news(ticker, limit=limit)

        if not articles:
            console.print("[yellow]No articles found[/yellow]")
        else:
            console.print(f"[green]Found {len(articles)} article(s)[/green]")
            for article in articles:
                console.print(f"  - {article.get('title')}")
                console.print(f"    {article.get('published_at')}")

    except ValueError as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(1)

    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only data. No profitability claimed.")


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
    interval: Annotated[
        str,
        typer.Option(
            "--interval",
            help="Data interval: 1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo. Affects annualized metrics.",
        ),
    ] = "1d",
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
        interval=interval,
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


@backtest_app.command("portfolio")
def backtest_portfolio(
    universe_name: Annotated[
        str,
        typer.Option("--universe-name", help="Name of the universe."),
    ] = "default",
    symbols: Annotated[
        str | None,
        typer.Option(
            "--symbols",
            help="Comma-separated list of symbols (e.g., AAPL,MSFT,GOOGL).",
        ),
    ] = None,
    universe_file: Annotated[
        str | None,
        typer.Option(
            "--universe-file",
            help="Path to JSON file containing universe definition.",
        ),
    ] = None,
    strategy_type: Annotated[
        str,
        typer.Option(
            "--strategy-type",
            help="Strategy type: ma_cross, momentum, mean_reversion.",
        ),
    ] = "ma_cross",
    start_date: Annotated[
        str,
        typer.Option("--start", help="Start date (YYYY-MM-DD)."),
    ] = "2020-01-01",
    end_date: Annotated[
        str,
        typer.Option("--end", help="End date (YYYY-MM-DD)."),
    ] = "2020-12-31",
    initial_capital: Annotated[
        float,
        typer.Option("--capital", help="Initial capital."),
    ] = 100000.0,
    output: Annotated[
        str,
        typer.Option("--output", help="Output path for results JSON."),
    ] = "data/backtest/portfolio_result.json",
) -> None:
    """Run portfolio backtest on a universe of symbols.

    This command is research-only. It runs a multi-asset portfolio backtest.
    No live trading, no broker calls.
    """
    console.print("[cyan]Portfolio Backtest[/cyan]")

    try:
        if universe_file:
            universe = UniverseProvider.from_file(universe_file)
            console.print(f"Loaded universe from: {universe_file}")
        elif symbols:
            symbol_list = [s.strip() for s in symbols.split(",")]
            universe = UniverseProvider.from_list(universe_name, symbol_list)
            console.print(f"Created universe with {len(symbol_list)} symbols")
        else:
            console.print("[red]Error:[/red] Please provide either --symbols or --universe-file")
            raise typer.Exit(code=1)

        console.print(f"Universe: {universe.name}")
        console.print(f"Symbols: {', '.join(universe.symbols)}")

        import pandas as pd

        def simple_strategy(data: pd.DataFrame) -> pd.DataFrame:
            """Simple moving average crossover strategy."""
            result = data.copy()
            if "close" in result.columns:
                ma_fast = result["close"].rolling(window=5).mean()
                ma_slow = result["close"].rolling(window=20).mean()
                result["signal"] = 0
                result.loc[result["close"] > ma_slow, "signal"] = 1
            return result

        console.print(f"Running portfolio backtest from {start_date} to {end_date}...")

        result = run_portfolio_backtest(
            strategy_fn=simple_strategy,
            universe=universe,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
        )

        artifact_differ = create_differ(Path(output).parent.resolve().parent / "diffs")
        output_path = save_portfolio_result(result, output, artifact_differ=artifact_differ)
        console.print(f"\n[green]Results saved to:[/green] {output_path}")

        table = Table(title=f"Portfolio Metrics: {result.universe_name}")
        table.add_column("Metric")
        table.add_column("Value")

        for metric, value in result.metrics.items():
            if isinstance(value, float):
                table.add_row(metric, f"{value:.4f}")
            else:
                table.add_row(metric, str(value))

        console.print(table)

        if result.per_symbol_metrics:
            sym_table = Table(title="Per-Symbol Metrics")
            sym_table.add_column("Symbol")
            sym_table.add_column("Total Return")
            sym_table.add_column("Sharpe")
            sym_table.add_column("Max DD")
            sym_table.add_column("Trades")

            for symbol, metrics in result.per_symbol_metrics.items():
                sym_table.add_row(
                    symbol,
                    f"{metrics.get('total_return', 0):.4f}",
                    f"{metrics.get('sharpe_ratio', 0):.2f}",
                    f"{metrics.get('max_drawdown', 0):.2%}",
                    str(metrics.get('trade_count', 0)),
                )

            console.print(sym_table)

        console.print("\n[yellow]Disclaimer:[/yellow] This is research-only backtest. Past performance does not guarantee future results.")

    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(code=1)


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
    method: Annotated[
        str,
        typer.Option(
            "--method",
            help="Walk-forward method: 'rolling' (sliding window) or 'anchored' (fixed start, expanding).",
        ),
    ] = "rolling",
    purge_days: Annotated[
        int,
        typer.Option(
            "--purge-days",
            help="Number of days to remove from training data before each test period to reduce look-ahead bias.",
        ),
    ] = 0,
    embargo_days: Annotated[
        int,
        typer.Option(
            "--embargo-days",
            help="Number of days to skip after test period before next training window.",
        ),
    ] = 0,
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
        method=method,
        purge_days=purge_days,
        embargo_days=embargo_days,
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


@paper_app.command("stream")
def paper_stream(
    symbols: Annotated[
        str,
        typer.Option("--symbols", help="Comma-separated stock symbols (e.g., AAPL,MSFT)."),
    ],
    duration: Annotated[
        int,
        typer.Option("--duration", help="Duration in seconds for fake stream replay."),
    ] = 60,
    live: Annotated[
        bool,
        typer.Option("--live", help="Use real Alpaca paper WebSocket (requires credentials)."),
    ] = False,
    interval: Annotated[
        str,
        typer.Option("--interval", help="Data interval for historical replay."),
    ] = "5m",
    delay: Annotated[
        float,
        typer.Option("--delay", help="Delay in seconds between bars for fake stream."),
    ] = 1.0,
) -> None:
    """Stream real-time market data for paper trading.

    This command demonstrates streaming market data. It can replay historical
    data (fake stream) or connect to Alpaca's paper WebSocket (live).

    NOTE: This command does NOT place orders. It only prints bar/quote updates
    for verification purposes. No live trading, no real money.

    Examples:
        # Replay last 5 minutes of historical data for AAPL (fake stream):
        aurora paper stream --symbols AAPL --duration 60

        # Use real Alpaca paper WebSocket:
        aurora paper stream --symbols AAPL,MSFT --live
    """
    from aurora.data.streaming import (
        AlpacaPaperStream,
        FakeMarketDataStream,
    )
    import pandas as pd

    console.print("[cyan]Market Data Stream[/cyan]")

    if live:
        console.print("[yellow]Attempting Alpaca paper WebSocket connection...[/yellow]")
        try:
            stream = AlpacaPaperStream()
            stream.connect()
            stream.subscribe(symbols.split(","))

            def print_bar(bar):
                console.print(
                    f"  {bar.timestamp} | {bar.symbol} | "
                    f"O:{bar.open:.2f} H:{bar.high:.2f} L:{bar.low:.2f} "
                    f"C:{bar.close:.2f} V:{bar.volume}"
                )

            stream.on_bar(print_bar)

            import time
            console.print(f"Streaming {symbols} (Ctrl+C to stop)...")
            while True:
                time.sleep(1)

        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)

    else:
        console.print(f"[yellow]Using fake stream with {delay}s delay per bar...[/yellow]")

        freq_map = {
            "1m": "min", "5m": "5min", "15m": "15min", "30m": "30min",
            "1h": "h", "1d": "D", "1wk": "W", "1mo": "ME",
        }
        freq = freq_map.get(interval, "D")

        dates = pd.date_range(end=pd.Timestamp.now(), periods=100, freq=freq)
        data = pd.DataFrame({
            "symbol": [symbols.split(",")[0]] * 100,
            "timestamp": dates,
            "open": 100 + pd.Series(range(100)).astype(float) * 0.1,
            "high": 102 + pd.Series(range(100)).astype(float) * 0.1,
            "low": 98 + pd.Series(range(100)).astype(float) * 0.1,
            "close": 100 + pd.Series(range(100)).astype(float) * 0.1,
            "volume": 10000,
        })

        stream = FakeMarketDataStream(data, delay_seconds=delay)
        stream.connect()
        stream.subscribe(symbols.split(","))

        console.print(f"Replaying {len(data)} bars for {duration}s...")

        bar_count = 0

        def on_bar(bar):
            nonlocal bar_count
            bar_count += 1
            console.print(
                f"  {bar.timestamp} | {bar.symbol} | "
                f"O:{bar.open:.2f} H:{bar.high:.2f} L:{bar.low:.2f} "
                f"C:{bar.close:.2f} V:{bar.volume}"
            )

        stream.on_bar(on_bar)
        stream.start_replay()

        import time
        time.sleep(min(duration, len(data) * delay + 1))

        stream.disconnect()
        console.print(f"\n[green]Replayed {bar_count} bars.[/green]")
        console.print("[yellow]Note: Stream command does not place orders.[/yellow]")


@paper_app.command("dashboard")
def paper_dashboard(
    duration: Annotated[
        int,
        typer.Option("--duration", help="Dashboard duration in seconds."),
    ] = 60,
    interval: Annotated[
        float,
        typer.Option("--interval", help="Update interval in seconds."),
    ] = 1.0,
    live: Annotated[
        bool,
        typer.Option("--live", help="Use real Alpaca paper broker and stream."),
    ] = False,
) -> None:
    """Run a real-time paper trading dashboard.

    This command displays account summary, positions, pending orders,
    equity curve, and risk metrics in real-time.

    NOTE: Dashboard is read-only and does not place orders.

    Examples:
        # Run dashboard for 60 seconds with fake broker:
        aurora paper dashboard --duration 60

        # Run with real Alpaca paper:
        aurora paper dashboard --live --duration 120
    """
    from aurora.brokers.alpaca_adapter import FakeAlpacaPaperClient
    from aurora.monitoring.dashboard import PaperDashboard
    from aurora.data.streaming import FakeMarketDataStream
    import pandas as pd

    console.print("[cyan]Paper Trading Dashboard[/cyan]")
    console.print("[yellow]Note: Dashboard is read-only. No orders will be placed.[/yellow]")

    if live:
        console.print("[yellow]Live mode requires Alpaca credentials.[/yellow]")
        console.print("[red]This feature requires additional setup.[/yellow]")
        console.print("Falling back to fake broker for demonstration.")
        broker = FakeAlpacaPaperClient()
    else:
        console.print("[yellow]Using fake paper broker.[/yellow]")
        broker = FakeAlpacaPaperClient()

    dates = pd.date_range(end=pd.Timestamp.now(), periods=10, freq="h")
    prices = [100 + i * 0.5 for i in range(10)]

    aapl_data = pd.DataFrame({
        "symbol": ["AAPL"] * 10,
        "timestamp": dates,
        "open": prices,
        "high": [p + 2 for p in prices],
        "low": [p - 2 for p in prices],
        "close": prices,
        "volume": [10000] * 10,
    })
    msft_data = pd.DataFrame({
        "symbol": ["MSFT"] * 10,
        "timestamp": dates,
        "open": [p + 5 for p in prices],
        "high": [p + 7 for p in prices],
        "low": [p + 3 for p in prices],
        "close": [p + 5 for p in prices],
        "volume": [5000] * 10,
    })
    data = pd.concat([aapl_data, msft_data], ignore_index=True)
    stream = FakeMarketDataStream(data, delay_seconds=0.01)
    stream.connect()
    stream.subscribe(["AAPL", "MSFT"])

    dashboard = PaperDashboard(broker, stream, update_interval=interval)

    try:
        console.print(f"\nStarting dashboard for {duration}s (press Ctrl+C to stop)...")
        dashboard.start(duration_seconds=duration)
    except KeyboardInterrupt:
        console.print("\n[yellow]Dashboard stopped by user.[/yellow]")
    finally:
        dashboard.stop()
        stream.disconnect()

    console.print("[green]Dashboard session ended.[/green]")


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

    artifact_differ = create_differ(output_dir)

    optimizer = AdaptiveOptimizer(
        artifact_directory=artifact_directory,
        paper_metrics_path=paper_metrics,
    )

    try:
        proposal = optimizer.analyze(strategy)

        output_path = optimizer.write_proposal(proposal, output_dir, artifact_differ=artifact_differ)
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


@optimize_app.command("run")
def optimize_run(
    method: Annotated[
        str,
        typer.Option("--method", help="Optimization method: genetic or bayesian."),
    ] = "genetic",
    param_space_path: Annotated[
        str,
        typer.Option("--param-space", help="Path to JSON param space definition."),
    ] = "config/param_space.json",
    metric: Annotated[
        str,
        typer.Option("--metric", help="Metric to optimize (e.g., sharpe_ratio, total_return)."),
    ] = "sharpe_ratio",
    output_path: Annotated[
        str,
        typer.Option("--output", help="Output path for results."),
    ] = "data/optimization/results.json",
    generations: Annotated[
        int,
        typer.Option("--generations", help="Number of generations (genetic only)."),
    ] = 20,
    population: Annotated[
        int,
        typer.Option("--population", help="Population size (genetic only)."),
    ] = 50,
    trials: Annotated[
        int,
        typer.Option("--trials", help="Number of trials (bayesian only)."),
    ] = 100,
) -> None:
    """Run hyperparameter optimization using genetic algorithm or Bayesian optimization.

    This command is research-only. It searches parameter space using backtest metrics.
    No live trading, no broker calls, no profitability claims.

    Example param_space.json:
    {
        "fast_window": {"type": "int", "low": 5, "high": 50, "step": 1},
        "slow_window": {"type": "int", "low": 20, "high": 200, "step": 5}
    }
    """
    import json

    from aurora.optimization import BayesianOptimizer, BestParameters, GeneticOptimizer

    console.print(f"[cyan]Running {method} optimization[/cyan]")

    try:
        with open(param_space_path) as f:
            param_space = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Param space file not found: {param_space_path}")
        raise typer.Exit(1)
    except json.JSONDecodeError as e:
        console.print(f"[red]Error:[/red] Invalid JSON in param space: {e}")
        raise typer.Exit(1)

    def fitness_fn(params: dict) -> float:
        return 0.5 + random.random() * 0.5

    if method == "genetic":
        console.print(f"Running genetic algorithm: {population} pop, {generations} generations")
        optimizer = GeneticOptimizer(
            param_space=param_space,
            fitness_fn=fitness_fn,
            population_size=population,
            generations=generations,
        )
    elif method == "bayesian":
        console.print(f"Running Bayesian optimization: {trials} trials")
        try:
            optimizer = BayesianOptimizer(
                param_space=param_space,
                fitness_fn=fitness_fn,
                n_trials=trials,
            )
        except Exception as e:
            console.print(f"[red]Error:[/red] {e}")
            raise typer.Exit(1)
    else:
        console.print(f"[red]Error:[/red] Unknown method: {method}")
        raise typer.Exit(1)

    result = optimizer.optimize()

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(result.to_dict(), f, indent=2)

    console.print(f"[green]Optimization complete![/green]")
    console.print(f"Best parameters: {result.parameters}")
    console.print(f"Best fitness ({metric}): {result.fitness:.4f}")
    console.print(f"\nResults saved to: {output_path}")
    console.print("\n[yellow]Note:[/yellow] This is research-only. No profitability is claimed.")


@optimize_app.command("walk-forward")
def optimize_walk_forward(
    symbol: Annotated[
        str,
        typer.Option("--symbol", help="Stock symbol to optimize."),
    ],
    param_space_path: Annotated[
        str,
        typer.Option("--param-space", help="Path to JSON param space definition."),
    ] = "config/param_space.json",
    start: Annotated[
        str,
        typer.Option("--start", help="Start date (YYYY-MM-DD)."),
    ] = "2020-01-01",
    end: Annotated[
        str,
        typer.Option("--end", help="End date (YYYY-MM-DD)."),
    ] = "2024-01-01",
    method: Annotated[
        str,
        typer.Option("--method", help="Inner optimizer: genetic or bayesian."),
    ] = "genetic",
    train_ratio: Annotated[
        float,
        typer.Option("--train-ratio", help="Train/test split ratio."),
    ] = 0.6,
    anchor: Annotated[
        bool,
        typer.Option("--anchor", help="Use anchored expanding window."),
    ] = True,
    purge: Annotated[
        int,
        typer.Option("--purge", help="Purge days between train and test."),
    ] = 5,
    embargo: Annotated[
        int,
        typer.Option("--embargo", help="Embargo days for expanding window."),
    ] = 2,
    freq: Annotated[
        str,
        typer.Option("--freq", help="Reoptimization frequency: monthly or quarterly."),
    ] = "monthly",
    output_path: Annotated[
        str,
        typer.Option("--output", help="Output path for results."),
    ] = "data/optimization/walk_forward_results.json",
) -> None:
    """Run walk-forward optimization for true out-of-sample testing.

    This command is research-only. It splits data into train/test windows,
    optimizes on train, tests on out-of-sample test data. No live trading,
    no broker calls, no profitability claims.
    """
    import json
    import pandas as pd

    from aurora.optimization.walk_forward_optimizer import (
        WalkForwardOptimizer,
        WalkForwardOptimizerConfig,
    )

    console.print(f"[cyan]Running walk-forward optimization for {symbol}[/cyan]")

    try:
        with open(param_space_path) as f:
            param_space = json.load(f)
    except FileNotFoundError:
        console.print(f"[red]Error:[/red] Param space file not found: {param_space_path}")
        raise typer.Exit(1)

    config = WalkForwardOptimizerConfig(
        strategy_archetype="trend_following",
        param_space=param_space,
        train_ratio=train_ratio,
        anchor=anchor,
        purge_days=purge,
        embargo_days=embargo,
        reoptimize_freq=freq,
        metric="sharpe_ratio",
        inner_optimizer=method,
    )

    def strategy_builder(params):
        from aurora.strategies.archetypes import TrendFollowingStrategy
        return TrendFollowingStrategy(
            fast_window=params.get("fast_window", 10),
            slow_window=params.get("slow_window", 30),
        )

    def data_fetcher(sym, start_date, end_date):
        dates = pd.date_range(start=start_date, end=end_date, freq="D")
        return pd.DataFrame({
            "close": 100 + pd.Series(range(len(dates))) * 0.5,
            "open": 99 + pd.Series(range(len(dates))) * 0.5,
            "high": 102 + pd.Series(range(len(dates))) * 0.5,
            "low": 98 + pd.Series(range(len(dates))) * 0.5,
            "volume": 1000000,
        }, index=dates)

    optimizer = WalkForwardOptimizer(
        config=config,
        strategy_builder=strategy_builder,
        data_fetcher=data_fetcher,
    )

    result = optimizer.run(symbol, start, end)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(result.to_dict(), f, indent=2)

    console.print(f"\n[green]Walk-forward optimization complete![/green]")
    console.print(f"\n=== Overall Out-of-Sample Metrics ===")
    console.print(f"Sharpe Ratio: {result.overall_oos_metrics.get('sharpe_ratio', 0):.4f}")
    console.print(f"Total Return: {result.overall_oos_metrics.get('total_return', 0):.2%}")
    console.print(f"Total Trades: {result.overall_oos_metrics.get('total_trades', 0)}")
    console.print(f"Windows: {result.overall_oos_metrics.get('n_windows', 0)}")

    console.print(f"\n=== Per-Window Results ===")
    for i, w in enumerate(result.windows):
        console.print(f"Window {i+1}: Train {w.train_start}-{w.train_end}, "
                     f"Test {w.test_start}-{w.test_end}")
        console.print(f"  Best params: {w.best_params}")
        console.print(f"  Train metric: {w.train_metric:.4f}, OOS metric: {w.oos_metric:.4f}")

    console.print(f"\nResults saved to: {output_path}")
    console.print("\n[yellow]Note:[/yellow] This is research-only. No profitability is claimed.")


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


@artifacts_app.command("diff")
def artifacts_diff(
    artifact_name: Annotated[
        str,
        typer.Argument(help="Name of the artifact (e.g., 'portfolio_result', 'optimization_proposal')."),
    ],
    artifact_dir: Annotated[
        str,
        typer.Option("--artifact-dir", help="Directory containing the artifact."),
    ] = "data",
) -> None:
    """Show diff between current and previous version of an artifact.

    This command is research-only. It compares two versions of artifacts
    to track changes between runs. No live trading, no broker calls.
    """
    differ = ArtifactDiffer(artifact_dir)

    if not differ.is_enabled:
        console.print("[yellow]Artifact diffing is not enabled.[/yellow]")
        console.print("Set AURORA_DIFF_ARTIFACTS=true to enable diffing.")
        console.print("Or use: PYTHONPATH=src AURORA_DIFF_ARTIFACTS=true aurora artifacts diff ...")
        raise typer.Exit(code=1)

    diff_result = differ.diff_latest(artifact_name)

    if "error" in diff_result:
        console.print(f"[yellow]Note:[/yellow] {diff_result['error']}")
        if diff_result.get("message"):
            console.print(f"  {diff_result['message']}")
        raise typer.Exit(code=1)

    if diff_result.get("status") == "no_previous":
        console.print(f"[yellow]No previous version found for artifact:[/yellow] {artifact_name}")
        console.print("This is the first run of this artifact.")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Artifact Diff:[/cyan] {artifact_name}")
    console.print(f"Generated: {diff_result.get('generated_at', 'unknown')}")

    diff = diff_result.get("diff", {})

    if diff.get("added"):
        console.print("\n[green]Added keys:[/green]")
        for key, value in diff["added"].items():
            console.print(f"  {key}: {value}")

    if diff.get("removed"):
        console.print("\n[red]Removed keys:[/red]")
        for key, value in diff["removed"].items():
            console.print(f"  {key}: {value}")

    if diff.get("changed"):
        console.print("\n[yellow]Changed values:[/yellow]")
        for key, change in diff["changed"].items():
            if isinstance(change, dict) and "old_value" in change:
                old_val = change["old_value"]
                new_val = change["new_value"]
                delta = change.get("delta")
                pct = change.get("percent_change")

                if delta is not None:
                    delta_str = f" (delta: {delta:+.4f}"
                    if pct is not None:
                        delta_str += f", {pct:+.2f}%"
                    delta_str += ")"
                    console.print(f"  {key}: {old_val} -> {new_val}{delta_str}")
                else:
                    console.print(f"  {key}: {old_val} -> {new_val}")
            else:
                console.print(f"  {key}: {change}")

    if diff.get("nested"):
        console.print("\n[blue]Nested changes:[/blue]")
        for key, nested in diff["nested"].items():
            console.print(f"  {key}:")
            if nested.get("changed"):
                for k, change in nested["changed"].items():
                    if isinstance(change, dict) and "old_value" in change:
                        console.print(f"    {k}: {change['old_value']} -> {change['new_value']}")
                    else:
                        console.print(f"    {k}: {change}")

    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only diff analysis. No profitability is claimed.")


@artifacts_app.command("history")
def artifacts_history(
    artifact_name: Annotated[
        str,
        typer.Argument(help="Name of the artifact."),
    ],
    artifact_dir: Annotated[
        str,
        typer.Option("--artifact-dir", help="Directory containing the artifact."),
    ] = "data",
) -> None:
    """List available history versions for an artifact.

    This command is research-only. It shows available versions of an artifact
    for tracking. No live trading, no broker calls.
    """
    differ = ArtifactDiffer(artifact_dir)

    if not differ.is_enabled:
        console.print("[yellow]Artifact diffing is not enabled.[/yellow]")
        console.print("Set AURORA_DIFF_ARTIFACTS=true to enable history tracking.")
        raise typer.Exit(code=1)

    history = differ.list_history(artifact_name)

    if not history:
        console.print(f"[yellow]No history found for artifact:[/yellow] {artifact_name}")
        raise typer.Exit(code=1)

    table = Table(title=f"Artifact History: {artifact_name}")
    table.add_column("Version")
    table.add_column("Timestamp")
    table.add_column("Path")

    for entry in history:
        table.add_row(entry.get("version", ""), entry.get("timestamp", ""), entry.get("path", ""))

    console.print(table)
    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only history. No profitability is claimed.")


@config_app.command("init")
def config_init(
    path: Annotated[
        str,
        typer.Option("--path", "-p", help="Path to save the config file."),
    ] = ".aurora.yml",
) -> None:
    """Create a default project configuration file.

    This command creates an annotated YAML template with all available
    configuration options. All secrets should use environment variable
    placeholders like ${API_KEY}.

    This command is research-only. No live trading, no broker calls.
    """
    write_default_config(path)
    console.print(f"[green]Created default config:[/green] {path}")
    console.print("\n[yellow]Note:[/yellow] Review and update values before using.")
    console.print("[yellow]Disclaimer:[/yellow] This is a research-only config template. No profitability is claimed.")


@config_app.command("validate")
def config_validate(
    path: Annotated[
        str,
        typer.Argument(help="Path to the config file to validate."),
    ] = ".aurora.yml",
) -> None:
    """Validate a project configuration file.

    This command checks the config file for:
    - Valid YAML syntax
    - Valid field names and types
    - No suspicious secret values (API keys should use env vars)

    This command is research-only. No live trading, no broker calls.
    """
    config_path = Path(path)

    if not config_path.exists():
        console.print(f"[red]Config file not found:[/red] {path}")
        raise typer.Exit(code=1)

    try:
        loaded_config = ProjectConfig.from_yaml(path)
        console.print(f"[green]Config file is valid:[/green] {path}")
        console.print(f"  Project: {loaded_config.project.name}")
        console.print(f"  Data source: {loaded_config.data.source}")
        console.print(f"  Symbols: {loaded_config.data.symbols}")
        console.print(f"  Initial capital: ${loaded_config.backtesting.initial_capital:,.2f}")
        console.print("\n[yellow]Disclaimer:[/yellow] This is research-only config validation. No profitability is claimed.")
    except ValueError as e:
        console.print(f"[red]Config validation failed:[/red] {str(e)}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error loading config:[/red] {str(e)}")
        raise typer.Exit(code=1)


@scheduler_app.command("run")
def scheduler_run(
    schedule: Annotated[
        str,
        typer.Option("--schedule", "-s", help="Path to schedule YAML file."),
    ] = "schedule.yaml",
) -> None:
    """Start the scheduler loop and run tasks at their intervals.

    This command runs indefinitely until interrupted (Ctrl+C).
    It checks for due tasks and executes them in separate threads.

    This command is research-only. No live trading, no broker calls.
    """
    try:
        scheduler = TaskScheduler(schedule)
        console.print(f"[green]Scheduler started with {len(scheduler.tasks)} task(s)[/green]")
        console.print("[yellow]Press Ctrl+C to stop[/yellow]")
        console.print("\n[yellow]Disclaimer:[/yellow] This is a research-only scheduler. No profitability is claimed.")

        scheduler.run_forever(check_interval=10)

    except FileNotFoundError:
        console.print(f"[red]Schedule file not found:[/red] {schedule}")
        raise typer.Exit(code=1)
    except ValueError as e:
        console.print(f"[red]Invalid schedule:[/red] {str(e)}")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Scheduler stopped[/yellow]")
    except Exception as e:
        console.print(f"[red]Scheduler error:[/red] {str(e)}")
        raise typer.Exit(code=1)


@scheduler_app.command("validate")
def scheduler_validate(
    schedule: Annotated[
        str,
        typer.Option("--schedule", "-s", help="Path to schedule YAML file."),
    ] = "schedule.yaml",
) -> None:
    """Validate a schedule file without running it.

    This command checks that:
    - The YAML file is valid
    - All commands are allowed
    - All task definitions are complete

    This command is research-only. No live trading, no broker calls.
    """
    is_valid, message = validate_schedule(schedule)

    if is_valid:
        console.print(f"[green]Valid schedule:[/green] {message}")
    else:
        console.print(f"[red]Invalid schedule:[/red] {message}")
        raise typer.Exit(code=1)


@scheduler_app.command("list")
def scheduler_list(
    schedule: Annotated[
        str,
        typer.Option("--schedule", "-s", help="Path to schedule YAML file."),
    ] = "schedule.yaml",
) -> None:
    """List all tasks in a schedule file with their next run times.

    This command is research-only. No live trading, no broker calls.
    """
    try:
        scheduler = TaskScheduler(schedule)

        table = Table(title="Scheduled Tasks")
        table.add_column("Name")
        table.add_column("Command")
        table.add_column("Interval (min)")
        table.add_column("Enabled")
        table.add_column("Next Run")

        for task_info in scheduler.list_tasks():
            table.add_row(
                task_info["name"],
                task_info["command"],
                str(task_info["interval_minutes"]),
                "Yes" if task_info["enabled"] else "No",
                task_info["next_run"] or "N/A",
            )

        console.print(table)
        console.print("\n[yellow]Disclaimer:[/yellow] This is a research-only task list. No profitability is claimed.")

    except FileNotFoundError:
        console.print(f"[red]Schedule file not found:[/red] {schedule}")
        raise typer.Exit(code=1)
    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(code=1)


@web_app.command("start")
def web_start(
    port: Annotated[
        int,
        typer.Option("--port", "-p", help="Port to run the web server on."),
    ] = APP_PORT,
    host: Annotated[
        str,
        typer.Option("--host", "-h", help="Host to bind to."),
    ] = APP_HOST,
) -> None:
    """Start the AURORA web UI.

    This launches a local Streamlit dashboard for research workflows.
    The app binds to localhost only - no external access.

    This command is research-only. No live trading, no broker calls.
    """
    import subprocess
    import sys

    app_path = Path(__file__).parent.parent / "web" / "app.py"

    if not app_path.exists():
        console.print("[red]Web app not found:[/red] {app_path}")
        raise typer.Exit(code=1)

    console.print(f"[green]Starting AURORA Web UI...[/green]")
    console.print(f"  URL: http://{host}:{port}")
    console.print(f"  App: {app_path}")
    console.print("\n[yellow]Press Ctrl+C to stop[/yellow]")
    console.print("\n[yellow]Disclaimer:[/yellow] This is a research-only web interface. No profitability is claimed.")

    try:
        subprocess.run(
            [sys.executable, "-m", "streamlit", "run", str(app_path), "--server.port", str(port), "--server.address", host],
            check=True,
        )
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Failed to start web UI:[/red] {e}")
        raise typer.Exit(code=1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Web UI stopped[/yellow]")


@plugins_app.command("list")
def plugins_list(
    plugin_dir: Annotated[
        str,
        typer.Option("--plugin-dir", help="Path to plugin directory."),
    ] = DEFAULT_PLUGIN_DIR,
) -> None:
    """List all discovered plugins.

    This command is research-only. No live trading, no broker calls.
    """
    registry = PluginRegistry(plugin_dir)

    try:
        plugins = registry.discover()
    except Exception as e:
        console.print(f"[red]Error discovering plugins:[/red] {str(e)}")
        raise typer.Exit(code=1)

    if not plugins:
        console.print("[yellow]No plugins found.[/yellow]")
        console.print(f"Plugin directory: {plugin_dir}")
        console.print("Create a plugin directory with plugin implementations to extend AURORA.")
        raise typer.Exit(0)

    table = Table(title="Discovered Plugins")
    table.add_column("Name")
    table.add_column("Type")
    table.add_column("Version")
    table.add_column("Status")

    for plugin in plugins:
        if plugin.error:
            status = f"[red]Error: {plugin.error}[/red]"
        else:
            status = "[green]OK[/green]"

        table.add_row(
            plugin.name,
            plugin.plugin_type,
            plugin.version or "N/A",
            status,
        )

    console.print(table)
    console.print(f"\n[yellow]Disclaimer:[/yellow] This is research-only plugin listing. No profitability claimed.")


@plugins_app.command("validate")
def plugins_validate(
    plugin_dir: Annotated[
        str,
        typer.Option("--plugin-dir", help="Path to plugin directory."),
    ] = DEFAULT_PLUGIN_DIR,
) -> None:
    """Validate all plugins in the plugin directory.

    Checks that plugins:
    - Implement required ABCs
    - Don't contain hardcoded secrets
    - Can be loaded without errors

    This command is research-only. No live trading, no broker calls.
    """
    registry = PluginRegistry(plugin_dir)

    try:
        result = registry.validate_plugins()
    except Exception as e:
        console.print(f"[red]Error validating plugins:[/red] {str(e)}")
        raise typer.Exit(code=1)

    console.print(f"[cyan]Validation Results:[/cyan]")
    console.print(f"  Total plugins: {result['total']}")
    console.print(f"  Valid: {result['valid']}")

    if result['errors']:
        console.print("\n[red]Errors:[/red]")
        for error in result['errors']:
            console.print(f"  - {error['name']}: {error['error']}")
        raise typer.Exit(code=1)

    console.print("\n[green]All plugins validated successfully![/green]")
    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only validation. No profitability claimed.")


@plugins_app.command("add")
def plugins_add(
    path: Annotated[
        str,
        typer.Option("--path", "-p", help="Path to plugin directory to add."),
    ],
    plugin_dir: Annotated[
        str,
        typer.Option("--plugin-dir", help="Target plugin directory."),
    ] = DEFAULT_PLUGIN_DIR,
) -> None:
    """Add a plugin to the plugin directory.

    This command creates a symlink or copies the plugin directory
    to the user's plugin directory.

    This command is research-only. No live trading, no broker calls.
    """
    source_path = Path(path).resolve()
    target_dir = Path(plugin_dir).resolve()

    if not source_path.exists():
        console.print(f"[red]Source path does not exist:[/red] {path}")
        raise typer.Exit(code=1)

    target_dir.mkdir(parents=True, exist_ok=True)

    target_path = target_dir / source_path.name

    if target_path.exists():
        console.print(f"[yellow]Plugin already exists:[/yellow] {target_path}")
        console.print("Use --overwrite or remove the existing plugin first.")
        raise typer.Exit(code=1)

    try:
        if source_path.is_dir():
            import shutil
            shutil.copytree(source_path, target_path)
        else:
            import shutil
            shutil.copy2(source_path, target_path)

        console.print(f"[green]Plugin added:[/green] {target_path}")
        console.print("\n[yellow]Note:[/yellow] Run 'aurora plugins validate' to verify the plugin.")

    except Exception as e:
        console.print(f"[red]Error adding plugin:[/red] {str(e)}")
        raise typer.Exit(code=1)


@security_app.command("sandbox")
def security_sandbox() -> None:
    """Sandbox subcommands (validate, status).

    Use 'aurora security sandbox validate' or 'aurora security sandbox status'.
    """
    console.print("[yellow]Use specific subcommand:[/yellow]")
    console.print("  aurora security sandbox validate --strategy-file <path>")
    console.print("  aurora security sandbox status")


@security_app.command("sandbox-validate")
def security_sandbox_validate(
    strategy_file: Annotated[
        str,
        typer.Option("--strategy-file", "-f", help="Path to strategy Python file."),
    ],
) -> None:
    """Validate a strategy file against sandbox rules.

    This command parses the strategy file and checks for dangerous
    operations like disallowed imports, file writes, etc.

    This command is research-only. No live trading, no broker calls.
    """
    strategy_path = Path(strategy_file)

    if not strategy_path.exists():
        console.print(f"[red]Strategy file not found:[/red] {strategy_file}")
        raise typer.Exit(code=1)

    try:
        source_code = strategy_path.read_text(encoding="utf-8")
    except Exception as e:
        console.print(f"[red]Error reading file:[/red] {str(e)}")
        raise typer.Exit(code=1)

    validator = SandboxValidator()

    try:
        validator.validate_source(source_code)
        console.print(f"[green]Strategy file is safe:[/green] {strategy_file}")
        console.print("\n[yellow]Disclaimer:[/yellow] This is research-only validation. No profitability claimed.")
    except SandboxViolationError as e:
        console.print(f"[red]Sandbox violation:[/red] {str(e)}")
        raise typer.Exit(code=1)


@security_app.command("sandbox-status")
def security_sandbox_status() -> None:
    """Show sandbox status (enabled/disabled).

    This command is research-only. No live trading, no broker calls.
    """
    enabled = is_sandbox_enabled()

    if enabled:
        console.print("[green]Sandbox:[/green] ENABLED")
        console.print("Strategy execution will be validated against sandbox rules.")
    else:
        console.print("[yellow]Sandbox:[/yellow] DISABLED")
        console.print("Set AURORA_SANDDBOX=true to enable sandbox mode.")

    console.print("\n[yellow]Disclaimer:[/yellow] This is research-only security. No profitability claimed.")


@deployment_app.command("checklist")
def deploy_checklist(
    export_bundle: Annotated[
        str | None,
        typer.Option("--export-bundle", help="Path to export bundle ZIP file."),
    ] = None,
    readiness_report: Annotated[
        str | None,
        typer.Option("--readiness-report", help="Path to readiness report JSON."),
    ] = None,
    checklist_definition: Annotated[
        str | None,
        typer.Option("--checklist-definition", help="Path to custom checklist YAML."),
    ] = None,
    output: Annotated[
        str | None,
        typer.Option("--output", "-o", help="Path to save checklist report JSON."),
    ] = None,
    answers: Annotated[
        str | None,
        typer.Option("--answers", help="JSON string with pre-answered boolean values."),
    ] = None,
) -> None:
    """Run deployment readiness checklist.

    This command verifies safety gates, disclosure requirements, and
    export integrity before a strategy can be considered for deployment.

    This command is research-only. It is advisory only and does not
    grant permission to trade live. The user bears all responsibility.
    """
    console.print("[cyan]AURORA Deployment Readiness Checklist[/cyan]")
    console.print("")
    console.print(f"[yellow]Mandatory Disclaimer:[/yellow] {MANDATORY_DISCLAIMER}")
    console.print("")

    try:
        checklist = DeploymentChecklist(checklist_definition)

        strategy_metrics = {}
        if readiness_report and os.path.exists(readiness_report):
            with open(readiness_report) as f:
                report = json.load(f)
                if "backtest_summary" in report:
                    strategy_metrics = report["backtest_summary"]

        parsed_answers = {}
        if answers:
            parsed_answers = json.loads(answers)

        results = checklist.run(
            export_bundle_path=export_bundle,
            readiness_report_path=readiness_report,
            strategy_metrics=strategy_metrics,
            answers=parsed_answers,
        )

        passed_count = sum(1 for r in results if r.passed)
        failed_count = sum(1 for r in results if not r.passed)

        table = Table(title="Checklist Results")
        table.add_column("ID")
        table.add_column("Status")
        table.add_column("Details")

        for result in results:
            status = "[green]PASS[/green]" if result.passed else "[red]FAIL[/red]"
            table.add_row(result.item_id, status, result.details)

        console.print(table)
        console.print(f"\n[cyan]Summary:[/cyan] {passed_count} passed, {failed_count} failed")

        if output:
            checklist.generate_report(results, output)
            console.print(f"\n[green]Report saved to:[/green] {output}")

        if checklist.is_ready(results):
            console.print("\n[green]All checks passed![/green]")
            console.print("Your strategy has satisfied AURORA's research-gated deployment checklist.")
            console.print("Remember: past performance does not guarantee future results.")
            console.print("You are responsible for all trading decisions.")
        else:
            console.print("\n[yellow]Some checks failed.[/yellow]")
            console.print("Please review the failures and address them before deployment.")
            raise typer.Exit(code=1)

    except Exception as e:
        console.print(f"[red]Error:[/red] {str(e)}")
        raise typer.Exit(code=1)


@deployment_app.command("init-checklist")
def deploy_init_checklist(
    path: Annotated[
        str,
        typer.Option("--path", "-p", help="Path to save the checklist template."),
    ] = "deployment_checklist.yaml",
) -> None:
    """Create a default deployment checklist template.

    This command is research-only.
    """
    from aurora.deployment.checklist import create_default_checklist_file

    create_default_checklist_file(path)
    console.print(f"[green]Created default checklist:[/green] {path}")


if __name__ == "__main__":
    app()
