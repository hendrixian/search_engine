#!/bin/bash
# setup_milvus_integration.sh
# Setup script for integrating Milvus vector database into the academic search engine

set -e

echo "🚀 Setting up Milvus Vector Database Integration"
echo "================================================"

# Create necessary directories
echo "📁 Creating directory structure..."
mkdir -p database
mkdir -p scripts
mkdir -p logs

# Check if docker-compose exists
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose not found. Please install Docker Compose first."
    exit 1
fi

# Check if Docker is running
if ! docker info &> /dev/null; then
    echo "❌ Docker is not running. Please start Docker first."
    exit 1
fi

# Create .env file template if it doesn't exist
if [ ! -f .env ]; then
    echo "📝 Creating .env template..."
    cat > .env << EOL
# MinIO Configuration
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin123
MINIO_SECURE=false

# Milvus Configuration
MILVUS_HOST=milvus-standalone
MILVUS_PORT=19530

# Flask Configuration
FLASK_SECRET_KEY=your-secret-key-here
FLASK_ENV=production

# Redis Configuration
REDIS_HOST=redis
REDIS_PORT=6379

# Elasticsearch Configuration
ELASTICSEARCH_HOST=http://elasticsearch:9200

# Hugging Face Token (optional)
HUGGINGFACE_TOKEN=your-token-here

# Mistral AI Token (optional)
MISTRAL_API_KEY=your-mistral-key-here

# Model Cache Directory
MODEL_CACHE_DIR=./models
EOL
    echo "✅ Created .env template - please update with your configurations"
fi

# Pull required Docker images
echo "🐳 Pulling required Docker images..."
docker pull quay.io/coreos/etcd:v3.5.5
docker pull minio/minio:RELEASE.2023-03-20T20-16-18Z  
docker pull milvusdb/milvus:v2.4.9
docker pull redis:alpine
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.13.4

# Start services
echo "🚀 Starting services with docker-compose..."
docker-compose up -d

# Wait for services to be healthy
echo "⏳ Waiting for services to be ready..."
sleep 30

# Check service health
echo "🔍 Checking service health..."

# Check Elasticsearch
if curl -f http://localhost:9200/_cluster/health &> /dev/null; then
    echo "✅ Elasticsearch is healthy"
else
    echo "⚠️ Elasticsearch may not be ready yet"
fi

# Check MinIO
if curl -f http://localhost:9000/minio/health/live &> /dev/null; then
    echo "✅ MinIO is healthy"
else
    echo "⚠️ MinIO may not be ready yet"
fi

# Check Milvus
if curl -f http://localhost:9091/healthz &> /dev/null; then
    echo "✅ Milvus is healthy"
else
    echo "⚠️ Milvus may not be ready yet"
fi

# Check Redis
if redis-cli -h localhost -p 6379 ping &> /dev/null; then
    echo "✅ Redis is healthy"
else
    echo "⚠️ Redis may not be ready yet"
fi

echo ""
echo "🎉 Milvus integration setup completed!"
echo ""
echo "📋 Next Steps:"
echo "1. Update your .env file with proper credentials"
echo "2. If you have existing passage data in MinIO, run the migration:"
echo "   python scripts/migrate_passages_to_milvus.py --dry-run"
echo "3. Start your Flask application with the enhanced features"
echo ""
echo "🌐 Service Endpoints:
echo "   - Search API: http://localhost:5000"
echo "   - Search UI: http://localhost:8080"
echo "   - Monitor Dashboard: http://localhost:5001"
echo "   - MinIO Console: http://localhost:9001"
echo "   - Elasticsearch: http://localhost:9200"
echo "   - Milvus: localhost:19530"
echo ""
echo "📚 To test vector search:"
echo "   curl -X POST http://localhost:5000/api/search \\"
echo "     -H 'Content-Type: application/json' \\"
echo "     -d '{\"query\": \"machine learning algorithms\"}'"
echo ""
echo "🔧 To check system status:"
echo "   curl http://localhost:5000/api/status"
echo ""
echo "Happy searching! 🔍✨"