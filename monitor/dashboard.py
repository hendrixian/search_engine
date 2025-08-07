import streamlit as st
import time
import json
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
from elasticsearch import Elasticsearch
from minio import Minio
import io
import os
from dotenv import load_dotenv
from collections import defaultdict, deque
import threading
import queue
import psutil
import requests
import asyncio
from concurrent.futures import ThreadPoolExecutor

load_dotenv()

# Configuration
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

# Global state for real-time monitoring
if 'search_logs' not in st.session_state:
    st.session_state.search_logs = deque(maxlen=100)
if 'system_metrics' not in st.session_state:
    st.session_state.system_metrics = deque(maxlen=50)
if 'crawler_stats' not in st.session_state:
    st.session_state.crawler_stats = defaultdict(list)
if 'ai_processing_logs' not in st.session_state:
    st.session_state.ai_processing_logs = deque(maxlen=50)

# Initialize connections
@st.cache_resource
def init_connections():
    try:
        es = Elasticsearch(ELASTICSEARCH_HOST)
        minio_client = Minio(MINIO_ENDPOINT, access_key=MINIO_ROOT_USER, secret_key=MINIO_ROOT_PASSWORD, secure=False)
        return es, minio_client
    except Exception as e:
        st.error(f"Failed to initialize connections: {e}")
        return None, None

es, minio_client = init_connections()

# System monitoring functions
def get_system_metrics():
    """Get current system performance metrics"""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            'timestamp': datetime.now(),
            'cpu_percent': cpu_percent,
            'memory_percent': memory.percent,
            'memory_used_gb': memory.used / (1024**3),
            'memory_total_gb': memory.total / (1024**3),
            'disk_percent': disk.percent,
            'disk_used_gb': disk.used / (1024**3),
            'disk_total_gb': disk.total / (1024**3)
        }
    except Exception as e:
        return {'timestamp': datetime.now(), 'error': str(e)}

def simulate_search_process(query):
    """Simulate and log a complete search process"""
    search_id = f"search_{int(time.time())}"
    
    # Stage 1: Query Analysis
    st.session_state.search_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Query Analysis',
        'query': query,
        'details': f"Analyzing query: '{query}' - {len(query.split())} terms detected",
        'status': 'processing'
    })
    
    time.sleep(0.5)  # Simulate processing time
    
    # Stage 2: Elasticsearch Search
    try:
        if es:
            es_start = time.time()
            es_result = es.search(index="academic-papers", query={
                "multi_match": {
                    "query": query,
                    "fields": ["title^3", "abstract", "authors"]
                }
            })
            es_time = time.time() - es_start
            
            st.session_state.search_logs.append({
                'search_id': search_id,
                'timestamp': datetime.now(),
                'stage': 'Elasticsearch Search',
                'query': query,
                'details': f"Found {es_result['hits']['total']['value']} papers in {es_time:.2f}s",
                'status': 'completed',
                'metrics': {'results': es_result['hits']['total']['value'], 'time': es_time}
            })
    except Exception as e:
        st.session_state.search_logs.append({
            'search_id': search_id,
            'timestamp': datetime.now(),
            'stage': 'Elasticsearch Search',
            'query': query,
            'details': f"Error: {str(e)}",
            'status': 'error'
        })
    
    # Stage 3: Web Crawling Simulation
    crawlers = ['GeeksforGeeks', 'MathWorld', 'Engineering.com']
    for crawler in crawlers:
        crawl_start = time.time()
        
        st.session_state.search_logs.append({
            'search_id': search_id,
            'timestamp': datetime.now(),
            'stage': f'Web Crawling - {crawler}',
            'query': query,
            'details': f"Searching {crawler}...",
            'status': 'processing'
        })
        
        time.sleep(np.random.uniform(0.5, 2.0))  # Simulate variable crawling time
        
        # Simulate results
        results_count = np.random.randint(0, 20)
        crawl_time = time.time() - crawl_start
        
        st.session_state.search_logs.append({
            'search_id': search_id,
            'timestamp': datetime.now(),
            'stage': f'Web Crawling - {crawler}',
            'query': query,
            'details': f"Found {results_count} results in {crawl_time:.2f}s",
            'status': 'completed' if results_count > 0 else 'no_results',
            'metrics': {'results': results_count, 'time': crawl_time}
        })
        
        # Update crawler stats
        st.session_state.crawler_stats[crawler].append({
            'timestamp': datetime.now(),
            'query': query,
            'results': results_count,
            'time': crawl_time,
            'success': results_count > 0
        })
    
    # Stage 4: Content Extraction
    st.session_state.search_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Content Extraction',
        'query': query,
        'details': "Extracting full content from web articles...",
        'status': 'processing'
    })
    
    time.sleep(1.5)  # Simulate content extraction
    
    extracted_count = np.random.randint(5, 25)
    st.session_state.search_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Content Extraction',
        'query': query,
        'details': f"Successfully extracted content from {extracted_count} articles",
        'status': 'completed',
        'metrics': {'extracted': extracted_count}
    })
    
    # Stage 5: AI Analysis
    ai_start = time.time()
    st.session_state.ai_processing_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Embedding Generation',
        'query': query,
        'details': f"Generating embeddings for {extracted_count + 50} passages...",
        'status': 'processing'
    })
    
    time.sleep(2.0)  # Simulate AI processing
    
    ai_time = time.time() - ai_start
    similarity_scores = np.random.beta(2, 5, 12)  # Simulate similarity scores
    
    st.session_state.ai_processing_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Semantic Search',
        'query': query,
        'details': f"Ranked passages by similarity. Top score: {max(similarity_scores):.3f}",
        'status': 'completed',
        'metrics': {'processing_time': ai_time, 'top_score': max(similarity_scores)}
    })
    
    # Stage 6: Answer Generation
    st.session_state.ai_processing_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Answer Generation',
        'query': query,
        'details': "Generating comprehensive answer using Mistral AI...",
        'status': 'processing'
    })
    
    time.sleep(3.0)  # Simulate answer generation
    
    st.session_state.ai_processing_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Answer Generation',
        'query': query,
        'details': f"Generated {np.random.randint(150, 500)} word answer",
        'status': 'completed',
        'metrics': {'word_count': np.random.randint(150, 500)}
    })
    
    # Final stage
    total_time = time.time() - (ai_start - 8)  # Approximate total time
    st.session_state.search_logs.append({
        'search_id': search_id,
        'timestamp': datetime.now(),
        'stage': 'Search Complete',
        'query': query,
        'details': f"Search completed successfully in {total_time:.1f}s",
        'status': 'completed',
        'metrics': {'total_time': total_time}
    })

