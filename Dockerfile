# ── Stage 1: Builder ──────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN pip install --no-cache-dir wheel hatchling

COPY pyproject.toml .
COPY README.md .
COPY src/ src/

RUN pip install --no-cache-dir --target /build/site-packages .


# ── Stage 2: Runtime ──────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/site-packages /usr/local/lib/python3.11/site-packages/

COPY src/ src/
COPY franz.py .
COPY franz.cfg .
COPY README.md .

RUN mkdir -p /app/data/memory /app/data/logs /app/plugins

ENV FRANZ_DIR=/app/data \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

RUN groupadd -r franz && useradd -r -g franz -d /app -s /bin/bash franz \
    && chown -R franz:franz /app
USER franz

VOLUME ["/app/data"]

ENTRYPOINT ["python", "franz.py"]
