# monitor/dashboard.py - Updated with Flask integration
import os
import time
import json
import threading
import random
import redis
from flask import Flask, render_template_string, jsonify, request, Response
from flask_sse import sse
from datetime import datetime, timedelta
from collections import defaultdict, deque
from concurrent.futures import ThreadPoolExecutor

# Optional dependencies that match your Streamlit original
try:
    from elasticsearch import Elasticsearch
except Exception:
    Elasticsearch = None

try:
    from minio import Minio
except Exception:
    Minio = None

try:
    import psutil
except Exception:
    psutil = None

import numpy as np
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Configuration (pull from env like your Streamlit app)
ELASTICSEARCH_HOST = os.getenv("ELASTICSEARCH_HOST", "http://localhost:9200")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "localhost:9000")
MINIO_ROOT_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_ROOT_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

# Redis configuration for receiving Flask app events
REDIS_HOST = os.getenv('REDIS_HOST', 'redis')
REDIS_PORT = int(os.getenv('REDIS_PORT', 6379))

# Flask app
app = Flask(__name__)
app.config['REDIS_URL'] = 'redis://redis:6379'  # or from environment
app.register_blueprint(sse, url_prefix='/stream')

# Global state (replace st.session_state)
STATE_LOCK = threading.Lock()
search_logs = deque(maxlen=200)           # each entry: dict
system_metrics = deque(maxlen=200)        # list of dicts
crawler_stats = defaultdict(list)         # crawler -> list of stats dicts
ai_processing_logs = deque(maxlen=100)    # list of dicts
auto_refresh_enabled = False
flask_integration_enabled = False

# Real-time connections for SSE
sse_connections = []

# Executor for running background tasks
executor = ThreadPoolExecutor(max_workers=8)

# Redis connection for receiving Flask app events
redis_conn = None
try:
    redis_conn = redis.Redis(
        host=REDIS_HOST, 
        port=REDIS_PORT, 
        decode_responses=True,
        socket_connect_timeout=5,
        socket_timeout=5
    )
    redis_conn.ping()
    print(f"✅ Redis connected for Flask integration: {REDIS_HOST}:{REDIS_PORT}")
    flask_integration_enabled = True
except Exception as e:
    print(f"⚠️ Redis connection failed: {e}")
    print("Dashboard will run in standalone mode")

# Initialize connections (similar to init_connections)
def init_connections():
    es_client = None
    minio_client = None
    if Elasticsearch is not None:
        try:
            es_client = Elasticsearch(ELASTICSEARCH_HOST)
            # quick ping
            if hasattr(es_client, "ping") and not es_client.ping():
                # not reachable - leave as None but log
                es_client = None
        except Exception:
            es_client = None
    if Minio is not None:
        try:
            minio_client = Minio(MINIO_ENDPOINT,
                                 access_key=MINIO_ROOT_USER,
                                 secret_key=MINIO_ROOT_PASSWORD,
                                 secure=False)
        except Exception:
            minio_client = None
    return es_client, minio_client

es, minio_client = init_connections()

# Helper: serialize timestamps
def now_iso():
    return datetime.now().isoformat()

class FlaskEventListener:
    """Listens to Redis events from Flask app"""
    
    def __init__(self, redis_client):
        self.redis = redis_client
        self.running = False
        self.thread = None
        
    def start(self):
        if not self.redis or self.running:
            return
        self.running = True
        self.thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.thread.start()
        print("🎧 Started listening for Flask app events")
        
    def stop(self):
        self.running = False
        if self.thread:
            self.thread.join(timeout=2)
            
    def _listen_loop(self):
        """Listen for Redis pub/sub events from Flask app"""
        try:
            pubsub = self.redis.pubsub()
            pubsub.subscribe('search_events')
            
            for message in pubsub.listen():
                if not self.running:
                    break
                    
                if message['type'] == 'message':
                    try:
                        event_data = json.loads(message['data'])
                        self._handle_flask_event(event_data)
                    except Exception as e:
                        print(f"Error processing Flask event: {e}")
                        
        except Exception as e:
            print(f"Redis listener error: {e}")
            
    def _handle_flask_event(self, event_data):
        """Process events from Flask app and add to dashboard logs"""
        event_type = event_data.get('event')
        search_id = event_data.get('search_id')
        timestamp = event_data.get('timestamp', now_iso())
        
        with STATE_LOCK:
            if event_type == 'search_start':
                # Add initial search log entry
                search_logs.append({
                    'search_id': search_id,
                    'timestamp': timestamp,
                    'stage': 'Query Received',
                    'query': event_data.get('query', ''),
                    'details': f"🔍 Real search from Flask app: '{event_data.get('query', '')}'",
                    'status': 'processing',
                    'source': 'flask_app',
                    'user_ip': event_data.get('ip_address', 'Unknown')
                })
                
            elif event_type == 'search_stage':
                # Map Flask stages to dashboard display
                stage_mapping = {
                    'web_search': 'Web Crawling',
                    'academic_search': 'Elasticsearch Search', 
                    'ai_processing': 'AI Analysis',
                    'passage_search': 'Content Extraction'
                }
                
                stage = event_data.get('stage', 'Unknown')
                display_stage = stage_mapping.get(stage, stage.replace('_', ' ').title())
                status = event_data.get('status', 'processing')
                
                details = event_data.get('details', f"{display_stage} in progress...")
                if 'results_count' in event_data:
                    details += f" ({event_data['results_count']} results)"
                if 'search_time' in event_data:
                    details += f" in {event_data['search_time']}s"
                
                search_logs.append({
                    'search_id': search_id,
                    'timestamp': timestamp,
                    'stage': display_stage,
                    'query': event_data.get('query', ''),
                    'details': details,
                    'status': status,
                    'source': 'flask_app',
                    'metrics': {
                        'results': event_data.get('results_count', 0),
                        'time': event_data.get('search_time', 0)
                    }
                })
                
                # If it's AI processing, also add to AI logs
                if stage == 'ai_processing':
                    ai_processing_logs.append({
                        'search_id': search_id,
                        'timestamp': timestamp,
                        'stage': 'AI Answer Generation',
                        'query': event_data.get('query', ''),
                        'details': details,
                        'status': status,
                        'metrics': event_data.get('metrics', {})
                    })
                
            elif event_type == 'search_complete':
                # Final completion log
                search_logs.append({
                    'search_id': search_id,
                    'timestamp': timestamp,
                    'stage': 'Search Complete',
                    'query': event_data.get('query', ''),
                    'details': f"✅ Search completed in {event_data.get('total_time', 0)}s with {event_data.get('total_results', 0)} total results",
                    'status': 'completed',
                    'source': 'flask_app',
                    'metrics': {
                        'total_time': event_data.get('total_time', 0),
                        'total_results': event_data.get('total_results', 0)
                    }
                })
                
            elif event_type == 'search_failed':
                # Error log
                search_logs.append({
                    'search_id': search_id,
                    'timestamp': timestamp,
                    'stage': 'Search Failed',
                    'query': event_data.get('query', ''),
                    'details': f"❌ Error: {event_data.get('error', 'Unknown error')}",
                    'status': 'error',
                    'source': 'flask_app'
                })

