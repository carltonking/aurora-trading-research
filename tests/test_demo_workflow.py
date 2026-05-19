import json
from pathlib import Path

from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.demo.workflow import (
    DEMO_SAFETY_FLAGS,
    DemoWorkflowConfig,
    demo_workflow_result_to_dict,
    run_demo_workflow,
)


LEDGER_FILENAMES = [
    "orders.jsonl",
    "risk_decisions.jsonl",
    "account.json",
    "positions.json",
]


def test_demo_workflow_writes_synthetic_data_and_artifacts(tmp_path, monkeypatch) -> None:
    _forbid_network_and_execution(monkeypatch)
    output_root = tmp_path / "demo"

    result = run_demo_workflow(
        DemoWorkflowConfig(
            output_root=str(output_root),
            rows=260,
            latest_test_count=247,
            create_packet_zip=True,
            run_safety_audit=True,
        )
    )

    expected_paths = [
        Path(result.manifest_path),
        Path(result.review_path),
        Path(result.readiness_path),
        Path(result.plan_path),
        Path(result.packet_manifest_path),
        Path(result.status_json_path),
        Path(result.status_markdown_path),
        Path(result.safety_audit_json_path),
        Path(result.safety_audit_markdown_path),
    ]
    for path in expected_paths:
        assert path.exists(), path

    cache_files = list((output_root / "data" / "cache").glob("*.csv"))
    assert len(cache_files) == 1
    assert "yfinance_dia-qqq-spy_2020-01-01_none_1d" in cache_files[0].stem
    assert Path(result.packet_zip_path).exists()

    payloads = [
        _read_json(result.manifest_path),
        _read_json(result.review_path),
        _read_json(result.readiness_path),
        _read_json(result.plan_path),
        _read_json(result.packet_manifest_path),
        _read_json(result.status_json_path),
        _read_json(result.safety_audit_json_path),
    ]
    for payload in payloads:
        json.dumps(payload)

    assert result.safety_flags == DEMO_SAFETY_FLAGS
    _assert_no_execution_flags(result.safety_flags)
    _assert_no_ledger_artifacts(output_root)


def test_demo_workflow_packet_zip_can_be_disabled(tmp_path, monkeypatch) -> None:
    _forbid_network_and_execution(monkeypatch)
    output_root = tmp_path / "demo"

    result = run_demo_workflow(
        DemoWorkflowConfig(
            output_root=str(output_root),
            create_packet_zip=False,
            run_safety_audit=False,
        )
    )

    assert result.packet_zip_path is None
    assert not (Path(result.research_run_dir) / "artifact_packet.zip").exists()
    assert result.safety_audit_json_path is None
    assert result.safety_audit_markdown_path is None
    _assert_no_ledger_artifacts(output_root)


def test_demo_workflow_result_is_json_serializable(tmp_path, monkeypatch) -> None:
    _forbid_network_and_execution(monkeypatch)
    result = run_demo_workflow(
        DemoWorkflowConfig(
            output_root=str(tmp_path / "demo"),
            symbols=["SPY", "QQQ", "SPY"],
            create_packet_zip=False,
            run_safety_audit=False,
        )
    )

    payload = demo_workflow_result_to_dict(result)

    assert payload["symbols"] == ["SPY", "QQQ"]
    json.dumps(payload)


def test_cli_demo_run_smoke(tmp_path, monkeypatch) -> None:
    _forbid_network_and_execution(monkeypatch)
    output_root = tmp_path / "demo_cli"
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "demo",
            "run",
            "--output-root",
            str(output_root),
            "--latest-test-count",
            "247",
            "--no-run-safety-audit",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Demo workflow uses synthetic local data only." in result.output
    assert "manifest_path" in result.output
    assert (output_root / "research_runs").exists()
    _assert_no_ledger_artifacts(output_root)


def _forbid_network_and_execution(monkeypatch) -> None:
    class Forbidden:
        def __init__(self, *args, **kwargs) -> None:
            raise AssertionError("demo workflow must not instantiate network or execution APIs")

    monkeypatch.setattr("aurora.research.run.YFinanceDataSource", Forbidden)
    monkeypatch.setattr("aurora.execution.simulation_broker.SimulationBroker", Forbidden)
    monkeypatch.setattr("aurora.execution.ledger.PaperLedger", Forbidden)


def _read_json(path: str | None) -> dict:
    assert path is not None
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _assert_no_execution_flags(flags: dict) -> None:
    assert flags["placed_orders"] is False
    assert flags["used_broker"] is False
    assert flags["wrote_ledger"] is False
    assert flags["external_llm_calls"] is False


def _assert_no_ledger_artifacts(output_root: Path) -> None:
    candidate_dirs = [
        output_root / "data" / "ledger",
        output_root / "ledger",
        output_root / "research_runs" / "ledger",
    ]
    for ledger_dir in candidate_dirs:
        for filename in LEDGER_FILENAMES:
            assert not (ledger_dir / filename).exists()