# Streamlit App
st.set_page_config(
    page_title="🔍 Academic Search System Monitor", 
    page_icon="🔍", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🔍 Academic Search System Monitor")
st.markdown("*Real-time insights into search algorithms, crawling, indexing, and AI analysis*")

# Sidebar controls
st.sidebar.header("🎛️ Control Panel")

# Test search functionality
st.sidebar.subheader("🧪 Test Search Process")
test_query = st.sidebar.text_input("Enter test query:", placeholder="machine learning")
if st.sidebar.button("🚀 Run Test Search"):
    with st.spinner("Running search simulation..."):
        simulate_search_process(test_query)

# System metrics collection
if st.sidebar.checkbox("📊 Collect System Metrics", value=True):
    if st.sidebar.button("📈 Update Metrics Now"):
        metrics = get_system_metrics()
        st.session_state.system_metrics.append(metrics)

# Auto-refresh settings
auto_refresh = st.sidebar.checkbox("🔄 Auto Refresh (5s)", value=False)
if auto_refresh:
    time.sleep(5)
    st.rerun()

# Clear logs
if st.sidebar.button("🗑️ Clear All Logs"):
    st.session_state.search_logs.clear()
    st.session_state.ai_processing_logs.clear()
    st.session_state.crawler_stats.clear()
    st.sidebar.success("Logs cleared!")

# Main dashboard
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "🔍 Live Search Process", 
    "🕷️ Crawler Analytics", 
    "🧠 AI Processing", 
    "📊 System Performance", 
    "📈 Search Analytics",
    "⚙️ Algorithm Details"
])

