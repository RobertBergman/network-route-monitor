FROM python:3.10-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install uvicorn for the web UI
RUN pip install --no-cache-dir uvicorn[standard]

# Copy application code
COPY *.py ./
COPY pytest.ini ./
COPY webui/ ./webui/

# Create directories for data persistence
RUN mkdir -p /app/route_snaps

# Expose ports
# 5000 - API server
# 8080 - Web UI (if run separately)
# 9108 - Prometheus metrics
EXPOSE 5000 8080 9108

# Default command (can be overridden in docker-compose)
CMD ["python", "poller.py"]