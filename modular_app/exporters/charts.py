"""Chart generation engine — parallel data-driven charts via ThreadPoolExecutor."""
from __future__ import annotations

import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend — required for thread safety
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import pandas as pd

# ── Design tokens ──────────────────────────────────────────────────────────
ACCENT   = "#7c3aed"
ACCENT2  = "#a78bfa"
ACCENT3  = "#10b981"
BG       = "#141b29"
BG_ALT   = "#1a2334"
GRID_CLR = "#1e2d45"
TEXT_CLR = "#f1f5f9"
TEXT_SUB = "#94a3b8"

# Matplotlib thread-safety: each worker creates its own Figure — no shared state
# as long as we never use plt.gcf() / plt.gca(). All code below uses the
# explicit Figure/Axes API (fig, ax = plt.subplots(...)).


def _style(ax: Any, title: str) -> None:
    ax.set_facecolor(BG)
    ax.figure.patch.set_facecolor(BG)
    ax.set_title(title, fontsize=11, fontweight="bold", pad=12, color=TEXT_CLR)
    ax.tick_params(labelsize=8, colors=TEXT_SUB)
    ax.xaxis.label.set_color(TEXT_SUB)
    ax.yaxis.label.set_color(TEXT_SUB)
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#2d3f5e")
    ax.yaxis.grid(True, color=GRID_CLR, linewidth=0.7)
    ax.set_axisbelow(True)


def _save_close(fig: Any, path: Path, dpi: int = 150) -> None:
    fig.savefig(str(path), dpi=dpi, bbox_inches="tight", facecolor=BG, edgecolor="none")
    plt.close(fig)


# ── Individual chart functions (each runs in its own thread) ─────────────────

def _chart_monthly_revenue(sales_df: pd.DataFrame, out: Path) -> Path:
    monthly = (
        sales_df.set_index("InvoiceDate")
        .resample("MS")["Revenue"]
        .sum()
        .reset_index()
    )
    monthly.columns = ["Month", "Revenue"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.fill_between(monthly["Month"], monthly["Revenue"], alpha=0.2, color=ACCENT)
    ax.plot(monthly["Month"], monthly["Revenue"], color=ACCENT, linewidth=2,
            marker="o", markersize=4, zorder=3)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x/1e6:.1f}M" if x >= 1e6 else f"${x/1e3:.0f}K")
    )
    _style(ax, "Monthly Revenue Trend")
    ax.set_xlabel("Month", fontsize=8)
    ax.set_ylabel("Revenue", fontsize=8)
    fig.tight_layout(pad=1.5)
    p = out / "chart_1_monthly_revenue.png"
    _save_close(fig, p)
    return p


def _chart_top_countries(sales_df: pd.DataFrame, out: Path) -> Path:
    country = (
        sales_df.groupby("Country")["Revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(country.index[::-1], country.values[::-1], color=ACCENT, height=0.6)
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x/1e3:.0f}K")
    )
    _style(ax, "Top 10 Countries by Revenue")
    ax.set_xlabel("Revenue", fontsize=8)
    fig.tight_layout(pad=1.5)
    p = out / "chart_2_top_countries.png"
    _save_close(fig, p)
    return p


def _chart_monthly_orders(sales_df: pd.DataFrame, out: Path) -> Path:
    monthly_orders = (
        sales_df.set_index("InvoiceDate")
        .resample("MS")["InvoiceNo"]
        .nunique()
        .reset_index()
    )
    monthly_orders.columns = ["Month", "Orders"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.bar(monthly_orders["Month"], monthly_orders["Orders"], color=ACCENT2, width=20)
    _style(ax, "Monthly Unique Orders")
    ax.set_xlabel("Month", fontsize=8)
    ax.set_ylabel("Orders", fontsize=8)
    fig.tight_layout(pad=1.5)
    p = out / "chart_3_monthly_orders.png"
    _save_close(fig, p)
    return p


def _chart_top_products(sales_df: pd.DataFrame, out: Path) -> Path:
    if "Description" not in sales_df.columns:
        raise ValueError("No Description column")
    top = (
        sales_df.groupby("Description")["Revenue"]
        .sum()
        .sort_values(ascending=False)
        .head(10)
    )
    labels = [str(l)[:30] for l in top.index[::-1]]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.barh(labels, top.values[::-1], color=ACCENT, height=0.6)
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x/1e3:.0f}K")
    )
    _style(ax, "Top 10 Products by Revenue")
    ax.set_xlabel("Revenue", fontsize=8)
    fig.tight_layout(pad=1.5)
    p = out / "chart_4_top_products.png"
    _save_close(fig, p)
    return p


