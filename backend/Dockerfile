FROM python:3.11-slim

WORKDIR /app

# Install only runtime Postgres libraries to keep the image slim and secure
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root system user and group
RUN groupadd -r appgroup && useradd -r -g appgroup -d /app -s /sbin/nologin appuser

# Copy requirements first to leverage Docker layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code with non-root ownership
COPY --chown=appuser:appgroup . .

# Run as non-root user
USER appuser

EXPOSE 8000

# Run database migrations before launching uvicorn server
CMD ["sh", "-c", "alembic upgrade head && uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
