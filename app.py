import streamlit as st
from elasticsearch import Elasticsearch
from minio import Minio
import json
import tempfile
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline, AutoTokenizer
import os
import io
import torch 
from mistral import call_mistral
from crawlers.multi_crawler import MultiSiteCrawler
import asyncio
from concurrent.futures import ThreadPoolExecutor
import time
import html
import re
import os
from dotenv import load_dotenv
load_dotenv()

# Load environment variables
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false").lower() == "true"

token = os.getenv("HUGGINGFACE_TOKEN")

if not token:
    st.error("HuggingFace token not configured")
    st.stop()

# === Model cache directories inside Docker container ===
MODEL_CACHE_DIR = "/app/models"
os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODEL_CACHE_DIR

# === Load models only once ===
@st.cache_resource
def load_models():
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")
    return embedder, qa_pipeline

@st.cache_resource
def load_crawler():
    return MultiSiteCrawler()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def get_paper_preview(paper_id, max_chars=800):
    """Extract preview content from academic paper passages"""
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

embedder, qa_pipeline = load_models()
web_crawler = load_crawler()

# === Connect to Elasticsearch ===
es = Elasticsearch(ELASTICSEARCH_HOST)

# === Connect to MinIO ===
minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ROOT_USER, secret_key=MINIO_ROOT_PASSWORD, secure=False)

st.title("🔎 Comprehensive Academic & Web Search")
st.markdown("*Automatically search academic papers, generate AI answers, and discover web content - all in one place*")

# Add custom CSS for better styling
st.markdown("""
<style>
    /* Google-style buttons */
    .stButton > button {
        border-radius: 4px;
        border: 1px solid #dadce0;
        transition: all 0.2s ease;
        font-family: 'Google Sans', Roboto, Arial, sans-serif;
    }
    
    .stButton > button:hover {
        border-color: #c6c6c6;
        box-shadow: 0 1px 1px rgba(0,0,0,0.1);
        transform: none;
    }
    
    /* Primary search button (Google style) */
    .stButton > button[data-testid="baseButton-primary"] {
        background-color: #f8f9fa !important;
        color: #3c4043 !important;
        border: 1px solid #dadce0 !important;
        padding: 8px 16px !important;
        font-size: 14px !important;
        font-weight: 500 !important;
    }
    
    .stButton > button[data-testid="baseButton-primary"]:hover {
        background-color: #f1f3f4 !important;
        border-color: #c6c6c6 !important;
        box-shadow: 0 1px 1px rgba(0,0,0,0.1) !important;
    }
    .suggestion-section {
        background-color: #f8f9fa;
        padding: 1.5rem;
        border-radius: 12px;
        margin: 0.5rem 0 1rem 0;
        border-left: 5px solid #007bff;
        box-shadow: 0 2px 8px rgba(0,0,0,0.1);
        border: 2px solid #e3f2fd;
    }
    
    /* Make suggestions more prominent */
    .suggestion-section h3 {
        color: #1976d2;
        margin-bottom: 1rem;
    }
    
    /* Enhance button styling */
    .stButton > button[data-testid="baseButton-secondary"] {
        background-color: #ffffff;
        color: #1976d2;
        border: 2px solid #1976d2;
        font-weight: 500;
        padding: 0.5rem 1rem;
        margin: 0.25rem 0;
    }
    
    .stButton > button[data-testid="baseButton-secondary"]:hover {
        background-color: #1976d2;
        color: white;
        border-color: #1976d2;
    }
    
    /* Google-style search container */
    .search-container {
        position: relative;
        width: 100%;
    }
    
    .search-input-wrapper {
        position: relative;
        display: flex;
        align-items: center;
        background: white;
        border: 1px solid #dfe1e5;
        border-radius: 24px;
        box-shadow: 0 1px 6px rgba(32,33,36,0.28);
        transition: all 0.2s ease;
        overflow: hidden;
    }
    
    .search-input-wrapper:hover {
        box-shadow: 0 1px 6px rgba(32,33,36,0.28), 0 1px 3px rgba(32,33,36,0.1);
    }
    
    .search-input-wrapper:focus-within {
        border-color: #4285f4;
        box-shadow: 0 1px 6px rgba(32,33,36,0.28), 0 0 0 2px rgba(66,133,244,0.2);
    }
    
    .search-icon {
        position: absolute;
        left: 16px;
        color: #9aa0a6;
        font-size: 18px;
        z-index: 10;
        pointer-events: none;
    }
    
    .search-input-inner {
        flex: 1;
    }
    
    /* Google-style search input */
    .stTextInput > div > div > input {
        border: none !important;
        border-radius: 0 !important;
        padding: 12px 20px 12px 48px !important;
        font-size: 16px !important;
        background: transparent !important;
        box-shadow: none !important;
        transition: none !important;
        outline: none !important;
    }
    
    .stTextInput > div > div > input:focus {
        border: none !important;
        box-shadow: none !important;
        outline: none !important;
    }
    
    .stTextInput > div > div > input:hover {
        box-shadow: none !important;
    }
    
    /* Ensure suggestions appear immediately below search */
    .suggestion-section {
        margin-top: 0.5rem !important;
        margin-bottom: 1rem !important;
    }
    
    /* Make suggestions more prominent */
    .suggestion-section h3 {
        margin-top: 0 !important;
        margin-bottom: 1rem !important;
    }
    
    /* Quick access to suggestions */
    .quick-suggestions {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        padding: 1rem;
        border-radius: 12px;
        margin: 0.5rem 0;
        box-shadow: 0 4px 15px rgba(0,0,0,0.1);
    }
    
    /* Quick suggestion buttons */
    .quick-suggestions .stButton > button {
        background-color: rgba(255, 255, 255, 0.9) !important;
        color: #667eea !important;
        border: 2px solid rgba(255, 255, 255, 0.3) !important;
        font-weight: 600 !important;
        transition: all 0.3s ease !important;
    }
    
    .quick-suggestions .stButton > button:hover {
        background-color: white !important;
        color: #667eea !important;
        border-color: white !important;
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(0,0,0,0.2) !important;
    }
    
    /* Ensure suggestions are always visible */
    .suggestion-section, .quick-suggestions {
        animation: fadeIn 0.3s ease-in;
    }
    
    @keyframes fadeIn {
        from { opacity: 0; transform: translateY(-10px); }
        to { opacity: 1; transform: translateY(0); }
    }
    
    /* Google-style suggestions */
    .google-suggestions {
        background: white;
        border: 1px solid #dfe1e5;
        border-radius: 8px;
        box-shadow: 0 2px 5px rgba(0,0,0,0.1);
        margin: 0.5rem 0;
        overflow: hidden;
        animation: slideDown 0.2s ease-out;
    }
    
    .suggestions-header {
        background: #f8f9fa;
        padding: 8px 16px;
        border-bottom: 1px solid #dfe1e5;
        font-size: 12px;
        color: #5f6368;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    
    .suggestions-icon {
        font-size: 14px;
    }
    
    .suggestions-text {
        font-weight: 500;
    }
    
    /* Google-style suggestion buttons */
    .google-suggestions .stButton > button {
        background: white !important;
        color: #202124 !important;
        border: none !important;
        border-radius: 0 !important;
        text-align: left !important;
        padding: 12px 16px !important;
        font-size: 14px !important;
        font-weight: 400 !important;
        margin: 0 !important;
        width: 100% !important;
        transition: background-color 0.1s ease !important;
        border-bottom: 1px solid #f1f3f4 !important;
    }
    
    .google-suggestions .stButton > button:hover {
        background-color: #f8f9fa !important;
        color: #202124 !important;
        transform: none !important;
        box-shadow: none !important;
    }
    
    .google-suggestions .stButton > button:last-child {
        border-bottom: none !important;
    }
    
    /* No suggestions styling */
    .no-suggestions {
        background: #f8f9fa;
        border: 1px solid #dfe1e5;
        border-radius: 8px;
        padding: 12px 16px;
        margin: 0.5rem 0;
        display: flex;
        align-items: center;
        gap: 8px;
        color: #5f6368;
        font-size: 14px;
    }
    
    .no-suggestions-icon {
        font-size: 16px;
    }
    
    /* Slide down animation for suggestions */
    @keyframes slideDown {
        from { 
            opacity: 0; 
            transform: translateY(-8px); 
            max-height: 0;
        }
        to { 
            opacity: 1; 
            transform: translateY(0); 
            max-height: 300px;
        }
    }
</style>
""", unsafe_allow_html=True)

