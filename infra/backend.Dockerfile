# Build context is ../backend (see infra/docker-compose.yml)
FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
# --timeout/--retries: this project's dev sandbox has intermittently slow
# registry throughput (see README's "What was and wasn't verified"); the
# pip defaults are too eager to give up on a slow-but-live connection,
# especially now that this list includes several large ML wheels.
RUN pip install --no-cache-dir --timeout 120 --retries 5 -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
