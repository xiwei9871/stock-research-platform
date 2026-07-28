FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

WORKDIR /app
COPY pyproject.toml ./
COPY deploy/dashboard-api-requirements.lock ./deploy/dashboard-api-requirements.lock
RUN python -m pip install --no-cache-dir --require-hashes --requirement deploy/dashboard-api-requirements.lock
COPY src ./src
COPY dashboard/dist ./dashboard/dist
RUN python -m pip install --no-cache-dir --no-deps .

ENV PYTHONPATH=/app/src
CMD ["python", "-m", "uvicorn", "stock_research.dashboard.app:app", "--host", "0.0.0.0", "--port", "8765", "--http", "h11"]
