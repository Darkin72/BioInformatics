FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends openjdk-17-jre-headless curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
    "cassandra-driver>=3.29.0" \
    "kafka-python>=2.0.2" \
    "pika>=1.3.2" \
    "pydantic>=2.8.0" \
    "pyspark==3.5.1" \
    "requests>=2.32.0"

COPY libs ./libs
COPY jobs/spark_streaming ./jobs/spark_streaming

EXPOSE 4040

CMD ["python", "jobs/spark_streaming/src/job.py"]