def _chart_revenue_dist(sales_df: pd.DataFrame, out: Path) -> Path:
    clipped = sales_df["Revenue"].clip(0, sales_df["Revenue"].quantile(0.99))
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.hist(clipped, bins=40, color=ACCENT, alpha=0.8, edgecolor="#141b29")
    ax.xaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x:.0f}")
    )
    _style(ax, "Order Revenue Distribution")
    ax.set_xlabel("Revenue per Line Item (99th-pct clipped)", fontsize=8)
    ax.set_ylabel("Frequency", fontsize=8)
    fig.tight_layout(pad=1.5)
    p = out / "chart_5_revenue_dist.png"
    _save_close(fig, p)
    return p


def _chart_kpi_summary(kpis: dict, out: Path) -> Path:
    rev = float(kpis.get("total_revenue", 0) or 0)
    orders = int(kpis.get("total_orders", 0) or 0)
    aov = float(kpis.get("average_order_value", 0) or 0)
    customers = int(kpis.get("unique_customers", 0) or 0)

    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.axis("off")
    table_data = [
        ["Metric", "Value"],
        ["Total Revenue", f"${rev:,.2f}"],
        ["Total Orders", f"{orders:,}"],
        ["Average Order Value", f"${aov:,.2f}"],
        ["Unique Customers", f"{customers:,}"],
    ]
    table = ax.table(
        cellText=table_data[1:],
        colLabels=table_data[0],
        cellLoc="center",
        loc="center",
        bbox=[0.05, 0.05, 0.9, 0.85],
    )
    table.auto_set_font_size(False)
    table.set_fontsize(10)
    for (row, col), cell in table.get_celld().items():
        if row == 0:
            cell.set_facecolor(ACCENT)
            cell.set_text_props(color="white", fontweight="bold")
        else:
            cell.set_facecolor(BG if row % 2 == 0 else BG_ALT)
            cell.set_text_props(color=TEXT_CLR)
        cell.set_edgecolor("#2d3f5e")
    ax.set_title("Executive KPI Summary", fontsize=11, fontweight="bold", pad=12, color=TEXT_CLR)
    fig.tight_layout(pad=1.5)
    p = out / "chart_6_kpi_summary.png"
    _save_close(fig, p)
    return p


def _chart_daily_rolling(sales_df: pd.DataFrame, out: Path) -> Path:
    daily = (
        sales_df.set_index("InvoiceDate")
        .resample("D")["Revenue"]
        .sum()
        .rolling(7, min_periods=1)
        .mean()
        .reset_index()
    )
    daily.columns = ["Date", "Revenue_7d"]
    fig, ax = plt.subplots(figsize=(9, 5))
    ax.plot(daily["Date"], daily["Revenue_7d"], color=ACCENT3, linewidth=1.5)
    ax.fill_between(daily["Date"], daily["Revenue_7d"], alpha=0.15, color=ACCENT3)
    ax.yaxis.set_major_formatter(
        mticker.FuncFormatter(lambda x, _: f"${x/1e3:.0f}K")
    )
    _style(ax, "Daily Revenue (7-Day Rolling Average)")
    ax.set_xlabel("Date", fontsize=8)
    ax.set_ylabel("Revenue", fontsize=8)
    fig.tight_layout(pad=1.5)
    p = out / "chart_7_daily_revenue.png"
    _save_close(fig, p)
    return p