# Tab 1: Live Search Process
with tab1:
    st.header("🔍 Real-Time Search Process Monitor")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("📋 Live Search Log")
        
        if st.session_state.search_logs:
            # Create a real-time log display
            for log in reversed(list(st.session_state.search_logs)[-10:]):  # Show last 10 entries
                status_emoji = {
                    'processing': '🔄',
                    'completed': '✅',
                    'error': '❌',
                    'no_results': '⚠️'
                }.get(log['status'], '🔍')
                
                timestamp = log['timestamp'].strftime("%H:%M:%S")
                
                st.markdown(f"""
                <div style="border-left: 3px solid {'#28a745' if log['status'] == 'completed' else '#ffc107' if log['status'] == 'processing' else '#dc3545'}; 
                           padding: 10px; margin: 5px 0; background-color: #f8f9fa;">
                    <div style="font-size: 12px; color: #6c757d;">{timestamp} | {log['search_id']}</div>
                    <div style="font-weight: bold; color: #495057;">{status_emoji} {log['stage']}</div>
                    <div style="color: #6c757d; margin-top: 5px;">{log['details']}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No search processes logged yet. Run a test search to see the process!")
    
    with col2:
        st.subheader("📊 Current Process Stats")
        
        if st.session_state.search_logs:
            # Calculate stats from recent searches
            recent_logs = list(st.session_state.search_logs)[-20:]
            
            completed_stages = [log for log in recent_logs if log['status'] == 'completed']
            processing_stages = [log for log in recent_logs if log['status'] == 'processing']
            error_stages = [log for log in recent_logs if log['status'] == 'error']
            
            st.metric("✅ Completed Stages", len(completed_stages))
            st.metric("🔄 Processing", len(processing_stages))
            st.metric("❌ Errors", len(error_stages))
            
            # Success rate
            if recent_logs:
                success_rate = len(completed_stages) / len(recent_logs) * 100
                st.metric("📈 Success Rate", f"{success_rate:.1f}%")
            
            # Recent search queries
            st.subheader("🔍 Recent Queries")
            unique_queries = list(set([log['query'] for log in recent_logs if 'query' in log]))[-5:]
            for query in unique_queries:
                st.code(query)

# Tab 2: Crawler Analytics
with tab2:
    st.header("🕷️ Web Crawler Performance Analytics")
    
    if st.session_state.crawler_stats:
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("📊 Crawler Success Rates")
            
            success_data = []
            for crawler, stats in st.session_state.crawler_stats.items():
                if stats:
                    successful = sum(1 for s in stats if s['success'])
                    total = len(stats)
                    success_rate = (successful / total * 100) if total > 0 else 0
                    success_data.append({
                        'Crawler': crawler,
                        'Success Rate': success_rate,
                        'Total Searches': total,
                        'Successful': successful
                    })
            
            if success_data:
                df = pd.DataFrame(success_data)
                fig = px.bar(df, x='Crawler', y='Success Rate', 
                           title='Crawler Success Rates (%)',
                           color='Success Rate',
                           color_continuous_scale='Viridis')
                st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("⏱️ Average Response Times")
            
            response_data = []
            for crawler, stats in st.session_state.crawler_stats.items():
                if stats:
                    avg_time = np.mean([s['time'] for s in stats])
                    response_data.append({
                        'Crawler': crawler,
                        'Avg Response Time (s)': avg_time
                    })
            
            if response_data:
                df = pd.DataFrame(response_data)
                fig = px.bar(df, x='Crawler', y='Avg Response Time (s)',
                           title='Average Response Times',
                           color='Avg Response Time (s)',
                           color_continuous_scale='Reds')
                st.plotly_chart(fig, use_container_width=True)
        
        # Detailed crawler table
        st.subheader("📋 Detailed Crawler Statistics")
        
        detailed_stats = []
        for crawler, stats in st.session_state.crawler_stats.items():
            if stats:
                total_results = sum(s['results'] for s in stats)
                avg_results = np.mean([s['results'] for s in stats])
                max_results = max(s['results'] for s in stats)
                min_time = min(s['time'] for s in stats)
                max_time = max(s['time'] for s in stats)
                
                detailed_stats.append({
                    'Crawler': crawler,
                    'Total Searches': len(stats),
                    'Total Results': total_results,
                    'Avg Results': f"{avg_results:.1f}",
                    'Max Results': max_results,
                    'Min Response Time': f"{min_time:.2f}s",
                    'Max Response Time': f"{max_time:.2f}s",
                    'Last Search': stats[-1]['timestamp'].strftime("%H:%M:%S")
                })
        
        if detailed_stats:
            st.dataframe(detailed_stats, use_container_width=True)
    else:
        st.info("No crawler data available yet. Run some test searches to see analytics!")

# Tab 3: AI Processing
with tab3:
    st.header("🧠 AI Processing & Analysis Monitor")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        st.subheader("🤖 AI Processing Pipeline")
        
        if st.session_state.ai_processing_logs:
            for log in reversed(list(st.session_state.ai_processing_logs)[-8:]):
                timestamp = log['timestamp'].strftime("%H:%M:%S")
                
                status_color = {
                    'processing': '#ffc107',
                    'completed': '#28a745',
                    'error': '#dc3545'
                }.get(log['status'], '#6c757d')
                
                st.markdown(f"""
                <div style="border: 1px solid {status_color}; border-radius: 8px; padding: 15px; margin: 10px 0; background-color: #f8f9fa;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
                        <strong style="color: {status_color};">🧠 {log['stage']}</strong>
                        <span style="color: #6c757d; font-size: 12px;">{timestamp}</span>
                    </div>
                    <div style="color: #495057; margin-bottom: 8px;">{log['details']}</div>
                    <div style="font-size: 11px; color: #6c757d;">Query: "{log['query']}"</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No AI processing logs yet. Run a test search to see AI analysis!")
    
    with col2:
        st.subheader("📊 AI Metrics")
        
        if st.session_state.ai_processing_logs:
            ai_logs = list(st.session_state.ai_processing_logs)
            
            # Count different AI stages
            embedding_logs = [log for log in ai_logs if 'Embedding' in log['stage']]
            semantic_logs = [log for log in ai_logs if 'Semantic' in log['stage']]
            generation_logs = [log for log in ai_logs if 'Generation' in log['stage']]
            
            st.metric("🔢 Embedding Operations", len(embedding_logs))
            st.metric("🔍 Semantic Searches", len(semantic_logs))
            st.metric("📝 Answer Generations", len(generation_logs))
            
            # Average processing times
            if semantic_logs:
                avg_semantic_time = np.mean([log.get('metrics', {}).get('processing_time', 0) 
                                           for log in semantic_logs if log.get('metrics')])
                st.metric("⏱️ Avg Semantic Time", f"{avg_semantic_time:.2f}s")
            
            # Similarity scores
            similarity_scores = [log.get('metrics', {}).get('top_score', 0) 
                               for log in semantic_logs if log.get('metrics', {}).get('top_score')]
            if similarity_scores:
                avg_similarity = np.mean(similarity_scores)
                st.metric("📈 Avg Top Similarity", f"{avg_similarity:.3f}")

# Tab 4: System Performance
with tab4:
    st.header("📊 System Performance Monitor")
    
    # Update system metrics
    current_metrics = get_system_metrics()
    st.session_state.system_metrics.append(current_metrics)
    
    if st.session_state.system_metrics and 'error' not in current_metrics:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("🖥️ CPU Usage", f"{current_metrics['cpu_percent']:.1f}%")
            st.metric("💾 Memory Usage", f"{current_metrics['memory_percent']:.1f}%")
        
        with col2:
            st.metric("💿 Disk Usage", f"{current_metrics['disk_percent']:.1f}%")
            st.metric("📊 Memory Used", f"{current_metrics['memory_used_gb']:.1f} GB")
        
        with col3:
            st.metric("💾 Memory Total", f"{current_metrics['memory_total_gb']:.1f} GB")
            st.metric("💿 Disk Free", f"{current_metrics['disk_total_gb'] - current_metrics['disk_used_gb']:.1f} GB")
        
        # Performance charts
        if len(st.session_state.system_metrics) > 1:
            metrics_df = pd.DataFrame(st.session_state.system_metrics)
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=metrics_df['timestamp'], y=metrics_df['cpu_percent'],
                                   mode='lines+markers', name='CPU %', line=dict(color='red')))
            fig.add_trace(go.Scatter(x=metrics_df['timestamp'], y=metrics_df['memory_percent'],
                                   mode='lines+markers', name='Memory %', line=dict(color='blue')))
            fig.add_trace(go.Scatter(x=metrics_df['timestamp'], y=metrics_df['disk_percent'],
                                   mode='lines+markers', name='Disk %', line=dict(color='green')))
            
            fig.update_layout(title='System Performance Over Time',
                            xaxis_title='Time',
                            yaxis_title='Usage %',
                            height=400)
            
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.error("Unable to collect system metrics")

