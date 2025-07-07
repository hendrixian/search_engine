FROM bitnami/python:3.11

# Set working directory
WORKDIR /app

# Install Java (required for PySpark)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-17-jre-headless && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# Set environment variables
ENV JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64
ENV PYTHONUTF8=1

# Pre-install heavy dependency separately to cache it better
RUN pip install --upgrade pip && \
    pip install --no-cache-dir pyspark==4.0.0 && \
    pip install elasticsearch==8.13.0




# Copy only requirements for caching
COPY requirements.txt .

# Install remaining Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Download nltk data at build time for efficiency
RUN python -m nltk.downloader punkt

# Copy rest of the app code
COPY . .

# Expose the Streamlit default port
EXPOSE 8501

# Run Streamlit app with hot reload
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.runOnSave=true"]
