# syntax=docker/dockerfile:1
FROM python:3.11-slim

# Set environment flags
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

# Install security updates and essential runtime utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-privileged user and group
RUN groupadd -g 10001 appgroup && \
    useradd -u 10001 -g appgroup -s /bin/bash -m appuser

# Install Python dependencies and the application package
COPY pyproject.toml .
COPY app/ ./app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir .

# Include the Alembic migration chain in the runtime image
COPY alembic.ini .
COPY migrations/ ./migrations/

# Switch ownership to non-root user
RUN chown -R appuser:appgroup /app

USER appuser

EXPOSE 8080

# Cloud Run injects $PORT (default 8080).
# uvicorn runs behind Google Cloud Load Balancer / Envoy proxy with HTTPS termination.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --proxy-headers --forwarded-allow-ips='*'"]
