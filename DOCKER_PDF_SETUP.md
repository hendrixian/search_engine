# 🐳 Docker PDF Auto-Extraction Setup

This guide shows how to run PDF auto-extraction using your existing Docker Compose setup.

## 🚀 Quick Start

### 1. Make sure you have the .env file in Docker folder:

Create `Docker/.env` with:

```bash
# MinIO Configuration
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin

# Mistral AI API Key (optional)
MISTRAL_API_KEY=your_mistral_api_key_here

# Flask Configuration
FLASK_SECRET_KEY=your_secret_key_here
```

### 2. Start all services:

```bash
cd Docker
docker-compose up -d
```

This will start:

- ✅ **MinIO** (ports 9000, 9001) with webhook configuration
- ✅ **PDF Processor Service** (port 5002) for automatic PDF processing
- ✅ **MinIO Setup** service to configure webhooks
- ✅ All your existing services (Elasticsearch, Milvus, etc.)

### 3. Check services are running:

```bash
# Check all services
docker-compose ps

# Check PDF processor logs
docker-compose logs pdf-processor

# Check MinIO setup logs
docker-compose logs minio-setup
```

You should see:

```
✅ PDF Processor Service initialized successfully
📡 Webhook endpoint: http://0.0.0.0:5002/webhook/minio
MinIO PDF auto-extraction setup completed!
```

## 🧪 Test PDF Auto-Extraction

### 1. Upload a PDF to MinIO:

- Go to MinIO Console: http://localhost:9001
- Login: `minioadmin` / `minioadmin`
- Navigate to `papers` bucket
- Upload any PDF file

### 2. Check the logs:

```bash
docker-compose logs -f pdf-processor
```

You should see:

```
📨 Received MinIO webhook: s3:ObjectCreated:Put
🔍 Processing file: papers/your-file.pdf
📥 Downloading PDF from MinIO: papers/your-file.pdf
🔍 Extracting metadata from: /tmp/papers_your-file.pdf
✅ Successfully extracted metadata for: Your PDF Title
🎉 PDF processed and added to papers.csv
```

### 3. Check papers.csv:

```bash
# Check if new paper was added
cat papers.csv
```

## 🔧 Manual Testing

### Test PDF processor directly:

```bash
# Test health check
curl http://localhost:5002/health

# Test status
curl http://localhost:5002/api/status

# Manually process a PDF
curl -X POST "http://localhost:5002/api/process-pdf/your-file.pdf?bucket=papers"
```

## 🐛 Troubleshooting

### Check service status:

```bash
# Check all services
docker-compose ps

# Check specific service logs
docker-compose logs pdf-processor
docker-compose logs minio
docker-compose logs minio-setup
```

### Common issues:

**1. PDF processor not starting:**

```bash
# Check if PDF libraries are installed in container
docker-compose exec pdf-processor python -c "import fitz, pdfplumber; print('PDF libs OK')"
```

**2. MinIO webhook not configured:**

```bash
# Re-run setup
docker-compose restart minio-setup

# Check MinIO events
docker-compose exec minio-setup mc event list minio/papers
```

**3. CSV file not writable:**

```bash
# Check file permissions
ls -la papers.csv

# Fix permissions if needed
chmod 666 papers.csv
```

**4. Webhook not receiving events:**

```bash
# Check MinIO webhook configuration
docker-compose logs minio

# Test webhook endpoint
curl -X POST http://localhost:5002/webhook/minio -H "Content-Type: application/json" -d '{}'
```

## 📊 Service Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   MinIO Web     │    │   PDF Processor  │    │   papers.csv    │
│  (port 9001)    │    │   (port 5002)    │    │                 │
│                 │    │                  │    │                 │
│ 1. Upload PDF   │───▶│ 2. Receive       │───▶│ 3. Add metadata │
│                 │    │    webhook       │    │                 │
└─────────────────┘    └──────────────────┘    └─────────────────┘
```

## 🎯 What Happens When You Upload a PDF:

1. **Upload PDF** to MinIO via web interface (localhost:9001)
2. **MinIO sends webhook** to PDF processor service
3. **PDF processor downloads** the PDF from MinIO
4. **Extracts metadata** (title, authors, abstract) using PyMuPDF + pdfplumber
5. **Adds new row** to papers.csv with extracted data
6. **Cleans up** temporary files
7. **Logs success** - ready for search engine to use!

## 🔄 Integration with Search Engine

After PDFs are added to papers.csv:

1. **Restart search services** to pick up new papers:

   ```bash
   docker-compose restart search-api search-ui
   ```

2. **Re-index if needed**:

   ```bash
   docker-compose exec search-api python index.py
   ```

3. **Update Milvus** (if using vector search):
   ```bash
   docker-compose exec search-api python scripts/migrate_passages_to_milvus.py
   ```

## ✅ Success!

Your PDF auto-extraction is now fully integrated with your existing Docker setup! 🎉

- Upload PDFs to MinIO → Automatic metadata extraction → Ready for search
- No manual intervention needed
- All logs available via `docker-compose logs`
- Scalable and maintainable architecture