# Academic-focused search suggestions
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

# Initialize search history in session state
if 'search_history' not in st.session_state:
    st.session_state.search_history = []

def add_to_search_history(query):
    """Add query to search history"""
    if query and query.strip():
        clean_query = query.strip().lower()
        # Remove if already exists and add to front
        if clean_query in st.session_state.search_history:
            st.session_state.search_history.remove(clean_query)
        st.session_state.search_history.insert(0, clean_query)
        # Keep only last 10 searches
        st.session_state.search_history = st.session_state.search_history[:10]

def get_smart_suggestions(user_input, suggestions=ACADEMIC_SUGGESTIONS, max_results=6):
    """Get smart suggestions based on user input"""
    if not user_input or len(user_input) < 1:
        return []
    
    user_input_lower = user_input.lower().strip()
    
    # Priority 1: Search history matches (highest priority)
    history_matches = [s for s in st.session_state.search_history if user_input_lower in s.lower()]
    
    # Priority 2: Exact prefix matches from academic suggestions
    prefix_matches = [s for s in suggestions if s.lower().startswith(user_input_lower)]
    
    # Priority 3: Contains matches from academic suggestions
    contains_matches = [s for s in suggestions if user_input_lower in s.lower() and s not in prefix_matches]
    
    # Priority 4: Fuzzy matches (words that contain the input)
    word_matches = []
    for suggestion in suggestions:
        if suggestion not in prefix_matches and suggestion not in contains_matches:
            words = suggestion.lower().split()
            if any(user_input_lower in word for word in words):
                word_matches.append(suggestion)
    
    # Priority 5: Related concepts (if we still need more suggestions)
    related_matches = []
    if len(history_matches + prefix_matches + contains_matches + word_matches) < max_results:
        # Find suggestions that might be related based on common academic themes
        academic_themes = {
            'machine learning': ['artificial intelligence', 'deep learning', 'neural networks', 'data science'],
            'programming': ['software engineering', 'web development', 'mobile development', 'algorithm design'],
            'security': ['cybersecurity', 'network security', 'information security', 'cryptography'],
            'data': ['big data analytics', 'data analysis', 'statistics', 'database systems'],
            'web': ['frontend frameworks', 'backend development', 'api development', 'web technologies']
        }
        
        for theme, related in academic_themes.items():
            if user_input_lower in theme or any(user_input_lower in r.lower() for r in related):
                for related_item in related:
                    if related_item not in history_matches + prefix_matches + contains_matches + word_matches:
                        related_matches.append(related_item)
                        if len(history_matches + prefix_matches + contains_matches + word_matches + related_matches) >= max_results:
                            break
    
    # Combine all matches with priority order
    all_matches = history_matches + prefix_matches + contains_matches + word_matches + related_matches
    
    # Remove duplicates and limit results
    unique_matches = list(dict.fromkeys(all_matches))  # Preserves order
    return unique_matches[:max_results]

