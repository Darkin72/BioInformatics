FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

COPY pyproject.toml README.md ./
RUN pip install --no-cache-dir \
    "cassandra-driver>=3.29.0" \
    "fastapi>=0.115.0" \
    "pydantic>=2.8.0" \
    "requests>=2.32.0" \
    "uvicorn[standard]>=0.30.0"

COPY libs ./libs
COPY apps/serving_api ./apps/serving_api

EXPOSE 8002

CMD ["uvicorn", "apps.serving_api.src.main:app", "--host", "0.0.0.0", "--port", "8002"]
