# =============================================================================
# Backend Dockerfile - Python + FastAPI
# =============================================================================
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install uv for fast dependency resolution
RUN pip install --no-cache-dir uv

# Copy dependency files first (layer caching)
COPY pyproject.toml ./

# Install dependencies using uv
RUN uv pip install --system --no-cache -e .

# Copy the rest of the application
COPY . .

# Create non-root user for security
RUN adduser --disabled-password --gecos "" appuser && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 8000

# Default command (overridden in docker-compose for dev with --reload)
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