# ── Orchestrator ──────────────────────────────────────────────────────────────

def generate_charts(
    df: pd.DataFrame,
    analysis_dict: dict,
    output_dir: str | Path,
    max_workers: int = 4,
) -> list[Path]:
    """Render all charts in parallel using ThreadPoolExecutor.

    Each chart function runs in its own thread and creates an independent
    matplotlib Figure — this is safe because we never touch shared pyplot
    global state (no plt.gcf/gca).

    Parameters
    ----------
    df:            Cleaned sales DataFrame.
    analysis_dict: Dict containing at minimum {"kpis": {...}}.
    output_dir:    Directory to write chart PNG files.
    max_workers:   Number of parallel worker threads (default 4).

    Returns
    -------
    Ordered list of Path objects for successfully generated charts.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    if df is None or df.empty:
        return []

    # ── Prepare shared derived columns ────────────────────────────────────────
    df = df.copy()
    if "Quantity" in df:
        df["Quantity"] = pd.to_numeric(df["Quantity"], errors="coerce")
    if "UnitPrice" in df:
        df["UnitPrice"] = pd.to_numeric(df["UnitPrice"], errors="coerce")
    if "InvoiceDate" in df:
        df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"], errors="coerce")
    if "Quantity" in df and "UnitPrice" in df:
        df["Revenue"] = df["Quantity"] * df["UnitPrice"]

    # Keep only positive-quantity sales rows
    has_revenue = "Revenue" in df.columns
    sales_df = (
        df[df["Quantity"] > 0].dropna(
            subset=["InvoiceDate", "Revenue"] if has_revenue else ["InvoiceDate"]
        )
        if has_revenue
        else df
    )

    kpis = analysis_dict.get("kpis", {})

    # ── Task registry: (output_path_key, callable) ───────────────────────────
    # Each task returns a Path on success or raises on failure.
    # We define them as lambdas so we can guard column prerequisites lazily.
    tasks: list[tuple[str, Callable[[], Path]]] = []

    if "Revenue" in sales_df.columns and "InvoiceDate" in sales_df.columns:
        tasks.append(("chart_1", lambda: _chart_monthly_revenue(sales_df, out)))

    if "Country" in sales_df.columns and "Revenue" in sales_df.columns:
        tasks.append(("chart_2", lambda: _chart_top_countries(sales_df, out)))

    if "InvoiceNo" in sales_df.columns and "InvoiceDate" in sales_df.columns:
        tasks.append(("chart_3", lambda: _chart_monthly_orders(sales_df, out)))

    if "Description" in sales_df.columns and "Revenue" in sales_df.columns:
        tasks.append(("chart_4", lambda: _chart_top_products(sales_df, out)))

    if "Revenue" in sales_df.columns:
        tasks.append(("chart_5", lambda: _chart_revenue_dist(sales_df, out)))

    if kpis:
        tasks.append(("chart_6", lambda: _chart_kpi_summary(kpis, out)))

    if "Revenue" in sales_df.columns and "InvoiceDate" in sales_df.columns:
        tasks.append(("chart_7", lambda: _chart_daily_rolling(sales_df, out)))

    if not tasks:
        return []

    # ── Parallel execution ────────────────────────────────────────────────────
    # Results keyed by task name so we preserve chart ordering
    results: dict[str, Path | None] = {name: None for name, _ in tasks}

    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as pool:
        future_to_name = {pool.submit(fn): name for name, fn in tasks}
        for future in as_completed(future_to_name):
            name = future_to_name[future]
            try:
                results[name] = future.result()
            except Exception:
                # Log but don't propagate — one failed chart must not abort all
                traceback.print_exc()

    # Return in insertion order (chart_1 → chart_7), skipping failures
    ordered = [results[name] for name, _ in tasks if results[name] is not None]
    return ordered
