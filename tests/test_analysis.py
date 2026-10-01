import pandas as pd
from modular_app.tools.analysis import (
    calculate_kpis,
    calculate_monthly_trends,
    calculate_pareto_segmentation,
    detect_anomalies,
)

def test_kpis(sample_df):
    result = calculate_kpis(sample_df)
    assert result["status"] == "ok"
    assert result["total_revenue"] == 80.0
    assert result["total_orders"] in {3, 4}

def test_analysis_empty_and_missing():
    res_empty = calculate_kpis(pd.DataFrame())
    assert res_empty["status"] in {"unavailable", "error"}

    res_missing = calculate_kpis(pd.DataFrame({"Quantity": [1]}))
    assert "status" in res_missing

def test_trends_pareto_anomalies(sample_df):
    assert calculate_monthly_trends(sample_df)["status"] == "ok"
    assert calculate_pareto_segmentation(sample_df)["status"] == "ok"
    assert detect_anomalies(sample_df)["status"] == "ok"

def test_edge_zero_price(sample_df):
    x = sample_df.copy()
    x.loc[0, "UnitPrice"] = 0
    assert calculate_kpis(x)["status"] == "ok"
