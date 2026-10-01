from typing import TypedDict, Any


class AgentState(TypedDict, total=False):
    # ── Input ────────────────────────────────────────────────────────────────
    user_query: str
    data_path: str
    output_dir: str          # passed through state so action_agent can write artifacts

    # ── Pipeline control ─────────────────────────────────────────────────────
    status: str
    quality_issues: list[str]
    retry_count: int
    warnings: list[str]

    # ── Analysis outputs ─────────────────────────────────────────────────────
    kpis: dict[str, Any]
    insights: list[dict[str, Any]]

    # ── Report outputs ───────────────────────────────────────────────────────
    report_summary: str
    email_draft: str

    # ── Artifact outputs ─────────────────────────────────────────────────────
    pdf_path: str
    chart_urls: list[str]    # HTTP-accessible URLs served via StaticFiles mount
    artifacts: dict[str, Any]
