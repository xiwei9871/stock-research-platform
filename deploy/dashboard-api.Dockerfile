FROM python:3.12.11-slim-bookworm

WORKDIR /app
COPY pyproject.toml ./
COPY deploy/dashboard-api-requirements.lock ./deploy/dashboard-api-requirements.lock
COPY src ./src
COPY dashboard/dist ./dashboard/dist
RUN python -m pip install --no-cache-dir --requirement deploy/dashboard-api-requirements.lock \
    && python -m pip install --no-cache-dir --no-deps .

ENV PYTHONPATH=/app/src
CMD ["python", "-m", "uvicorn", "stock_research.dashboard.app:app", "--host", "0.0.0.0", "--port", "8765", "--http", "h11"]
