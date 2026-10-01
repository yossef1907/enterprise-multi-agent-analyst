import sys
from pathlib import Path
import pandas as pd
import pytest
from reportlab.pdfgen import canvas

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

@pytest.fixture
def sample_df():
    return pd.DataFrame(
        {
            "InvoiceNo": ["10001", "10001", "10002", "C10003", "10004"],
            "StockCode": ["10001", "10002", "10001", "10001", "10003"],
            "Description": ["A", "B", "A", "A", "C"],
            "Quantity": [2, 1, 3, -1, 4],
            "InvoiceDate": pd.to_datetime(["2025-01-01", "2025-01-01", "2025-02-01", "2025-02-02", "2025-02-03"]),
            "UnitPrice": [10.0, 20.0, 10.0, 10.0, 5.0],
            "CustomerID": [1, 1, 2, 2, 3],
            "Country": ["UK", "UK", "DE", "DE", "UK"],
        }
    )

@pytest.fixture
def project_data(tmp_path):
    data_path = tmp_path / "data"
    data_path.mkdir(parents=True, exist_ok=True)

    # 1. إنشاء ملف PDF حقيقي متعدد العبارات لقراءته بـ pypdf
    pdf_file = data_path / "2025-Annual-Report-Target-Corporation.pdf"
    c = canvas.Canvas(str(pdf_file))
    c.drawString(100, 750, "Annual Report 2025 - Key Financial and Revenue Metrics Summary")
    c.drawString(100, 730, "The business achieved strong overall growth across key product segments and retail channels.")
    c.save()

    # 2. إنشاء ملف Excel حقيقي للاختبار
    sales_file = data_path / "Online Retail.xlsx"
    df = pd.DataFrame({
        "InvoiceNo": ["10001", "10002"],
        "StockCode": ["10001", "10002"],
        "Description": ["Product A", "Product B"],
        "Quantity": [10, 20],
        "InvoiceDate": ["2025-01-01", "2025-01-02"],
        "UnitPrice": [5.0, 10.0],
        "CustomerID": [12345, 67890],
        "Country": ["UK", "UK"]
    })
    df.to_excel(sales_file, index=False)

    return data_path
