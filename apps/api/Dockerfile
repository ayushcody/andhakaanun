# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy project configuration
COPY pyproject.toml .

# Install dependencies into a virtualenv
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Upgrade pip and install dependencies using setuptools backwards compatibility
RUN pip install --upgrade pip && \
    pip install .

# Runtime stage
FROM python:3.11-slim

WORKDIR /app

# Install runtime dependencies for psycopg2/asyncpg if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Copy virtualenv from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY apps/api /app/apps/api
COPY packages /app/packages
# If alembic.ini is at root, copy it
COPY alembic.ini /app/alembic.ini
COPY apps/api/entrypoint.sh /entrypoint.sh

RUN chmod +x /entrypoint.sh

# Expose port
EXPOSE 8000

# Use entrypoint to run migrations
ENTRYPOINT ["/entrypoint.sh"]

# Start the application using gunicorn with uvicorn workers
CMD ["gunicorn", "apps.api.main:app", "--workers", "4", "--worker-class", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:8000"]
