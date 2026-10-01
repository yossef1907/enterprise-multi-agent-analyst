"""PDF report builder — generates a valid binary PDF using ReportLab.

The previous implementation wrote plain UTF-8 text with a .pdf extension,
which browsers rejected with "Failed to load PDF document". This module
produces a proper PDF/1.4-compliant binary file.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

# ── ReportLab imports ──────────────────────────────────────────────────────
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    Image,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

# ── Brand palette ──────────────────────────────────────────────────────────
BRAND_PURPLE = colors.HexColor("#7c3aed")
BRAND_PURPLE_LIGHT = colors.HexColor("#ede9fe")
BRAND_DARK = colors.HexColor("#1a1830")
BRAND_GREY = colors.HexColor("#6b6585")
BRAND_BORDER = colors.HexColor("#e4e2f0")
WHITE = colors.white


def _extract_text(item: Any) -> str:
    if isinstance(item, dict):
        cat = item.get("category", "INSIGHT")
        txt = item.get("text", "")
        return f"[{cat}] {txt}"
    return str(item)


def _styles() -> dict:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            fontName="Helvetica-Bold",
            fontSize=20,
            textColor=BRAND_DARK,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            fontName="Helvetica",
            fontSize=10,
            textColor=BRAND_GREY,
            spaceAfter=4,
            alignment=TA_CENTER,
        ),
        "section": ParagraphStyle(
            "SectionHeader",
            fontName="Helvetica-Bold",
            fontSize=12,
            textColor=BRAND_PURPLE,
            spaceBefore=14,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "BodyText",
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND_DARK,
            leading=14,
            spaceAfter=4,
        ),
        "mono": ParagraphStyle(
            "MonoText",
            fontName="Courier",
            fontSize=8,
            textColor=BRAND_DARK,
            leading=12,
            spaceAfter=2,
        ),
        "caption": ParagraphStyle(
            "Caption",
            fontName="Helvetica-Oblique",
            fontSize=8,
            textColor=BRAND_GREY,
            spaceAfter=6,
            alignment=TA_CENTER,
        ),
        "kpi_value": ParagraphStyle(
            "KPIValue",
            fontName="Helvetica-Bold",
            fontSize=11,
            textColor=BRAND_DARK,
            alignment=TA_RIGHT,
        ),
        "kpi_label": ParagraphStyle(
            "KPILabel",
            fontName="Helvetica",
            fontSize=9,
            textColor=BRAND_GREY,
            alignment=TA_LEFT,
        ),
    }


def _kpi_table(kpis: dict, st: dict) -> Table:
    """Build a styled KPI metrics table."""
    rev = float(kpis.get("total_revenue", 0) or 0)
    orders = int(kpis.get("total_orders", 0) or 0)
    customers = int(kpis.get("unique_customers", 0) or 0)
    aov = float(kpis.get("average_order_value", 0) or 0)
    products = int(kpis.get("unique_products", 0) or 0)
    d_start = kpis.get("date_start", "N/A")
    d_end = kpis.get("date_end", "N/A")

    rows = [
        # header
        [
            Paragraph("<b>Metric</b>", st["body"]),
            Paragraph("<b>Value</b>", st["body"]),
            Paragraph("<b>Period</b>", st["body"]),
        ],
        [
            Paragraph("Total Revenue", st["kpi_label"]),
            Paragraph(f"${rev:,.2f}", st["kpi_value"]),
            Paragraph(f"{d_start} → {d_end}", st["body"]),
        ],
        [
            Paragraph("Total Orders", st["kpi_label"]),
            Paragraph(f"{orders:,}", st["kpi_value"]),
            Paragraph("Unique invoice numbers", st["body"]),
        ],
        [
            Paragraph("Unique Customers", st["kpi_label"]),
            Paragraph(f"{customers:,}", st["kpi_value"]),
            Paragraph("Distinct CustomerIDs", st["body"]),
        ],
        [
            Paragraph("Average Order Value", st["kpi_label"]),
            Paragraph(f"${aov:,.2f}", st["kpi_value"]),
            Paragraph("Revenue ÷ Orders", st["body"]),
        ],
        [
            Paragraph("Unique Products", st["kpi_label"]),
            Paragraph(f"{products:,}", st["kpi_value"]),
            Paragraph("Distinct StockCodes", st["body"]),
        ],
    ]

    col_widths = [7 * cm, 5 * cm, 6 * cm]
    tbl = Table(rows, colWidths=col_widths, repeatRows=1)
    tbl.setStyle(
        TableStyle([
            # Header row
            ("BACKGROUND", (0, 0), (-1, 0), BRAND_PURPLE),
            ("TEXTCOLOR", (0, 0), (-1, 0), WHITE),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, 0), 9),
            # Alternating rows
            ("BACKGROUND", (0, 1), (-1, -1), WHITE),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, BRAND_PURPLE_LIGHT]),
            # Grid
            ("GRID", (0, 0), (-1, -1), 0.4, BRAND_BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ])
    )
    return tbl


def build_pdf(results: dict, charts: list, output_path: str | Path) -> str:
    """Generate a professional binary PDF report using ReportLab.

    Parameters
    ----------
    results:     Pipeline state dict containing kpis, insights, report_summary, etc.
    charts:      List of Path objects pointing to generated chart PNG files.
    output_path: Destination path for the PDF file.

    Returns
    -------
    Absolute path string to the written PDF.
    """
    p = Path(output_path)
    p.parent.mkdir(parents=True, exist_ok=True)

    st = _styles()

    # Page margins
    doc = SimpleDocTemplate(
        str(p),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
        title="Enterprise Executive Business Analysis Report",
        author="Multi-Agent Business Intelligence Engine",
        subject="Sales Analytics & KPI Report",
    )

    story: list = []

    # ── Cover ────────────────────────────────────────────────────────────────
    story.append(Spacer(1, 1 * cm))
    story.append(Paragraph("ENTERPRISE EXECUTIVE BUSINESS ANALYSIS REPORT", st["title"]))
    story.append(Paragraph("Generated by: Multi-Agent Business Intelligence Engine", st["subtitle"]))
    story.append(Spacer(1, 0.3 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=BRAND_PURPLE))
    story.append(Spacer(1, 0.6 * cm))

    # ── 1. Executive Summary ─────────────────────────────────────────────────
    story.append(Paragraph("1. Executive Summary", st["section"]))
    summary_text = (
        results.get("report_summary", "") or "No executive summary generated."
    )
    # Wrap long lines safely
    for para in summary_text.split("\n"):
        if para.strip():
            story.append(Paragraph(para.strip(), st["body"]))
    story.append(Spacer(1, 0.4 * cm))

    # ── 2. KPI Table ─────────────────────────────────────────────────────────
    story.append(Paragraph("2. Key Performance Indicators", st["section"]))
    kpis = results.get("kpis", {})
    story.append(_kpi_table(kpis, st))
    story.append(Spacer(1, 0.4 * cm))

    # ── 3. Strategic Insights ────────────────────────────────────────────────
    story.append(Paragraph("3. Strategic AI Research Insights", st["section"]))
    insights = results.get("insights", [])
    if insights:
        for item in insights:
            txt = _extract_text(item)
            story.append(Paragraph(f"• {txt}", st["body"]))
    else:
        story.append(Paragraph("No insights generated.", st["body"]))
    story.append(Spacer(1, 0.4 * cm))

    # ── 4. Email Draft ───────────────────────────────────────────────────────
    story.append(Paragraph("4. Action Agent — Email Draft", st["section"]))
    email = results.get("email_draft", "") or "No email draft generated."
    for line in email.split("\n"):
        story.append(Paragraph(line or "&nbsp;", st["mono"]))
    story.append(Spacer(1, 0.4 * cm))

    # ── 5. Charts ────────────────────────────────────────────────────────────
    if charts:
        story.append(PageBreak())
        story.append(Paragraph("5. Generated Visual Analytics Charts", st["section"]))
        story.append(Spacer(1, 0.3 * cm))

        # 2-column chart grid
        CHART_W = 8.5 * cm
        CHART_H = 5.5 * cm
        chart_pairs = []
        existing = [Path(c) for c in charts if Path(c).exists()]
        for i in range(0, len(existing), 2):
            row = []
            for cp in existing[i : i + 2]:
                try:
                    img = Image(str(cp), width=CHART_W, height=CHART_H)
                    row.append(img)
                except Exception:
                    row.append(Paragraph(f"[Chart: {cp.name}]", st["caption"]))
            if len(row) == 1:
                row.append("")  # pad to 2 columns
            chart_pairs.append(row)

        if chart_pairs:
            chart_table = Table(chart_pairs, colWidths=[CHART_W + 0.5 * cm, CHART_W + 0.5 * cm])
            chart_table.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(chart_table)

        story.append(Spacer(1, 0.2 * cm))
        story.append(
            Paragraph(f"Total Charts Generated: {len(existing)}", st["caption"])
        )

    # ── 6. Warnings ──────────────────────────────────────────────────────────
    warnings = results.get("warnings", [])
    if warnings:
        story.append(Spacer(1, 0.4 * cm))
        story.append(Paragraph("6. Pipeline Warnings", st["section"]))
        for w in warnings:
            story.append(Paragraph(f"⚠ {w}", st["body"]))

    # ── Build ────────────────────────────────────────────────────────────────
    doc.build(story)
    return str(p)
