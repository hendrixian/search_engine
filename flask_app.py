from flask import Flask, render_template, request, jsonify
import time
import json
from datetime import datetime
import os
import io
import html
import re
from functools import lru_cache
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
print(f"🔍 Environment file loaded from: {os.path.abspath('.env')}")

# Import your existing search functionality
try:
    from elasticsearch import Elasticsearch
    from minio import Minio
    from sentence_transformers import SentenceTransformer
    from transformers import pipeline
    from crawlers.multi_crawler import MultiSiteCrawler
    print("✅ Core modules imported successfully")
except ImportError as e:
    print(f"Warning: Some core modules not found: {e}")
    print("Please ensure all required modules are installed and available.")

# Import Mistral separately (optional)
try:
    from mistral import call_mistral
    mistral_available = True
    print("✅ Mistral AI module imported successfully")
except ImportError as e:
    print(f"⚠️  Mistral AI not available: {e}")
    call_mistral = None
    mistral_available = False
except ValueError as e:
    print(f"⚠️  Mistral API key not configured: {e}")
    call_mistral = None
    mistral_available = False

app = Flask(__name__)
app.secret_key = os.getenv('FLASK_SECRET_KEY', 'your-secure-secret-key-here')

# Environment variables
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

# Model cache directories
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "./models")
os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODEL_CACHE_DIR

# Global variables for loaded models and services
embedder = None
qa_pipeline = None
web_crawler = None
es = None
minio_client = None

def load_models():
    """Load AI models (called once at startup)"""
    global embedder, qa_pipeline
    try:
        print("Loading AI models...")
        embedder = SentenceTransformer("all-MiniLM-L6-v2")
        qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")
        print("✅ AI models loaded successfully")
    except Exception as e:
        print(f"❌ Error loading AI models: {e}")
        embedder = None
        qa_pipeline = None

def initialize_services():
    """Initialize all search services"""
    global web_crawler, es, minio_client
    
    # Initialize web crawler
    try:
        web_crawler = MultiSiteCrawler()
        print("✅ Web crawler initialized")
    except Exception as e:
        print(f"❌ Error initializing web crawler: {e}")
        web_crawler = None
    
    # Initialize Elasticsearch (optional - won't crash if not available)
    try:
        es = Elasticsearch([ELASTICSEARCH_HOST], request_timeout=3, max_retries=1)
        # Test connection with shorter timeout
        if es.ping():
            print("✅ Elasticsearch connected")
        else:
            print("⚠️  Elasticsearch not responding - academic search will be disabled")
            es = None
    except Exception as e:
        print(f"⚠️  Elasticsearch not available - academic search will be disabled: {e}")
        es = None
    
    # Initialize MinIO (optional - won't crash if not available)
    try:
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ROOT_USER,
            secret_key=MINIO_ROOT_PASSWORD,
            secure=MINIO_SECURE
        )
        # Test connection with shorter timeout
        minio_client.list_buckets()
        print("✅ MinIO client initialized")
    except Exception as e:
        print(f"⚠️  MinIO not available - passage search will be disabled: {e}")
        minio_client = None

# Initialize services at startup
print("🚀 Initializing Flask app services...")
initialize_services()
load_models()
print("✅ Flask app initialization complete!")

# Academic suggestions (from your original code)
ACADEMIC_SUGGESTIONS = [
    "machine learning algorithms", "deep learning neural networks", "natural language processing",
    "computer vision", "artificial intelligence", "data science", "quantum computing",
    "cybersecurity", "software engineering", "web development", "database systems",
    "python programming", "javascript frameworks", "data structures algorithms",
    "mobile app development", "user interface design", "network protocols",
    "operating systems", "cloud computing", "blockchain technology",
    "machine learning applications", "neural network architecture", "computer science",
    "information technology", "software architecture", "web technologies",
    "programming languages", "algorithm design", "data analysis", "statistics",
    "mathematical modeling", "optimization techniques", "research methodology",
    "big data analytics", "machine learning models", "deep learning frameworks",
    "computer graphics", "human computer interaction", "software testing",
    "agile development", "devops practices", "microservices architecture",
    "api development", "frontend frameworks", "backend development",
    "mobile app design", "user experience design", "information security",
    "network security", "cryptography", "distributed systems",
    "parallel computing", "high performance computing", "bioinformatics",
    "computational biology", "robotics", "autonomous systems",
    "internet of things", "edge computing", "fog computing"
]

# Utility functions from your original code
def clean_html_snippet(snippet):
    """Clean HTML tags from snippet text and return plain text"""
    if not snippet:
        return ""
    
    # Remove HTML tags
    clean_text = re.sub(r'<[^>]+>', '', snippet)
    
    # Decode HTML entities
    clean_text = html.unescape(clean_text)
    
    # Clean up extra whitespace
    clean_text = re.sub(r'\s+', ' ', clean_text).strip()
    
    return clean_text

def format_time_elapsed(seconds):
    """Format elapsed time like Google (e.g., 'About 0.23 seconds')"""
    if seconds < 1:
        return f"About {seconds:.2f} seconds"
    else:
        return f"About {seconds:.1f} seconds"