# Tab 5: Search Analytics
with tab5:
    st.header("📈 Search Analytics & Insights")
    
    if st.session_state.search_logs:
        # Search volume over time
        search_df = pd.DataFrame(st.session_state.search_logs)
        search_df['hour'] = search_df['timestamp'].dt.hour
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.subheader("🕐 Searches by Hour")
            hourly_searches = search_df.groupby('hour').size().reset_index(name='count')
            fig = px.bar(hourly_searches, x='hour', y='count', 
                        title='Search Volume by Hour')
            st.plotly_chart(fig, use_container_width=True)
        
        with col2:
            st.subheader("📊 Stage Success Rate")
            stage_stats = search_df.groupby(['stage', 'status']).size().unstack(fill_value=0)
            if 'completed' in stage_stats.columns and 'error' in stage_stats.columns:
                stage_stats['success_rate'] = stage_stats['completed'] / (stage_stats['completed'] + stage_stats['error']) * 100
                fig = px.bar(stage_stats.reset_index(), x='stage', y='success_rate',
                           title='Success Rate by Stage (%)')
                st.plotly_chart(fig, use_container_width=True)
        
        # Query analysis
        st.subheader("🔍 Query Analysis")
        queries = [log['query'] for log in st.session_state.search_logs if 'query' in log]
        if queries:
            query_lengths = [len(q.split()) for q in queries]
            unique_queries = set(queries)
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("📝 Total Queries", len(queries))
            with col2:
                st.metric("🎯 Unique Queries", len(unique_queries))
            with col3:
                st.metric("📏 Avg Query Length", f"{np.mean(query_lengths):.1f} words")
            
            # Most common queries
            from collections import Counter
            query_counts = Counter(queries)
            if query_counts:
                st.subheader("🔥 Most Common Queries")
                for query, count in query_counts.most_common(5):
                    st.write(f"**{query}** ({count} times)")

