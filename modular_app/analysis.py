"""Deterministic analytics: Python computes; an LLM may interpret results."""
from __future__ import annotations
from typing import Any
import numpy as np
import pandas as pd

_REQUIRED = {"InvoiceNo", "Quantity", "UnitPrice", "InvoiceDate"}

def _empty(message: str) -> dict:
    return {"status": "unavailable", "error": message}

def _prepare(df: pd.DataFrame) -> tuple[pd.DataFrame, str | None]:
    if not isinstance(df, pd.DataFrame): return pd.DataFrame(), "Expected a pandas DataFrame."
    if df.empty: return df.copy(), "DataFrame is empty."
    missing = sorted(_REQUIRED - set(df.columns))
    if missing: return pd.DataFrame(), f"Missing required columns: {missing}"
    out = df.copy()
    out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce")
    out["UnitPrice"] = pd.to_numeric(out["UnitPrice"], errors="coerce")
    out["InvoiceDate"] = pd.to_datetime(out["InvoiceDate"], errors="coerce")
    out = out.dropna(subset=["Quantity", "UnitPrice", "InvoiceDate"])
    out["Revenue"] = out["Quantity"] * out["UnitPrice"]
    out["IsReturn"] = out["InvoiceNo"].astype(str).str.startswith("C") | (out["Quantity"] < 0)
    out["Date"] = out["InvoiceDate"].dt.normalize()
    return out, None

def _sales(df: pd.DataFrame) -> pd.DataFrame:
    return df[(~df["IsReturn"]) & (df["Quantity"] > 0)].copy()

def calculate_kpis(df: pd.DataFrame) -> dict:
    """Return revenue, orders, AOV, and customer KPIs."""
    x, err = _prepare(df)
    if err: return _empty(err)
    s = _sales(x)
    if s.empty: return _empty("No positive sales rows available.")
    revenue = float(s["Revenue"].sum()); orders = int(s["InvoiceNo"].nunique())
    return {"status":"ok", "total_revenue":round(revenue,2), "total_orders":orders,
            "average_order_value":round(revenue/orders,2) if orders else 0.0,
            "unique_customers":int(s["CustomerID"].nunique()) if "CustomerID" in s else 0,
            "unique_products":int(s["StockCode"].nunique()) if "StockCode" in s else 0,
            "returns_value":round(float(abs(x[x["IsReturn"]]["Revenue"].sum())),2),
            "date_start":str(s["InvoiceDate"].min().date()), "date_end":str(s["InvoiceDate"].max().date())}

def calculate_monthly_trends(df: pd.DataFrame) -> dict:
    """Aggregate revenue/orders by calendar month and compute MoM growth."""
    x, err = _prepare(df)
    if err: return _empty(err)
    s = _sales(x)
    if s.empty: return _empty("No sales rows available.")
    m = s.set_index("InvoiceDate").resample("MS").agg(revenue=("Revenue","sum"), orders=("InvoiceNo","nunique")).reset_index()
    m["month"] = m.pop("InvoiceDate").dt.strftime("%Y-%m")
    m["mom_growth_pct"] = m["revenue"].pct_change().replace([np.inf,-np.inf],np.nan).fillna(0)*100
    return {"status":"ok", "monthly":m.round(2).to_dict("records")}

def calculate_pareto_segmentation(df: pd.DataFrame) -> dict:
    """Rank customers and identify the smallest set contributing to 80% revenue."""
    x, err = _prepare(df)
    if err: return _empty(err)
    if "CustomerID" not in x: return _empty("CustomerID column is required.")
    s = _sales(x).dropna(subset=["CustomerID"])
    if s.empty: return _empty("No identified customers available.")
    c = s.groupby("CustomerID", as_index=False)["Revenue"].sum().sort_values("Revenue", ascending=False)
    total=float(c["Revenue"].sum()); c["cumulative_share_pct"] = c["Revenue"].cumsum()/total*100 if total else 0
    c["segment"] = np.where(c["cumulative_share_pct"] <= 80, "top_80_percent_contributors", "long_tail")
    cutoff = int((c["cumulative_share_pct"] <= 80).sum())
    return {"status":"ok", "customer_count":int(len(c)), "top_customer_count":cutoff, "top_customer_share_pct":round(float(c.iloc[:max(1,cutoff)]["Revenue"].sum()/total*100),2) if total else 0, "customers":c.round(2).to_dict("records")}

def detect_anomalies(df: pd.DataFrame) -> dict:
    """Detect statistical outliers with IQR and robust median/MAD z-scores."""
    x, err = _prepare(df)
    if err: return _empty(err)
    s = _sales(x)
    if s.empty: return _empty("No sales rows available.")
    metrics = [c for c in ["Revenue","Quantity"] if c in s]
    flags = pd.DataFrame(index=s.index); thresholds={}
    for col in metrics:
        q1,q3=s[col].quantile([.25,.75]); iqr=q3-q1; upper=float(q3+3*iqr)
        med=float(s[col].median()); mad=float((s[col]-med).abs().median())
        robust_z=0.6745*(s[col]-med)/mad if mad else pd.Series(0.0,index=s.index)
        flags[col]=(s[col]>upper) | (robust_z.abs()>3.5); thresholds[col]={"iqr_upper":round(upper,2),"robust_z_threshold":3.5}
    flagged = s[flags.any(axis=1)].copy()
    examples = flagged.head(20).copy()
    if not examples.empty:
        reasons = flags.loc[examples.index].apply(lambda r: ", ".join(r.index[r].tolist()), axis=1)
        examples["reasons"] = reasons
    keep=[c for c in ["InvoiceNo","Quantity","UnitPrice","Revenue","InvoiceDate","reasons"] if c in examples]
    records = examples[keep].to_dict("records")
    for row in records:
        for key in ("Quantity", "UnitPrice", "Revenue"):
            if key in row and pd.notna(row[key]): row[key] = round(float(row[key]), 2)
        if "InvoiceDate" in row and pd.notna(row["InvoiceDate"]): row["InvoiceDate"] = str(row["InvoiceDate"])
    return {"status":"ok", "method":"IQR + robust z-score (statistical anomalies, not fraud)", "thresholds":thresholds, "flagged_count":int(len(flagged)), "flagged_pct":round(len(flagged)/len(s)*100,2), "examples":records}