@lru_cache(maxsize=100)
def get_paper_preview(paper_id, max_chars=800):
    """Extract preview content from academic paper passages"""
    if not minio_client:
        return "MinIO not available - no preview content"
    
    try:
        objects = minio_client.list_objects("passages")
        for obj in objects:
            if obj.object_name.endswith(".json") and paper_id in obj.object_name:
                resp = minio_client.get_object("passages", obj.object_name)
                buffer = io.BytesIO()
                for chunk in resp.stream(32 * 1024):
                    buffer.write(chunk)
                buffer.seek(0)
                data = json.load(buffer)
                
                # Get first meaningful passage
                for passage in data:
                    text = passage.get("text", "").strip()
                    if len(text) > 100:  # Skip very short passages
                        # Clean and truncate
                        preview = text.replace("\n", " ").strip()
                        if len(preview) > max_chars:
                            preview = preview[:max_chars] + "..."
                        return preview
    except Exception as e:
        return f"Could not load preview: {str(e)}"
    return "No preview available"

def generate_comprehensive_answer(query, web_results, academic_papers):
    """Generate AI answer using Mistral API with context from search results"""
    try:
        # Prepare context from search results
        context_parts = []
        
        # Add web results context
        for i, result in enumerate(web_results[:3]):  # Top 3 web results
            title = result.get('title', 'No title')
            snippet = clean_html_snippet(result.get('snippet', ''))
            context_parts.append(f"Web Result {i+1}: {title}\n{snippet}")
        
        # Add academic papers context
        for i, paper in enumerate(academic_papers[:3]):  # Top 3 papers
            title = paper.get('title', 'No title')
            abstract = paper.get('abstract', '')
            context_parts.append(f"Academic Paper {i+1}: {title}\n{abstract}")
        
        # Combine context
        full_context = "\n\n".join(context_parts)
        
        if not full_context.strip():
            return "No sufficient context available to generate a comprehensive answer."
        
        # Call Mistral API
        ai_response = call_mistral(query, full_context)
        return ai_response
        
    except Exception as e:
        return f"Error generating AI answer: {str(e)}"

def get_smart_suggestions(query, suggestions_list, max_results=5):
    """Generate smart suggestions based on query (adapted from your original code)"""
    if not query or len(query.strip()) < 1:
        return []
    
    query_lower = query.lower().strip()
    matched_suggestions = []
    
    # Exact starts-with matches (highest priority)
    for suggestion in suggestions_list:
        if suggestion.lower().startswith(query_lower):
            matched_suggestions.append(suggestion)
    
    # Partial word matches
    if len(matched_suggestions) < max_results:
        for suggestion in suggestions_list:
            if query_lower in suggestion.lower() and suggestion not in matched_suggestions:
                matched_suggestions.append(suggestion)
    
    # Fuzzy matches for individual words
    if len(matched_suggestions) < max_results:
        query_words = query_lower.split()
        for suggestion in suggestions_list:
            if suggestion not in matched_suggestions:
                suggestion_lower = suggestion.lower()
                if any(word in suggestion_lower for word in query_words):
                    matched_suggestions.append(suggestion)
    
    return matched_suggestions[:max_results]

@app.route('/')
def index():
    """Main search page"""
    return render_template('index.html')

@app.route('/api/suggestions')
def get_suggestions():
    """API endpoint for real-time auto-suggestions"""
    query = request.args.get('q', '').strip()
    
    if not query or len(query) < 1:
        return jsonify({'suggestions': []})
    
    suggestions = get_smart_suggestions(query, ACADEMIC_SUGGESTIONS, max_results=5)
    
    return jsonify({
        'suggestions': suggestions,
        'query': query,
        'count': len(suggestions)
    })

