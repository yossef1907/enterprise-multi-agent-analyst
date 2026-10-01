"""LangGraph orchestration and production pipeline entrypoint."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pandas as pd
from langgraph.graph import END, START, StateGraph

try:
    from langgraph.checkpoint.memory import MemorySaver
except Exception:
    MemorySaver = None

from modular_app.datastore import STORE
from modular_app.exporters.action_exporter import export_results
from modular_app.exporters.charts import generate_charts
from modular_app.exporters.pdf_builder import build_pdf
from modular_app.state import AgentState

# Import from the FULL analysis module (not the stub in tools/)
from modular_app.analysis import calculate_kpis
from modular_app.tools.retrieval import PDFRetriever

MAX_RETRIES = 2

# Default output dir — passed through run_pipeline
_DEFAULT_OUTPUT = r"D:\odc_project\modular_smoke_output"


# ── Node 1 ──────────────────────────────────────────────────────────────────

def request_check(state: AgentState) -> dict:
    """Fast-path: validate that the user query is non-empty."""
    query = state.get("user_query", "").strip()
    return {
        "status": "request_valid" if query else "invalid_request",
        "warnings": [] if query else ["user_query is empty"],
    }


# ── Node 2 ──────────────────────────────────────────────────────────────────

def data_retrieval(state: AgentState) -> dict:
    """Resolve the sales dataset path and load into STORE.

    Uses a cross-run file-level cache (DataStore._FILE_CACHE) so the
    23 MB Excel workbook is only parsed once per server process.
    """
    input_path = state.get("data_path") or r"D:\odc_project\data"
    candidate_paths = [
        Path(input_path),
        Path(r"D:\odc_project\data"),
        Path.cwd() / "data",
        Path.cwd(),
    ]

    sales_path: Path | None = None
    warnings: list[str] = []

    for p in candidate_paths:
        if not p.exists():
            continue
        if p.is_file() and p.suffix.lower() in {".xlsx", ".xls", ".csv"}:
            sales_path = p
            break
        if p.is_dir():
            # Priority: exact "Online Retail" name → any xlsx/xls → csv
            matches = (
                list(p.rglob("Online Retail.xlsx"))
                or list(p.rglob("Online Retail.xls"))
                or list(p.rglob("*.xlsx"))
                or list(p.rglob("*.xls"))
                or list(p.rglob("*.csv"))
            )
            if matches:
                sales_path = matches[0]
                break

    if sales_path is None:
        return {
            "status": "data_missing",
            "warnings": [
                "Sales dataset (.xlsx/.xls/.csv) not found in: "
                + str([str(cp) for cp in candidate_paths])
            ],
        }

    try:
        # ── Cache check ──────────────────────────────────────────────────────
        cached = STORE.get_cached_file(sales_path)
        if cached is not None:
            df = cached.copy()  # cheap copy — avoids downstream mutation on cache
            warnings.append(f"Dataset loaded from in-memory cache: {sales_path.name}")
        else:
            t0 = time.perf_counter()
            df = (
                pd.read_csv(sales_path)
                if sales_path.suffix.lower() == ".csv"
                else pd.read_excel(sales_path)
            )
            elapsed = time.perf_counter() - t0
            STORE.set_cached_file(sales_path, df)
            warnings.append(
                f"Dataset loaded from disk in {elapsed:.2f}s and cached: {sales_path.name}"
            )

        STORE.set_sales_data(raw=df)
        STORE.set_path("sales", sales_path)

        # Index the accompanying PDF (annual report) for RAG — best-effort
        pdf = next(sales_path.parent.rglob("*.pdf"), None)
        if pdf:
            try:
                PDFRetriever(pdf).build()
                STORE.set_path("report", pdf)
            except Exception as exc:
                warnings.append(f"PDF retrieval unavailable: {exc}")

        return {"status": "data_retrieved", "warnings": warnings}

    except Exception as exc:
        return {
            "status": "retrieval_error",
            "warnings": [f"Retrieval failed: {type(exc).__name__}: {exc}"],
        }


# ── Node 3 ──────────────────────────────────────────────────────────────────

def quality_check(state: AgentState) -> dict:
    """Schema and statistical quality checks on the raw sales DataFrame."""
    df = STORE.get_sales_data(clean=False)
    issues: list[str] = []

    if df is None or df.empty:
        issues.append("Sales DataFrame is missing or empty")
    else:
        required = {"InvoiceNo", "Quantity", "UnitPrice", "InvoiceDate"}
        issues.extend(
            f"Missing column: {c}" for c in sorted(required - set(df.columns))
        )
        if "Quantity" in df and pd.to_numeric(df["Quantity"], errors="coerce").isna().any():
            issues.append("Invalid quantities detected")
        if "UnitPrice" in df and (pd.to_numeric(df["UnitPrice"], errors="coerce") < 0).any():
            issues.append("Negative prices detected")

    warnings = list(state.get("warnings", []))
    if issues and int(state.get("retry_count", 0)) >= MAX_RETRIES:
        warnings.append(
            f"Maximum quality retries ({MAX_RETRIES}) reached; "
            "continuing to analysis with unresolved issues."
        )

    return {
        "quality_issues": issues,
        "warnings": warnings,
        "status": "quality_issue" if issues else "quality_ok",
    }


# ── Node 4 ──────────────────────────────────────────────────────────────────

def clean_data(state: AgentState) -> dict:
    """Normalize and clean the raw DataFrame.

    Preserves negative-quantity return rows so that the analysis module
    can calculate the returns_value KPI via its own IsReturn flag logic.
    """
    df = STORE.get_sales_data(clean=False)
    if df is None:
        return {"warnings": ["Cleaning skipped: no raw data"]}

    out = df.copy()
    out["InvoiceDate"] = pd.to_datetime(out["InvoiceDate"], errors="coerce")
    out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce")
    out["UnitPrice"] = pd.to_numeric(out["UnitPrice"], errors="coerce")
    out = out.dropna(subset=["InvoiceDate", "Quantity", "UnitPrice"]).drop_duplicates()
    # Preserve negative quantities (returns); only exclude negative unit prices
    out = out[out["UnitPrice"] >= 0]
    STORE.set_sales_data(clean=out)
    return {"retry_count": int(state.get("retry_count", 0)) + 1, "status": "cleaned"}


# ── Node 5 ──────────────────────────────────────────────────────────────────

def data_analysis(state: AgentState) -> dict:
    """Deterministic KPI engine: revenue, orders, AOV, customers, products."""
    df = STORE.get_sales_data(clean=True)
    if df is None:
        df = STORE.get_sales_data(clean=False)
    if df is None or df.empty:
        return {
            "status": "analysis_unavailable",
            "warnings": ["No DataFrame available for analysis"],
        }

    kpis = calculate_kpis(df)
    kpis["status"] = "ok"
    return {"kpis": kpis, "status": "analysis_complete"}


# ── Node 6 ──────────────────────────────────────────────────────────────────

def research_insight(state: AgentState) -> dict:
    """Generate categorised, evidence-backed insights using LLM dynamically (with deterministic fallback)."""
    user_query = state.get("user_query", "").strip() or "Analyze total sales revenue and present key executive recommendations"
    kpis = state.get("kpis", {})
    rev = float(kpis.get("total_revenue", 0))
    orders = int(kpis.get("total_orders", 0))
    aov = float(kpis.get("average_order_value", 0))
    customers = int(kpis.get("unique_customers", 0))
    products = int(kpis.get("unique_products", 0))
    date_start = kpis.get("date_start", "N/A")
    date_end = kpis.get("date_end", "N/A")

    groq_key = os.getenv("GROQ_API_KEY") or os.getenv("GROQ_API_TOKEN")
    insights: list[dict] = []

    # ── 1. LLM Generation (If API Key is set) ──────────────────────────────
    if groq_key and rev > 0:
        try:
            from langchain_groq import ChatGroq
            llm = ChatGroq(model_name="llama-3.3-70b-versatile", groq_api_key=groq_key, temperature=0.2)
            
            prompt = f"""You are a Lead Financial & Executive Business Analyst.