# Initialize Flask event listener
flask_listener = None
if flask_integration_enabled:
    flask_listener = FlaskEventListener(redis_conn)
    flask_listener.start()

# System monitoring function
def get_system_metrics_once():
    """Return a dict of system metrics (serializable)."""
    if psutil is None:
        return {
            "timestamp": now_iso(),
            "error": "psutil not installed"
        }
    try:
        cpu_percent = psutil.cpu_percent(interval=0.5)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        return {
            "timestamp": now_iso(),
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_used_gb": round(memory.used / (1024 ** 3), 2),
            "memory_total_gb": round(memory.total / (1024 ** 3), 2),
            "disk_percent": disk.percent,
            "disk_used_gb": round(disk.used / (1024 ** 3), 2),
            "disk_total_gb": round(disk.total / (1024 ** 3), 2)
        }
    except Exception as e:
        return {"timestamp": now_iso(), "error": str(e)}

# The main simulation ported from your Streamlit simulate_search_process
def simulate_search_process(query: str):
    """Simulate and append logs for a search (runs in background)."""
    search_id = f"sim_search_{int(time.time()*1000)}_{random.randint(0,999)}"
    # Stage 1: Query Analysis
    with STATE_LOCK:
        search_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Query Analysis',
            'query': query,
            'details': f"Analyzing query: '{query}' - {len(query.split()) if query else 0} terms detected",
            'status': 'processing',
            'source': 'simulation'
        })

    time.sleep(0.5)

    # Stage 2: Elasticsearch Search (attempt)
    try:
        if es:
            t0 = time.time()
            # Use a safe call if API differs
            try:
                es_result = es.search(index="academic-papers", query={
                    "multi_match": {
                        "query": query,
                        "fields": ["title^3", "abstract", "authors"]
                    }
                })
                hits = es_result.get('hits', {}).get('total', {}).get('value', 0) if isinstance(es_result.get('hits', {}).get('total'), dict) else es_result.get('hits', {}).get('total', 0)
            except Exception:
                # fallback if older ES client
                es_result = es.search(index="academic-papers", body={
                    "query": {"multi_match": {"query": query, "fields": ["title^3", "abstract", "authors"]}}
                })
                hits = es_result.get('hits', {}).get('total', {}).get('value', 0) if isinstance(es_result.get('hits', {}).get('total'), dict) else es_result.get('hits', {}).get('total', 0)
            es_time = time.time() - t0
            with STATE_LOCK:
                search_logs.append({
                    'search_id': search_id,
                    'timestamp': now_iso(),
                    'stage': 'Elasticsearch Search',
                    'query': query,
                    'details': f"Found {hits} papers in {es_time:.2f}s",
                    'status': 'completed',
                    'source': 'simulation',
                    'metrics': {'results': hits, 'time': round(es_time, 3)}
                })
        else:
            raise RuntimeError("Elasticsearch client not available")
    except Exception as e:
        with STATE_LOCK:
            search_logs.append({
                'search_id': search_id,
                'timestamp': now_iso(),
                'stage': 'Elasticsearch Search',
                'query': query,
                'details': f"Error: {str(e)}",
                'status': 'error',
                'source': 'simulation'
            })

    # Stage 3: Web Crawling Simulation
    crawlers = ['GeeksforGeeks', 'MathWorld', 'Engineering.com']
    for crawler in crawlers:
        crawl_start = time.time()
        with STATE_LOCK:
            search_logs.append({
                'search_id': search_id,
                'timestamp': now_iso(),
                'stage': f'Web Crawling - {crawler}',
                'query': query,
                'details': f"Searching {crawler}...",
                'status': 'processing',
                'source': 'simulation'
            })

        time.sleep(random.uniform(0.4, 1.6))  # simulate variable time

        results_count = random.randint(0, 20)
        crawl_time = time.time() - crawl_start

        with STATE_LOCK:
            search_logs.append({
                'search_id': search_id,
                'timestamp': now_iso(),
                'stage': f'Web Crawling - {crawler}',
                'query': query,
                'details': f"Found {results_count} results in {crawl_time:.2f}s",
                'status': 'completed' if results_count > 0 else 'no_results',
                'source': 'simulation',
                'metrics': {'results': results_count, 'time': round(crawl_time,3)}
            })
            crawler_stats[crawler].append({
                'timestamp': now_iso(),
                'query': query,
                'results': results_count,
                'time': round(crawl_time,3),
                'success': results_count > 0
            })

    # Stage 4: Content Extraction
    with STATE_LOCK:
        search_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Content Extraction',
            'query': query,
            'details': "Extracting full content from web articles...",
            'status': 'processing',
            'source': 'simulation'
        })
    time.sleep(random.uniform(1.0, 2.2))

    extracted_count = random.randint(5, 25)
    with STATE_LOCK:
        search_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Content Extraction',
            'query': query,
            'details': f"Successfully extracted content from {extracted_count} articles",
            'status': 'completed',
            'source': 'simulation',
            'metrics': {'extracted': extracted_count}
        })

    # Stage 5: AI Analysis (embedding + semantic)
    ai_start = time.time()
    with STATE_LOCK:
        ai_processing_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Embedding Generation',
            'query': query,
            'details': f"Generating embeddings for {extracted_count + 50} passages...",
            'status': 'processing'
        })
    time.sleep(random.uniform(1.5, 2.5))

    ai_time = time.time() - ai_start
    similarity_scores = np.random.beta(2, 5, 12).tolist()
    with STATE_LOCK:
        ai_processing_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Semantic Search',
            'query': query,
            'details': f"Ranked passages by similarity. Top score: {max(similarity_scores):.3f}",
            'status': 'completed',
            'metrics': {'processing_time': round(ai_time,3), 'top_score': round(float(max(similarity_scores)),3)}
        })

    # Stage 6: Answer Generation
    with STATE_LOCK:
        ai_processing_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Answer Generation',
            'query': query,
            'details': "Generating comprehensive answer using Mistral AI...",
            'status': 'processing'
        })
    time.sleep(random.uniform(2.0, 3.5))

    word_count = random.randint(150, 500)
    with STATE_LOCK:
        ai_processing_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Answer Generation',
            'query': query,
            'details': f"Generated {word_count} word answer",
            'status': 'completed',
            'metrics': {'word_count': word_count}
        })

    # Final stage
    total_time = time.time() - (ai_start - 8)
    with STATE_LOCK:
        search_logs.append({
            'search_id': search_id,
            'timestamp': now_iso(),
            'stage': 'Search Complete',
            'query': query,
            'details': f"Search completed successfully in {total_time:.1f}s",
            'status': 'completed',
            'source': 'simulation',
            'metrics': {'total_time': round(total_time,2)}
        })

