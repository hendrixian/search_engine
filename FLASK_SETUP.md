# Flask Search Engine Setup Guide

## 🚀 Complete Integration of Your Existing Services

Your Flask app now integrates all your existing search services:

- ✅ **MultiSiteCrawler** - Web search across GeeksforGeeks, MathWorld, Engineering.com
- ✅ **Elasticsearch** - Academic papers search
- ✅ **MinIO** - Document storage and passages
- ✅ **Mistral AI** - Intelligent answer generation
- ✅ **Sentence Transformers** - Semantic search capabilities
- ✅ **Real-time Auto-suggestions** - No unwanted automatic searches

## 📋 Prerequisites

### 1. Environment Variables

Create a `.env` file in your project root:

```bash
# Flask Configuration
FLASK_SECRET_KEY=your-super-secret-key-change-this-in-production

# Elasticsearch Configuration
ELASTICSEARCH_HOST=http://localhost:9200

# MinIO Configuration
MINIO_ENDPOINT=localhost:9000
MINIO_ROOT_USER=minioadmin
MINIO_ROOT_PASSWORD=minioadmin
MINIO_SECURE=false

# AI API Configuration
HUGGINGFACE_TOKEN=your-huggingface-token-here
MISTRAL_API_KEY=your-mistral-api-key-here

# Model Cache Directory (optional)
MODEL_CACHE_DIR=./models

# Flask Development Settings
FLASK_ENV=development
FLASK_DEBUG=true
```

### 2. Required Services

Make sure these services are running:

#### Elasticsearch

```bash
# Using Docker
docker run -d --name elasticsearch \
  -p 9200:9200 \
  -e "discovery.type=single-node" \
  -e "xpack.security.enabled=false" \
  elasticsearch:8.11.0
```

#### MinIO

```bash
# Using Docker
docker run -d --name minio \
  -p 9000:9000 \
  -p 9001:9001 \
  -e "MINIO_ROOT_USER=minioadmin" \
  -e "MINIO_ROOT_PASSWORD=minioadmin" \
  minio/minio server /data --console-address ":9001"
```

## 🔧 Installation

### 1. Install Dependencies

```bash
pip install -r requirements_flask.txt
```

### 2. Verify Your Project Structure

```
search_engine/
├── flask_app.py              # ✅ Updated with all services
├── mistral.py                # ✅ Your existing Mistral integration
├── crawlers/
│   ├── multi_crawler.py      # ✅ Your existing web crawler
│   ├── geeksforgeeks.py      # ✅ Your existing crawler
│   ├── mathworld.py          # ✅ Your existing crawler
│   └── engineering.py        # ✅ Your existing crawler
├── templates/
│   └── index.html            # ✅ Beautiful UI
├── static/
│   ├── css/style.css         # ✅ Modern styling
│   └── js/search.js          # ✅ Real-time functionality
├── requirements_flask.txt    # ✅ All dependencies
├── run_flask.py             # ✅ Easy launcher
└── .env                     # ✅ Your configuration
```

### 3. Run the Application

```bash
# Easy way
python run_flask.py

# Or manually
python flask_app.py
```

### 4. Open in Browser

Navigate to: `http://localhost:5000`

## 🎯 Features Available

### ✅ **Real-time Auto-suggestions**

- Debounced input (200ms)
- Smart academic suggestions
- No unwanted automatic searches

### ✅ **Comprehensive Search**

- **Web Results**: Your MultiSiteCrawler searches GeeksforGeeks, MathWorld, Engineering.com
- **Academic Papers**: Elasticsearch semantic search
- **Document Passages**: MinIO document processing
- **AI Answers**: Mistral AI generates comprehensive responses

### ✅ **Service Status Monitoring**

The app automatically detects which services are available:

- Web Crawler: ✅/❌
- Elasticsearch: ✅/❌
- MinIO: ✅/❌
- Mistral AI: ✅/❌

## 🔍 How It Works

### Search Flow

1. **Type in search box** → Auto-suggestions appear (no search triggered)
2. **Click Search or suggestion** → All services search in parallel:
   - MultiSiteCrawler searches web sources
   - Elasticsearch searches academic papers
   - MinIO provides document passages
   - Mistral AI generates comprehensive answer

### API Endpoints

#### `GET /api/suggestions?q=query`

Real-time suggestions with academic focus

#### `POST /api/search`

Comprehensive search across all your services

**Example Response:**

```json
{
  "query": "machine learning",
  "web_results": [...],       // From your MultiSiteCrawler
  "academic_papers": [...],   // From Elasticsearch
  "passages": [...],          // From MinIO
  "ai_answer": "...",         // From Mistral AI
  "search_time": 1.23,
  "service_status": {
    "web_crawler": true,
    "elasticsearch": true,
    "minio": true,
    "mistral_ai": true
  }
}
```

## 🚨 Troubleshooting

### Service Not Available

The app gracefully handles missing services:

- If Elasticsearch is down: Academic search disabled, others work
- If MinIO is down: Passage search disabled, others work
- If Mistral API fails: Shows fallback message, search results still available

### Port Conflicts

Change the port in `flask_app.py`:

```python
app.run(debug=True, host='0.0.0.0', port=5001)  # Use different port
```

### Model Loading Issues

Models are cached to `./models/` directory. If loading fails:

1. Check available disk space
2. Verify HuggingFace token
3. Check internet connection for first-time downloads

## 🎉 Testing Your Setup

1. **Start the app**: `python run_flask.py`
2. **Check console output** for service status:
   ```
   ✅ Web crawler initialized
   ✅ Elasticsearch connected
   ✅ MinIO client initialized
   ✅ AI models loaded successfully
   ```
3. **Open browser**: `http://localhost:5000`
4. **Test auto-suggestions**: Type "machine" - should show suggestions immediately
5. **Test search**: Click a suggestion or search button - should show all result types

## 🔄 Migration from Streamlit

Your Flask app now provides:

- ✅ **Better performance** - No unwanted reruns
- ✅ **Real-time suggestions** - Smooth, responsive
- ✅ **Full control** - Search only when intended
- ✅ **All your services** - Everything integrated
- ✅ **Beautiful UI** - Modern, responsive design

The Flask version maintains all your existing functionality while solving the auto-search issues you experienced with Streamlit!

## 🚀 Next Steps

1. **Test all services** with your existing data
2. **Customize suggestions** in `ACADEMIC_SUGGESTIONS` list
3. **Add authentication** if needed
4. **Deploy to production** with proper security settings
5. **Monitor performance** and add caching as needed

Your search engine is now fully functional with Flask! 🎉