User Prompt / Focus: "{user_query}"

Deterministic Financial KPIs Computed from Sales Data:
- Total Revenue: ${rev:,.2f}
- Total Orders: {orders:,}
- Average Order Value (AOV): ${aov:,.2f}
- Unique Customers: {customers:,}
- Unique Products (SKUs): {products:,}
- Date Range: {date_start} to {date_end}

Task:
Analyze the provided KPI data to directly answer and address the user's prompt ("{user_query}").
Provide 3 structured, categorized insights/recommendations tailored specifically to this query.

Return ONLY a valid JSON array with this exact format (no markdown code blocks, just raw JSON):
[
  {{"category": "Category Title", "text": "Specific insight or recommendation directly addressing the user query", "evidence": ["Supporting KPI data point"]}}
]"""

            response = llm.invoke(prompt)
            content = str(response.content).strip()

            if content.startswith("```json"):
                content = content.replace("```json", "").replace("```", "").strip()
            elif content.startswith("```"):
                content = content.replace("```", "").strip()

            parsed = json.loads(content)
            if isinstance(parsed, list) and len(parsed) > 0:
                insights = parsed
        except Exception as exc:
            print(f"[Research Insight LLM] Falling back to deterministic mode: {exc}")

    # ── 2. Deterministic Fallback (If LLM skipped or failed) ────────────────
    if not insights:
        if rev > 0:
            insights.append({
                "category": "Revenue Performance",
                "text": (
                    f"Total sales revenue of ${rev:,.2f} was generated across {orders:,} unique orders "
                    f"({date_start} – {date_end}), yielding an Average Order Value (AOV) of ${aov:,.2f}."
                ),
                "evidence": ["Deterministic pandas computation on Online Retail dataset"],
            })
            insights.append({
                "category": "Customer Base",
                "text": (
                    f"The platform served {customers:,} unique customers purchasing across "
                    f"{products:,} distinct product SKUs."
                ),
                "evidence": ["CustomerID and StockCode column analysis"],
            })
            insights.append({
                "category": "Strategic Recommendation",
                "text": (
                    f"Addressing prompt ('{user_query}'): With an AOV of ${aov:,.2f}, targeted upsell campaigns "
                    f"and bundle promotions could increase per-order revenue by 10–15%, adding an estimated "
                    f"${rev * 0.12:,.2f} in incremental annual revenue."
                ),
                "evidence": ["AOV-based revenue uplift modelling"],
            })
        else:
            insights.append({
                "category": "Warning",
                "text": "Analysis ran without valid positive-revenue transaction data.",
                "evidence": [],
            })

    return {"insights": insights, "status": "research_complete"}


# ── Node 7 ──────────────────────────────────────────────────────────────────

def report_agent(state: AgentState) -> dict:
    """Synthesise a structured executive narrative that directly answers the user_query.

    Structure:
      § 1 — Opening KPI headline (hard facts, no repetition of insight text)
      § 2 — 1–3 key insight themes extracted from research_insight output
      § 3 — Actionable closing recommendation tied to the user's prompt
    """
    kpis       = state.get("kpis", {})
    insights   = state.get("insights", [])
    user_query = state.get("user_query", "").strip() or "business performance analysis"

    rev       = float(kpis.get("total_revenue", 0) or 0)
    orders    = int(kpis.get("total_orders", 0) or 0)
    aov       = float(kpis.get("average_order_value", 0) or 0)
    customers = int(kpis.get("unique_customers", 0) or 0)
    products  = int(kpis.get("unique_products", 0) or 0)
    d_start   = kpis.get("date_start", "N/A")
    d_end     = kpis.get("date_end", "N/A")

    # § 1 — Headline KPI paragraph
    para1 = (
        f"Analysis of the sales dataset ({d_start} – {d_end}) surfaces total revenue of "
        f"${rev:,.2f} across {orders:,} transactions — an Average Order Value of ${aov:,.2f}. "
        f"The platform engaged {customers:,} unique customers across {products:,} distinct product SKUs."
    )

    # § 2 — Insight themes (deduplicated by category, not raw text concatenation)
    seen_cats: set[str] = set()
    theme_lines: list[str] = []
    for item in insights:
        if isinstance(item, dict):
            cat  = str(item.get("category", ""))
            text = str(item.get("text", "")).strip()
        else:
            cat  = "Insight"
            text = str(item).strip()
        # Skip near-duplicate categories; include up to 3 themes
        key = cat.lower().split()[0] if cat else "other"
        if key in seen_cats or not text:
            continue
        seen_cats.add(key)
        theme_lines.append(f"• {cat}: {text}")
        if len(theme_lines) >= 3:
            break

    para2 = "\n".join(theme_lines) if theme_lines else ""

    # § 3 — Actionable closing tied to the prompt
    uplift_est = rev * 0.12
    para3 = (
        f"In direct response to the request — \"{user_query}\" — the data supports a targeted "
        f"strategy focused on AOV uplift and customer retention. A conservative 12% improvement "
        f"in per-transaction value would yield an estimated ${uplift_est:,.2f} in incremental "
        f"annual revenue. Recommended actions include tiered bundle promotions, loyalty segmentation, "
        f"and regional market expansion into the top-performing geographic clusters."
    )

    sections = [para1]
    if para2:
        sections.append(para2)
    sections.append(para3)

    report_summary = "\n\n".join(sections)
    return {"report_summary": report_summary, "status": "report_ready"}


# ── Node 8 ──────────────────────────────────────────────────────────────────

def action_agent(state: AgentState) -> dict:
    """Materialise all artifacts: charts (parallel), PDF, and email draft.

    This node now owns the complete artifact generation lifecycle so that
    _materialize_artifacts() can be removed from run_pipeline() and the
    SSE stream immediately reflects the true completion state.
    """
    output_dir = state.get("output_dir", _DEFAULT_OUTPUT)
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    kpis = state.get("kpis", {})
    report_summary = state.get("report_summary", "")
    rev = float(kpis.get("total_revenue", 0))
    orders = int(kpis.get("total_orders", 0))
    aov = float(kpis.get("average_order_value", 0))
    customers = int(kpis.get("unique_customers", 0))

    # ── Email draft ─────────────────────────────────────────────────────────
    email_draft = (
        "Subject: Executive Business Performance & KPI Analysis Report\n\n"
        "Dear Executive Team,\n\n"
        "The multi-agent analytics pipeline has completed its evaluation of the "
        "sales dataset. Please find the key findings summarised below:\n\n"
        f"  • Total Revenue:          ${rev:,.2f}\n"
        f"  • Total Orders:           {orders:,}\n"
        f"  • Average Order Value:    ${aov:,.2f}\n"
        f"  • Unique Customers:       {customers:,}\n\n"
        "Executive Summary:\n"
        f"{report_summary}\n\n"
        "The full analysis report (PDF) has been generated and attached for review.\n\n"
        "Best regards,\n"
        "Multi-Agent Business Intelligence Engine"
    )

    # ── Charts (parallel) ───────────────────────────────────────────────────
    df = STORE.get_sales_data(clean=True)
    if df is None:
        df = STORE.get_sales_data(clean=False)
    charts: list[Path] = []
    chart_dir = out / "charts"
    if df is not None and not df.empty:
        charts = generate_charts(df, {"kpis": kpis}, chart_dir)

    # ── PDF (real binary via ReportLab) ─────────────────────────────────────
    result_snapshot = {
        "report_summary": report_summary,
        "insights": state.get("insights", []),
        "kpis": kpis,
        "email_draft": email_draft,
        "warnings": state.get("warnings", []),
    }
    pdf_path = build_pdf(result_snapshot, charts, out / "multi_agent_business_report.pdf")

    # ── Write email to disk ─────────────────────────────────────────────────
    email_file = out / "email_summary.txt"
    email_file.write_text(email_draft, encoding="utf-8")

    # ── Export JSON logs ────────────────────────────────────────────────────
    export_results({**result_snapshot, "email_draft": email_draft}, out)

    # ── Build public chart URLs ─────────────────────────────────────────────
    # These map to the StaticFiles mount at /charts in api.py
    _base = "http://127.0.0.1:8000/charts"
    chart_urls = [f"{_base}/{c.name}" for c in charts if c.exists()]

    return {
        "email_draft": email_draft,
        "pdf_path": pdf_path,
        "chart_urls": chart_urls,
        "artifacts": {
            "pdf": pdf_path,
            "charts": [str(c) for c in charts],
            "chart_urls": chart_urls,
            "email_summary": str(email_file),
        },
        "status": "completed",
    }


# ── Router ───────────────────────────────────────────────────────────────────

def route_quality(state: AgentState) -> str:
    issues = state.get("quality_issues", [])
    retries = int(state.get("retry_count", 0))
    return "clean_data" if issues and retries < MAX_RETRIES else "data_analysis"


# ── Graph builder ────────────────────────────────────────────────────────────

def build_graph(checkpointer=None):
    graph = StateGraph(AgentState)
    nodes = [
        ("request_check", request_check),
        ("data_retrieval", data_retrieval),
        ("quality_check", quality_check),
        ("clean_data", clean_data),
        ("data_analysis", data_analysis),
        ("research_insight", research_insight),
        ("report_agent", report_agent),
        ("action_agent", action_agent),
    ]
    for name, fn in nodes:
        graph.add_node(name, fn)

    graph.add_edge(START, "request_check")
    graph.add_edge("request_check", "data_retrieval")
    graph.add_edge("data_retrieval", "quality_check")
    graph.add_conditional_edges(
        "quality_check",
        route_quality,
        {"clean_data": "clean_data", "data_analysis": "data_analysis"},
    )
    graph.add_edge("clean_data", "quality_check")
    graph.add_edge("data_analysis", "research_insight")
    graph.add_edge("research_insight", "report_agent")
    graph.add_edge("report_agent", "action_agent")
    graph.add_edge("action_agent", END)
    return graph.compile(
        checkpointer=checkpointer or (MemorySaver() if MemorySaver else None)
    )


# ── Public entrypoint ────────────────────────────────────────────────────────

def run_pipeline(
    user_query: str,
    data_path: str,
    output_dir: str | Path = _DEFAULT_OUTPUT,
) -> dict:
    """Execute the full 8-node LangGraph pipeline and return the final state dict."""
    STORE.reset()  # clear per-run state; file cache is preserved

    initial: AgentState = {
        "user_query": user_query,
        "data_path": data_path or r"D:\odc_project\data",
        # Pass output_dir through state so action_agent can use it
        "output_dir": str(output_dir),
        "status": "started",
        "quality_issues": [],
        "retry_count": 0,
        "kpis": {},
        "insights": [],
        "pdf_path": "",
        "chart_urls": [],
        "warnings": [],
        "report_summary": "",
        "email_draft": "",
        "artifacts": {},
    }

    app = build_graph()
    result = dict(
        app.invoke(
            initial,
            config={
                "configurable": {"thread_id": "business-analyst-run"},
                "recursion_limit": 30,
            },
        )
    )
    return result