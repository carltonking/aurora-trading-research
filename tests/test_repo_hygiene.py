import re
from pathlib import Path


def test_env_example_exists_and_has_no_obvious_real_secrets() -> None:
    env_example = Path(".env.example")

    assert env_example.exists()
    content = env_example.read_text(encoding="utf-8")
    assert "Do not commit real API keys or secrets" in content
    assert "do not support live trading" in content
    assert "ALPACA_API_KEY" not in content
    assert "ALPACA_SECRET_KEY" not in content
    assert not re.search(r"(?i)(api[_-]?key|secret|token)\s*=\s*\S+", content)


def test_readme_mentions_core_safety_disclaimers() -> None:
    content = Path("README.md").read_text(encoding="utf-8").lower()

    assert "paper-trading-first" in content
    assert "does not support live trading" in content
    assert "not profitability guarantees" in content
    assert "do not commit" in content and "api" in content
    assert "not provide financial advice" in content


def test_safety_doc_exists_and_mentions_boundaries() -> None:
    safety_doc = Path("docs/SAFETY.md")

    assert safety_doc.exists()
    content = safety_doc.read_text(encoding="utf-8").lower()
    assert "no live trading" in content
    assert "no real broker execution" in content
    assert "no direct order placement from prompts" in content
    assert "no real api keys" in content


def test_paper_broker_integration_design_doc_is_safety_only() -> None:
    design_doc = Path("docs/PAPER_BROKER_INTEGRATION.md")

    assert design_doc.exists()
    content = design_doc.read_text(encoding="utf-8")
    lowered = content.lower()
    assert "no live trading is implemented" in lowered
    assert "no broker adapter is implemented by this document" in lowered
    assert "riskmanager" in lowered
    assert "paper-only by default" in lowered
    assert not re.search(r"(?i)(api[_-]?key|secret|token)\s*=\s*\S+", content)
    assert not re.search(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]{16,}", content)
    assert "sk-" not in lowered


def test_release_package_docs_exist_and_do_not_approve_live_trading() -> None:
    release_docs = [
        Path("CHANGELOG.md"),
        Path("RELEASE_NOTES.md"),
        Path("docs/RELEASE_CHECKLIST.md"),
    ]

    for path in release_docs:
        assert path.exists()
        content = path.read_text(encoding="utf-8").lower()
        assert "approved for live trading" not in content
        assert "live trading approved" not in content
