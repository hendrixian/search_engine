FROM python:3.11-slim

# Force apt to use IPv4 (to avoid connection issues with IPv6)
ENV APT_CONFIG=/etc/apt/apt.conf.d/99force-ipv4
RUN echo 'Acquire::ForceIPv4 "true";' > $APT_CONFIG

# Set working directory
WORKDIR /app

# Install system dependencies (including curl for health checks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
ENV PYTHONUTF8=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# FIXED: Set model cache directory and memory optimization
ENV TRANSFORMERS_CACHE=/app/model_cache
ENV SENTENCE_TRANSFORMERS_HOME=/app/models
ENV TORCH_HOME=/app/model_cache
ENV HF_HOME=/app/models  
# Instead of TRANSFORMERS_CACHE
# Memory optimization for PyTorch
ENV OMP_NUM_THREADS=2
ENV TOKENIZERS_PARALLELISM=false

# Copy requirements first for better caching
COPY requirements.txt .

# FIXED: Install core dependencies with explicit versions and CPU-only PyTorch
RUN pip install --upgrade pip && \
    pip install --no-cache-dir \
    torch==2.2.2+cpu torchvision==0.17.2+cpu torchaudio==2.2.2+cpu \
    --index-url https://download.pytorch.org/whl/cpu && \
    pip install --no-cache-dir \
    transformers==4.53.1 \
    sentence-transformers==5.0.0 \
    pandas==2.3.0 \
    numpy==1.26.4 \
    pyspark==4.0.0 \
    gunicorn==21.2.0 \
    gevent==23.9.1

# Install remaining Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download nltk data at build time for efficiency
RUN python -c "import nltk; nltk.download('punkt', download_dir='/app/nltk_data')"
ENV NLTK_DATA=/app/nltk_data

# Copy application code
COPY . .


COPY templates/ /app/templates/
COPY static/ /app/static/
# Create necessary directories
RUN mkdir -p /app/templates /app/static /app/model_cache /app/nltk_data

# FIXED: Set proper permissions and create non-root user for security
RUN groupadd -r appuser && useradd -r -g appuser appuser && \
    chown -R appuser:appuser /app
USER appuser

# Expose ports
EXPOSE 5000 8080

# FIXED: Better health check with proper timeout
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:5000/api/status || exit 1

# FIXED: Remove conflicting worker configurations
# Use only sync workers since we have gevent specified in docker-compose
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "2", \
     "--timeout", "120", "--preload", "--max-requests", "1000", \
     "--max-requests-jitter", "50", "wsgi:app"]