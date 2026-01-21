# Cold Outreach Copilot - Docker Image
FROM python:3.10-slim

WORKDIR /app

# Install system dependencies for Playwright and healthcheck
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better layer caching)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright browsers (this takes a while, so do it before app code)
RUN playwright install chromium
RUN playwright install-deps chromium

# Copy application code
COPY app/ ./app/
COPY src/ ./src/
COPY .env.example .env.example

# Create data directories with proper permissions
RUN mkdir -p data/uploads data/scraped_content && \
    chmod -R 777 data/

# Expose Streamlit port
EXPOSE 8501

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

# Run Streamlit
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
