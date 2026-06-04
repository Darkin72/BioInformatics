FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps ./apps
COPY contracts ./contracts
COPY docs ./docs
COPY libs ./libs
COPY ml ./ml
COPY jobs ./jobs
COPY cafa6 ./cafa6

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -e .

EXPOSE 8000

CMD ["uvicorn", "apps.serving_api.src.main:app", "--host", "0.0.0.0", "--port", "8000"]
