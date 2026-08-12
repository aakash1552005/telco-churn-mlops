# ==============================================================================
# Phase 11 — Docker Containerization
# Multi-stage production build for FastAPI Telco Churn Prediction Service
#
# ARCHITECTURAL SEPARATION & MOUNT CONTRACT:
# - Image contains: application code (src/), dependencies (/opt/venv), entrypoint.
# - Host bind mounts provide (runtime): models/, mlruns/, and mlflow.db.
# ==============================================================================

# ------------------------------------------------------------------------------
# Stage 1: Builder Stage
# ------------------------------------------------------------------------------
FROM python:3.12.3-slim-bookworm AS builder

WORKDIR /build

# Prevent interactive prompts during build
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Install system build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create isolated virtual environment for dependencies
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy dependency definition file
COPY pyproject.toml .

# Install dependencies into virtual environment (excluding secrets or dev tools)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir .

# ------------------------------------------------------------------------------
# Stage 2: Production Runner Stage
# ------------------------------------------------------------------------------
FROM python:3.12.3-slim-bookworm AS runner

# OCI Image Specification Metadata Labels
LABEL org.opencontainers.image.title="Telco Churn Prediction API" \
      org.opencontainers.image.description="Production REST API serving registered MLflow models with feature transformation and optimal thresholding" \
      org.opencontainers.image.vendor="Telco MLOps Team" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.schema-version="1.0.0"

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH="/opt/venv/bin:$PATH" \
    API_HOST="0.0.0.0" \
    API_PORT="8000" \
    ENVIRONMENT="development"

# Install curl for readiness container healthcheck instruction
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy virtual environment from builder stage
COPY --from=builder /opt/venv /opt/venv

# Create non-root system user and group for security compliance
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Prepare app directory structure with correct appuser permissions
# (models/, mlruns/, and mlflow.db will be supplied dynamically via host bind mounts)
RUN mkdir -p /app/models /app/mlruns /app/src && \
    chown -R appuser:appgroup /app

# Copy application source code and package configuration
COPY --chown=appuser:appgroup src/ /app/src/
COPY --chown=appuser:appgroup pyproject.toml /app/pyproject.toml

# Switch to non-root user
USER appuser

# Expose FastAPI HTTP server port
EXPOSE 8000

# Configure Docker Healthcheck instruction based on /health/readiness
HEALTHCHECK --interval=10s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/readiness || exit 1

# Default Command: Launch Uvicorn ASGI server serving FastAPI prediction application
CMD ["python", "-m", "uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
