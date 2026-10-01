from pathlib import Path
from modular_app.graph import run_pipeline

def test_end_to_end_pipeline(project_data, tmp_path):
    result = run_pipeline("Analyze sales KPIs and produce a report", str(project_data), output_dir=tmp_path)
    assert result["status"] == "completed"
    assert result["kpis"]["status"] == "ok"
    assert Path(result["pdf_path"]).exists()
