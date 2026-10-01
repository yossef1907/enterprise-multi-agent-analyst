"""FastAPI service for the modular multi-agent business analyst — v1.3.0"""
from __future__ import annotations

import asyncio
import json
import os
import smtplib
import time
from collections.abc import AsyncGenerator
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from modular_app.graph import run_pipeline

# ── Default paths ─────────────────────────────────────────────────────────
DEFAULT_DATA_PATH   = r"D:\odc_project\data"
DEFAULT_OUTPUT_PATH = r"D:\odc_project\modular_smoke_output"
CHARTS_DIR          = Path(DEFAULT_OUTPUT_PATH) / "charts"

# Ensure the charts directory exists at startup so StaticFiles doesn't fail
CHARTS_DIR.mkdir(parents=True, exist_ok=True)


# ── Application ───────────────────────────────────────────────────────────
app = FastAPI(title="Multi-Agent Business Analyst API", version="1.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static file mount for charts ──────────────────────────────────────────
# Charts are written to CHARTS_DIR by the pipeline and served at /charts/*.png
# e.g. http://127.0.0.1:8000/charts/chart_1_monthly_revenue.png
app.mount(
    "/charts",
    StaticFiles(directory=str(CHARTS_DIR)),
    name="charts",
)


# ── Pydantic models ───────────────────────────────────────────────────────

class AnalysisRequest(BaseModel):
    user_query: str = Field(..., min_length=1)
    data_path: str | None = None
    output_path: str | None = None
    recipient_email: str | None = Field(
        default="yossefayman1903@gmail.com", 
        description="Target email address to receive the executive report"
    )


class AnalysisResponse(BaseModel):
    status: str
    kpis: dict[str, Any] = Field(default_factory=dict)
    insights: list[Any] = Field(default_factory=list)
    report_summary: str = ""
    email_draft: str = ""
    pdf_path: str = ""
    chart_urls: list[str] = Field(default_factory=list)
    artifacts: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


# ── Email Delivery Helper ──────────────────────────────────────────────────

def send_actual_email(
    to_email: str = "yossefayman1903@gmail.com", 
    subject: str = "Executive Business Performance & KPI Analysis Report", 
    body_text: str = "", 
    pdf_path: str | Path | None = None
) -> bool:
    """Send an automated executive report email with PDF attachment using SMTP."""
    smtp_server = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_password = os.getenv("SMTP_PASSWORD", "")

    target_email = to_email or "yossefayman1903@gmail.com"

    if not smtp_user or not smtp_password:
        print(f"[Email Service] SMTP_USER/SMTP_PASSWORD missing in env. Email draft generated but dispatch skipped for {target_email}.")
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = smtp_user
        msg["To"] = target_email
        msg["Subject"] = subject

        msg.attach(MIMEText(body_text, "plain", "utf-8"))

        if pdf_path:
            pdf_file = Path(pdf_path)
            if pdf_file.exists() and pdf_file.is_file():
                with open(pdf_file, "rb") as f:
                    part = MIMEApplication(f.read(), Name=pdf_file.name)
                    part["Content-Disposition"] = f'attachment; filename="{pdf_file.name}"'
                    msg.attach(part)

        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.send_message(msg)

        print(f"✓ [Email Service] Successfully dispatched executive report to {target_email}")
        return True

    except Exception as exc:
        print(f"❌ [Email Service] Failed to send email to {target_email}: {exc}")
        return False


# ── Serialization helpers ─────────────────────────────────────────────────

def sanitize_data(value: Any) -> Any:
    """Recursively make any value JSON-safe.

    Handles: WindowsPath, PosixPath, numpy int64/float64/ndarray,
    pandas Timestamp, and arbitrary custom objects.
    """
    if isinstance(value, dict):
        return {str(k): sanitize_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize_data(v) for v in value]
    if isinstance(value, Path) or hasattr(value, "__fspath__"):
        return str(value)
    # numpy scalar / array coercion
    try:
        import numpy as np
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return float(value)
        if isinstance(value, np.ndarray):
            return value.tolist()
    except ImportError:
        pass
    # pandas Timestamp
    try:
        import pandas as pd
        if isinstance(value, pd.Timestamp):
            return str(value)
    except ImportError:
        pass
    # Final JSON probe
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


# ── Chart URL helpers ─────────────────────────────────────────────────────

BASE_CHART_URL = "http://127.0.0.1:8000/charts"


def _discover_chart_urls(output_path: str, result_chart_urls: list[str]) -> list[str]:
    """Return HTTP URLs for charts, adding a unique timestamp parameter (?t=...)
    to break browser cache and force rendering updated charts on every run.
    """
    ts = int(time.time() * 1000)

    # If action_agent already built chart_urls, append timestamp parameter
    if result_chart_urls:
        return [f"{url}?t={ts}" if "?" not in url else url for url in result_chart_urls]

    # Fallback: scan the charts directory and build URLs with timestamp
    chart_dir = Path(output_path) / "charts"
    if chart_dir.is_dir():
        pngs = sorted(
            p for p in chart_dir.iterdir() if p.suffix.lower() == ".png" and p.stat().st_size > 0
        )
        return [f"{BASE_CHART_URL}/{p.name}?t={ts}" for p in pngs]
    return []


# ── Response payload builder ──────────────────────────────────────────────

def _build_report_summary(result: dict, kpis: dict) -> str:
    """Prefer the graph-generated summary; fall back to a KPI-derived string."""
    summary = result.get("report_summary", "")
    if summary and "deterministic" not in summary.lower() and len(summary) > 30:
        return summary
    rev    = float(kpis.get("total_revenue", 0) or 0)
    orders = int(kpis.get("total_orders", 0) or 0)
    aov    = float(kpis.get("average_order_value", 0) or 0)
    custs  = int(kpis.get("unique_customers", 0) or 0)
    return (
        f"Financial performance analysis reveals total sales revenue of ${rev:,.2f} "
        f"across {orders:,} transactions, yielding an AOV of ${aov:,.2f}. "
        f"The platform served {custs:,} unique customers."
    )


def _read_email(result: dict[str, Any], output_path: str) -> str:
    """Multi-strategy email resolution: state → disk → reconstruct."""
    draft = result.get("email_draft", "")
    if draft and draft.strip() not in ("", "No email draft generated."):
        return draft

    candidate = Path(output_path) / "email_summary.txt"
    if candidate.is_file():
        content = candidate.read_text(encoding="utf-8").strip()
        if content and content != "No email draft generated.":
            return content

    kpis = result.get("kpis", {})
    rev    = float(kpis.get("total_revenue", 0) or 0)
    orders = int(kpis.get("total_orders", 0) or 0)
    aov    = float(kpis.get("average_order_value", 0) or 0)
    custs  = int(kpis.get("unique_customers", 0) or 0)
    return (
        "Subject: Executive Business Performance & KPI Analysis Report\n\n"
        "Dear Executive Team,\n\n"
        "The multi-agent analytics pipeline completed its evaluation.\n\n"
        f"  • Total Revenue:       ${rev:,.2f}\n"
        f"  • Total Orders:        {orders:,}\n"
        f"  • Average Order Value: ${aov:,.2f}\n"
        f"  • Unique Customers:    {custs:,}\n\n"
        "Best regards,\nMulti-Agent Business Intelligence Engine"
    )


def _response_payload(result: dict[str, Any], output_path: str, recipient_email: str | None = None) -> dict[str, Any]:
    kpis    = result.get("kpis", {})
    summary = _build_report_summary(result, kpis)

    # PDF path — prefer result state, then scan disk
    pdf_path = result.get("pdf_path", "")
    if not pdf_path:
        candidate = Path(output_path) / "multi_agent_business_report.pdf"
        pdf_path = str(candidate) if candidate.is_file() else ""

    chart_urls = _discover_chart_urls(output_path, result.get("chart_urls", []))
    email_draft_text = _read_email(result, output_path)

    # Automatically trigger real email dispatch
    target_recipient = recipient_email or "yossefayman1903@gmail.com"
    send_actual_email(
        to_email=target_recipient,
        subject="Executive Business Performance & KPI Analysis Report",
        body_text=email_draft_text,
        pdf_path=pdf_path
    )

    return {
        "status":         result.get("status", "unknown"),
        "kpis":           sanitize_data(kpis),
        "insights":       sanitize_data(result.get("insights", [])),
        "report_summary": summary,
        "email_draft":    email_draft_text,
        "pdf_path":       str(pdf_path),
        "chart_urls":     sanitize_data(chart_urls),
        "artifacts":      sanitize_data(result.get("artifacts", {})),
        "warnings":       sanitize_data(result.get("warnings", [])),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "multi-agent-business-analyst", "version": "1.3.0"}


@app.get("/api/v1/download-pdf")
def download_pdf() -> FileResponse:
    """Stream the generated PDF report as a binary attachment.

    Uses explicit Content-Type and Content-Disposition headers to guarantee
    the browser treats the response as a file download, not an inline render.
    """
    candidates = [
        Path(DEFAULT_OUTPUT_PATH) / "multi_agent_business_report.pdf",
        Path(r"D:\odc_project\modular_smoke_output\multi_agent_business_report.pdf"),
        Path.cwd() / "modular_smoke_output" / "multi_agent_business_report.pdf",
    ]
    for pdf_path in candidates:
        if pdf_path.is_file() and pdf_path.stat().st_size > 100:
            return FileResponse(
                path=str(pdf_path.resolve()),
                media_type="application/pdf",
                filename="multi_agent_business_report.pdf",
                headers={
                    # Force download — prevents browser PDF viewer from trying to render
                    "Content-Disposition": (
                        'attachment; filename="multi_agent_business_report.pdf"'
                    ),
                    "Content-Type": "application/pdf",
                    "Cache-Control": "no-cache, no-store, must-revalidate",
                    "Pragma": "no-cache",
                },
            )
    raise HTTPException(
        status_code=404,
        detail={
            "error": "PDF report not found",
            "hint": "Run an analysis first to generate the PDF report.",
            "searched": [str(c) for c in candidates],
        },
    )


@app.get("/api/v1/charts/{filename}")
def serve_chart_fallback(filename: str) -> FileResponse:
    """Fallback chart endpoint — streams PNGs directly from disk.

    This supplements the StaticFiles mount at /charts and handles cache-busting
    query parameters (?t=...) transparently since FastAPI strips QS before routing.

    Clients should prefer /charts/{filename} (StaticFiles, faster) but can
    fall back to /api/v1/charts/{filename} if the mount is unavailable.
    """
    # Guard against path traversal
    safe_name = Path(filename).name
    chart_path = CHARTS_DIR / safe_name
    if not chart_path.is_file() or chart_path.suffix.lower() != ".png":
        raise HTTPException(
            status_code=404,
            detail=f"Chart '{safe_name}' not found. Run an analysis first.",
        )
    return FileResponse(
        path=str(chart_path.resolve()),
        media_type="image/png",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma":        "no-cache",
        },
    )


