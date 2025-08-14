# 🔎 Academic Search Engine

A powerful Flask-based search engine that combines web crawling, academic paper search, and AI-powered answers. Built with modern web technologies and comprehensive search capabilities.

## ✨ Features

- **🌐 Web Crawler**: Search across GeeksforGeeks, MathWorld, and Engineering.com
- **📚 Academic Search**: Elasticsearch integration for research papers and documents
- **🤖 AI Answers**: Mistral AI-powered comprehensive responses using all sources
- **💡 Auto-suggestions**: Google-style search suggestions as you type
- **🎨 Modern UI**: Beautiful tabbed interface with responsive design
- **⚡ Real-time Search**: Instant results across all sources simultaneously

## 🏗️ Architecture

- **Frontend**: HTML5, CSS3, JavaScript (Vanilla)
- **Backend**: Flask (Python)
- **Search Engine**: Elasticsearch
- **Object Storage**: MinIO
- **AI Models**: Sentence Transformers, Hugging Face Transformers
- **AI API**: Mistral AI
- **Web Crawlers**: Custom MultiSiteCrawler
- **Containerization**: Docker & Docker Compose

## 📋 Prerequisites

- **Python 3.8+**
- **Docker Desktop** (for Elasticsearch and MinIO)
- **Git**

## 🚀 Quick Setup

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/academic-search-engine.git
cd academic-search-engine
```

### 2. Install Python Dependencies

```bash
pip install -r requirements.txt
```

### 3. Set Up Environment Variables

Create a `.env` file in the root directory:

```env
# Mistral AI API Key (Required for AI answers)
MISTRAL_API_KEY=your_mistral_api_key_here

# Hugging Face Token (Required for AI models)
HUGGINGFACE_TOKEN=your_huggingface_token_here

# Flask Secret Key
FLASK_SECRET_KEY=your_secure_secret_key_here

# Optional: Custom paths
MODEL_CACHE_DIR=./models
```

### 4. Start Required Services

Start Elasticsearch and MinIO using Docker:

```bash
cd Docker
docker-compose up -d elasticsearch minio
```

Wait for services to be ready (about 1-2 minutes).

### 5. Run the Application

```bash
python flask_app.py
```

The app will be available at: **http://localhost:5000**

## 🔧 Detailed Setup

### Environment Variables Explained

| Variable            | Description               | Required | Default        |
| ------------------- | ------------------------- | -------- | -------------- |
| `MISTRAL_API_KEY`   | Your Mistral AI API key   | ✅ Yes   | -              |
| `HUGGINGFACE_TOKEN` | Hugging Face access token | ✅ Yes   | -              |
| `FLASK_SECRET_KEY`  | Flask application secret  | ❌ No    | Auto-generated |
| `MODEL_CACHE_DIR`   | AI models cache directory | ❌ No    | `./models`     |

### Getting API Keys

#### Mistral AI API Key

1. Go to [Mistral AI Console](https://console.mistral.ai/)
2. Sign up/Login
3. Navigate to API Keys section
4. Create a new API key
5. Copy and paste into `.env` file

#### Hugging Face Token

1. Go to [Hugging Face](https://huggingface.io/)
2. Sign up/Login
3. Go to Settings → Access Tokens
4. Create a new token
5. Copy and paste into `.env` file

### Docker Services

The project uses Docker Compose to manage:

- **Elasticsearch**: Search engine for academic papers
- **MinIO**: Object storage for document passages

```bash
# Start services
docker-compose up -d elasticsearch minio

# Stop services
docker-compose down

# View logs
docker-compose logs elasticsearch
docker-compose logs minio
```

## 📁 Project Structure

```
academic-search-engine/
├── flask_app.py              # Main Flask application
├── requirements.txt           # Python dependencies
├── README.md                 # This file
├── .env                      # Environment variables (create this)
├── templates/
│   └── index.html           # Main web interface
├── static/                   # Static assets (CSS, JS, images)
├── crawlers/                 # Web crawler modules
│   ├── base_engine.py
│   ├── multi_crawler.py
│   ├── geeksforgeeks.py
│   ├── mathworld.py
│   └── engineering.py
├── Docker/                   # Docker configuration
│   ├── docker-compose.yml
│   └── Dockerfile
└── monitor/                  # Monitoring dashboard
    └── dashboard.py
```

## 🎯 Usage

### Basic Search

1. Open **http://localhost:5000** in your browser
2. Type your query in the search bar
3. Click "🔍 Search All Sources" or press Enter
4. View results in the three tabs:
   - **🌐 Web Crawler**: Results from websites
   - **📚 Academic Papers**: Research papers
   - **🤖 AI Answer**: AI-generated comprehensive answer

### Auto-suggestions

- Start typing to see instant suggestions
- Click any suggestion to search automatically
- Suggestions include academic terms and previous searches

### Tab Navigation

- Switch between tabs to view different result types
- Each tab shows loading states during search
- Results are organized by source and relevance

## 🐛 Troubleshooting

### Common Issues

#### 1. "Elasticsearch not available"

```bash
# Check if Elasticsearch is running
docker ps | grep elasticsearch

# Restart if needed
cd Docker
docker-compose restart elasticsearch
```

#### 2. "MinIO not available"

```bash
# Check if MinIO is running
docker ps | grep minio

# Restart if needed
cd Docker
docker-compose restart minio
```

#### 3. "AI models not loaded"

- Ensure you have a valid `HUGGINGFACE_TOKEN`
- Check internet connection (models are downloaded on first run)
- Verify the `.env` file is in the root directory

#### 4. "Mistral AI not available"

- Verify your `MISTRAL_API_KEY` is correct
- Check if the API key has sufficient credits
- Ensure the `.env` file is properly formatted

### Port Conflicts

If port 5000 is already in use:

```bash
# Find what's using the port
netstat -an | findstr :5000

# Kill the process or change the port in flask_app.py
```

## 🔒 Security Notes

- **Never commit your `.env` file** to version control
- **Keep API keys secure** and rotate them regularly
- **Use strong Flask secret keys** in production
- **Consider rate limiting** for production deployments

## 🚀 Production Deployment

For production use, consider:

- Using a production WSGI server (Gunicorn, uWSGI)
- Setting up proper logging
- Implementing rate limiting
- Using environment-specific configurations
- Setting up monitoring and health checks

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- **Mistral AI** for powerful language models
- **Hugging Face** for transformer models
- **Elasticsearch** for search capabilities
- **MinIO** for object storage
- **Flask** for the web framework

## 📞 Support

If you encounter any issues:

1. Check the troubleshooting section above
2. Search existing GitHub issues
3. Create a new issue with detailed information
4. Include your environment details and error messages

---

**Happy Searching! 🔍✨**
