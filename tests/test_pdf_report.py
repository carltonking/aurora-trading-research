"""Tests for PDF report generation."""

import pytest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
import json


def test_generate_pdf_no_fpdf() -> None:
    """Test that PDF generation fails when fpdf2 is not available."""
    from aurora.reporting import pdf_report

    original_available = pdf_report.FPDF_AVAILABLE
    pdf_report.FPDF_AVAILABLE = False

    try:
        from aurora.reporting.readiness_report import ReadinessReport

        report = ReadinessReport(
            strategy_name="test_strategy",
            generated_at="2024-01-01",
        )

        with pytest.raises(ImportError, match="fpdf2 is not installed"):
            pdf_report.generate_pdf(report, "/tmp/test.pdf")
    finally:
        pdf_report.FPDF_AVAILABLE = original_available


def test_fpdf_available_flag() -> None:
    """Test that FPDF_AVAILABLE flag exists and is a boolean."""
    from aurora.reporting import pdf_report

    assert isinstance(pdf_report.FPDF_AVAILABLE, bool)


def test_mandatory_disclaimer_exists() -> None:
    """Test that mandatory disclaimer is defined."""
    from aurora.reporting import pdf_report

    assert pdf_report.MANDATORY_DISCLAIMER
    assert len(pdf_report.MANDATORY_DISCLAIMER) > 50
    assert "DISCLAIMER" in pdf_report.MANDATORY_DISCLAIMER


def test_page_footer_disclaimer_exists() -> None:
    """Test that page footer disclaimer is defined."""
    from aurora.reporting import pdf_report

    assert pdf_report.PAGE_FOOTER_DISCLAIMER
    assert len(pdf_report.PAGE_FOOTER_DISCLAIMER) > 10


def test_generate_pdf_basic() -> None:
    """Test basic PDF generation when fpdf2 is available."""
    pytest.importorskip("fpdf")

    from aurora.reporting import pdf_report
    from aurora.reporting.readiness_report import ReadinessReport
    from aurora.analysis.paper_performance import PaperMetrics

    report = ReadinessReport(
        strategy_name="test_strategy",
        generated_at="2024-01-01",
        backtest_summary={"total_return": 0.15, "sharpe": 1.2},
        overall_assessment="Assessment text",
    )

    output_path = "/tmp/test_pdf_basic.pdf"
    result = pdf_report.generate_pdf(report, output_path)

    assert Path(output_path).exists()
    assert Path(output_path).stat().st_size > 0


def test_generate_pdf_with_charts() -> None:
    """Test PDF generation with chart images when fpdf2 is available."""
    pytest.importorskip("fpdf")

    from aurora.reporting import pdf_report
    from aurora.reporting.readiness_report import ReadinessReport

    report = ReadinessReport(
        strategy_name="test_strategy",
        generated_at="2024-01-01",
    )

    import tempfile
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots()
    ax.plot([1, 2, 3], [1, 2, 3])
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        plt.savefig(tmp.name)
        chart_path = tmp.name
    plt.close(fig)

    output_path = "/tmp/test_pdf_with_charts.pdf"
    result = pdf_report.generate_pdf(
        report,
        output_path,
        include_charts=True,
        chart_images=[chart_path],
    )

    assert Path(output_path).exists()


def test_generate_pdf_paper_performance() -> None:
    """Test PDF generation includes paper performance section."""
    pytest.importorskip("fpdf")

    from aurora.reporting import pdf_report
    from aurora.reporting.readiness_report import ReadinessReport
    from aurora.analysis.paper_performance import PaperMetrics

    report = ReadinessReport(
        strategy_name="test_strategy",
        generated_at="2024-01-01",
        paper_performance=PaperMetrics(
            strategy_name="test",
            total_trades=100,
            win_count=60,
            loss_count=40,
            win_rate=0.6,
            total_pnl=5000.0,
            avg_pnl_per_trade=50.0,
            max_drawdown=0.15,
            sharpe_ratio=1.5,
            profit_factor=2.0,
        ),
    )

    output_path = "/tmp/test_pdf_paper.pdf"
    result = pdf_report.generate_pdf(report, output_path)

    assert Path(output_path).exists()
    assert Path(output_path).stat().st_size > 0


def test_disclaimer_in_pdf() -> None:
    """Test that disclaimer appears in the PDF content."""
    pytest.importorskip("fpdf")

    from aurora.reporting import pdf_report
    from aurora.reporting.readiness_report import ReadinessReport

    report = ReadinessReport(
        strategy_name="test_strategy",
        generated_at="2024-01-01",
    )

    output_path = "/tmp/test_pdf_disclaimer.pdf"
    result = pdf_report.generate_pdf(report, output_path)

    with open(output_path, "rb") as f:
        content = f.read()

    assert b"DISCLAIMER" in content or b"research" in content.lower()