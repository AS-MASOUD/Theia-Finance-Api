# Multi-stage production build
FROM python:3.12-slim AS builder

WORKDIR /build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --upgrade pip uv

COPY pyproject.toml .
# Install dependencies into target directory
RUN uv pip install --system --target /build/deps -r pyproject.toml

# Final stage
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH="/app/deps:/app" \
    PATH="/app/deps/bin:$PATH"

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create unprivileged user
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -s /bin/bash -m appuser

# Create upload, storage, and data directories as root and assign ownership before switching to USER
RUN mkdir -p /app/uploads /app/data /app/wwwroot/uploads && \
    chown -R appuser:appgroup /app/uploads /app/data /app/wwwroot/uploads

COPY --from=builder /build/deps /app/deps
COPY --chown=appuser:appgroup alembic.ini /app/
COPY --chown=appuser:appgroup alembic /app/alembic
COPY --chown=appuser:appgroup src /app/src

USER appuser

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
