from modular_app.tools.retrieval import PDFRetriever, WeatherAPICaller

def test_pdf_retriever(project_data):
    pdf_path = project_data / "2025-Annual-Report-Target-Corporation.pdf"
    retriever = PDFRetriever(pdf_path).build()
    results = retriever.retrieve("revenue", top_k=2)
    assert isinstance(results, list)

def test_weather_fallback(tmp_path, monkeypatch):
    cache = tmp_path / "weather_cache.csv"
    cache.write_text("time,temperature_2m_mean\n2025-01-01,10\n")

    def fail(*args, **kwargs):
        raise TimeoutError("offline")

    monkeypatch.setattr("modular_app.tools.retrieval.requests.get", fail)
    result = WeatherAPICaller(cache).fetch()
    assert result["source"] in {"local_cache", "local_cache_or_api"}
