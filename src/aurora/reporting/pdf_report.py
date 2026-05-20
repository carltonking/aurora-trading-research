"""PDF report generation for readiness reports.

This module provides PDF export using fpdf2 (pure Python).
PDFs are research-only and include mandatory disclaimers.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

logger = logging.getLogger(__name__)

try:
    from fpdf import FPDF
    FPDF_AVAILABLE = True
except ImportError:
    FPDF_AVAILABLE = False
    logger.warning("fpdf2 not available. PDF generation will fail.")


MANDATORY_DISCLAIMER = (
    "DISCLAIMER: This report is for research and educational purposes only. "
    "Past performance does not guarantee future results. This is not investment advice. "
    "No profitability is guaranteed or implied. Paper trading results are simulated "
    "and may not reflect actual market conditions. Always conduct your own due diligence."
)

PAGE_FOOTER_DISCLAIMER = (
    "This document is a research artifact. Not for trading. "
    "No guarantees of profitability."
)


if FPDF_AVAILABLE:
    class ReadinessPDF(FPDF):
        """Custom PDF class for readiness reports with footer."""

        def __init__(self) -> None:
            super().__init__()
            self.set_auto_page_break(auto=True, margin=15)

        def footer(self) -> None:
            self.set_y(-15)
            self.set_font("Helvetica", size=8)
            self.multi_cell(0, 4, PAGE_FOOTER_DISCLAIMER)


def generate_pdf(
    report: " ReadinessReport",
    output_path: str,
    include_charts: bool = False,
    chart_images: list[str] | None = None,
) -> Path:
    """Generate a PDF report from a ReadinessReport.

    Args:
        report: The readiness report to export.
        output_path: Path to save the PDF file.
        include_charts: Whether to include chart images.
        chart_images: List of paths to PNG chart images.

    Returns:
        Path to the generated PDF.

    Raises:
        ImportError: If fpdf2 is not available.
    """
    if not FPDF_AVAILABLE:
        raise ImportError(
            "fpdf2 is not installed. Install with: pip install fpdf2"
        )

    pdf = ReadinessPDF()
    pdf.add_page()

    pdf.set_font("Helvetica", size=24, style="B")
    pdf.cell(0, 20, "AURORA Readiness Report", ln=True, align="C")
    pdf.ln(10)

    pdf.set_font("Helvetica", size=14)
    pdf.cell(0, 10, f"Strategy: {report.strategy_name}", ln=True)
    pdf.cell(0, 10, f"Generated: {report.generated_at}", ln=True)
    pdf.ln(5)

    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 5, MANDATORY_DISCLAIMER)
    pdf.ln(10)

    pdf.set_font("Helvetica", size=12, style="B")
    pdf.cell(0, 10, "Backtest Summary", ln=True)
    pdf.set_font("Courier", size=9)
    _write_dict_as_table(pdf, report.backtest_summary)
    pdf.ln(5)

    pdf.add_page()
    pdf.set_font("Helvetica", size=12, style="B")
    pdf.cell(0, 10, "Walk-Forward Summary", ln=True)
    pdf.set_font("Courier", size=9)
    _write_dict_as_table(pdf, report.walk_forward_summary)
    pdf.ln(5)

    if report.paper_performance:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12, style="B")
        pdf.cell(0, 10, "Paper Trading Performance", ln=True)
        pdf.set_font("Courier", size=9)

        pm = report.paper_performance
        paper_data = {
            "Total Trades": str(pm.total_trades),
            "Win Rate": f"{pm.win_rate:.2%}",
            "Total P&L": f"${pm.total_pnl:.2f}",
            "Max Drawdown": f"{pm.max_drawdown:.2%}",
            "Sharpe Ratio": f"{pm.sharpe_ratio:.3f}",
            "Profit Factor": f"{pm.profit_factor:.3f}",
        }
        _write_dict_as_table(pdf, paper_data)
        pdf.ln(5)

    if report.optimization_proposal:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12, style="B")
        pdf.cell(0, 10, "Optimization Proposal", ln=True)
        pdf.set_font("Courier", size=9)

        proposal = report.optimization_proposal
        opt_data = {
            "Status": proposal.status,
            "Confidence": f"{proposal.confidence:.2f}" if proposal.confidence else "N/A",
            "Rationale": proposal.rationale[:100] + "..." if len(proposal.rationale) > 100 else proposal.rationale,
        }
        _write_dict_as_table(pdf, opt_data)
        pdf.ln(5)

    pdf.add_page()
    pdf.set_font("Helvetica", size=12, style="B")
    pdf.cell(0, 10, "Overall Assessment", ln=True)
    pdf.set_font("Helvetica", size=10)
    pdf.multi_cell(0, 5, report.overall_assessment or "No assessment provided.")
    pdf.ln(10)

    if report.disclaimer:
        pdf.set_font("Helvetica", size=9, style="I")
        pdf.multi_cell(0, 5, f"Note: {report.disclaimer}")

    if include_charts and chart_images:
        pdf.add_page()
        pdf.set_font("Helvetica", size=12, style="B")
        pdf.cell(0, 10, "Performance Charts", ln=True)
        pdf.ln(5)

        for chart_path in chart_images:
            if Path(chart_path).exists():
                try:
                    pdf.image(chart_path, w=180)
                    pdf.ln(5)
                except Exception as e:
                    logger.warning(f"Could not embed chart {chart_path}: {e}")

    output_file = Path(output_path)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(output_file))

    logger.info(f"PDF report saved to {output_file}")
    return output_file


def _write_dict_as_table(pdf: "ReadinessPDF", data: dict[str, Any]) -> None:
    """Write a dictionary as a simple key-value table."""
    if not data:
        pdf.cell(0, 5, "No data available.", ln=True)
        return

    for key, value in data.items():
        if value is not None:
            key_str = str(key)
            val_str = str(value)
            pdf.cell(50, 5, key_str + ":", border=0)
            pdf.cell(0, 5, val_str, ln=True)