"""Action exporter — serializes analysis results to disk artifacts."""
from __future__ import annotations

from pathlib import Path
import json


def export_results(results: dict, output_dir: str | Path) -> list[Path]:
    """Write analysis results, execution log, and email draft to disk.

    Returns a list of Paths for the files created.
    NOTE: Callers should NOT unpack this return value with **; use it as a list.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    artifacts: list[Path] = []

    # 1. Full analysis results as JSON
    p1 = out / "analysis_results.json"
    p1.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    artifacts.append(p1)

    # 2. Execution log (lightweight summary)
    p2 = out / "execution_log.json"
    p2.write_text(
        json.dumps(
            {
                "status": results.get("status", "completed"),
                "warnings": results.get("warnings", []),
                "retry_count": results.get("retry_count", 0),
                "kpis_status": results.get("kpis", {}).get("status", "unknown"),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    artifacts.append(p2)

    # 3. Email draft (Action Agent output)
    p3 = out / "email_summary.txt"
    email_content = results.get("email_draft", "")
    if not email_content or email_content.strip() == "No email draft generated.":
        # Reconstruct from KPIs if email_draft is missing
        kpis = results.get("kpis", {})
        rev = float(kpis.get("total_revenue", 0) or 0)
        orders = int(kpis.get("total_orders", 0) or 0)
        aov = float(kpis.get("average_order_value", 0) or 0)
        email_content = (
            "Subject: Executive Business Performance & KPI Analysis Report\n\n"
            "Dear Executive Team,\n\n"
            "The multi-agent analytics pipeline completed its evaluation.\n\n"
            f"  • Total Revenue:       ${rev:,.2f}\n"
            f"  • Total Orders:        {orders:,}\n"
            f"  • Average Order Value: ${aov:,.2f}\n\n"
            "Best regards,\nMulti-Agent BI Engine"
        )
    p3.write_text(email_content, encoding="utf-8")
    artifacts.append(p3)

    return artifacts