# Tab 6: Algorithm Details
with tab6:
    st.header("⚙️ Search Algorithm Details")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("🔍 Search Process Flow")
        st.markdown("""
        ```
        1. 📝 Query Analysis
           ├── Tokenization
           ├── Stop word removal
           └── Term expansion
        
        2. 🔍 Multi-Source Search
           ├── 📚 Academic Papers (Elasticsearch)
           ├── 🕷️ Web Crawling (GeeksforGeeks, MathWorld, Engineering.com)
           └── 📄 Content Extraction
        
        3. 🧠 AI Processing
           ├── 🔢 Embedding Generation (Sentence Transformers)
           ├── 📊 Semantic Similarity Search
           ├── 🎯 Relevance Ranking
           └── 🤖 Answer Generation (Mistral AI)
        
        4. 📋 Result Compilation
           ├── 📊 Source Ranking
           ├── 🔄 Deduplication
           └── 📄 Final Presentation
        ```
        """)
    
    with col2:
        st.subheader("🧮 Ranking Algorithm")
        st.markdown("""
        **Academic Papers Ranking:**
        - Title match: 3x weight
        - Abstract relevance: 1x weight
        - Author match: 1x weight
        - Publication year recency bonus
        
        **Web Results Ranking:**
        - Source reliability score
        - Content length and quality
        - Semantic similarity score
        - Crawl success rate
        
        **AI Answer Generation:**
        - Top-K semantic similarity (K=12)
        - Context window: 1500 tokens
        - Temperature: 0.7
        - Multi-source fusion
        """)
        
        st.subheader("⚡ Performance Optimizations")
        st.markdown("""
        - **Parallel Processing**: Concurrent web crawling
        - **Caching**: Model caching, result caching
        - **Indexing**: Elasticsearch full-text search
        - **Batching**: Efficient embedding generation
        - **Streaming**: Real-time result updates
        """)
    
    st.subheader("📊 Algorithm Configuration")
    
    config_col1, config_col2, config_col3 = st.columns(3)
    
    with config_col1:
        st.markdown("**🔍 Search Parameters**")
        st.code("""
max_results_per_source: 10
elasticsearch_timeout: 30s
web_crawl_timeout: 20s
content_extraction_timeout: 15s
        """)
    
    with config_col2:
        st.markdown("**🧠 AI Parameters**")
        st.code("""
embedding_model: all-MiniLM-L6-v2
similarity_threshold: 0.3
context_max_tokens: 1500
top_k_passages: 12
        """)
    
    with config_col3:
        st.markdown("**⚡ Performance Settings**")
        st.code("""
max_workers: 8
batch_size: 32
cache_ttl: 300s
retry_attempts: 3
        """)

# Footer
st.markdown("---")
st.markdown(f"""
<div style="text-align: center; color: #6c757d; padding: 20px;">
    <p>🔍 <strong>Academic Search System Monitor</strong> - Real-time system insights</p>
    <p>Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | 
       Active searches: {len(st.session_state.search_logs)} | 
       System metrics: {len(st.session_state.system_metrics)}</p>
</div>
""", unsafe_allow_html=True)

# Auto-refresh indicator
if auto_refresh:
    st.markdown("""
    <div style="position: fixed; top: 10px; right: 10px; background-color: #28a745; color: white; 
                padding: 5px 10px; border-radius: 15px; font-size: 12px; z-index: 1000;">
        🔄 Auto-refreshing...
    </div>
    """, unsafe_allow_html=True)