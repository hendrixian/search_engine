# Enhanced flask_app.py with Milvus vector database integration
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
from concurrent.futures import ThreadPoolExecutor
import torch
import httpx
import redis
from flask_sse import sse
import random
import threading

# Load environment variables
load_dotenv()

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

# Import Milvus vector database manager
try:
    from database.milvus_manager import MilvusVectorManager
    milvus_available = True
    print("✅ Milvus vector database module imported successfully")
except ImportError as e:
    print(f"⚠️ Milvus not available: {e}")
    MilvusVectorManager = None
    milvus_available = False

# Import Mistral separately (optional)
try:
    from mistral import call_mistral, call_mistral_enhanced, enhanced_available
    mistral_available = True
    print("✅ Mistral AI module imported successfully")
    if enhanced_available:
        print("✅ Enhanced Mistral AI features available")
    else:
        print("⚠️ Enhanced Mistral AI features not available, using legacy mode")
except ImportError as e:
    print(f"⚠️ Mistral AI not available: {e}")
    call_mistral = None
    call_mistral_enhanced = None
    mistral_available = False
    enhanced_available = False
except ValueError as e:
    print(f"⚠️ Mistral API key not configured: {e}")
    call_mistral = None
    call_mistral_enhanced = None
    mistral_available = False
    enhanced_available = False

# Import auto_upload's main function
try:
    from auto_upload import main as auto_upload_main
    print("✅ Auto-upload module imported successfully")
except ImportError as e:
    print(f"⚠️ Auto-upload module not found: {e}")
    auto_upload_main = None

# === Background Auto-Upload (Scheduled every 60s) ===
def background_auto_upload():
    """Triggers the auto-upload process on a schedule."""
    while True:
        try:
            print("🔄 Background: Checking for new PDFs to upload...")
            if auto_upload_main:
                auto_upload_main()
                print("✅ Background: Auto-upload cycle finished.")
            else:
                print("⚠️ Auto-upload module not available, skipping.")
        except Exception as e:
            print(f"❌ Background Auto-Upload error: {e}")
        
        time.sleep(60)  # Wait 60 seconds before next cycle

# Start background threads
threading.Thread(target=background_auto_upload, daemon=True).start()

app = Flask(__name__, template_folder='templates')
app.secret_key = os.getenv('FLASK_SECRET_KEY')

# Redis configuration for dashboard communication
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# Environment variables
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://elasticsearch:9200")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"
HUGGINGFACE_TOKEN = os.getenv("HUGGINGFACE_TOKEN")

# Milvus configuration
MILVUS_HOST = os.getenv("MILVUS_HOST", "milvus-standalone")
MILVUS_PORT = os.getenv("MILVUS_PORT", "19530")

# Model cache directories
MODEL_CACHE_DIR = os.getenv("MODEL_CACHE_DIR", "./models")
os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODEL_CACHE_DIR

# Global variables for loaded models and services - LAZY LOADED
_embedder = None
_qa_pipeline = None
_web_crawler = None
_es = None
_minio_client = None
_milvus_manager = None

# Redis connection for dashboard integration
try:
    redis_conn = redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    redis_conn.ping()
    print("✅ Redis connected for dashboard integration")
except Exception as e:
    print(f"⚠️ Redis connection failed: {e}")
    redis_conn = None