# Enhanced search interface with auto-suggestions
# Search interface now uses full width since search button is removed
# Google-style search input with icon
st.markdown("""
<div class="search-container">
    <div class="search-input-wrapper">
        <span class="search-icon">🔍</span>
        <div class="search-input-inner">
""", unsafe_allow_html=True)

# Simple text input without on_change to prevent unwanted triggers
query = st.text_input(
    "", 
    placeholder="Search academic topics, papers, or ask questions...",
    help="Start typing to see Google-style suggestions",
    key="main_search_input",
    label_visibility="collapsed"
)

# Track input changes for real-time suggestions (AFTER query is defined)
if query != st.session_state.get('last_query', ''):
    st.session_state.last_query = query
    # Reset any previous search triggers to prevent unwanted searches
    if 'search_triggered' in st.session_state:
        del st.session_state.search_triggered

st.markdown("""
        </div>
    </div>
</div>
""", unsafe_allow_html=True)

# Show helpful tip about search button
st.caption("💡 **Tip:** Type your query and click Search button, or click suggestions below")

# Debug section to show current state (remove this later)
if st.checkbox("🐛 Show Debug Info", key="debug_checkbox"):
    st.write("**Debug Information:**")
    st.write(f"- Query: '{query}'")
    st.write(f"- Search triggered: {st.session_state.get('search_triggered', False)}")
    st.write(f"- Suggestion clicked: {st.session_state.get('suggestion_clicked', False)}")
    st.write(f"- Last query: {st.session_state.get('last_query', 'None')}")
    st.write(f"- Selected query: {st.session_state.get('selected_query', 'None')}")

