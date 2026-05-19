"""Static safety boundary audit reporting."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any

from aurora.reporting.exceptions import AuroraReportingError
from aurora.reporting.reports import save_json_report

SAFETY_AUDIT_PASS = "PASS"
SAFETY_AUDIT_WARN = "WARN"
SAFETY_AUDIT_FAIL = "FAIL"

AUDIT_WARNING = "WARNING"
AUDIT_CRITICAL = "CRITICAL"

SAFETY_AUDIT_JSON_FILENAME = "safety_audit.json"
SAFETY_AUDIT_MARKDOWN_FILENAME = "safety_audit.md"

SAFETY_AUDIT_FLAGS = {
    "safety_audit_only": True,
    "placed_orders": False,
    "used_broker": False,
    "wrote_ledger": False,
    "external_llm_calls": False,
}

SUPPORTED_SUFFIXES = {".py", ".md", ".toml", ".yaml", ".yml", ".txt"}
DEFAULT_ALLOWLISTED_PATHS = [
    "src/aurora/brokers/base.py",
    "src/aurora/brokers/alpaca_paper.py",
    "src/aurora/execution",
    "src/aurora/risk",
    "src/aurora/readiness",
    "src/aurora/review",
    "src/aurora/strategies/prompt_lab.py",
    "src/aurora/reporting/safety_audit.py",
    "tests",
]
NEGATED_CONTEXT_MARKERS = (
    "no ",
    "not ",
    "does not",
    "do not",
    "without ",
    "never ",
    "unsupported",
    "not supported",
    "reject",
    "rejected",
    "prohibit",
    "must not",
    "approve live trading",
    "approving live trading",
)


@dataclass(frozen=True)
class SafetyAuditFinding:
    """Single static safety audit finding."""

    code: str
    severity: str
    file_path: str
    line_number: int | None
    message: str
    matched_text: str | None = None


@dataclass(frozen=True)
class SafetyAuditConfig:
    """Configuration for a local static safety boundary audit."""

    source_dir: str = "src/aurora"
    output_dir: str = "data/status"
    include_tests: bool = False
    fail_on_critical: bool = True
    allowlisted_paths: list[str] | None = None


@dataclass(frozen=True)
class SafetyAuditResult:
    """Result from a static safety boundary audit."""

    status: str
    audited_at: str
    source_dir: str
    output_dir: str
    json_path: str
    markdown_path: str
    files_scanned: int
    findings: list[SafetyAuditFinding]
    safety_flags: dict[str, Any]


class SafetyAuditError(AuroraReportingError):
    """Raised when a safety audit cannot be completed."""


@dataclass(frozen=True)
class _PatternRule:
    code: str
    severity: str
    text: str
    message: str


def run_safety_boundary_audit(config: SafetyAuditConfig) -> SafetyAuditResult:
    """Run deterministic static scanning for risky boundary patterns."""
    source_dir = Path(config.source_dir)
    if not source_dir.exists() or not source_dir.is_dir():
        raise SafetyAuditError(f"Source directory not found: {source_dir}")

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    findings: list[SafetyAuditFinding] = []
    files_scanned = 0
    allowlisted_paths = list(DEFAULT_ALLOWLISTED_PATHS)
    if config.allowlisted_paths:
        allowlisted_paths.extend(config.allowlisted_paths)

    for path in _iter_scannable_files(source_dir, config.include_tests):
        text = _read_text(path)
        if text is None:
            continue
        files_scanned += 1
        findings.extend(_scan_file(path, text, allowlisted_paths))

    status = _audit_status(findings, config.fail_on_critical)
    result = SafetyAuditResult(
        status=status,
        audited_at=datetime.now(UTC).isoformat(),
        source_dir=str(source_dir),
        output_dir=str(output_dir),
        json_path=str(output_dir / SAFETY_AUDIT_JSON_FILENAME),
        markdown_path=str(output_dir / SAFETY_AUDIT_MARKDOWN_FILENAME),
        files_scanned=files_scanned,
        findings=findings,
        safety_flags=dict(SAFETY_AUDIT_FLAGS),
    )
    save_safety_audit_json(result, result.json_path)
    Path(result.markdown_path).write_text(render_safety_audit_markdown(result), encoding="utf-8")
    return result


def safety_audit_result_to_dict(result: SafetyAuditResult) -> dict[str, Any]:
    """Convert a safety audit result to a JSON-serializable dictionary."""
    return asdict(result)


def render_safety_audit_markdown(result: SafetyAuditResult) -> str:
    """Render a safety audit result as Markdown."""
    lines = [
        "# AURORA Safety Boundary Audit",
        "",
        f"Audited: {result.audited_at}",
        f"Status: {result.status}",
        f"Files scanned: {result.files_scanned}",
        "",
        (
            "This safety audit is static analysis only. It does not trade, place orders, "
            "call brokers, call external APIs, or approve live trading."
        ),
        "",
        "## Findings",
        "",
    ]
    if not result.findings:
        lines.append("- No findings.")
    else:
        for finding in result.findings:
            location = finding.file_path
            if finding.line_number is not None:
                location = f"{location}:{finding.line_number}"
            lines.append(f"- {finding.severity} `{finding.code}` at `{location}`")
            lines.append(f"  - {finding.message}")
            if finding.matched_text:
                lines.append(f"  - matched: `{finding.matched_text}`")
    lines.append("")
    return "\n".join(lines)


def save_safety_audit_json(result: SafetyAuditResult, path: str | Path) -> None:
    """Save a safety audit JSON artifact."""
    save_json_report(safety_audit_result_to_dict(result), path)


def _iter_scannable_files(source_dir: Path, include_tests: bool) -> list[Path]:
    files: list[Path] = []
    for path in sorted(source_dir.rglob("*")):
        if not path.is_file():
            continue
        if _has_hidden_part(path, source_dir):
            continue
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        if not include_tests and _is_test_path(path, source_dir):
            continue
        files.append(path)
    return files


def _scan_file(
    path: Path,
    text: str,
    allowlisted_paths: list[str],
) -> list[SafetyAuditFinding]:
    findings: list[SafetyAuditFinding] = []
    allowlisted = _is_allowlisted(path, allowlisted_paths)
    for line_number, line in enumerate(text.splitlines(), start=1):
        line_findings = _scan_line(path, line_number, line, allowlisted)
        findings.extend(line_findings)
    return findings


def _scan_line(
    path: Path,
    line_number: int,
    line: str,
    allowlisted: bool,
) -> list[SafetyAuditFinding]:
    findings: list[SafetyAuditFinding] = []
    for rule in _pattern_rules():
        match = re.search(re.escape(rule.text), line, flags=re.IGNORECASE)
        if match is None:
            continue
        if _is_negated_safety_context(line, match.start(), rule.text):
            continue
        severity = rule.severity
        if severity == AUDIT_CRITICAL and allowlisted:
            severity = AUDIT_WARNING
        findings.append(
            SafetyAuditFinding(
                code=rule.code,
                severity=severity,
                file_path=str(path),
                line_number=line_number,
                message=rule.message,
                matched_text=match.group(0),
            )
        )
    return findings


def _pattern_rules() -> list[_PatternRule]:
    return [
        _critical("potential_order_placement", _join("submit", "_order")),
        _critical("potential_order_placement", _join("place", "_order")),
        _critical("potential_order_placement", _join("create", "_order")),
        _critical("potential_order_placement", _join("market", "_order")),
        _critical("potential_order_placement", _join("limit", "_order")),
        _critical("potential_live_trading", _join("live", " trading")),
        _critical("potential_real_money_trading", _join("real", " money")),
        _critical("broker_api_integration", _join("alpaca", ".trading")),
        _critical("broker_api_integration", _join("Trading", "Client")),
        _critical("broker_api_integration", _join("Interactive", "Brokers")),
        _critical("broker_api_integration", _join("ib", "_insync")),
        _critical("broker_api_integration", "ccxt"),
        _critical("external_llm_or_api_call", _join("open", "ai")),
        _critical("external_llm_or_api_call", _join("anth", "ropic")),
        _critical("external_llm_or_api_call", _join("chat", ".completions")),
        _critical("external_llm_or_api_call", _join("responses", ".create")),
        _critical("external_llm_or_api_call", _join("requests", ".post")),
        _critical("external_llm_or_api_call", _join("requests", ".get")),
        _critical("external_llm_or_api_call", _join("httpx", ".")),
        _critical("external_llm_or_api_call", _join("urllib", ".request")),
        _critical("direct_ledger_write_path", _join("orders", ".jsonl")),
        _critical("direct_ledger_write_path", _join("risk", "_decisions.jsonl")),
        _critical("direct_ledger_write_path", _join("positions", ".json")),
        _critical("direct_ledger_write_path", _join("account", ".json")),
        _warning("profitability_claim", _join("guaranteed", " profit")),
        _warning("profitability_claim", _join("risk", "-free")),
        _warning("profitability_claim", _join("cannot", " lose")),
        _warning("profitability_claim", _join("sure", " thing")),
        _warning("profitability_claim", _join("guaranteed", " return")),
        _warning("ambiguous_execution_language", _join("execute", " trade")),
        _warning("ambiguous_execution_language", _join("send", " order")),
        _warning("ambiguous_execution_language", _join("broker", " execution")),
        _warning("ambiguous_execution_language", _join("go", " live")),
    ]


def _critical(code: str, text: str) -> _PatternRule:
    return _PatternRule(code, AUDIT_CRITICAL, text, f"Critical safety pattern found: {text}.")


def _warning(code: str, text: str) -> _PatternRule:
    return _PatternRule(code, AUDIT_WARNING, text, f"Risky or ambiguous pattern found: {text}.")


def _audit_status(findings: list[SafetyAuditFinding], fail_on_critical: bool) -> str:
    has_critical = any(finding.severity == AUDIT_CRITICAL for finding in findings)
    if has_critical and fail_on_critical:
        return SAFETY_AUDIT_FAIL
    if findings:
        return SAFETY_AUDIT_WARN
    return SAFETY_AUDIT_PASS


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def _has_hidden_part(path: Path, source_dir: Path) -> bool:
    try:
        parts = path.relative_to(source_dir).parts
    except ValueError:
        parts = path.parts
    return any(part.startswith(".") for part in parts)


def _is_test_path(path: Path, source_dir: Path) -> bool:
    try:
        relative_parts = path.relative_to(source_dir).parts
    except ValueError:
        relative_parts = path.parts
    return "tests" in relative_parts or (path.name.startswith("test_") and path.suffix == ".py")


def _is_allowlisted(path: Path, allowlisted_paths: list[str]) -> bool:
    path_resolved = _safe_resolve(path)
    path_text = path_resolved.as_posix()
    for raw_allowlisted in allowlisted_paths:
        allowlisted = Path(raw_allowlisted)
        allowlisted_text = allowlisted.as_posix().rstrip("/")
        if allowlisted.is_absolute():
            allowlisted_resolved = _safe_resolve(allowlisted)
            if path_resolved == allowlisted_resolved or allowlisted_resolved in path_resolved.parents:
                return True
        elif allowlisted_text and allowlisted_text in path_text:
            return True
    return False


def _is_negated_safety_context(line: str, start_index: int, pattern: str) -> bool:
    if pattern not in {"live trading", "real money", "broker execution", "go live"}:
        return False
    lower_line = line.lower()
    context_start = max(0, start_index - 80)
    context = lower_line[context_start : start_index + len(pattern) + 40]
    return any(marker in context for marker in NEGATED_CONTEXT_MARKERS)


def _safe_resolve(path: Path) -> Path:
    try:
        return path.resolve()
    except OSError:
        return path.absolute()


def _join(*parts: str) -> str:
    return "".join(parts)