@app.route('/api/search', methods=['POST'])
def search():
    """Main search API endpoint using all your existing services"""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    if not query:
        return jsonify({'error': 'No query provided'}), 400
    
    search_start_time = time.time()
    
    # Initialize results
    results = {
        'query': query,
        'timestamp': datetime.now().isoformat(),
        'web_results': [],
        'academic_papers': [],
        'passages': [],
        'ai_answer': '',
        'search_time': 0,
        'total_results': 0,
        'service_status': {
            'web_crawler': bool(web_crawler),
            'elasticsearch': bool(es),
            'minio': bool(minio_client),
            'mistral_ai': mistral_available and bool(call_mistral)
        }
    }
    
    try:
        # === WEB SEARCH using your MultiSiteCrawler ===
        if web_crawler:
            try:
                print(f"🔍 Starting web search for: {query}")
                web_results = web_crawler.search_web(query)
                # Clean and format web results
                formatted_web_results = []
                for result in web_results:
                    formatted_result = {
                        'title': result.get('title', 'Untitled'),
                        'url': result.get('url', ''),
                        'snippet': clean_html_snippet(result.get('snippet', '')),
                        'description': clean_html_snippet(result.get('description', '')),
                        'source': result.get('source', 'Web')
                    }
                    formatted_web_results.append(formatted_result)
                
                results['web_results'] = formatted_web_results
                print(f"✅ Web search completed: {len(formatted_web_results)} results")
            except Exception as e:
                print(f"❌ Web search error: {e}")
                results['web_results'] = []
        
        # === ACADEMIC PAPERS SEARCH using Elasticsearch ===
        if es:
            try:
                print(f"📚 Starting academic search for: {query}")
                es_result = es.search(index="academic-papers", query={
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "abstract^2", "content", "authors"],
                        "type": "best_fields",
                        "fuzziness": "AUTO"
                    }
                }, size=10)
                
                academic_papers = []
                for hit in es_result['hits']['hits']:
                    paper = hit['_source']
                    paper_data = {
                        'title': paper.get('title', 'Untitled Paper'),
                        'authors': paper.get('authors', 'Unknown Authors'),
                        'abstract': paper.get('abstract', '')[:500] + ('...' if len(paper.get('abstract', '')) > 500 else ''),
                        'year': paper.get('year', 'Unknown'),
                        'pdf_path': paper.get('pdf_path', ''),
                        'score': round(hit['_score'], 2),
                        'preview': get_paper_preview(hit['_id'])
                    }
                    academic_papers.append(paper_data)
                
                results['academic_papers'] = academic_papers
                print(f"✅ Academic search completed: {len(academic_papers)} papers found")
            except Exception as e:
                print(f"❌ Academic search error: {e}")
                results['academic_papers'] = []
        else:
            print("⚠️  Elasticsearch not available - academic search skipped")
            results['academic_papers'] = []
        
        # === PASSAGE SEARCH using MinIO (if available) ===
        if minio_client:
            try:
                print(f"📄 Searching passages for: {query}")
                # This would be your passage search logic
                # For now, we'll include preview data from academic papers
                passages_data = []
                for paper in results['academic_papers'][:5]:
                    if paper.get('preview') and paper['preview'] != "No preview available":
                        passages_data.append({
                            'text': paper['preview'],
                            'source': paper['title'],
                            'relevance': paper['score']
                        })
                
                results['passages'] = passages_data
                print(f"✅ Passage search completed: {len(passages_data)} passages")
            except Exception as e:
                print(f"❌ Passage search error: {e}")
                results['passages'] = []
        else:
            print("⚠️  MinIO not available - passage search skipped")
            results['passages'] = []
        
        # === AI ANSWER GENERATION using Mistral ===
        if mistral_available and call_mistral:
            try:
                print(f"🤖 Generating AI answer for: {query}")
                ai_answer = generate_comprehensive_answer(
                    query, 
                    results['web_results'], 
                    results['academic_papers']
                )
                results['ai_answer'] = ai_answer
                print("✅ AI answer generated successfully")
            except Exception as e:
                print(f"❌ AI answer error: {e}")
                results['ai_answer'] = "AI answer generation temporarily unavailable. Please check your Mistral API configuration."
        else:
            print("⚠️  Mistral AI not available - skipping AI answer generation")
            results['ai_answer'] = "AI answer generation is not available. Please configure your Mistral API key in the .env file to enable this feature."
        
        # Calculate totals and timing
        results['total_results'] = (
            len(results['web_results']) + 
            len(results['academic_papers']) + 
            len(results['passages'])
        )
        results['search_time'] = round(time.time() - search_start_time, 2)
        
        print(f"🎉 Search completed in {results['search_time']}s - {results['total_results']} total results")
        return jsonify(results)
    
    except Exception as e:
        print(f"💥 Search failed: {str(e)}")
        return jsonify({
            'error': f'Search failed: {str(e)}',
            'query': query,
            'service_status': results.get('service_status', {})
        }), 500

@app.route('/api/status')
def get_status():
    """Get status of all services"""
    return jsonify({
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'services': {
            'web_crawler': {
                'available': bool(web_crawler),
                'status': 'ready' if web_crawler else 'not available'
            },
            'elasticsearch': {
                'available': bool(es),
                'status': 'connected' if es else 'not available',
                'host': ELASTICSEARCH_HOST
            },
            'minio': {
                'available': bool(minio_client),
                'status': 'connected' if minio_client else 'not available',
                'endpoint': MINIO_ENDPOINT
            },
            'mistral_ai': {
                'available': mistral_available and bool(call_mistral),
                'status': 'ready' if (mistral_available and call_mistral) else 'not available'
            },
            'ai_models': {
                'available': bool(embedder) and bool(qa_pipeline),
                'status': 'loaded' if (embedder and qa_pipeline) else 'not loaded'
            }
        },
        'features': {
            'web_search': bool(web_crawler),
            'academic_search': bool(es),
            'passage_search': bool(minio_client),
            'ai_answers': mistral_available and bool(call_mistral),
            'auto_suggestions': True  # Always available
        }
    })

@app.route('/api/history')
def get_search_history():
    """Get search history (you can implement with a database or session storage)"""
    # For now, return empty - you can implement with SQLite or session storage
    return jsonify({'history': []})

if __name__ == '__main__':
    # Create templates and static directories if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)
