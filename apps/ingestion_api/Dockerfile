FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
    "cassandra-driver>=3.29.0" \
    "fastapi>=0.115.0" \
    "kafka-python>=2.0.2" \
    "pika>=1.3.2" \
    "pydantic>=2.8.0" \
    "requests>=2.32.0" \
    "uvicorn[standard]>=0.30.0"

COPY libs ./libs
COPY apps/ingestion_api ./apps/ingestion_api

EXPOSE 8001

CMD ["uvicorn", "apps.ingestion_api.src.main:app", "--host", "0.0.0.0", "--port", "8001"]