@app.post("/api/v1/analyze", response_model=AnalysisResponse)
def analyze(request: AnalysisRequest) -> AnalysisResponse:
    data_path   = request.data_path or DEFAULT_DATA_PATH
    output_path = request.output_path or DEFAULT_OUTPUT_PATH
    try:
        result = run_pipeline(request.user_query, data_path, output_dir=output_path)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Analysis failed: {type(exc).__name__}: {exc}",
        ) from exc
    return AnalysisResponse(**_response_payload(result, output_path, request.recipient_email))


# ── SSE streaming ─────────────────────────────────────────────────────────

async def _stream(
    user_query: str, data_path: str, output_path: str, recipient_email: str | None = None
) -> AsyncGenerator[str, None]:
    """Server-Sent Events generator.

    Emits node_start events immediately for fast client feedback, runs
    the full pipeline in a thread (non-blocking), then emits the complete
    payload as a single SSE frame.
    """

    def _sse(payload: dict) -> str:
        return f"data: {json.dumps(payload, default=str)}\n\n"

    STEPS = [
        ("request_check",   "Validating user query and request parameters…"),
        ("data_retrieval", "Loading sales dataset (cached after first run)…"),
        ("quality_check",   "Running schema and statistical quality checks…"),
        ("clean_data",     "Normalising and deduplicating the DataFrame…"),
        ("data_analysis",   "Computing deterministic KPIs and financial metrics…"),
        ("research_insight","Generating categorised strategic insights…"),
        ("report_agent",   "Synthesising executive narrative summary…"),
        ("action_agent",   "Rendering charts in parallel, building PDF, drafting email…"),
    ]

    # ── Phase 1: emit first 2 node events before blocking I/O ────────────────
    for node, msg in STEPS[:2]:
        yield _sse({"type": "node_start", "node": node, "message": msg})
        await asyncio.sleep(0.02)   # minimal delay — just enough to flush

    # ── Phase 2: run pipeline in worker thread ────────────────────────────────
    try:
        result = await asyncio.to_thread(
            run_pipeline, user_query, data_path, output_path
        )
    except Exception as exc:
        result = {
            "status": "failed",
            "error": f"{type(exc).__name__}: {exc}",
            "kpis": {}, "insights": [], "warnings": [str(exc)],
        }

    # ── Phase 3: emit remaining node events quickly ───────────────────────────
    for node, msg in STEPS[2:]:
        yield _sse({"type": "node_start", "node": node, "message": msg})
        await asyncio.sleep(0.015)

    # ── Phase 4: emit full result payload ─────────────────────────────────────
    payload = _response_payload(result, output_path, recipient_email)
    payload["error"] = result.get("error", "")
    yield _sse({"type": "complete", "data": payload})


@app.post("/api/v1/analyze/stream")
async def analyze_stream(request: AnalysisRequest) -> StreamingResponse:
    data_path   = request.data_path or DEFAULT_DATA_PATH
    output_path = request.output_path or DEFAULT_OUTPUT_PATH
    return StreamingResponse(
        _stream(request.user_query, data_path, output_path, request.recipient_email),
        media_type="text/event-stream",
        headers={
            "Cache-Control":     "no-cache",
            "X-Accel-Buffering": "no",
            "Connection":        "keep-alive",
        },
    )