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

query = st.text_input("Enter a keyword or ask a question", placeholder="e.g., 'machine learning algorithms' or 'quantum computing applications'")

if query:
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

col1, col2 = st.columns(2)
with col1:
    st.markdown("*💡 **Search Tips:** Use specific technical terms, combine concepts, or ask direct questions*")
with col2:
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