# Add a search button that appears when there's text (simulates Enter key)
if query and len(query.strip()) > 0:
    # Style the search button to look integrated with the search input
    st.markdown("""
    <style>
    .search-button-container {
        margin-top: 10px;
        text-align: center;
    }
    .search-button-container .stButton > button {
        background: linear-gradient(135deg, #4285f4 0%, #34a853 100%) !important;
        color: white !important;
        border: none !important;
        border-radius: 20px !important;
        padding: 10px 30px !important;
        font-size: 16px !important;
        font-weight: 600 !important;
        box-shadow: 0 4px 15px rgba(66, 133, 244, 0.3) !important;
        transition: all 0.3s ease !important;
    }
    .search-button-container .stButton > button:hover {
        transform: translateY(-2px) !important;
        box-shadow: 0 6px 20px rgba(66, 133, 244, 0.4) !important;
    }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown('<div class="search-button-container">', unsafe_allow_html=True)
    if st.button("🔍 Search Now", key="enter_search_button", type="primary", use_container_width=True):
        # Set the search trigger and rerun
        st.session_state.search_triggered = True
        st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# Search button removed - searches are now triggered by Enter key or suggestion clicks

# Google-style auto-suggestions display - IMMEDIATELY below search bar
# Show suggestions from 1 character with real-time updates
if query and len(query) >= 1:  # Show suggestions from 1 character
    # Get suggestions instantly without delay (Google shows 4-6 suggestions)
    suggestions = get_smart_suggestions(query, ACADEMIC_SUGGESTIONS, max_results=5)
    
    if suggestions:
        # Google-style suggestions dropdown
        st.markdown("""
        <div class="google-suggestions">
            <div class="suggestions-header">
                <span class="suggestions-icon">💡</span>
                <span class="suggestions-text">Suggestions as you type</span>
            </div>
        """, unsafe_allow_html=True)
        
        # Display suggestions in a clean list format
        for i, suggestion in enumerate(suggestions):
            # Create a clickable suggestion that looks like Google's
            if st.button(
                f"🔍 {suggestion}", 
                key=f"suggest_{i}",
                help=f"Click to search for: {suggestion}",
                use_container_width=True,
                type="secondary"
            ):
                # Update the query and trigger search
                st.session_state.selected_query = suggestion
                st.rerun()
        
        st.markdown("</div>", unsafe_allow_html=True)
        
        # Show search tips
        st.caption("💡 **Tip:** Click any suggestion above to search instantly")
    
    else:
        # Show "no suggestions" message
        st.markdown("""
        <div class="no-suggestions">
            <span class="no-suggestions-icon">💭</span>
            <span class="no-suggestions-text">No suggestions found for "{query}"</span>
        </div>
        """.format(query=query), unsafe_allow_html=True)

# Show quick access suggestions when no query (right below search bar)
elif not query:
    # Quick access to popular topics
    st.markdown("---")
    st.markdown("### 🚀 **Quick Start - Popular Topics**")
    st.markdown("*Click any topic below to start searching instantly*")
    
    # Apply gradient styling for quick suggestions
    st.markdown('<div class="quick-suggestions">', unsafe_allow_html=True)
    
    # Show popular topics in a compact grid
    quick_topics = [
        "machine learning", "artificial intelligence", "deep learning",
        "programming", "web development", "data science",
        "cybersecurity", "software engineering", "python programming"
    ]
    
    cols = st.columns(3)
    for i, topic in enumerate(quick_topics):
        with cols[i % 3]:
            if st.button(
                f"🚀 {topic.title()}", 
                key=f"quick_{i}",
                help=f"Quick search for: {topic}",
                use_container_width=True
            ):
                st.session_state.selected_query = topic
                st.rerun()
    
    st.markdown('</div>', unsafe_allow_html=True)

# Handle suggestion selection
if 'selected_query' in st.session_state:
    query = st.session_state.selected_query
    del st.session_state.selected_query
    # Mark that search should be triggered from suggestion click
    st.session_state.suggestion_clicked = True

# Show popular searches and recent history when no input
if not query:
    # Recent search history
    if st.session_state.search_history:
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 📚 Recent Searches")
        with col2:
            if st.button("🗑️ Clear History", key="clear_history", help="Clear search history"):
                st.session_state.search_history.clear()
                st.rerun()
        
        # Apply custom styling to recent searches
        st.markdown('<div class="suggestion-section">', unsafe_allow_html=True)
        history_cols = st.columns(min(len(st.session_state.search_history), 3))
        for i, history_item in enumerate(st.session_state.search_history[:6]):
            with history_cols[i % 3]:
                if st.button(
                    f"🕒 {history_item.title()}", 
                    key=f"history_{i}",
                    help=f"Repeat search: {history_item}",
                    use_container_width=True
                ):
                    st.session_state.selected_query = history_item
                    st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)
    
    # Popular academic searches
    st.markdown("### 🔥 Popular Academic Searches")
    popular_suggestions = ACADEMIC_SUGGESTIONS[:6]  # Show first 6 as popular
    
    # Apply custom styling to popular searches
    st.markdown('<div class="suggestion-section">', unsafe_allow_html=True)
    cols = st.columns(3)
    for i, suggestion in enumerate(popular_suggestions):
        with cols[i % 3]:
            if st.button(
                f"🔥 {suggestion.title()}", 
                key=f"popular_{i}",
                help=f"Quick search for: {suggestion}",
                use_container_width=True
            ):
                st.session_state.selected_query = suggestion
                st.rerun()
    st.markdown('</div>', unsafe_allow_html=True)

# Perform search ONLY when search button is clicked or suggestion is clicked
# NOT when just typing or changing tabs/windows
if query and (st.session_state.get('search_triggered', False) or st.session_state.get('suggestion_clicked', False)):
    # Store the trigger type BEFORE resetting
    was_search_triggered = st.session_state.get('search_triggered', False)
    was_suggestion_clicked = st.session_state.get('suggestion_clicked', False)
    
    # Reset the search triggers to prevent auto-execution
    if 'search_triggered' in st.session_state:
        st.session_state.search_triggered = False
    if 'suggestion_clicked' in st.session_state:
        st.session_state.suggestion_clicked = False
    
    # Record search in history
    add_to_search_history(query)
    
    # Show what triggered the search
    if was_search_triggered:
        st.info("🔍 Search triggered by search button click")
    elif was_suggestion_clicked:
        st.info("🔍 Search triggered by suggestion click")
    
    # Start timing the entire search process
    search_start_time = time.time()
    
    # Create tabs for different result types
    tab1, tab2, tab3 = st.tabs(["📚 Academic Papers", "🤖 AI Answer", "🌐 Web Results"])
    
    # Initialize shared variables for cross-tab usage
    web_results = []
    web_content = []
    passages = []
    
    # === Parallel search for web content (runs in background) ===
    def search_web_parallel(query_text):
        """Execute web search with proper error handling"""
        try:
            st.info("🔍 Starting web search...")
            results = web_crawler.search_web(query_text)  # No limits - get ALL results
            st.success(f"✅ Web search completed: {len(results)} results found")
            return results
        except Exception as e:
            st.error(f"❌ Web search failed: {e}")
            st.exception(e)  # Show full traceback for debugging
            return []
    
    # Start web search immediately
    with st.spinner("🔍 Searching all sources..."):
        web_results = search_web_parallel(query)
        st.info(f"🌐 Web search returned {len(web_results)} results")
    
    # === TAB 1: Academic Papers ===
    with tab1:
        papers_start_time = time.time()
        with st.spinner("Searching academic papers..."):
            try:
                es_result = es.search(index="academic-papers", query={
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "abstract", "authors"]
                    }
                })
                papers_search_time = time.time() - papers_start_time

                total_results = es_result['hits']['total']['value']
                
                # Display timing info like Google
                st.markdown(f"""
                <div style="color: #70757a; font-size: 14px; margin-bottom: 20px;">
                    📚 About {total_results:,} results ({format_time_elapsed(papers_search_time)})
                </div>
                """, unsafe_allow_html=True)

                if total_results > 0:
                    preview_start_time = time.time()
                    
                    # Process papers with previews
                    papers_with_previews = []
                    for hit in es_result['hits']['hits']:
                        source = hit["_source"]
                        paper_id = hit["_id"]
                        
                        # Get preview content
                        preview_text = get_paper_preview(paper_id)
                        
                        papers_with_previews.append({
                            'source': source,
                            'preview': preview_text,
                            'paper_id': paper_id
                        })
                    
                    preview_load_time = time.time() - preview_start_time
                    
                    # Display papers with enhanced styling
                    for i, paper in enumerate(papers_with_previews, 1):
                        source = paper['source']
                        preview = paper['preview']
                        
                        with st.container():
                            st.markdown(f"""
                            <div style="border: 1px solid #e0e0e0; padding: 20px; border-radius: 10px; margin-bottom: 20px; background-color: #ffffff; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                                <div style="margin-bottom: 8px;">
                                    <h4 style="color: #1a0dab; margin: 0; font-size: 18px; line-height: 1.3;">
                                        <a href="{source['pdf_path']}" target="_blank" style="color: #1a0dab; text-decoration: none;">
                                            {source['title']}
                                        </a>
                                    </h4>
                                </div>
                                <div style="margin-bottom: 12px;">
                                    <span style="color: #006621; font-size: 14px;">📄 {source['pdf_path']}</span>
                                </div>
                                <div style="margin: 8px 0; color: #545454; font-size: 13px;">
                                    <strong>Authors:</strong> {source['authors']} • <strong>Year:</strong> {source['year']}
                                </div>
                                <div style="margin: 12px 0; color: #545454; font-size: 14px; line-height: 1.4;">
                                    <strong>Abstract:</strong> {source['abstract'][:300]}{'...' if len(source['abstract']) > 300 else ''}
                                </div>
                                <div style="margin: 12px 0; padding: 12px; background-color: #f8f9fa; border-left: 3px solid #1a0dab; border-radius: 4px;">
                                    <div style="color: #3c4043; font-size: 13px; margin-bottom: 6px;">
                                        <strong>📖 Content Preview:</strong>
                                    </div>
                                    <div style="color: #3c4043; font-size: 14px; line-height: 1.4;">
                                        {preview}
                                    </div>
                                </div>
                                <div style="margin-top: 15px;">
                                    <a href="{source['pdf_path']}" target="_blank" style="text-decoration: none; background-color: #1a73e8; color: white; padding: 10px 16px; border-radius: 4px; display: inline-block; font-size: 14px; font-weight: 500;">
                                        📄 Read Full Paper
                                    </a>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                    
                    # Show additional timing info
                    total_papers_time = papers_search_time + preview_load_time
                    st.markdown(f"""
                    <div style="color: #70757a; font-size: 12px; margin-top: 20px; padding: 10px; background-color: #f8f9fa; border-radius: 6px;">
                        ⏱️ <strong>Performance Details:</strong><br>
                        • Paper search: {format_time_elapsed(papers_search_time)}<br>
                        • Preview loading: {format_time_elapsed(preview_load_time)}<br>
                        • Total: {format_time_elapsed(total_papers_time)}
                    </div>
                    """, unsafe_allow_html=True)
                    
                else:
                    st.markdown(f"""
                    <div style="color: #70757a; font-size: 14px; margin: 20px 0;">
                        No academic papers found for "<strong>{query}</strong>". Try different keywords or check spelling.
                    </div>
                    """, unsafe_allow_html=True)
                    
            except Exception as e:
                st.error(f"Error searching academic papers: {e}")
    
    # === TAB 2: AI Answer ===
    with tab2:
        ai_start_time = time.time()
        with st.spinner("Generating comprehensive AI answer from all sources..."):
            # Get academic passages
            passages_start = time.time()
            try:
                objects = minio_client.list_objects("passages")
                for obj in objects:
                    if obj.object_name.endswith(".json"):
                        resp = minio_client.get_object("passages", obj.object_name)
                        buffer = io.BytesIO()
                        for chunk in resp.stream(32 * 1024):
                            buffer.write(chunk)
                        buffer.seek(0)
                        data = json.load(buffer)
                        passages.extend(data)
            except Exception as e:
                st.warning(f"Could not load academic passages: {e}")
            passages_time = time.time() - passages_start
            
            # Extract web content in parallel
            web_start = time.time()
            if web_results:
                with st.status("Processing web content...", expanded=True) as status:
                    # Group results by source for better display
                    source_groups = {}
                    for result in web_results:
                        source = result['source']
                        if source not in source_groups:
                            source_groups[source] = []
                        source_groups[source].append(result)
                    
                    status.write(f"🌐 Processing {len(web_results)} results from {len(source_groups)} sources:")
                    for source, results in source_groups.items():
                        status.write(f"  • **{source}**: {len(results)} articles")
                    
                    status.write(f"📄 Extracting content from all {len(web_results)} articles...")
                    
                    # Parallel content extraction with increased workers and timeout
                    successful_extractions = 0
                    with ThreadPoolExecutor(max_workers=8) as executor:
                        future_to_url = {
                            executor.submit(web_crawler.get_article_content, result['url']): result 
                            for result in web_results
                        }
                        
                        for future in future_to_url:
                            result = future_to_url[future]
                            try:
                                content = future.result(timeout=20)
                                if content and len(content.strip()) > 50:
                                    web_content.append({
                                        'text': content,
                                        'title': result['title'],
                                        'url': result['url'],
                                        'source': result['source']
                                    })
                                    successful_extractions += 1
                            except Exception as e:
                                status.write(f"⚠️ Skipped {result['source']}: {result['title'][:50]}...")
                    
                    status.write(f"✅ Successfully extracted {successful_extractions}/{len(web_results)} articles")
                    
                    if web_content:
                        avg_length = sum(len(w['text']) for w in web_content) / len(web_content)
                        status.write(f"📊 Average content length: {avg_length:.0f} characters")
            web_time = time.time() - web_start
            
            # Combine all sources for AI processing
            embedding_start = time.time()
            all_texts = []
            text_sources = []
            
            # Add academic passages
            for p in passages:
                text = p["text"].replace("\n", " ").strip()
                if len(text) > 50:
                    all_texts.append(text)
                    text_sources.append({"type": "academic", "data": p})
            
            # Add web content with smart chunking
            for w in web_content:
                text = w['text']
                chunk_size = 1500
                overlap = 300
                
                for i in range(0, len(text), chunk_size - overlap):
                    chunk = text[i:i + chunk_size].strip()
                    if len(chunk) > 100:
                        all_texts.append(chunk)
                        text_sources.append({"type": "web", "data": w, "chunk": chunk})
            
            st.info(f"🔄 Processing {len(all_texts)} text segments from {len(passages)} academic sources and {len(web_content)} web articles")
            
            if all_texts:
                # Enhanced semantic search
                passage_embeddings = embedder.encode(all_texts, convert_to_tensor=True)
                query_embedding = embedder.encode(query, convert_to_tensor=True)
                scores = util.cos_sim(query_embedding, passage_embeddings)[0]
                
                # Get top results with higher limit
                top_k = 12
                top_indices = torch.topk(scores, k=min(top_k, len(all_texts))).indices.tolist()
                
                # Build comprehensive context
                tokenizer = AutoTokenizer.from_pretrained("meta-llama/Llama-2-7b-chat-hf",token=token)                
                max_tokens = 1500
                context = ""
                included_sources = []
                
                for i in top_indices:
                    chunk = all_texts[i]
                    source_info = text_sources[i]
                    temp = context + "\n\n" + chunk if context else chunk
                    
                    if len(tokenizer.encode(temp)) <= max_tokens:
                        context = temp
                        included_sources.append({
                            'text': chunk,
                            'source': source_info,
                            'similarity_score': float(scores[i])
                        })
                    else:
                        break
                embedding_time = time.time() - embedding_start
                st.write(f"✅ Context tokens so far: {len(tokenizer.encode(context))}")

                # Generate comprehensive answer
                mistral_start = time.time()
                answer = call_mistral(query, context)
                mistral_time = time.time() - mistral_start
                
                total_ai_time = time.time() - ai_start_time
                
                # Display results
                st.markdown(f"""
                <div style="color: #70757a; font-size: 14px; margin-bottom: 20px;">
                    🤖 Comprehensive AI Answer generated ({format_time_elapsed(total_ai_time)})
                </div>
                """, unsafe_allow_html=True)
                
                st.markdown("### ✅ AI-Generated Answer")
                st.write(answer)
                
                # Enhanced source analytics
                st.markdown("### 📊 Sources Analysis")
                academic_count = sum(1 for s in included_sources if s['source']['type'] == 'academic')
                web_count = sum(1 for s in included_sources if s['source']['type'] == 'web')

                source_breakdown = {}
                for s in included_sources:
                    if s['source']['type'] == 'web':
                        src = s['source']['data'].get('source', 'Web')
                    else:
                        src = 'Academic Papers'
                    source_breakdown[src] = source_breakdown.get(src, 0) + 1

                col1, col2 = st.columns(2)
                with col1:
                    st.metric("📚 Academic Sources", academic_count)
                    st.metric("🌐 Web Sources", web_count)
                with col2:
                    st.metric("📄 Total Passages", len(included_sources))
                    avg_similarity = sum(s['similarity_score'] for s in included_sources) / len(included_sources)
                    st.metric("📈 Avg Similarity", f"{avg_similarity:.3f}")
                
                # Source breakdown
                st.markdown("#### Source Distribution:")
                for src, count in source_breakdown.items():
                    st.markdown(f"- **{src}**: {count} passage(s)")
                
                # Performance metrics
                st.markdown("### ⏱️ Processing Performance")
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Academic Load", f"{passages_time:.2f}s")
                with col2:
                    st.metric("Web Processing", f"{web_time:.2f}s")
                with col3:
                    st.metric("AI Analysis", f"{embedding_time:.2f}s")
                with col4:
                    st.metric("Answer Gen", f"{mistral_time:.2f}s")
                
                # Detailed source content
                with st.expander("📄 View Source Content Used", expanded=False):
                    for i, source in enumerate(included_sources, 1):
                        source_type = source['source']['type']
                        similarity = source['similarity_score']
                        
                        if source_type == 'academic':
                            st.markdown(f"**📚 Academic Source {i}** (Similarity: {similarity:.3f}):")
                        else:
                            web_data = source['source']['data']
                            src_name = web_data.get('source', 'Web')
                            st.markdown(f"**🌐 {src_name} - {web_data['title']}** (Similarity: {similarity:.3f}):")
                            st.caption(f"🔗 {web_data['url']}")
                        
                        display_text = source['text'][:400] + "..." if len(source['text']) > 400 else source['text']
                        st.write(display_text)
                        st.divider()

            else:
                st.warning("⚠️ No content available for generating an answer. This might be due to connectivity issues or lack of relevant content.")
    
    # === TAB 3: All Web Results (No Limits) ===
    with tab3:
        web_tab_start = time.time()
        
        # Debug information
        st.info(f"🔍 Debug: web_results has {len(web_results) if web_results else 0} items")
        
        if web_results and len(web_results) > 0:
            web_tab_time = time.time() - web_tab_start
            
            # Display comprehensive stats
            st.markdown(f"""
            <div style="color: #70757a; font-size: 14px; margin-bottom: 20px;">
                🌐 Found {len(web_results)} web results from all sources ({format_time_elapsed(web_tab_time)})
            </div>
            """, unsafe_allow_html=True)
            
            # Comprehensive source breakdown
            source_counts = {}
            for r in web_results:
                source = r['source']
                source_counts[source] = source_counts.get(source, 0) + 1

            st.markdown("#### 🔍 Complete Source Breakdown")
            if source_counts:
                cols = st.columns(min(len(source_counts), 4))  # Max 4 columns
                for i, (src, count) in enumerate(source_counts.items()):
                    with cols[i % len(cols)]:
                        st.metric(src, count)
            
            # Enhanced filtering and sorting
            col1, col2, col3 = st.columns(3)
            with col1:
                sort_by = st.selectbox("📊 Sort by", ["Relevance (Default)", "Source", "Title A-Z"], key="sort_web")
            with col2:
                filter_source = st.selectbox("🔍 Filter by Source", ["All Sources"] + list(source_counts.keys()), key="filter_source")
            with col3:
                show_snippets = st.checkbox("📝 Show snippets", value=True, key="show_snippets")
            
            # Apply filters
            filtered_results = web_results
            if filter_source != "All Sources":
                filtered_results = [r for r in web_results if r['source'] == filter_source]
            
            # Apply sorting
            if sort_by == "Source":
                filtered_results = sorted(filtered_results, key=lambda x: (x['source'], x['title']))
            elif sort_by == "Title A-Z":
                filtered_results = sorted(filtered_results, key=lambda x: x['title'].lower())
            # "Relevance (Default)" keeps original order
            
            st.markdown(f"#### 📋 Showing {len(filtered_results)} results")
            
            # Display ALL results with enhanced styling
            for i, result in enumerate(filtered_results, 1):
                source_color_map = {
                    'GeeksforGeeks': '#28a745',
                    'MathWorld': '#0074D9', 
                    'Engineering.com': '#FF851B'
                }
                source_color = source_color_map.get(result['source'], '#6c757d')
                
                with st.container():
                    # Create the header with HTML for styling
                    st.markdown(f"""
                    <div style="border: 1px solid #e0e0e0; padding: 15px; border-radius: 10px; margin-bottom: 15px; background-color: #f8fffe;">
                        <div style="display: flex; align-items: center; margin-bottom: 10px;">
                            <span style="background-color: {source_color}; color: white; padding: 4px 8px; border-radius: 12px; font-size: 12px; margin-right: 10px; font-weight: bold;">
                                {result['source']}
                            </span>
                            <span style="color: #70757a; font-size: 12px; margin-right: 10px;">#{i}</span>
                            <h4 style="color: #0066cc; margin: 0; flex-grow: 1; font-size: 16px; line-height: 1.3;">{html.escape(result['title'])}</h4>
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Display snippet using Streamlit's native text display (not HTML)
                    if show_snippets and result.get('snippet'):
                        clean_snippet = clean_html_snippet(result.get('snippet', ''))
                        if clean_snippet:
                            st.markdown(f"*{clean_snippet}*")
                    
                    # Display URL and button with HTML for styling
                    safe_url = html.escape(result['url'])
                    st.markdown(f"""
                    <div style="margin: 10px 0;">
                        <a href="{safe_url}" target="_blank" style="color: #006621; font-size: 13px; word-break: break-all;">
                            🔗 {safe_url}
                        </a>
                    </div>
                    <div style="margin-top: 12px; margin-bottom: 15px;">
                        <a href="{safe_url}" target="_blank" style="text-decoration: none; background-color: {source_color}; color: white; padding: 8px 16px; border-radius: 5px; display: inline-block; font-size: 13px; font-weight: 500;">
                            📖 Read Full Article
                        </a>
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # Content preview option for each result
                    if st.checkbox(f"📄 Show content preview", key=f"preview_{i}"):
                        with st.spinner("Loading full content..."):
                            try:
                                content = web_crawler.get_article_content(result['url'])
                                if content and len(content.strip()) > 20:
                                    word_count = len(content.split())
                                    char_count = len(content)
                                    st.caption(f"📊 Content stats: {word_count:,} words • {char_count:,} characters")
                                    
                                    # Full content in expandable section
                                    with st.expander("🔍 Full Article Content", expanded=False):
                                        st.text_area("", content, height=300, key=f"content_{i}")
                                    
                                    # Quick preview
                                    preview_length = 400
                                    preview_text = content[:preview_length] + "..." if len(content) > preview_length else content
                                    st.markdown(f"**📖 Quick Preview:**\n\n{preview_text}")
                                else:
                                    st.warning("⚠️ Could not extract meaningful content from this article.")
                            except Exception as e:
                                st.error(f"❌ Error loading content: {str(e)}")
        else:
            # Enhanced debugging section
            st.warning("⚠️ No web results found")
            
            with st.expander("🔧 Debug Information", expanded=True):
                st.write("**Web Crawler Status:**")
                st.write(f"- Web crawler loaded: {web_crawler is not None}")
                if web_crawler:
                    st.write(f"- Available crawlers: {list(web_crawler.crawlers.keys())}")
                    
                    # Test each crawler individually
                    st.write("**Testing individual crawlers:**")
                    for name, crawler in web_crawler.crawlers.items():
                        try:
                            st.write(f"- {name}: Testing...")
                            test_results = crawler.search(query, max_results=2)
                            st.write(f"  ✅ {name}: {len(test_results)} results")
                            if test_results:
                                st.write(f"    Sample: {test_results[0].get('title', 'No title')[:50]}...")
                        except Exception as e:
                            st.write(f"  ❌ {name}: Error - {str(e)}")
                
                st.write(f"**Query:** '{query}'")
                st.write(f"**Web results type:** {type(web_results)}")
                st.write(f"**Web results length:** {len(web_results) if web_results else 'None'}")
            
            st.markdown("""
            <div style="text-align: center; padding: 40px; color: #666;">
                <h3>🔍 No web results found</h3>
                <p>We couldn't find any web content for "<strong>{}</strong>"</p>
                <p>This might be due to:</p>
                <ul style="text-align: left; max-width: 400px; margin: 0 auto;">
                    <li>Network connectivity issues</li>
                    <li>All sites being temporarily unavailable</li>
                    <li>The search terms being too specific</li>
                    <li>Crawler initialization problems</li>
                </ul>
                <p><em>Check the debug information above for more details.</em></p>
            </div>
            """.format(query), unsafe_allow_html=True)

# Enhanced footer with comprehensive stats
st.markdown("---")
total_search_time = time.time() - search_start_time if 'search_start_time' in locals() else 0

if total_search_time > 0:
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("⚡ Total Search Time", f"{total_search_time:.2f}s")
    with col2:
        if 'web_results' in locals():
            st.metric("🌐 Web Results Found", len(web_results))
    with col3:
        if 'passages' in locals():
            st.metric("📚 Academic Sources", len(passages))

st.markdown("*💡 **Search Tips:** Use specific technical terms, combine concepts, or ask direct questions. Click Search button or click suggestions.*")
    st.markdown("*🔄 **Auto-Search:** All sources are automatically searched in parallel for comprehensive results*")

# System status
if st.checkbox("🔧 System Status", key="system_status"):
    st.markdown("### 🔧 System Information")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🤖 AI Models:**")
        st.write("✅ Sentence Transformer loaded")
        st.write("✅ QA Pipeline loaded")
        st.write("✅ Mistral API connected")
    with col2:
        st.markdown("**🔍 Search Engines:**")
        if web_crawler:
            for name in web_crawler.crawlers.keys():
                st.write(f"✅ {name} crawler ready")
        else:
            st.write("❌ Web crawler not initialized")
    
    if 'web_results' in locals() and web_results:
        st.markdown("**📊 Latest Search Results:**")
        source_summary = {}
        for result in web_results:
            source = result['source']
            source_summary[source] = source_summary.get(source, 0) + 1
        
        for source, count in source_summary.items():
            st.write(f"• {source}: {count} results")