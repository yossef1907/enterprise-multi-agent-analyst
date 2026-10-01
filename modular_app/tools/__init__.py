"""Deterministic and retrieval tools.

IMPORTANT: calculate_kpis and related functions are re-exported from the
full modular_app.analysis module (not the stub tools/analysis.py) to ensure
all callers get the production-quality implementation with return filtering,
anomaly detection, and proper revenue calculation.
"""
# ✅ Import from the full, production analysis module
from modular_app.analysis import (
    calculate_kpis,
    calculate_monthly_trends,
    calculate_pareto_segmentation,
    detect_anomalies,
)
from .retrieval import PDFRetriever, WeatherAPICaller

__all__ = [
    "calculate_kpis",
    "calculate_monthly_trends",
    "calculate_pareto_segmentation",
    "detect_anomalies",
    "PDFRetriever",
    "WeatherAPICaller",
]