class DashboardLogger:
    """Helper class to stream search events to dashboard"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        
    def log_search_event(self, event_type, search_id, **kwargs):
        """Log search event to Redis stream for dashboard monitoring"""
        if not self.redis:
            return
            
        try:
            event_data = {
                "event": event_type,
                "search_id": search_id,
                "timestamp": datetime.now().isoformat(),
                **kwargs
            }
            self.redis.xadd("search_stream", event_data)
            
            # Also publish to pub/sub for real-time updates
            self.redis.publish("search_events", json.dumps(event_data))
            
        except Exception as e:
            print(f"Failed to log to dashboard: {e}")
    
    def log_stage(self, search_id, stage, status, **details):
        """Log a specific search stage"""
        self.log_search_event(
            "search_stage",
            search_id,
            stage=stage,
            status=status,
            **details
        )
    
    def log_error(self, search_id, stage, error):
        """Log an error during search"""
        self.log_search_event(
            "search_error",
            search_id,
            stage=stage,
            error=str(error)
        )

# Initialize dashboard logger
dashboard_logger = DashboardLogger(redis_conn)

def get_embedder():
    """Lazy load embedder model only when needed"""
    global _embedder
    if _embedder is None:
        try:
            print("🔥 Loading SentenceTransformer model...")
            _embedder = SentenceTransformer("all-MiniLM-L6-v2")
            print("✅ SentenceTransformer loaded successfully")
        except Exception as e:
            print(f"❌ Error loading SentenceTransformer: {e}")
            _embedder = False  # Mark as failed
    return _embedder if _embedder is not False else None

def get_qa_pipeline():
    """Lazy load QA pipeline only when needed"""
    global _qa_pipeline
    if _qa_pipeline is None:
        try:
            print("🔥 Loading QA pipeline model...")
            _qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")
            print("✅ QA pipeline loaded successfully")
        except Exception as e:
            print(f"❌ Error loading QA pipeline: {e}")
            _qa_pipeline = False  # Mark as failed
    return _qa_pipeline if _qa_pipeline is not False else None

def get_web_crawler():
    """Lazy load web crawler only when needed"""
    global _web_crawler
    if _web_crawler is None:
        try:
            print("🔥 Initializing web crawler...")
            _web_crawler = MultiSiteCrawler()
            print("✅ Web crawler initialized")
        except Exception as e:
            print(f"❌ Error initializing web crawler: {e}")
            _web_crawler = False
    return _web_crawler if _web_crawler is not False else None

def get_elasticsearch():
    """Lazy load Elasticsearch connection only when needed"""
    global _es
    if _es is None:
        try:
            print("🔥 Connecting to Elasticsearch...")
            _es = Elasticsearch([ELASTICSEARCH_HOST], request_timeout=3, max_retries=1)
            if _es.ping():
                print("✅ Elasticsearch connected")
            else:
                print("⚠️ Elasticsearch not responding")
                _es = False
        except Exception as e:
            print(f"⚠️ Elasticsearch not available: {e}")
            _es = False
    return _es if _es is not False else None

def get_minio_client():
    """Lazy load MinIO client only when needed"""
    global _minio_client
    if _minio_client is None:
        try:
            print("🔥 Connecting to MinIO...")
            _minio_client = Minio(
                MINIO_ENDPOINT,
                access_key=MINIO_ROOT_USER,
                secret_key=MINIO_ROOT_PASSWORD,
                secure=MINIO_SECURE
            )
            # Test connection
            list(_minio_client.list_buckets())
            print("✅ MinIO client initialized")
        except Exception as e:
            print(f"⚠️ MinIO not available: {e}")
            _minio_client = False
    return _minio_client if _minio_client is not False else None

def get_milvus_manager():
    """Lazy load Milvus vector database manager only when needed"""
    global _milvus_manager
    if _milvus_manager is None and milvus_available:
        try:
            print("🔥 Connecting to Milvus vector database...")
            _milvus_manager = MilvusVectorManager(
                host=MILVUS_HOST,
                port=MILVUS_PORT
            )
            if _milvus_manager.connect():
                print("✅ Milvus vector database connected")
            else:
                print("⚠️ Milvus connection failed")
                _milvus_manager = False
        except Exception as e:
            print(f"⚠️ Milvus not available: {e}")
            _milvus_manager = False
    return _milvus_manager if _milvus_manager is not False else None

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

def get_paper_preview_from_milvus(paper_id, max_chars=800):
    """Get paper preview from Milvus vector database instead of MinIO buckets"""
    milvus_manager = get_milvus_manager()
    if not milvus_manager:
        return "Milvus vector database not available - no preview content"
    
    try:
        # Search for passages from this specific paper
        # Use a broad query to get any passage from the paper
        results = milvus_manager.collection.query(
            expr=f'paper_id == "{paper_id}"',
            output_fields=["passage_text", "page_number", "passage_index"],
            limit=1
        )
        
        if results:
            # Get the first passage as preview
            passage_text = results[0].get('passage_text', '')
            if passage_text:
                # Clean and truncate
                preview = passage_text.replace("\n", " ").strip()
                if len(preview) > max_chars:
                    preview = preview[:max_chars] + "..."
                return preview
        
        return "No preview available for this paper"
        
    except Exception as e:
        return f"Could not load preview: {str(e)}"

# DEPRECATED: This function is replaced by Milvus vector search
@lru_cache(maxsize=100)
def get_paper_preview(paper_id, max_chars=800):
    """DEPRECATED: Extract preview content from academic paper passages in MinIO"""
    # This function is kept for backward compatibility but should use Milvus instead
    return get_paper_preview_from_milvus(paper_id, max_chars)

def generate_comprehensive_answer(query, web_results, academic_papers, passages, search_id):
    """
    Generate enhanced AI answer using advanced optimization features
    Returns separated AI answer and sources as requested
    """
    dashboard_logger.log_stage(
        search_id, 
        "ai_processing", 
        "started",
        details="Starting enhanced AI answer generation with optimization features"
    )
    
    try:
        # Prepare sources in the format expected by enhanced AI
        all_sources = []
        
        # Add web results as sources
        for result in web_results:
            source = {
                'title': result.get('title', 'No title'),
                'content': clean_html_snippet(result.get('snippet', '')),
                'url': result.get('url', ''),
                'source_type': 'web',
                'relevance_score': 0.8  # Default web relevance
            }
            all_sources.append(source)
        
        # Add academic papers as sources
        for paper in academic_papers:
            source = {
                'title': paper.get('title', 'No title'),
                'content': paper.get('abstract', ''),
                'url': paper.get('pdf_path', ''),
                'source_type': 'academic',
                'relevance_score': paper.get('score', 0.9)  # Use ES score
            }
            all_sources.append(source)
        
        # Add vector search passages as sources
        for passage in passages:
            source = {
                'title': passage.get('title', 'No title'),
                'content': passage.get('text', ''),
                'url': '',  # Vector passages don't have URLs
                'source_type': 'vector',
                'relevance_score': passage.get('similarity_score', 0.0)
            }
            all_sources.append(source)
        
        if not all_sources:
            dashboard_logger.log_error(search_id, "ai_processing", "No sources available for AI processing")
            return {
                'ai_answer': {
                    'content': "No sufficient sources available to generate a comprehensive answer.",
                    'confidence_score': 0.0,
                    'processing_time': 0.0,
                    'validation_passed': False,
                    'refinement_iterations': 0,
                    'perspectives_considered': 1
                },
                'sources': [],
                'processing_info': {
                    'total_sources_available': 0,
                    'sources_selected': 0,
                    'error': 'No sources available'
                }
            }
        
        dashboard_logger.log_stage(
            search_id, 
            "ai_processing", 
            "processing",
            total_sources=len(all_sources),
            web_sources=len(web_results),
            academic_sources=len(academic_papers),
            vector_sources=len(passages),
            details=f"Processing {len(all_sources)} total sources with enhanced AI"
        )
        
        # Use enhanced AI if available, otherwise fall back to legacy
        if enhanced_available and call_mistral_enhanced:
            # Use enhanced AI with all optimization features
            enhanced_result = call_mistral_enhanced(query, "", all_sources, search_id)
            
            dashboard_logger.log_stage(
                search_id, 
                "ai_processing", 
                "completed",
                enhanced_features_used=True,
                confidence_score=enhanced_result['ai_answer'].get('confidence_score', 0.0),
                sources_selected=enhanced_result['processing_info'].get('sources_selected', 0),
                details=f"Enhanced AI processing completed with {enhanced_result['ai_answer'].get('perspectives_considered', 1)} perspectives"
            )
            
            return enhanced_result
        
        else:
            # Fall back to legacy mode with separated response format
            dashboard_logger.log_stage(
                search_id, 
                "ai_processing", 
                "fallback",
                details="Using legacy AI mode (enhanced features not available)"
            )
            
            # Prepare context for legacy AI
            context_parts = []
            for i, source in enumerate(all_sources[:10]):  # Limit for legacy mode
                context_parts.append(f"{source['source_type'].title()} Source {i+1}: {source['title']}\n{source['content'][:500]}...")
            
            full_context = "\n\n".join(context_parts)
            
            # Call legacy Mistral API
            ai_response = call_mistral(query, full_context)
            
            # Format legacy response in new separated format
            formatted_sources = []
            for source in all_sources[:10]:
                formatted_source = {
                    'title': source['title'],
                    'url': source['url'],
                    'content': source['content'][:300] + "..." if len(source['content']) > 300 else source['content'],
                    'source_type': source['source_type'],
                    'relevance_score': round(source.get('relevance_score', 0.0), 3)
                }
                formatted_sources.append(formatted_source)
            
            dashboard_logger.log_stage(
                search_id, 
                "ai_processing", 
                "completed",
                enhanced_features_used=False,
                word_count=len(ai_response.split()),
                sources_used=len(formatted_sources),
                details=f"Legacy AI processing completed with {len(ai_response.split())} words"
            )
            
            return {
                'ai_answer': {
                    'content': ai_response,
                    'confidence_score': 0.7,  # Default confidence for legacy mode
                    'processing_time': 0.0,
                    'validation_passed': True,
                    'refinement_iterations': 0,
                    'perspectives_considered': 1
                },
                'sources': formatted_sources,
                'processing_info': {
                    'total_sources_available': len(all_sources),
                    'sources_selected': len(formatted_sources),
                    'optimization_features_used': {
                        'validation': False,
                        'multi_perspective': False,
                        'iterative_refinement': False,
                        'smart_selector': False
                    },
                    'legacy_mode': True
                }
            }
        
    except Exception as e:
        dashboard_logger.log_error(search_id, "ai_processing", str(e))
        return {
            'ai_answer': {
                'content': f"Error generating enhanced AI answer: {str(e)}",
                'confidence_score': 0.0,
                'processing_time': 0.0,
                'validation_passed': False,
                'refinement_iterations': 0,
                'perspectives_considered': 0
            },
            'sources': [],
            'processing_info': {
                'total_sources_available': len(all_sources) if 'all_sources' in locals() else 0,
                'sources_selected': 0,
                'error': str(e)
            }
        }

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
    """Enhanced search API endpoint with Milvus vector search integration"""
    data = request.get_json()
    query = data.get('query', '').strip()
    
    # Generate unique search ID
    search_id = f"search_{int(time.time()*1000)}_{random.randint(1000,9999)}"
    search_start_time = time.time()
    
    # Log search initiation to dashboard
    dashboard_logger.log_search_event(
        "search_start", 
        search_id,
        query=query,
        stage="query_received",
        user_agent=request.headers.get('User-Agent', 'Unknown'),
        ip_address=request.remote_addr
    )

    if not query:
        dashboard_logger.log_error(search_id, "validation", "Empty query provided")
        return jsonify({'error': 'No query provided'}), 400
    
    results = {
        'query': query,
        'search_id': search_id,
        'timestamp': datetime.now().isoformat(),
        'web_results': [],
        'academic_papers': [],
        'passages': [],  # Now from Milvus vector search
        'ai_answer': '',
        'search_time': 0,
        'total_results': 0,
        'service_status': {}
    }

    try:
        # Track service status
        services = {
            'web_crawler': False,
            'elasticsearch': False,
            'minio': False,
            'milvus': False,
            'mistral_ai': False
        }

        # === WEB SEARCH ===
        dashboard_logger.log_stage(search_id, "web_search", "started")
        
        web_crawler = get_web_crawler()
        services['web_crawler'] = web_crawler is not None
        
        if web_crawler:
            try:
                web_search_start = time.time()
                web_results = web_crawler.search_web(query)
                web_search_time = time.time() - web_search_start
                
                formatted_web_results = []
                for result in web_results:
                    formatted_result = {
                        'title': result.get('title', 'Untitled'),
                        'url': result.get('url', ''),
                        'snippet': clean_html_snippet(result.get('snippet', '')),
                        'source': result.get('source', 'Web')
                    }
                    formatted_web_results.append(formatted_result)
                
                results['web_results'] = formatted_web_results
                
                dashboard_logger.log_stage(
                    search_id, 
                    "web_search", 
                    "completed",
                    results_count=len(formatted_web_results),
                    search_time=round(web_search_time, 3),
                    details=f"Found {len(formatted_web_results)} web results in {web_search_time:.2f}s"
                )
                
            except Exception as e:
                dashboard_logger.log_error(search_id, "web_search", str(e))
                results['web_results'] = []

        # === ACADEMIC SEARCH ===
        dashboard_logger.log_stage(search_id, "academic_search", "started")
        
        es = get_elasticsearch()
        services['elasticsearch'] = es is not None
        
        if es:
            try:
                es_search_start = time.time()
                es_result = es.search(index="academic-papers", query={
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "abstract^2", "content", "authors"],
                        "fuzziness": "AUTO"
                    }
                }, size=10)
                es_search_time = time.time() - es_search_start
                
                academic_papers = []
                for hit in es_result['hits']['hits']:
                    paper = hit['_source']
                    paper_data = {
                        'title': paper.get('title'),
                        'authors': paper.get('authors', 'Unknown'),
                        'abstract': paper.get('abstract', '')[:500] + ('...' if len(paper.get('abstract', '')) > 500 else ''),
                        'score': round(hit['_score'], 2)
                    }
                    academic_papers.append(paper_data)
                
                results['academic_papers'] = academic_papers
                
                dashboard_logger.log_stage(
                    search_id, 
                    "academic_search", 
                    "completed",
                    results_count=len(academic_papers),
                    search_time=round(es_search_time, 3),
                    total_hits=es_result['hits']['total']['value'] if isinstance(es_result['hits']['total'], dict) else es_result['hits']['total'],
                    details=f"Found {len(academic_papers)} academic papers in {es_search_time:.2f}s"
                )
                
            except Exception as e:
                dashboard_logger.log_error(search_id, "academic_search", str(e))
                results['academic_papers'] = []

        # === MILVUS VECTOR SEARCH (NEW) ===
        dashboard_logger.log_stage(search_id, "vector_search", "started")
        
        milvus_manager = get_milvus_manager()
        services['milvus'] = milvus_manager is not None
        
        if milvus_manager:
            try:
                vector_search_start = time.time()
                
                # Perform semantic vector search
                vector_passages = milvus_manager.search_passages(
                    query=query,
                    limit=15,
                    similarity_threshold=0.6
                )
                
                vector_search_time = time.time() - vector_search_start
                
                # Format passages for response
                formatted_passages = []
                for passage in vector_passages:
                    formatted_passage = {
                        'id': passage.get('id'),
                        'text': passage.get('text', '')[:800] + ('...' if len(passage.get('text', '')) > 800 else ''),
                        'title': passage.get('title', 'Untitled'),
                        'authors': passage.get('authors', 'Unknown'),
                        'year': passage.get('year', 'Unknown'),
                        'page_number': passage.get('page_number', 0),
                        'similarity_score': round(passage.get('similarity_score', 0), 3),
                        'paper_id': passage.get('paper_id', ''),
                        'source': 'Vector Search'
                    }
                    formatted_passages.append(formatted_passage)
                
                results['passages'] = formatted_passages
                
                dashboard_logger.log_stage(
                    search_id, 
                    "vector_search", 
                    "completed",
                    results_count=len(formatted_passages),
                    search_time=round(vector_search_time, 3),
                    avg_similarity=round(sum(p.get('similarity_score', 0) for p in vector_passages) / len(vector_passages), 3) if vector_passages else 0,
                    details=f"Found {len(formatted_passages)} semantically similar passages in {vector_search_time:.2f}s"
                )
                
            except Exception as e:
                dashboard_logger.log_error(search_id, "vector_search", str(e))
                results['passages'] = []

        # === AI ANSWER GENERATION ===
        services['mistral_ai'] = mistral_available and bool(call_mistral)
        
        if services['mistral_ai']:
            try:
                # Generate comprehensive answer with separated format
                ai_result = generate_comprehensive_answer(
                    query, 
                    results['web_results'],
                    results['academic_papers'],
                    results['passages'],  # Now includes vector search results
                    search_id
                )
                
                # Update results with separated AI answer and sources
                results['ai_answer'] = ai_result['ai_answer']
                results['ai_sources'] = ai_result['sources']  # Separated sources for AI answer
                results['ai_processing_info'] = ai_result['processing_info']
                
            except Exception as e:
                dashboard_logger.log_error(search_id, "ai_processing", str(e))
                results['ai_answer'] = {
                    'content': "AI answer generation failed",
                    'confidence_score': 0.0,
                    'processing_time': 0.0,
                    'validation_passed': False,
                    'refinement_iterations': 0,
                    'perspectives_considered': 0
                }
                results['ai_sources'] = []
                results['ai_processing_info'] = {'error': str(e)}

        # === FINALIZE RESULTS ===
        results['total_results'] = sum([
            len(results['web_results']),
            len(results['academic_papers']),
            len(results.get('passages', []))
        ])
        results['search_time'] = round(time.time() - search_start_time, 2)
        results['service_status'] = services

        # Log search completion
        dashboard_logger.log_search_event(
            "search_complete",
            search_id,
            total_results=results['total_results'],
            total_time=results['search_time'],
            services_used=[k for k, v in services.items() if v],
            query_terms=len(query.split()),
            has_ai_answer=bool(results.get('ai_answer')),
            vector_passages=len(results.get('passages', []))
        )

        return jsonify(results)

    except Exception as e:
        dashboard_logger.log_search_event(
            "search_failed",
            search_id,
            error=str(e),
            total_time=round(time.time() - search_start_time, 2)
        )
        
        return jsonify({
            'error': f'Search failed: {str(e)}',
            'query': query,
            'search_id': search_id,
            'service_status': services
        }), 500

@app.route('/api/status')
def get_status():
    """Get status of all services including Milvus vector database"""
    dashboard_connected = redis_conn is not None
    
    if dashboard_connected:
        try:
            redis_conn.ping()
            dashboard_status = "connected"
        except:
            dashboard_status = "connection_lost"
            dashboard_connected = False
    else:
        dashboard_status = "not_available"
    
    # Check Milvus status
    milvus_manager = get_milvus_manager()
    milvus_status = "not_available"
    milvus_stats = {}
    
    if milvus_manager:
        try:
            milvus_stats = milvus_manager.get_collection_stats()
            milvus_status = "connected" if milvus_stats.get('status') == 'healthy' else "error"
        except:
            milvus_status = "connection_error"
    
    return jsonify({
        'status': 'running',
        'timestamp': datetime.now().isoformat(),
        'dashboard_integration': {
            'enabled': dashboard_connected,
            'status': dashboard_status,
            'redis_host': REDIS_HOST,
            'redis_port': REDIS_PORT
        },
        'services': {
            'web_crawler': {
                'available': get_web_crawler() is not None,
                'status': 'ready' if get_web_crawler() else 'not available'
            },
            'elasticsearch': {
                'available': get_elasticsearch() is not None,
                'status': 'connected' if get_elasticsearch() else 'not available',
                'host': ELASTICSEARCH_HOST
            },
            'minio': {
                'available': get_minio_client() is not None,
                'status': 'connected' if get_minio_client() else 'not available',
                'endpoint': MINIO_ENDPOINT
            },
            'milvus': {
                'available': milvus_manager is not None,
                'status': milvus_status,
                'host': MILVUS_HOST,
                'port': MILVUS_PORT,
                'stats': milvus_stats
            },
            'mistral_ai': {
                'available': mistral_available and bool(call_mistral),
                'status': 'ready' if (mistral_available and call_mistral) else 'not available'
            },
            'ai_models': {
                'available': get_embedder() is not None and get_qa_pipeline() is not None,
                'status': 'loaded' if (get_embedder() and get_qa_pipeline()) else 'not loaded'
            }
        },
        'features': {
            'web_search': get_web_crawler() is not None,
            'academic_search': get_elasticsearch() is not None,
            'vector_search': milvus_manager is not None,  # NEW
            'passage_search': milvus_manager is not None,  # UPDATED: Now uses Milvus instead of MinIO
            'ai_answers': mistral_available and bool(call_mistral),
            'auto_suggestions': True,  # Always available
            'dashboard_monitoring': dashboard_connected
        }
    })

@app.route('/api/milvus/stats')
def get_milvus_stats():
    """Get detailed Milvus vector database statistics"""
    milvus_manager = get_milvus_manager()
    
    if not milvus_manager:
        return jsonify({'error': 'Milvus not available'}), 503
    
    try:
        stats = milvus_manager.get_collection_stats()
        return jsonify(stats)
    except Exception as e:
        return jsonify({'error': f'Failed to get Milvus stats: {str(e)}'}), 500

@app.route('/api/upload/passages', methods=['POST'])
def upload_passages_to_milvus():
    """
    API endpoint to upload passages to Milvus vector database
    This replaces the MinIO bucket storage approach
    """
    milvus_manager = get_milvus_manager()
    
    if not milvus_manager:
        return jsonify({'error': 'Milvus vector database not available'}), 503
    
    try:
        data = request.get_json()
        passages = data.get('passages', [])
        
        if not passages:
            return jsonify({'error': 'No passages provided'}), 400
        
        # Upload to Milvus
        success = milvus_manager.add_passages(passages)
        
        if success:
            return jsonify({
                'message': f'Successfully uploaded {len(passages)} passages to Milvus',
                'passages_count': len(passages),
                'status': 'success'
            })
        else:
            return jsonify({'error': 'Failed to upload passages to Milvus'}), 500
            
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

@app.route('/api/history')
def get_search_history():
    """Get search history from Redis if available"""
    if not redis_conn:
        return jsonify({'history': [], 'error': 'Dashboard not connected'})
    
    try:
        # Get recent search events from Redis stream
        stream_data = redis_conn.xrevrange("search_stream", count=50)
        
        history = []
        for stream_id, fields in stream_data:
            if fields.get('event') == 'search_start':
                history.append({
                    'search_id': fields.get('search_id'),
                    'query': fields.get('query'),
                    'timestamp': fields.get('timestamp'),
                    'ip_address': fields.get('ip_address', 'Unknown')
                })
        
        return jsonify({'history': history})
        
    except Exception as e:
        return jsonify({'history': [], 'error': f'Failed to fetch history: {str(e)}'})

@app.route('/api/dashboard/trigger_test', methods=['POST'])
def trigger_dashboard_test():
    """Trigger a test search for dashboard demonstration"""
    if not redis_conn:
        return jsonify({'error': 'Dashboard not connected'}), 503
    
    data = request.get_json() or {}
    test_query = data.get('query', 'machine learning algorithms')
    
    # Create a test search event
    search_id = f"test_search_{int(time.time()*1000)}"
    
    dashboard_logger.log_search_event(
        "search_start",
        search_id,
        query=test_query,
        stage="test_initiated",
        source="dashboard_trigger"
    )
    
    return jsonify({
        'message': 'Test search event sent to dashboard',
        'search_id': search_id,
        'query': test_query
    })

# Remove automatic initialization - only initialize when needed!
print("✅ Enhanced Flask app ready with Milvus vector database integration")
print(f"📊 Dashboard logging: {'Enabled' if redis_conn else 'Disabled (Redis not available)'}")
print(f"🔍 Vector search: {'Enabled' if milvus_available else 'Disabled (Milvus not available)'}")

if __name__ == '__main__':
    # Create templates and static directories if they don't exist
    os.makedirs('templates', exist_ok=True)
    os.makedirs('static/css', exist_ok=True)
    os.makedirs('static/js', exist_ok=True)
    os.makedirs('database', exist_ok=True)
    
    app.run(debug=True, host='0.0.0.0', port=5000)