# Endpoint: run a test search (POST)
@app.route("/api/run_search", methods=["POST"])
def api_run_search():
    payload = request.json or request.form
    query = payload.get("query", "") if payload else ""
    # Run in background
    executor.submit(simulate_search_process, query)
    return jsonify({"status": "started", "query": query})

# Endpoint: clear logs
@app.route("/api/clear_logs", methods=["POST"])
def api_clear_logs():
    with STATE_LOCK:
        search_logs.clear()
        ai_processing_logs.clear()
        crawler_stats.clear()
    return jsonify({"status": "cleared"})

# Endpoint: fetch recent search logs (paginated via query params)
@app.route("/api/search_logs")
def api_search_logs():
    with STATE_LOCK:
        logs = list(search_logs)
    # Return most recent first, add source info
    processed_logs = []
    for log in reversed(logs):
        processed_log = dict(log)
        # Add visual indicators for source
        if log.get('source') == 'flask_app':
            processed_log['source_indicator'] = '🔴 LIVE'
        else:
            processed_log['source_indicator'] = '🔵 SIM'
        processed_logs.append(processed_log)
    
    return jsonify({"logs": processed_logs})

# Endpoint: fetch AI logs
@app.route("/api/ai_logs")
def api_ai_logs():
    with STATE_LOCK:
        logs = list(ai_processing_logs)
    return jsonify({"ai_logs": list(reversed(logs))})

# Endpoint: fetch crawler stats
@app.route("/api/crawler_stats")
def api_crawler_stats():
    with STATE_LOCK:
        cs = {k: v[-50:] for k, v in crawler_stats.items()}
    return jsonify({"crawler_stats": cs})

# Endpoint: system metrics (append to history)
@app.route("/api/system_metrics", methods=["GET", "POST"])
def api_system_metrics():
    if request.method == "POST":
        metric = get_system_metrics_once()
        with STATE_LOCK:
            system_metrics.append(metric)
        return jsonify({"status": "ok", "metric": metric})
    else:
        # return last N metrics
        with STATE_LOCK:
            metrics = list(system_metrics)
        return jsonify({"metrics": metrics})

# Endpoint: fetch overview (dashboard summary)
@app.route("/api/overview")
def api_overview():
    with STATE_LOCK:
        recent = list(search_logs)[-50:]
        ai_logs_list = list(ai_processing_logs)[-50:]
        crawlers = {c: len(v) for c, v in crawler_stats.items()}
        metrics = list(system_metrics)[-50:]
        
        # Count live vs simulated searches
        live_searches = len([log for log in recent if log.get('source') == 'flask_app'])
        sim_searches = len([log for log in recent if log.get('source') == 'simulation'])
    
    overview = {
        "recent_search_count": len(recent),
        "live_search_count": live_searches,
        "simulation_count": sim_searches,
        "ai_log_count": len(ai_logs_list),
        "crawler_counts": crawlers,
        "system_metrics_count": len(metrics),
        "flask_integration": flask_integration_enabled,
        "redis_status": "connected" if redis_conn else "disconnected"
    }
    return jsonify(overview)

