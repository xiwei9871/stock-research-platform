FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY dashboard/dist ./dashboard/dist
RUN python -m pip install --no-cache-dir ".[dashboard]"

ENV PYTHONPATH=/app/src
CMD ["python", "-m", "uvicorn", "stock_research.dashboard.app:app", "--host", "0.0.0.0", "--port", "8765", "--http", "h11"]
