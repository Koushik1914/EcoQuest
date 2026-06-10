# ════════════════════════════════════════════════════════════════════════════
# EcoQuest Backend — Multi-stage Docker build
# Base: python:3.11-slim  |  Non-root user  |  Minimal final image
# ════════════════════════════════════════════════════════════════════════════

# ── Stage 1: Builder ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

# Install only build-time system deps (wheel compilation, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

# Copy and install Python dependencies into an isolated directory
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ──────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

# Install only runtime system deps
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libffi8 \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Create non-root application user
RUN groupadd --gid 10001 appgroup \
    && useradd --uid 10001 --gid appgroup --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copy application source (before switching user for correct ownership)
COPY --chown=appuser:appgroup app/ ./app/

# Switch to non-root user
USER appuser

# Expose Cloud Run default port
EXPOSE 8080

# Health check — Cloud Run will use this before directing traffic
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

# Launch uvicorn with production settings
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8080", \
     "--workers", "1", \
     "--loop", "uvloop", \
     "--http", "httptools", \
     "--log-level", "info", \
     "--no-access-log"]
