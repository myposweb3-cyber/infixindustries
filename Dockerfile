FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN pip install gunicorn

# Copy application code
COPY . .

# Expose port
EXPOSE 5000

# Run application with Gunicorn
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:5000", "--timeout", "300", "--max-requests", "10", "--max-requests-jitter", "2", "--access-logfile", "-", "--error-logfile", "-", "app:create_app()"]

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/health || exit 1
