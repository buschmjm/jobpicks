# syntax=docker/dockerfile:1

FROM node:22-bookworm-slim AS web-builder

ARG VITE_OIDC_AUTHORITY=https://auth.jbuschmann.com/realms/homelab
ARG VITE_OIDC_CLIENT_ID=job-platform
ARG VITE_APP_BASE_URL=https://app.willowriverautomation.com/jobpicks
ARG VITE_APP_MOUNT_PATH=/jobpicks
ENV VITE_OIDC_AUTHORITY=${VITE_OIDC_AUTHORITY} \
    VITE_OIDC_CLIENT_ID=${VITE_OIDC_CLIENT_ID} \
    VITE_APP_BASE_URL=${VITE_APP_BASE_URL} \
    VITE_APP_MOUNT_PATH=${VITE_APP_MOUNT_PATH}

WORKDIR /web
COPY web/package.json web/package-lock.json* ./
RUN npm ci --ignore-scripts 2>/dev/null || npm install
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS builder

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY api/ api/
COPY core/ core/
COPY ingest/ ingest/
COPY inference/ inference/
COPY workers/ workers/
COPY migrations/ migrations/
COPY prompts/ prompts/
COPY templates/ templates/
COPY seeds/ seeds/
COPY alembic.ini ./

RUN pip install --upgrade pip && pip install .

FROM python:3.12-slim AS runtime

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/* \
    && adduser --disabled-password --gecos "" appuser \
    && mkdir -p /data/resumes /ms-playwright && chown appuser:appuser /data/resumes

COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /app /app
COPY --from=web-builder /web/dist /app/web/dist
COPY scripts/ /app/scripts/

# Chromium + OS deps for Apply Browser (Playwright)
RUN playwright install-deps chromium \
    && PLAYWRIGHT_BROWSERS_PATH=/ms-playwright playwright install chromium \
    && chown -R appuser:appuser /ms-playwright

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
