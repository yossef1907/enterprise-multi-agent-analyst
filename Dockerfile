FROM python:3.12-slim AS runtime
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt fastapi uvicorn pytest ruff
COPY modular_app/ ./modular_app/
COPY data/ ./data/

EXPOSE 8000
CMD ["python", "-m", "uvicorn", "modular_app.api:app", "--host", "0.0.0.0", "--port", "8000"]