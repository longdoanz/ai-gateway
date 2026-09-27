# AI Gateway - Docker Image
# Optimized single-stage build

FROM python:3.10-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Create non-root user for security (UID 1000 to match host for bind mount)
RUN groupadd -r -g 1000 aigw && useradd -r -u 1000 -g aigw aigw

# Set working directory and give ownership to aigw user
WORKDIR /app
RUN chown aigw:aigw /app

# Install dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY --chown=aigw:aigw . .

# Remove runtime files that should not be in image
# (in case they were copied from build context or cache)
RUN rm -f credentials.json state.json

# Create directory for debug logs with proper permissions
RUN mkdir -p debug_logs && chown -R aigw:aigw debug_logs
#COPY --chown=aigw:aigw /home/administrator/.local/share/kiro-cli/data.sqlite3 /app/data.sqlite3

# Switch to non-root user
USER aigw

# Expose port
EXPOSE 8000

# Health check
# Using httpx (our main HTTP library) instead of requests
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health', timeout=5)"

# Run the application
CMD ["python", "main.py"]
