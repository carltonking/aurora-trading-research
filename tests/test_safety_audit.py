import json
from pathlib import Path

from typer.testing import CliRunner

from aurora.cli.app import app
from aurora.reporting.safety_audit import (
    AUDIT_CRITICAL,
    AUDIT_WARNING,
    SAFETY_AUDIT_FAIL,
    SAFETY_AUDIT_PASS,
    SAFETY_AUDIT_WARN,
    SafetyAuditConfig,
    run_safety_boundary_audit,
    safety_audit_result_to_dict,
)


def test_clean_source_tree_produces_pass(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def answer() -> int:\n    return 42\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )

    assert result.status == SAFETY_AUDIT_PASS
    assert result.files_scanned == 1
    assert result.findings == []


def test_submit_order_pattern_produces_fail_when_critical_fails(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "broker.py", "client.submit_order(symbol='SPY')\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )

    assert result.status == SAFETY_AUDIT_FAIL
    assert _has_finding(result, "potential_order_placement", AUDIT_CRITICAL)


def test_profitability_claim_produces_warn(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "README.md", "This is not a guaranteed profit system.\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )

    assert result.status == SAFETY_AUDIT_WARN
    assert _has_finding(result, "profitability_claim", AUDIT_WARNING)


def test_allowlisted_path_downgrades_critical_to_warning(tmp_path) -> None:
    source_dir = tmp_path / "src"
    allowed_dir = source_dir / "local_only"
    _write_text(allowed_dir / "broker.py", "client.submit_order(symbol='SPY')\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(
            source_dir=str(source_dir),
            output_dir=str(tmp_path / "status"),
            allowlisted_paths=[str(allowed_dir)],
        )
    )

    assert result.status == SAFETY_AUDIT_WARN
    assert _has_finding(result, "potential_order_placement", AUDIT_WARNING)
    assert not _has_finding(result, "potential_order_placement", AUDIT_CRITICAL)


def test_include_tests_false_excludes_test_files_and_tests_directories(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")
    _write_text(source_dir / "test_bad.py", "client.submit_order(symbol='SPY')\n")
    _write_text(source_dir / "tests" / "test_bad.py", "client.submit_order(symbol='QQQ')\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )

    assert result.status == SAFETY_AUDIT_PASS
    assert result.files_scanned == 1
    assert result.findings == []


def test_include_tests_true_scans_test_files(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")
    _write_text(source_dir / "tests" / "test_bad.py", "client.submit_order(symbol='SPY')\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(
            source_dir=str(source_dir),
            output_dir=str(tmp_path / "status"),
            include_tests=True,
        )
    )

    assert result.status == SAFETY_AUDIT_WARN
    assert result.files_scanned == 2
    assert _has_finding(result, "potential_order_placement", AUDIT_WARNING)


def test_json_and_markdown_reports_are_written(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )

    assert Path(result.json_path).exists()
    assert Path(result.markdown_path).exists()


def test_json_contains_safety_flags(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )
    payload = json.loads(Path(result.json_path).read_text(encoding="utf-8"))

    assert payload["safety_flags"]["safety_audit_only"] is True
    assert payload["safety_flags"]["placed_orders"] is False
    assert payload["safety_flags"]["used_broker"] is False
    assert payload["safety_flags"]["wrote_ledger"] is False
    assert payload["safety_flags"]["external_llm_calls"] is False


def test_markdown_contains_static_analysis_safety_statement(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )
    markdown = Path(result.markdown_path).read_text(encoding="utf-8")

    assert (
        "This safety audit is static analysis only. It does not trade, place orders, "
        "call brokers, call external APIs, or approve live trading."
    ) in markdown


def test_safety_audit_result_to_dict_is_json_serializable(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")

    result = run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "status"))
    )
    payload = safety_audit_result_to_dict(result)
    encoded = json.dumps(payload)

    assert "safety_audit_only" in encoded
    assert "PASS" in encoded


def test_cli_reports_safety_audit_smoke(tmp_path) -> None:
    source_dir = tmp_path / "src"
    output_dir = tmp_path / "status"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")
    runner = CliRunner()

    result = runner.invoke(
        app,
        [
            "reports",
            "safety-audit",
            "--source-dir",
            str(source_dir),
            "--output-dir",
            str(output_dir),
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Safety audit is static analysis only" in result.output
    assert "PASS" in result.output
    assert "safety_audit.json" in result.output
    assert "safety_audit.md" in result.output


def test_safety_audit_does_not_create_ledger_files(tmp_path) -> None:
    source_dir = tmp_path / "src"
    _write_text(source_dir / "module.py", "def clean() -> bool:\n    return True\n")

    run_safety_boundary_audit(
        SafetyAuditConfig(source_dir=str(source_dir), output_dir=str(tmp_path / "data" / "status"))
    )

    ledger_dir = tmp_path / "data" / "ledger"
    assert not (ledger_dir / "orders.jsonl").exists()
    assert not (ledger_dir / "risk_decisions.jsonl").exists()
    assert not (ledger_dir / "account.json").exists()
    assert not (ledger_dir / "positions.json").exists()


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _has_finding(result, code: str, severity: str) -> bool:
    return any(finding.code == code and finding.severity == severity for finding in result.findings)