# SSE endpoint for real-time updates
@app.route('/events')
def sse_stream():
    """Server-Sent Events stream for real-time updates"""
    def event_stream():
        while True:
            # Send periodic updates
            try:
                with STATE_LOCK:
                    recent_logs = list(search_logs)[-5:]
                
                for log in recent_logs:
                    # Only send logs from the last 30 seconds
                    log_time = datetime.fromisoformat(log['timestamp'].replace('Z', '+00:00') if log['timestamp'].endswith('Z') else log['timestamp'])
                    if (datetime.now() - log_time.replace(tzinfo=None)).seconds < 30:
                        yield f"data: {json.dumps(log)}\n\n"
                
                time.sleep(2)  # Update every 2 seconds
                
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
                time.sleep(5)
    
    return Response(event_stream(), mimetype="text/plain")

# Optional background metrics poller when auto-refresh is toggled from UI
def metrics_poller(interval=5):
    while auto_refresh_enabled:
        metric = get_system_metrics_once()
        with STATE_LOCK:
            system_metrics.append(metric)
        time.sleep(interval)

# ----------------------------
# UPDATED UI with Flask integration status
# ----------------------------
PAGE_HTML = r'''
<!doctype html>
<html>
<head>
  <meta charset="utf-8"/>
  <title>🔍 Academic Search System Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
  <style>
    :root{
      --left-bg: #fff6f7;
      --panel-width: 320px;
      --muted: #6c757d;
      --rainbow: linear-gradient(90deg,#ff6b6b,#ffb86b,#ffd93d,#7bed9f,#4bc0ff,#b28bff);
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:Inter,Segoe UI,Roboto,Arial;background:#fff}
    /* Header */
    .topbar{display:flex;align-items:center;gap:20px;padding:18px 24px;border-bottom:1px solid #eee;flex-wrap:wrap}
    .title-left{display:flex;align-items:center;gap:12px}
    .logo-circle{width:60px;height:60px;border-radius:12px;background:var(--rainbow);display:flex;align-items:center;justify-content:center;color:#fff;font-weight:800;font-size:22px}
    .title-text{font-size:20px;font-weight:700;color:#111}
    .rainbow-title{font-size:48px;font-weight:900;letter-spacing:2px;background:var(--rainbow);-webkit-background-clip:text;background-clip:text;color:transparent;margin-left:12px}
    /* Flask integration status */
    .flask-status{margin-left:auto;padding:8px 12px;border-radius:8px;font-size:13px;font-weight:600}
    .flask-connected{background:#d4edda;color:#155724;border:1px solid #c3e6cb}
    .flask-disconnected{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb}
    /* Layout */
    .layout{display:grid;grid-template-columns:var(--panel-width) 1fr;min-height:calc(100vh - 120px);transition:all .22s ease}
    .layout.collapsed{grid-template-columns:70px 1fr}
    .left-panel{background:var(--left-bg);padding:28px;border-right:1px solid #f0e8e8;display:flex;flex-direction:column;gap:20px;overflow:hidden;transition:all .25s ease}
    .left-panel.collapsed { padding:12px 8px; }
    .left-panel .hide-on-collapse { transition:opacity .18s; }
    .left-panel.collapsed .hide-on-collapse { opacity:0; visibility:hidden; height:0; overflow:hidden; }
    .control-title{font-size:20px;font-weight:900;display:flex;align-items:center;gap:8px}
    .input-rounded{padding:14px 18px;border-radius:28px;border:0;background:linear-gradient(90deg,#eee,#f7f7f7);width:100%;outline:none;font-size:15px}
    .big-btn{padding:12px;border-radius:40px;border:0;cursor:pointer;font-weight:800;font-size:16px;background:linear-gradient(90deg,#ffd1ff,#fff3b0);box-shadow:0 6px 18px rgba(0,0,0,0.08)}
    .big-btn:active{transform:translateY(1px)}
    .toggle-row{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:6px 0}
    .small-note{font-size:13px;color:var(--muted)}
    .clear-btn{background:linear-gradient(90deg,#ffd3a5,#ff7ab6);color:#080; font-weight:800}
    /* Source indicators */
    .source-live{border-left:4px solid #dc3545 !important}
    .source-sim{border-left:4px solid #007bff !important}
    /* Tabs area */
    .tabs-row{border-bottom:1px solid #eee;padding:8px 20px;display:flex;gap:12px;flex-nowrap:wrap;align-items:left}
    .tab-pill{font-size:14.5px; position:relative;padding:13px 14px 10px;border-radius:20px;cursor:pointer;font-weight:800;display:inline-flex;gap:8px;align-items:center;justify-content:center;color:#333;transition:all .25s}
    .tab-pill::after{
      content:"";position:absolute;left:10%;right:10%;bottom:-10px;height:6px;border-radius:20px;opacity:0;transform:translateY(10px);transition:all .22s;
      background:var(--rainbow);
    }
    /* RAINBOW TEXT EFFECT on hover/active */
    .tab-pill:hover, .tab-pill.tab-active {
      color: transparent;
      background-image: var(--rainbow);
      -webkit-background-clip: text;
      background-clip: text;
      transform: translateY(-4px);
    }
    .tab-pill:hover::after, .tab-pill.tab-active::after { opacity:1; transform:translateY(0); }
    .tab-pill:hover { text-decoration:none; }
    .tab-active{ color:#111;}
    /* content area */
    .content{padding:18px}
    .grid-two{display:grid;grid-template-columns:2fr 1fr;gap:18px}
    .card{background:#fff;padding:14px;border-radius:12px;box-shadow:0 6px 18px rgba(10,10,10,0.04)}
    .metric{font-weight:800;font-size:20px}
    .log-item{padding:10px;border-radius:10px;margin-bottom:8px;background:#fbfbfb;border-left:6px solid #eee}
    .status-processing{border-left-color:#ffc107}
    .status-completed{border-left-color:#28a745}
    .status-error{border-left-color:#dc3545}
    .smallmono{font-family:monospace;font-size:12px;color:var(--muted)}
    /* toggle control pill (collapsed) */
    .collapse-btn{position:absolute;left:var(--panel-width);top:140px;width:28px;height:28px;left:280px; border-radius:8px;background:#fff;border:1px solid #eee;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 6px 18px rgba(0,0,0,0.06);transition:left .22s}
    .layout.collapsed .collapse-btn{left:35px}
    /* responsiveness */
    @media (max-width: 1100px){
      :root{--panel-width:300px}
      .rainbow-title{font-size:40px}
    }
    @media (max-width: 760px){
      .layout{grid-template-columns:1fr}
      .left-panel{order:2;border-right:0;border-top:1px solid #eee}
      .tabs-row{overflow-x:auto;padding-left:12px}
      .rainbow-title{font-size:28px}
      .collapse-btn{display:none}
    }
  </style>
</head>
<body>
  <div class="topbar">
    <div class="title-left">
      <div class="logo-circle">🔍</div>
      <div>
        <div class="title-text">Academic Search System</div>
        <div class="rainbow-title">DASHBOARD</div>
      </div>
    </div>
    <div id="flaskStatus" class="flask-status flask-disconnected">Flask App: Checking...</div>
    <div style="margin-right:12px; padding:50px 0px 10px 10px;" class="smallmono">Server: Flask • Port: 8502</div>
    <!-- Control Panel toggle (visible on wide screens) -->
    <button id="panelToggle" style="margin-left:auto;padding:8px 12px;border-radius:10px;border:0;background:#fff;box-shadow:0 6px 18px rgba(0,0,0,0.06);cursor:pointer">Toggle Panel</button>
  </div>

  <div id="mainLayout" class="layout">
    <!-- LEFT PANEL -->
    <div id="leftPanel" class="left-panel">
      <div>
      <div class="collapse-btn" id="collapseHandle" title="Toggle control panel">☰</div>
        <div class="control-title">🧭 <span class="hide-on-collapse">Control Panel</span></div>
        <div class="smallmono hide-on-collapse" style="opacity:0.9">Test Search Process</div>
      </div>

      <div>
        <label class="smallmono hide-on-collapse">Enter test query:</label>
        <input id="testQuery" class="input-rounded hide-on-collapse" placeholder="What would you like to search for?" />
        <div style="height:12px"></div>
        <button id="runTestBtn" class="big-btn" style="width:100%">🚀 <span class="hide-on-collapse">Run Test Search</span></button>
      </div>

      <div class="hide-on-collapse">
        <div class="smallmono" style="margin-bottom:8px">📡 Integration Status</div>
        <div id="integrationStatus" class="smallmono" style="padding:8px;background:#f8f9fa;border-radius:6px">
          Flask App: <span id="flaskStatusText">Checking...</span><br>
          Redis: <span id="redisStatusText">Checking...</span><br>
          Live Events: <span id="liveEventsText">Initializing...</span>
        </div>
      </div>

      <div class="toggle-row hide-on-collapse">
        <div class="smallmono">🔄 Auto Refresh (5s)</div>
        <label style="display:inline-flex;align-items:center;gap:6px"><input id="autoToggle" type="checkbox"/> </label>
      </div>

      <div class="toggle-row hide-on-collapse">
        <div class="smallmono">📊 Collect System Metrics</div>
        <label style="display:inline-flex;align-items:center;gap:6px"><input id="collectToggle" type="checkbox"/> </label>
      </div>

      <div>
        <button id="updateMetricsBtn" class="big-btn hide-on-collapse" style="width:100%;margin-top:6px">📈 Update Metrics Now</button>
      </div>

      <div>
        <button id="clearAllBtn" class="big-btn clear-btn hide-on-collapse" style="width:100%;margin-top:10px">🗑️ Clear All Logs</button>
      </div>

      <div style="margin-top:12px" class="hide-on-collapse">
        <div class="smallmono">Connections</div>
        <div class="smallmono" id="connStatus">ES: checking... • MinIO: checking...</div>
      </div>

    </div>

    <!-- collapse handle (desktop) -->
    

    <!-- RIGHT / MAIN -->
    <div>
      <div class="tabs-row" id="tabsRow">
        <div class="tab-pill tab-active" data-tab="tab1">🔍 Live Search Process</div>
        <div class="tab-pill" data-tab="tab2">🕷️ Crawler Analytics</div>
        <div class="tab-pill" data-tab="tab3">🧠 AI Processing</div>
        <div class="tab-pill" data-tab="tab4">📊 System Performance</div>
        <div class="tab-pill" data-tab="tab5">📈 Search Analytics</div>
        <div class="tab-pill" data-tab="tab6">⚙️ Algorithm Details</div>
      </div>

      <div class="content">
        <div id="tab1" class="tab-content active">
          <div class="grid-two">
            <div>
              <div class="card">
                <h5>📋 Live Search Log</h5>
                <div style="margin-bottom:10px;font-size:12px;color:#666">
                  🔴 LIVE = Real searches from Flask app | 🔵 SIM = Test simulations
                </div>
                <div id="liveLogs" style="margin-top:10px;max-height:520px;overflow:auto"></div>
              </div>
            </div>
            <div>
              <div class="card">
                <div>✅ Completed: <span id="completedCount">0</span></div>
                <div>🔄 Processing: <span id="processingCount">0</span></div>
                <div>❌ Errors: <span id="errorCount">0</span></div>
                <div>🔴 Live Searches: <span id="liveSearchCount">0</span></div>
                <div>🔵 Simulations: <span id="simSearchCount">0</span></div>
                <hr/>
                <div class="smallmono">Recent Queries</div>
                <pre id="recentQueries" class="smallmono" style="white-space:pre-wrap;"></pre>
              </div>
            </div>
          </div>
        </div>

        <div id="tab2" class="tab-content" style="display:none">
          <div class="card">
            <h5>🕷️ Crawler Analytics</h5>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px">
              <div style="flex:1;min-width:280px"><div id="crawlerSuccessChart" style="height:280px"></div></div>
              <div style="flex:1;min-width:280px"><div id="crawlerTimeChart" style="height:280px"></div></div>
            </div>
            <div id="crawlerTable" style="margin-top:12px"></div>
          </div>
        </div>

        <div id="tab3" class="tab-content" style="display:none">
          <div class="card">
            <h5>🧠 AI Processing</h5>
            <div id="aiLogs" style="margin-top:10px;max-height:500px;overflow:auto"></div>
          </div>
        </div>

        <div id="tab4" class="tab-content" style="display:none">
          <div class="card">
            <h5>📊 System Performance</h5>
            <div id="systemPerf" style="height:360px;margin-top:10px"></div>
          </div>
        </div>

        <div id="tab5" class="tab-content" style="display:none">
          <div class="card">
            <h5>📈 Search Analytics</h5>
            <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px">
              <div style="flex:1;min-width:260px"><div id="searchHourChart" style="height:240px"></div></div>
              <div style="flex:1;min-width:260px"><div id="stageSuccessChart" style="height:240px"></div></div>
            </div>
            <div style="margin-top:12px">
              <div>Total Queries: <span id="totalQueries">0</span></div>
              <div>Unique Queries: <span id="uniqueQueries">0</span></div>
              <div>Avg Query Length: <span id="avgQueryLen">0.0</span></div>
              <div id="commonQueries" style="margin-top:8px"></div>
            </div>
          </div>
        </div>

        <div id="tab6" class="tab-content" style="display:none">
          <div class="card">
            <h5>⚙️ Algorithm Details</h5>
            <pre style="background:#fafafa;padding:12px;border-radius:8px;color:#111">
1. Query Analysis
   ├── Tokenization
   ├── Stop word removal
   └── Term expansion

2. Multi-Source Search
   ├── Academic Papers (Elasticsearch)
   ├── Web Crawling (GeeksforGeeks, MathWorld, Engineering.com)
   └── Content Extraction

3. AI Processing
   ├── Embedding Generation (Sentence Transformers)
   ├── Semantic Similarity Search
   ├── Relevance Ranking
   └── Answer Generation (Mistral AI)
            </pre>
          </div>
        </div>

      </div>
    </div>
  </div>

  <!-- Auto-refresh badge -->
  <div id="autoBadge" style="display:none;position:fixed;top:12px;right:12px;background:#28a745;color:#fff;padding:6px 10px;border-radius:16px;font-size:13px;z-index:9999;">
    🔄 Auto-refreshing...
  </div>

  <!-- Live events badge -->
  <div id="liveBadge" style="display:none;position:fixed;top:52px;right:12px;background:#dc3545;color:#fff;padding:6px 10px;border-radius:16px;font-size:13px;z-index:9999;">
    🔴 Live Events Active
  </div>

  <script>
    const pollIntervalMs = 3000;
    let pollTimer = null;
    let flaskIntegrationEnabled = false;
    let eventSource = null;

    // Tab switching with rainbow active style
    document.querySelectorAll('.tab-pill').forEach(p=>{
      p.addEventListener('click', (e)=>{
        document.querySelectorAll('.tab-pill').forEach(x=>x.classList.remove('tab-active'));
        p.classList.add('tab-active');
        const tab = p.getAttribute('data-tab');
        document.querySelectorAll('.tab-content').forEach(c=>c.style.display='none');
        document.getElementById(tab).style.display = 'block';
      });
    });

    // Panel toggle handlers
    const mainLayout = document.getElementById('mainLayout');
    const leftPanel = document.getElementById('leftPanel');
    document.getElementById('panelToggle').addEventListener('click', ()=>{
      mainLayout.classList.toggle('collapsed');
      leftPanel.classList.toggle('collapsed');
    });
    document.getElementById('collapseHandle').addEventListener('click', ()=>{
      mainLayout.classList.toggle('collapsed');
      leftPanel.classList.toggle('collapsed');
    });

    async function fetchOverview(){
      try {
        const r = await fetch('/api/overview'); 
        const j = await r.json();
        
        document.getElementById('completedCount').innerText = j.recent_search_count || 0;
        document.getElementById('liveSearchCount').innerText = j.live_search_count || 0;
        document.getElementById('simSearchCount').innerText = j.simulation_count || 0;
        
        // Update integration status
        flaskIntegrationEnabled = j.flask_integration || false;
        updateIntegrationStatus(flaskIntegrationEnabled, j.redis_status || 'disconnected');
      } catch(e) {
        console.error('Failed to fetch overview:', e);
        updateIntegrationStatus(false, 'error');
      }
    }

    function updateIntegrationStatus(flaskEnabled, redisStatus) {
      const flaskStatusEl = document.getElementById('flaskStatus');
      const flaskStatusTextEl = document.getElementById('flaskStatusText');
      const redisStatusTextEl = document.getElementById('redisStatusText');
      const liveEventsTextEl = document.getElementById('liveEventsText');
      
      if (flaskEnabled && redisStatus === 'connected') {
        flaskStatusEl.className = 'flask-status flask-connected';
        flaskStatusEl.textContent = 'Flask App: Connected ✅';
        flaskStatusTextEl.textContent = 'Connected ✅';
        redisStatusTextEl.textContent = 'Connected ✅';
        liveEventsTextEl.textContent = 'Active 🔴';
        document.getElementById('liveBadge').style.display = 'block';
      } else {
        flaskStatusEl.className = 'flask-status flask-disconnected';
        flaskStatusEl.textContent = 'Flask App: Disconnected ❌';
        flaskStatusTextEl.textContent = 'Disconnected ❌';
        redisStatusTextEl.textContent = redisStatus === 'connected' ? 'Connected ✅' : 'Disconnected ❌';
        liveEventsTextEl.textContent = 'Inactive ⚫';
        document.getElementById('liveBadge').style.display = 'none';
      }
    }

    async function fetchConnections(){
      try{
        await fetch('/api/overview');
        document.getElementById('connStatus').innerText = 'ES: configured • MinIO: configured';
      }catch(e){
        document.getElementById('connStatus').innerText = 'ES: not reachable • MinIO: not reachable';
      }
    }

    async function fetchLogs(){
      const res = await fetch('/api/search_logs'); const data = await res.json();
      const logs = data.logs || [];
      const area = document.getElementById('liveLogs');
      area.innerHTML = '';
      const slice = logs.slice(0, 100);
      for(let log of slice){
        const div = document.createElement('div');
        let statusClass = 'log-item ';
        if(log.status === 'processing') statusClass += 'status-processing';
        else if(log.status === 'completed') statusClass += 'status-completed';
        else if(log.status === 'error') statusClass += 'status-error';
        
        // Add source-specific styling
        if(log.source === 'flask_app') statusClass += ' source-live';
        else statusClass += ' source-sim';
        
        div.className = statusClass;
        const t = new Date(log.timestamp).toLocaleTimeString();
        const sourceIndicator = log.source_indicator || '🔵 SIM';
        div.innerHTML = `
          <div class="smallmono">${t} | ${log.search_id} ${sourceIndicator}</div>
          <div style="font-weight:700">${log.stage}</div>
          <div style="color:#666;margin-top:6px">${log.details}</div>
        `;
        area.appendChild(div);
      }
      const recent = slice.slice(0,50);
      const completed = recent.filter(x=>x.status==='completed').length;
      const processing = recent.filter(x=>x.status==='processing').length;
      const error = recent.filter(x=>x.status==='error').length;
      document.getElementById('completedCount').innerText = completed;
      document.getElementById('processingCount').innerText = processing;
      document.getElementById('errorCount').innerText = error;
      const uq = [...new Set(recent.map(x=>x.query).filter(Boolean))].slice(-5).reverse().join('\n');
      document.getElementById('recentQueries').innerText = uq || '—';
    }

    async function fetchAI(){
      const res = await fetch('/api/ai_logs'); const data = await res.json();
      const logs = data.ai_logs || [];
      const area = document.getElementById('aiLogs');
      area.innerHTML = '';
      for(let l of logs.slice(0,50)){
        const div = document.createElement('div');
        div.className = 'log-item';
        const t = new Date(l.timestamp).toLocaleTimeString();
        div.innerHTML = `<div style="display:flex;justify-content:space-between"><strong>🧠 ${l.stage}</strong><small class="smallmono">${t}</small></div><div style="margin-top:6px;color:#555">${l.details}</div><div class="smallmono">Query: "${l.query}"</div>`;
        area.appendChild(div);
      }
    }

    async function fetchCrawler(){
      const res = await fetch('/api/crawler_stats'); const data = await res.json();
      const cs = data.crawler_stats || {};
      const names = Object.keys(cs);
      if(!names.length){
        document.getElementById('crawlerSuccessChart').innerHTML = '<div class="smallmono">No crawler data</div>';
        document.getElementById('crawlerTimeChart').innerHTML = '';
        document.getElementById('crawlerTable').innerHTML = '';
        return;
      }
      const success = names.map(n => {
        const arr = cs[n];
        const succ = arr.filter(x=>x.success).length;
        return arr.length ? Math.round((succ/arr.length)*100) : 0;
      });
      Plotly.newPlot('crawlerSuccessChart', [{x:names,y:success,type:'bar'}], {margin:{t:30}});
      const avgTimes = names.map(n => {
        const arr = cs[n]; if(!arr.length) return 0;
        const avg = arr.reduce((s,x)=>s + (x.time||0),0) / arr.length; return Math.round(avg*100)/100;
      });
      Plotly.newPlot('crawlerTimeChart', [{x:names,y:avgTimes,type:'bar'}], {margin:{t:30}});
      let html = '<table style="width:100%;border-collapse:collapse"><thead><tr style="background:#fafafa"><th style="padding:8px">Crawler</th><th>Searches</th><th>Total Results</th><th>Avg Results</th><th>Min Time</th><th>Max Time</th><th>Last</th></tr></thead><tbody>';
      for(let n of names){
        const arr = cs[n]; if(!arr.length) continue;
        const totalResults = arr.reduce((s,x)=>s + (x.results||0),0);
        const avgResults = (totalResults/arr.length).toFixed(1);
        const maxRes = Math.max(...arr.map(x=>x.results));
        const times = arr.map(x=>x.time); const minT = (Math.min(...times)||0).toFixed(2); const maxT = (Math.max(...times)||0).toFixed(2);
        const last = new Date(arr[arr.length-1].timestamp).toLocaleTimeString();
        html += `<tr><td style="padding:8px">${n}</td><td>${arr.length}</td><td>${totalResults}</td><td>${avgResults}</td><td>${minT}s</td><td>${maxT}s</td><td>${last}</td></tr>`;
      }
      html += '</tbody></table>';
      document.getElementById('crawlerTable').innerHTML = html;
    }

    async function fetchSystem(){
      const res = await fetch('/api/system_metrics'); const data = await res.json();
      const metrics = data.metrics || [];
      if(!metrics.length) return;
      const times = metrics.map(m=>new Date(m.timestamp).toLocaleTimeString());
      const cpu = metrics.map(m=>m.cpu_percent||0); const mem = metrics.map(m=>m.memory_percent||0); const disk = metrics.map(m=>m.disk_percent||0);
      Plotly.newPlot('systemPerf',[{x:times,y:cpu,mode:'lines+markers',name:'CPU %'},{x:times,y:mem,mode:'lines+markers',name:'Memory %'},{x:times,y:disk,mode:'lines+markers',name:'Disk %'}], {margin:{t:30}});
    }

    async function fetchSearchAnalytics(){
      const res = await fetch('/api/search_logs'); const data = await res.json();
      const logs = data.logs || [];
      if(!logs.length) return;
      const hours = {};
      const byStage = {};
      const queries = [];
      for(let l of logs){
        const d = new Date(l.timestamp); hours[d.getHours()] = (hours[d.getHours()]||0)+1;
        const stg = l.stage || 'unknown'; byStage[stg] = byStage[stg] || {completed:0,error:0};
        if(l.status==='completed') byStage[stg].completed++; if(l.status==='error') byStage[stg].error++;
        if(l.query) queries.push(l.query);
      }
      const hourLabels = Object.keys(hours).sort((a,b)=>a-b); const hourCounts = hourLabels.map(h=>hours[h]);
      Plotly.newPlot('searchHourChart', [{x:hourLabels,y:hourCounts,type:'bar'}], {margin:{t:20}});
      const stages = Object.keys(byStage);
      const successRates = stages.map(s=>{
        const c = byStage[s].completed, e = byStage[s].error; const denom = (c+e)||1;
        return Math.round((c/denom)*10000)/100;
      });
      Plotly.newPlot('stageSuccessChart', [{x:stages,y:successRates,type:'bar'}], {margin:{t:20},height:240});
      const totalQ = queries.length; const uniqueQ = new Set(queries).size;
      const avgLen = totalQ ? (queries.map(q=>q.split(/\s+/).length).reduce((a,b)=>a+b,0)/totalQ).toFixed(1) : '0.0';
      document.getElementById('totalQueries').innerText = totalQ; document.getElementById('uniqueQueries').innerText = uniqueQ; document.getElementById('avgQueryLen').innerText = avgLen;
      const c = {}; for(let q of queries) c[q] = (c[q]||0)+1;
      const pairs = Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,6);
      document.getElementById('commonQueries').innerHTML = pairs.map(p=>`<div>${p[0]} <span style="color:#888">(${p[1]})</span></div>`).join('');
    }

    async function refreshAll(){
      await fetchOverview();
      await fetchLogs();
      await fetchAI();
      await fetchCrawler();
      await fetchSystem();
      await fetchSearchAnalytics();
      await fetchConnections();
    }

    function startPolling(){ 
      if(pollTimer) clearInterval(pollTimer); 
      pollTimer = setInterval(refreshAll, pollIntervalMs); 
      refreshAll(); 
      document.getElementById('autoBadge').style.display='block'; 
    }
    
    function stopPolling(){ 
      if(pollTimer) clearInterval(pollTimer); 
      pollTimer=null; 
      document.getElementById('autoBadge').style.display='none'; 
    }

    // Initialize real-time event streaming
    function initEventStream() {
      if (eventSource) {
        eventSource.close();
      }
      
      eventSource = new EventSource('/events');
      
      eventSource.onmessage = function(event) {
        try {
          const data = JSON.parse(event.data);
          if (data.error) {
            console.error('SSE Error:', data.error);
            return;
          }
          
          // Handle real-time log updates
          if (data.search_id && data.stage) {
            console.log('Real-time event:', data);
            // Force refresh of logs to show new data
            fetchLogs();
          }
        } catch (e) {
          console.error('Error parsing SSE data:', e);
        }
      };
      
      eventSource.onerror = function(event) {
        console.log('SSE connection error, will retry...');
      };
    }

    document.addEventListener('DOMContentLoaded', ()=>{
      // Initialize event stream for real-time updates
      initEventStream();
      
      // Start auto-polling
      startPolling();

      document.getElementById('runTestBtn').addEventListener('click', async ()=>{
        const q = document.getElementById('testQuery').value || 'machine learning';
        document.getElementById('runTestBtn').disabled = true;
        await fetch('/api/run_search', {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({query:q})});
        setTimeout(()=>document.getElementById('runTestBtn').disabled = false, 700);
      });

      document.getElementById('clearAllBtn').addEventListener('click', async ()=>{
        if(!confirm('Clear all logs?')) return;
        await fetch('/api/clear_logs', {method:'POST'});
        refreshAll();
      });

      document.getElementById('updateMetricsBtn').addEventListener('click', async ()=>{
        await fetch('/api/system_metrics', {method:'POST'});
        fetchSystem();
      });

      document.getElementById('autoToggle').addEventListener('change', (e)=>{
        if(e.target.checked) startPolling(); else stopPolling();
      });
      
      // Auto-toggle is on by default
      document.getElementById('autoToggle').checked = true;

      document.getElementById('collectToggle').addEventListener('change', (e)=>{
        if(e.target.checked) fetch('/api/system_metrics', {method:'POST'});
      });
    });
  </script>
</body>
</html>'''

@app.route('/')
def index():
    return render_template_string(PAGE_HTML)

if __name__ == '__main__':
    # Pre-populate system metrics history a bit
    for _ in range(6):
        system_metrics.append(get_system_metrics_once())
        time.sleep(0.05)
    
    print("🚀 Dashboard started with Flask integration support")
    print(f"📡 Redis integration: {'Enabled' if flask_integration_enabled else 'Disabled'}")
    print("🔍 Dashboard will display real searches from Flask app when connected")
    
    # Run Flask
    app.run(host='0.0.0.0', port=8502, debug=True)