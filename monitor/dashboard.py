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
import queue


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
search_logs = deque(maxlen=200)  # each entry: dict
system_metrics = deque(maxlen=200)  # list of dicts
crawler_stats = defaultdict(list)  # crawler -> list of stats dicts
ai_processing_logs = deque(maxlen=100)  # list of dicts
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

class ImprovedFlaskEventListener:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.running = False
        self.pubsub_thread = None
        self.stream_thread = None
        
    def start(self):
        if not self.redis or self.running:
            return
        
        self.running = True
        
        # Start pub/sub listener for real-time events
        self.pubsub_thread = threading.Thread(target=self._pubsub_loop, daemon=True)
        self.pubsub_thread.start()
        
        # Start stream reader for historical events
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()
        
        print("Started listening for Flask app events (pub/sub + stream)")
        
    def stop(self):
        self.running = False
        if self.pubsub_thread:
            self.pubsub_thread.join(timeout=2)
        if self.stream_thread:
            self.stream_thread.join(timeout=2)
    
    # Replace your ImprovedFlaskEventListener class with this improved version:

class ImprovedFlaskEventListener:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.running = False
        self.pubsub_thread = None
        self.stream_thread = None
        self.last_reconnect_attempt = 0
        self.reconnect_delay = 1  # Start with 1 second delay
        
    def start(self):
        if not self.redis or self.running:
            return
        
        self.running = True
        
        # Start pub/sub listener for real-time events
        self.pubsub_thread = threading.Thread(target=self._pubsub_loop, daemon=True)
        self.pubsub_thread.start()
        
        # Start stream reader for historical events
        self.stream_thread = threading.Thread(target=self._stream_loop, daemon=True)
        self.stream_thread.start()
        
        print("Started listening for Flask app events (pub/sub + stream)")
        
    def stop(self):
        self.running = False
        if self.pubsub_thread:
            self.pubsub_thread.join(timeout=2)
        if self.stream_thread:
            self.stream_thread.join(timeout=2)
    
    def _pubsub_loop(self):
        """Listen for real-time pub/sub events with robust error handling"""
        while self.running:
            try:
                # Create a new pubsub connection for each attempt
                pubsub = self.redis.pubsub()
                pubsub.subscribe('search_events')
                
                print("Pub/sub listener connected to Redis")
                
                # Listen with timeout and handle connection properly
                while self.running:
                    try:
                        # Use get_message with timeout instead of listen()
                        message = pubsub.get_message(timeout=10.0, ignore_subscribe_messages=True)
                        
                        if message and message['type'] == 'message':
                            try:
                                event_data = json.loads(message['data'])
                                self._handle_flask_event(event_data)
                                self._broadcast_sse_event(event_data)
                            except Exception as e:
                                print(f"Error processing Flask event: {e}")
                                
                        # Reset reconnect delay on successful operation
                        self.reconnect_delay = 1
                        
                    except redis.exceptions.TimeoutError:
                        # This is expected - just continue the loop
                        continue
                    except redis.exceptions.ConnectionError as e:
                        print(f"Redis connection error in pub/sub: {e}")
                        break
                    except Exception as e:
                        print(f"Unexpected error in pub/sub: {e}")
                        break
                
                # Close the pubsub connection before reconnecting
                try:
                    pubsub.close()
                except:
                    pass
                    
            except redis.exceptions.ConnectionError as e:
                print(f"Failed to create pub/sub connection: {e}")
            except Exception as e:
                print(f"Unexpected error in pub/sub setup: {e}")
            
            # Exponential backoff for reconnection
            if self.running:
                current_time = time.time()
                if current_time - self.last_reconnect_attempt >= self.reconnect_delay:
                    print(f"Reconnecting pub/sub in {self.reconnect_delay}s...")
                    time.sleep(self.reconnect_delay)
                    self.reconnect_delay = min(self.reconnect_delay * 2, 60)  # Cap at 60 seconds
                    self.last_reconnect_attempt = current_time

    def _stream_loop(self):
        """Stream reader with improved error handling"""
        last_id = "0"
        reconnect_delay = 1
        
        while self.running:
            try:
                # Read new events from stream
                streams = self.redis.xread(
                    {"search_stream": last_id}, 
                    count=10, 
                    block=5000  # 5 second timeout
                )
                
                if streams:
                    for stream_data in streams:
                        # stream_data is a tuple: (stream_name, messages)
                        stream_name, messages = stream_data
                        for message in messages:
                            # message is a tuple: (message_id, fields_dict)
                            message_id, fields = message
                            try:
                                # Convert Redis fields to event data
                                event_data = dict(fields)
                                self._handle_flask_event(event_data)
                                last_id = message_id
                            except Exception as e:
                                print(f"Error processing stream event: {e}")
                
                # Reset reconnect delay on successful operation
                reconnect_delay = 1
            except redis.exceptions.TimeoutError:
                # This is expected - just continue the loop
                continue
            except redis.exceptions.ConnectionError as e:
                print(f"Redis connection error in stream reader: {e}")
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)  # Exponential backoff
            except Exception as e:
                print(f"Stream reader error: {e}")
                time.sleep(reconnect_delay)
                reconnect_delay = min(reconnect_delay * 2, 60)


    def _stream_loop(self):
      last_id = "0"
      while self.running:
          try:
              # Read new events from stream
              streams = self.redis.xread(
                  {"search_stream": last_id}, 
                  count=10, 
                  block=5000  # 5 second timeout
              )
              
              if streams:
                  for stream_data in streams:
                      # stream_data is a tuple: (stream_name, messages)
                      stream_name, messages = stream_data
                      for message in messages:
                          # message is a tuple: (message_id, fields_dict)
                          message_id, fields = message
                          try:
                              # Convert Redis fields to event data
                              event_data = dict(fields)
                              self._handle_flask_event(event_data)
                              last_id = message_id
                          except Exception as e:
                              print(f"Error processing stream event: {e}")
                              
          except redis.exceptions.TimeoutError:
              # This is expected - just continue the loop
              continue
          except redis.exceptions.ConnectionError as e:
              print(f"Redis connection error: {e}")
              time.sleep(10)  # Wait longer before retry
          except Exception as e:
              print(f"Stream reader error: {e}")
              time.sleep(5)  # Wait before retry
      
    def _broadcast_sse_event(self, event_data):
        """Broadcast event to SSE clients"""
        try:
            # Add to a global queue that SSE endpoint can read from
            if hasattr(app, 'sse_queue'):
                app.sse_queue.put_nowait(event_data)
        except Exception as e:
            print(f"SSE broadcast error: {e}")
    
    def _handle_flask_event(self, event_data):
      try:
          # Convert string values back to their original types
          processed_data = {}
          for key, value in event_data.items():
              if value == "true":
                  processed_data[key] = True
              elif value == "false":
                  processed_data[key] = False
              elif value == "null":
                  processed_data[key] = None
              elif value.isdigit():
                  processed_data[key] = int(value)
              elif value.replace('.', '', 1).isdigit() and value.count('.') < 2:
                  processed_data[key] = float(value)
              elif value.startswith('[') and value.endswith(']'):
                  try:
                      processed_data[key] = json.loads(value)
                  except:
                      processed_data[key] = value
              elif value.startswith('{') and value.endswith('}'):
                  try:
                      processed_data[key] = json.loads(value)
                  except:
                      processed_data[key] = value
              else:
                  processed_data[key] = value
          
          # Now process with the converted data
          event_type = processed_data.get('event')
          search_id = processed_data.get('search_id')
          timestamp = processed_data.get('timestamp', now_iso())
          
          with STATE_LOCK:
              if event_type == 'search_start':
                  search_logs.append({
                      'search_id': search_id,
                      'timestamp': timestamp,
                      'stage': 'Query Received',
                      'query': processed_data.get('query', ''),  # ✅ FIXED
                      'details': f"Real search from Flask app: '{processed_data.get('query', '')}'",  # ✅ FIXED
                      'status': 'processing',
                      'source': 'flask_app',
                      'user_ip': processed_data.get('ip_address', 'Unknown')  # ✅ FIXED
                  })
                  
              elif event_type == 'search_stage':
                  # Map Flask stages to dashboard display
                  stage_mapping = {
                      'web_search': 'Web Crawling',
                      'academic_search': 'Elasticsearch Search', 
                      'vector_search': 'Vector Search',
                      'ai_processing': 'AI Analysis',
                      'passage_search': 'Content Extraction'
                  }
                  
                  stage = processed_data.get('stage', 'Unknown')  # ✅ FIXED
                  display_stage = stage_mapping.get(stage, stage.replace('_', ' ').title())
                  status = processed_data.get('status', 'processing')  # ✅ FIXED
                  query = processed_data.get('query', 'Unknown query')
                  
                  details = processed_data.get('details', f"{display_stage} in progress...")  # ✅ FIXED
                  if 'results_count' in processed_data:  # ✅ FIXED
                      details += f" ({processed_data['results_count']} results)"  # ✅ FIXED
                  if 'search_time' in processed_data:  # ✅ FIXED
                      details += f" in {processed_data['search_time']}s"  # ✅ FIXED

                  if stage == 'ai_processing':
                    details = f"Processing query: '{query}' - {details}"

                  search_logs.append({
                      'search_id': search_id,
                      'timestamp': timestamp,
                      'stage': display_stage,
                      'query': query,
                      'details': details,
                      'status': status,
                      'source': 'flask_app',
                      'metrics': {
                          'results': processed_data.get('results_count', 0),  # ✅ FIXED
                          'time': processed_data.get('search_time', 0)  # ✅ FIXED
                      }
                  })
                  
                  # If it's AI processing, also add to AI logs
                  if stage == 'ai_processing':
                      ai_processing_logs.append({
                          'search_id': search_id,
                          'timestamp': timestamp,
                          'stage': 'AI Answer Generation',
                          'query': query,
                          'details': details,
                          'status': status,
                          'metrics': processed_data.get('metrics', {})  # ✅ FIXED
                      })
      except Exception as e:
          print(f"Error processing event data: {e}")
          
# Initialize Flask event listener
flask_listener = None
if flask_integration_enabled:
    flask_listener = ImprovedFlaskEventListener(redis_conn)
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
    search_id = f"sim_search_{int(time.time() * 1000)}_{random.randint(0, 999)}"
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
                hits = es_result.get('hits', {}).get('total', {}).get('value', 0) if isinstance(
                    es_result.get('hits', {}).get('total'), dict) else es_result.get('hits', {}).get('total', 0)
            except Exception:
                # fallback if older ES client
                es_result = es.search(index="academic-papers", body={
                    "query": {"multi_match": {"query": query, "fields": ["title^3", "abstract", "authors"]}}
                })
                hits = es_result.get('hits', {}).get('total', {}).get('value', 0) if isinstance(
                    es_result.get('hits', {}).get('total'), dict) else es_result.get('hits', {}).get('total', 0)
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
                'metrics': {'results': results_count, 'time': round(crawl_time, 3)}
            })
            crawler_stats[crawler].append({
                'timestamp': now_iso(),
                'query': query,
                'results': results_count,
                'time': round(crawl_time, 3),
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
            'metrics': {'processing_time': round(ai_time, 3), 'top_score': round(float(max(similarity_scores)), 3)}
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
            'metrics': {'total_time': round(total_time, 2)}
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

app.sse_queue = queue.Queue()
# SSE endpoint for real-time updates
@app.route('/events')
def sse_stream():
    """Lightweight Server-Sent Events implementation"""
    def event_generator():
        client_id = f"client_{int(time.time() * 1000)}_{random.randint(1000, 9999)}"
        print(f"SSE client connected: {client_id}")
        
        try:
            # Send connection confirmation
            yield f"retry: 1000\n"
            yield f"event: connected\ndata: {json.dumps({'client_id': client_id})}\n\n"
            
            last_heartbeat = time.time()
            
            while True:
                try:
                    # Check for events with shorter timeout
                    try:
                        event = app.sse_queue.get(timeout=10)  # Reduced from 25
                        yield f"event: update\ndata: {json.dumps(event)}\n\n"
                        app.sse_queue.task_done()
                        last_heartbeat = time.time()
                    except queue.Empty:
                        # Send heartbeat more frequently
                        if time.time() - last_heartbeat > 5:  # Reduced from 15
                            yield f"event: heartbeat\ndata: {{}}\n\n"
                            last_heartbeat = time.time()
                        
                except Exception as e:
                    print(f"Error in SSE stream for {client_id}: {e}")
                    break
                    
        except GeneratorExit:
            print(f"SSE client disconnected: {client_id}")
    
    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'text/event-stream',
        }
    )
    return Response(
        event_generator(),
        mimetype="text/event-stream",
        headers={
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'Content-Type': 'text/event-stream; charset=utf-8',
            'Access-Control-Allow-Origin': '*',
            'X-Accel-Buffering': 'no'
        }
    )
    
@app.route("/api/algorithm_metrics")
def api_algorithm_metrics():
    """Get performance metrics for different algorithms"""
    # Simulate real-time metrics (in production, these would come from actual monitoring)
    metrics = {
        "query_analysis": {
            "avg_processing_time": round(random.uniform(0.05, 0.15), 3),
            "success_rate": random.randint(95, 100),
            "throughput": random.randint(800, 1200),
            "active_processes": random.randint(1, 3),
            "error_rate": round(random.uniform(0.1, 0.5), 2)
        },
        "web_crawling": {
            "avg_processing_time": round(random.uniform(1.5, 3.5), 2),
            "success_rate": random.randint(85, 98),
            "throughput": random.randint(50, 150),
            "active_crawlers": random.randint(3, 8),
            "pages_crawled": random.randint(1000, 5000),
            "error_rate": round(random.uniform(1.0, 5.0), 2)
        },
        "elasticsearch_search": {
            "avg_response_time": round(random.uniform(0.1, 0.4), 3),
            "success_rate": random.randint(97, 100),
            "throughput": random.randint(200, 400),
            "cache_hit_rate": random.randint(65, 85),
            "error_rate": round(random.uniform(0.1, 0.8), 2)
        },
        "vector_search": {
            "avg_response_time": round(random.uniform(0.2, 0.6), 3),
            "success_rate": random.randint(96, 100),
            "throughput": random.randint(150, 300),
            "similarity_threshold": 0.6,
            "error_rate": round(random.uniform(0.2, 1.0), 2)
        },
        "embedding_generation": {
            "avg_processing_time": round(random.uniform(0.8, 2.5), 2),
            "success_rate": random.randint(92, 99),
            "throughput": random.randint(80, 200),
            "model": "all-MiniLM-L6-v2",
            "dimensions": 384,
            "error_rate": round(random.uniform(0.5, 2.0), 2)
        },
        "answer_generation": {
            "avg_processing_time": round(random.uniform(2.0, 4.5), 2),
            "success_rate": random.randint(88, 97),
            "throughput": random.randint(40, 100),
            "avg_response_length": random.randint(150, 450),
            "confidence_score": round(random.uniform(65, 92), 1),
            "error_rate": round(random.uniform(1.0, 5.0), 2)
        }
    }
    return jsonify(metrics)


@app.route("/api/algorithm_metrics_history")
def api_algorithm_metrics_history():
    """Get historical performance data for charts - FIXED TIME AXIS"""
    # Generate time series data for the last 60 minutes (real-time)
    now = datetime.now()
    timestamps = [(now - timedelta(minutes=i)).strftime("%H:%M") for i in range(59, -1, -1)]
    
    # Generate realistic time-series data that correlates properly
    base_time = time.time()
    
    # Create correlated data - when throughput is high, success rate should generally be good
    throughput_values = []
    success_rates = []
    
    for i in range(60):
        # Simulate daily patterns - higher throughput during working hours
        hour = (now - timedelta(minutes=59-i)).hour
        is_peak_time = 9 <= hour <= 17  # 9 AM to 5 PM
        
        # Base throughput with daily variation
        base_throughput = random.randint(80, 120) if is_peak_time else random.randint(40, 80)
        
        # Add some random variation but maintain correlation
        throughput = max(20, base_throughput + random.randint(-20, 20))
        throughput_values.append(throughput)
        
        # Success rate should correlate with throughput (but not perfectly)
        # Higher load can sometimes reduce success rate
        success_rate = 95 + random.randint(-5, 5)  # Base 95% ±5%
        if throughput > 100:  # Very high load might reduce success rate slightly
            success_rate = max(85, success_rate - random.randint(0, 8))
        success_rates.append(success_rate)
    
    # Processing times with realistic correlation to throughput
    # Higher throughput might slightly increase processing times due to load
    processing_times = []
    for i, throughput in enumerate(throughput_values):
        base_time = 0.1 + (throughput / 200)  # Slight increase with load
        processing_times.append(round(base_time + random.uniform(-0.05, 0.1), 3))
    
    history = {
        "timestamps": timestamps,
        "throughput": throughput_values,
        "success_rate": success_rates,
        "processing_time": processing_times
    }
    
    return jsonify(history)

@app.route('/health')
def health_check():
    """Simple health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'redis_connected': redis_conn.ping() if redis_conn else False,
        'timestamp': now_iso()
    })

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
<!DOCTYPE html>
<head>
  <meta charset="utf-8"/>
  <title>🔍 Academic Search System Dashboard</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <script src="https://cdn.plot.ly/plotly-2.24.1.min.js"></script>
  <style>
    :root{
      --muted: #6c757d;
      --gradient: linear-gradient(135deg, #1a73e8 0%, #34a853 100%);
    }
    *{box-sizing:border-box}
    body{margin:0;font-family:"Segoe UI", Tahoma, Geneva, Verdana, sans-serif;background:#f8f9fa;padding:20px;}
    .container {
      max-width: 1200px;
      margin: 0 auto;
      background: white;
      padding: 30px;
      border-radius: 12px;
      box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    h1 {
      text-align: center;
      color: #1a73e8;
      margin-bottom: 30px;
    }

    /* Tabs */
    .tabs {
      display: flex;
      border-bottom: 2px solid #e0e0e0;
      margin: 30px 0 20px 0;
    }
    .tab {
      padding: 15px 25px;
      background: #f8f9fa;
      border: none;
      cursor: pointer;
      font-size: 16px;
      font-weight: 500;
      color: #666;
      transition: all 0.3s ease;
      border-radius: 8px 8px 0 0;
      margin-right: 5px;
      position: relative;
      overflow: hidden;
    }
    .tab::after {
      content: '';
      position: absolute;
      bottom: 0;
      left: 0;
      width: 100%;
      height: 3px;
      background: var(--gradient);
      transform: scaleX(0);
      transform-origin: bottom right;
      transition: transform 0.3s ease;
    }
    .tab:hover {
      color: transparent;
      background-clip: text;
      -webkit-background-clip: text;
      background-image: var(--gradient);
    }
    .tab:hover::after {
      transform: scaleX(1);
      transform-origin: bottom left;
    }
    .tab.active {
      background: var(--gradient);
      color: white;
      box-shadow: 0 4px 12px rgba(26, 115, 232, 0.2);
    }
    .tab.active::after {
      display: none;
    }

    .tab-content {
      display: none;
      padding: 20px 0;
    }
    .tab-content.active { display: block; }

    /* Cards */
    .card {
      background: #fff;
      padding: 20px;
      border-radius: 12px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.05);
      margin-bottom: 20px;
    }

    .grid-two {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 20px;
    }

    /* Logs */
    .log-item {
      padding: 12px;
      border-radius: 8px;
      margin-bottom: 10px;
      background: #fbfbfb;
      border-left: 6px solid #e0e0e0;
      font-size: 14px;
    }
    .status-processing { border-left-color: #ffc107; }
    .status-completed { border-left-color: #34a853; }
    .status-error { border-left-color: #dc3545; }

    .smallmono {
      font-family: monospace;
      font-size: 12px;
      color: #666;
    }

    /* Flask integration status */
    .flask-status {
      position: fixed;
      top: 12px;
      right: 12px;
      padding: 8px 12px;
      border-radius: 8px;
      font-size: 13px;
      font-weight: 600;
      z-index: 1000;
    }
    .flask-connected{background:#d4edda;color:#155724;border:1px solid #c3e6cb}
    .flask-disconnected{background:#f8d7da;color:#721c24;border:1px solid #f5c6cb}

    /* Auto-refresh badge */
    .auto-badge {
      position: fixed;
      top: 52px;
      right: 12px;
      background: #28a745;
      color: #fff;
      padding: 6px 10px;
      border-radius: 16px;
      font-size: 13px;
      z-index: 9999;
    }

    /* Live events badge */
    .live-badge {
      position: fixed;
      top: 92px;
      right: 12px;
      background: #dc3545;
      color: #fff;
      padding: 6px 10px;
      border-radius: 16px;
      font-size: 13px;
      z-index: 9999;
    }
    .value-high { color: #28a745; }
    .value-medium { color: #ffc107; }
    .value-low { color: #dc3545; }

    .algorithm-metric-card {
      background: #f8f9fa;
      border-radius: 8px;
      padding: 15px;
      margin-bottom: 15px;
      border-left: 4px solid #1a73e8;
    } 
    .query-highlight {
        background: #f0f8ff;
        border-left: 4px solid #1a73e8;
        padding: 8px 12px;
        margin: 8px 0;
        border-radius: 6px;
        font-weight: 500;
    }

    .ai-query-card {
        background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
        border: 1px solid #dee2e6;
        border-radius: 8px;
        padding: 12px;
        margin: 8px 0;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }

    .live-query {
        border-left: 4px solid #dc3545;
    }

    .sim-query {
        border-left: 4px solid #007bff;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>📊 Academic Search System Dashboard</h1>

    <div id="flaskStatus" class="flask-status flask-disconnected">Flask App: Checking...</div>
    <div id="autoBadge" class="auto-badge" style="display:none;">🔄 Auto-refreshing...</div>
    <div id="liveBadge" class="live-badge" style="display:none;">🔴 Live Events Active</div>

    <!-- Tabs -->
    <div class="tabs">
      <button class="tab active" data-tab="liveTab">🔍 Live Search</button>
      <button class="tab" data-tab="crawlerTab">🕷️ Crawler</button>
      <button class="tab" data-tab="aiTab">🤖 AI Processing</button>
      <button class="tab" data-tab="analyticsTab">📈 Analytics</button>
      <button class="tab" data-tab="algoTab">⚙️ Algorithms</button>
    </div>

    <!-- Tab Contents -->
    <div id="liveTab" class="tab-content active">
      <div class="grid-two">
        <div class="card">
          <h3>📋 Live Search Log</h3>
          <p class="smallmono">🔴 LIVE = Real searches | 🔵 SIM = Test simulations</p>
          <div id="liveLogs">
            <div class="log-item status-processing">Processing query: "Deep learning in physics"</div>
            <div class="log-item status-completed">Completed query: "Graph neural networks"</div>
            <div class="log-item status-error">Error on query: "Quantum compiler benchmarks"</div>
          </div>
        </div>
        <div class="card">
          <h3>📊 Search Volume</h3>
          <div style="display:flex; flex-direction: column;">
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

    <div id="crawlerTab" class="tab-content">
      <div class="card">
        <h3>🕷️ Crawler Analytics</h3>
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:12px">
          <div style="flex:1;min-width:280px"><div id="crawlerSuccessChart" style="height:280px"></div></div>
          <div style="flex:1;min-width:280px"><div id="crawlerTimeChart" style="height:280px"></div></div>
        </div>
        <div id="crawlerTable" style="margin-top:12px"></div>
      </div>
    </div>

    <div id="aiTab" class="tab-content">
      <div class="card">
        <h3>🤖 AI Processing</h3>
        <div id="aiLogs" style="margin-top:10px;max-height:500px;overflow:auto"></div>
      </div>
    </div>

    <div id="analyticsTab" class="tab-content">
      <div class="card">
        <h3>📈 Search Analytics</h3>
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

    <div id="algoTab" class="tab-content">
      <div class="card">
        <h3>⚡ Real-time Algorithm Performance</h3>
        <div id="algorithmMetricsContainer">
          <div class="smallmono">Loading algorithm metrics...</div>
        </div>
      </div>
      
      
      <div class="card" style="margin-top: 20px;">
        <h4>🔧 Algorithm Details</h4>
        <pre style="background:#fafafa;padding:12px;border-radius:8px;color:#111;overflow:auto;">
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

  <script>
    const pollIntervalMs = 3000;
  let pollTimer = null;
  let flaskIntegrationEnabled = false;
  let eventSource = null;
  let connectionRetryCount = 0;
  const maxRetries = 5;
  let reconnectTimeoutId = null;

  // Tab switching
  document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const tabId = tab.getAttribute('data-tab');
      document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
      document.getElementById(tabId).classList.add('active');
    });
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
      if (flaskStatusEl) {
        flaskStatusEl.className = 'flask-status flask-connected';
        flaskStatusEl.textContent = 'Flask App: Connected ✅';
      }
      if (flaskStatusTextEl) flaskStatusTextEl.textContent = 'Connected ✅';
      if (redisStatusTextEl) redisStatusTextEl.textContent = 'Connected ✅';
      if (liveEventsTextEl) liveEventsTextEl.textContent = 'Active 🔴';
      
      const liveBadge = document.getElementById('liveBadge');
      if (liveBadge) {
        liveBadge.style.display = 'block';
        liveBadge.style.backgroundColor = '#28a745';
        liveBadge.textContent = '🔴 Live Events Active';
      }
    } else {
      if (flaskStatusEl) {
        flaskStatusEl.className = 'flask-status flask-disconnected';
        flaskStatusEl.textContent = 'Flask App: Disconnected ❌';
      }
      if (flaskStatusTextEl) flaskStatusTextEl.textContent = 'Disconnected ❌';
      if (redisStatusTextEl) redisStatusTextEl.textContent = redisStatus === 'connected' ? 'Connected ✅' : 'Disconnected ❌';
      if (liveEventsTextEl) liveEventsTextEl.textContent = 'Inactive ⚫';
      
      const liveBadge = document.getElementById('liveBadge');
      if (liveBadge) liveBadge.style.display = 'none';
    }
  }

  async function fetchLogs(){
    try {
      const res = await fetch('/api/search_logs'); 
      const data = await res.json();
      const logs = data.logs || [];
      const area = document.getElementById('liveLogs');
      if (!area) return;
      
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
      
      if (document.getElementById('completedCount')) document.getElementById('completedCount').innerText = completed;
      if (document.getElementById('processingCount')) document.getElementById('processingCount').innerText = processing;
      if (document.getElementById('errorCount')) document.getElementById('errorCount').innerText = error;
      
      const uq = [...new Set(recent.map(x=>x.query).filter(Boolean))].slice(-5).reverse().join('\n');
      if (document.getElementById('recentQueries')) document.getElementById('recentQueries').innerText = uq || '—';
    } catch(e) {
      console.error('Error fetching logs:', e);
    }
  }

  // Update the fetchAI function to show queries prominently
  async function fetchAI(){
      try {
        const res = await fetch('/api/ai_logs'); 
        const data = await res.json();
        const logs = data.ai_logs || [];
        const area = document.getElementById('aiLogs');
        if (!area) return;
        
        area.innerHTML = '';
        for(let l of logs.slice(0,50)){
          const div = document.createElement('div');
          div.className = 'log-item';
          const t = new Date(l.timestamp).toLocaleTimeString();
          
          // Enhanced display with query prominently featured
          div.innerHTML = `
            <div style="display:flex;justify-content:space-between">
              <strong>🧠 ${l.stage}</strong>
              <small class="smallmono">${t}</small>
            </div>
            <div style="margin:8px 0;padding:8px;background:#f0f8ff;border-radius:6px;border-left:4px solid #1a73e8">
              <strong>🔍 Query:</strong> "${l.query || 'No query specified'}"
            </div>
            <div style="margin-top:6px;color:#555">${l.details}</div>
          `;
          area.appendChild(div);
        }
      } catch(e) {
        console.error('Error fetching AI logs:', e);
      }
  }

  // Add this function to extract and display recent AI queries
  function updateRecentAIQueries(logs) {
      const aiQueriesContainer = document.getElementById('recentAIQueries');
      if (!aiQueriesContainer) return;
      
      // Extract unique AI queries from logs
      const aiQueries = [];
      const seenQueries = new Set();
      
      logs.forEach(log => {
          if (log.query && !seenQueries.has(log.query)) {
              aiQueries.push({
                  query: log.query,
                  timestamp: log.timestamp,
                  source: log.source
              });
              seenQueries.add(log.query);
          }
      });
      
      // Display the most recent 5 AI queries
      const recentQueries = aiQueries.slice(-5).reverse();
      
      if (recentQueries.length === 0) {
          aiQueriesContainer.innerHTML = '<div>No AI queries yet</div>';
          return;
      }
      
      aiQueriesContainer.innerHTML = recentQueries.map(q => `
          <div style="margin-bottom:8px;padding:6px;border-left:3px solid ${q.source === 'flask_app' ? '#dc3545' : '#007bff'};background:white;">
              <div style="font-weight:500">"${q.query}"</div>
              <div style="font-size:11px;color:#666">
                  ${new Date(q.timestamp).toLocaleTimeString()} | 
                  ${q.source === 'flask_app' ? '🔴 LIVE' : '🔵 SIM'}
              </div>
          </div>
      `).join('');
  }

  // Call this in your fetchLogs function
  async function fetchLogs(){
      try {
        const res = await fetch('/api/search_logs'); 
        const data = await res.json();
        const logs = data.logs || [];
        // ... existing code ...
        
        // Update recent AI queries display
        updateRecentAIQueries(logs);
        
      } catch(e) {
        console.error('Error fetching logs:', e);
      }
  }

  async function fetchCrawler(){
    try {
      const res = await fetch('/api/crawler_stats'); 
      const data = await res.json();
      const cs = data.crawler_stats || {};
      const names = Object.keys(cs);
      
      const successChart = document.getElementById('crawlerSuccessChart');
      const timeChart = document.getElementById('crawlerTimeChart');
      const table = document.getElementById('crawlerTable');
      
      if(!names.length){
        if (successChart) successChart.innerHTML = '<div class="smallmono">No crawler data</div>';
        if (timeChart) timeChart.innerHTML = '';
        if (table) table.innerHTML = '';
        return;
      }
      
      const success = names.map(n => {
        const arr = cs[n];
        const succ = arr.filter(x=>x.success).length;
        return arr.length ? Math.round((succ/arr.length)*100) : 0;
      });
      
      if (successChart && typeof Plotly !== 'undefined') {
        Plotly.newPlot('crawlerSuccessChart', [{x:names,y:success,type:'bar'}], {margin:{t:30}});
      }
      
      const avgTimes = names.map(n => {
        const arr = cs[n]; if(!arr.length) return 0;
        const avg = arr.reduce((s,x)=>s + (x.time||0),0) / arr.length; return Math.round(avg*100)/100;
      });
      
      if (timeChart && typeof Plotly !== 'undefined') {
        Plotly.newPlot('crawlerTimeChart', [{x:names,y:avgTimes,type:'bar'}], {margin:{t:30}});
      }
      
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
      if (table) table.innerHTML = html;
    } catch(e) {
      console.error('Error fetching crawler data:', e);
    }
  }

  async function fetchSearchAnalytics(){
    try {
      const res = await fetch('/api/search_logs'); 
      const data = await res.json();
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
      
      const hourLabels = Object.keys(hours).sort((a,b)=>a-b); 
      const hourCounts = hourLabels.map(h=>hours[h]);
      
      if (document.getElementById('searchHourChart') && typeof Plotly !== 'undefined') {
        Plotly.newPlot('searchHourChart', [{x:hourLabels,y:hourCounts,type:'bar'}], {margin:{t:20}});
      }
      
      const stages = Object.keys(byStage);
      const successRates = stages.map(s=>{
        const c = byStage[s].completed, e = byStage[s].error; const denom = (c+e)||1;
        return Math.round((c/denom)*10000)/100;
      });
      
      if (document.getElementById('stageSuccessChart') && typeof Plotly !== 'undefined') {
        Plotly.newPlot('stageSuccessChart', [{x:stages,y:successRates,type:'bar'}], {margin:{t:20},height:240});
      }
      
      const totalQ = queries.length; 
      const uniqueQ = new Set(queries).size;
      const avgLen = totalQ ? (queries.map(q=>q.split(/\s+/).length).reduce((a,b)=>a+b,0)/totalQ).toFixed(1) : '0.0';
      
      if (document.getElementById('totalQueries')) document.getElementById('totalQueries').innerText = totalQ; 
      if (document.getElementById('uniqueQueries')) document.getElementById('uniqueQueries').innerText = uniqueQ; 
      if (document.getElementById('avgQueryLen')) document.getElementById('avgQueryLen').innerText = avgLen;
      
      const c = {}; for(let q of queries) c[q] = (c[q]||0)+1;
      const pairs = Object.entries(c).sort((a,b)=>b[1]-a[1]).slice(0,6);
      
      if (document.getElementById('commonQueries')) {
        document.getElementById('commonQueries').innerHTML = pairs.map(p=>`<div>${p[0]} <span style="color:#888">(${p[1]})</span></div>`).join('');
      }
    } catch(e) {
      console.error('Error fetching search analytics:', e);
    }
  }

  async function refreshAll(){
    await fetchOverview();
    await fetchLogs();
    await fetchAI();
    await fetchCrawler();
    await fetchSearchAnalytics();
    await fetchAlgorithmMetrics();        // Add this line
    await fetchAlgorithmMetricsHistory(); // Add this line
}

  function startPolling(){ 
    if(pollTimer) clearInterval(pollTimer); 
    pollTimer = setInterval(refreshAll, pollIntervalMs); 
    refreshAll(); 
    const autoBadge = document.getElementById('autoBadge');
    if (autoBadge) autoBadge.style.display='block'; 
  }

  function stopPolling(){ 
    if(pollTimer) clearInterval(pollTimer); 
    pollTimer=null; 
    const autoBadge = document.getElementById('autoBadge');
    if (autoBadge) autoBadge.style.display='none'; 
  }

  // Enhanced real-time event streaming with Redis integration
  // Enhanced SSE client with better reconnection logic
function initEventStream() {
    if (eventSource) {
        eventSource.close();
    }
    
    // Clear any pending reconnect timeout
    if (reconnectTimeoutId) {
        clearTimeout(reconnectTimeoutId);
        reconnectTimeoutId = null;
    }

    console.log('Initializing SSE connection...');
    
    // Add cache-buster to URL to prevent stale connections
    const url = '/events?t=' + Date.now();
    eventSource = new EventSource(url);

    eventSource.onopen = function(event) {
        console.log('SSE connection opened successfully');
        connectionRetryCount = 0;
        updateConnectionStatus('connected');
        
        // Show connection success notification
        showNotification('Real-time connection established', 'success');
    };

    eventSource.onmessage = function(event) {
        try {
            const data = JSON.parse(event.data);
            
            // Handle heartbeat messages silently
            if (data.type === 'heartbeat') {
                // Update last heartbeat time but don't log
                lastHeartbeat = Date.now();
                return;
            }
            
            switch(data.type) {
                case 'connection':
                    console.log('SSE connected with client ID:', data.client_id);
                    break;
                    
                case 'search_update':
                    handleSearchUpdate(data.data);
                    break;
                    
                case 'error':
                    console.error('SSE Error from server:', data.message);
                    break;
                    
                default:
                    if (data.search_id && data.stage) {
                        handleSearchUpdate(data);
                    }
            }
        } catch (e) {
            console.error('Error parsing SSE data:', e, 'Raw data:', event.data);
        }
    };

    eventSource.onerror = function(event) {
        console.log('SSE connection error, readyState:', eventSource.readyState);
        updateConnectionStatus('error');
        
        // Close the connection properly
        eventSource.close();
        
        if (connectionRetryCount < maxRetries) {
            connectionRetryCount++;
            // Exponential backoff for reconnection
            const retryDelay = Math.min(1000 * Math.pow(2, connectionRetryCount), 30000);
            console.log(`Retrying SSE connection in ${retryDelay}ms (attempt ${connectionRetryCount}/${maxRetries})`);
            
            showNotification(`Connection lost, retrying in ${retryDelay/1000}s...`, 'warning');
            
            reconnectTimeoutId = setTimeout(() => {
                initEventStream();
            }, retryDelay);
        } else {
            console.log('Max SSE connection retries reached');
            updateConnectionStatus('failed');
            showNotification('Real-time connection failed. Using polling mode.', 'error');
        }
    };
}

// Add this variable to track heartbeats
let lastHeartbeat = Date.now();

// Monitor connection health
setInterval(() => {
    if (eventSource && eventSource.readyState === EventSource.OPEN) {
        // If no heartbeat for 30 seconds, assume connection is dead
        if (Date.now() - lastHeartbeat > 30000) {
            console.log('No heartbeat received, forcing reconnect');
            initEventStream(); // Force reconnect
        }
    }
}, 10000); // Check every 10 seconds

  function handleSearchUpdate(logData) {
    // Immediately refresh logs to show new data
    fetchLogs();
    
    // Show notification for new searches from Flask app
    if (logData.stage === 'Query Received' && logData.source === 'flask_app') {
      showNotification(`🔍 New search: "${logData.query}"`, 'info');
    }
    
    // Show notification for search completion
    if (logData.stage === 'Search Complete' && logData.source === 'flask_app') {
      const metrics = logData.metrics || {};
      showNotification(`✅ Search completed in ${metrics.total_time || 0}s`, 'success');
    }
    
    // Update counters immediately
    updateSearchCounters();
  }

  function updateConnectionStatus(status) {
    const liveEventsTextEl = document.getElementById('liveEventsText');
    const liveBadge = document.getElementById('liveBadge');
    
    if (!liveEventsTextEl || !liveBadge) return;
    
    switch(status) {
      case 'connected':
        liveEventsTextEl.textContent = 'Active (Live) 🔴';
        liveBadge.style.display = 'block';
        liveBadge.style.backgroundColor = '#28a745';
        liveBadge.textContent = '🔴 Live Events Active';
        break;
      case 'error':
        liveEventsTextEl.textContent = 'Reconnecting... 🔄';
        liveBadge.style.backgroundColor = '#ffc107';
        liveBadge.textContent = '🔄 Reconnecting...';
        break;
      case 'failed':
        liveEventsTextEl.textContent = 'Connection Failed ❌';
        liveBadge.style.backgroundColor = '#dc3545';
        liveBadge.textContent = '❌ Connection Failed';
        break;
    }
  }

  function updateHeartbeat(data) {
    // Update active search count from heartbeat
    const activeCount = data.active_searches || 0;
    const processingCountEl = document.getElementById('processingCount');
    if (processingCountEl) {
      processingCountEl.textContent = activeCount;
    }
    
    // Update last heartbeat time
    console.log('Heartbeat received:', data.timestamp);
  }

  function updateSearchCounters() {
    // Force refresh of overview to update counters
    fetchOverview();
  }

  function showNotification(message, type = 'info') {
    // Create temporary notification
    const notification = document.createElement('div');
    
    let backgroundColor;
    switch(type) {
      case 'success': backgroundColor = '#28a745'; break;
      case 'error': backgroundColor = '#dc3545'; break;
      case 'warning': backgroundColor = '#ffc107'; break;
      case 'info': 
      default: backgroundColor = '#17a2b8'; break;
    }
    
    notification.style.cssText = `
      position: fixed;
      top: 100px;
      right: 20px;
      background: ${backgroundColor};
      color: white;
      padding: 12px 16px;
      border-radius: 8px;
      z-index: 10000;
      box-shadow: 0 4px 12px rgba(0,0,0,0.2);
      transition: all 0.3s ease;
      max-width: 300px;
      font-size: 14px;
      line-height: 1.4;
    `;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Animate in
    setTimeout(() => {
      notification.style.transform = 'translateX(0)';
    }, 10);
    
    // Remove after 4 seconds
    setTimeout(() => {
      notification.style.opacity = '0';
      notification.style.transform = 'translateX(100%)';
      setTimeout(() => {
        if (document.body.contains(notification)) {
          document.body.removeChild(notification);
        }
      }, 300);
    }, 4000);
  }

  // Test Redis integration
  async function testRedisIntegration() {
    try {
      const response = await fetch('/api/run_search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: 'Redis integration test query'
        })
      });
      
      const result = await response.json();
      
      if (response.ok) {
        showNotification('✅ Redis integration test started', 'success');
        console.log('Redis test result:', result);
      } else {
        showNotification('❌ Redis integration test failed', 'error');
        console.error('Redis test error:', result);
      }
    } catch (error) {
      showNotification('❌ Redis test request failed', 'error');
      console.error('Redis test request error:', error);
    }
  }
  async function fetchAlgorithmMetrics() {
      try {
          const response = await fetch('/api/algorithm_metrics');
          const metrics = await response.json();
          updateAlgorithmMetricsUI(metrics);
      } catch (error) {
          console.error('Error fetching algorithm metrics:', error);
      }
  }
  
  function updateAlgorithmMetricsUI(metrics) {
    const container = document.getElementById('algorithmMetricsContainer');
    if (!container) return;
    
    let html = `
    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 15px;">
    `;
    
    for (const [algorithm, data] of Object.entries(metrics)) {
        const title = algorithm.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
        
        html += `
        <div class="card" style="padding: 15px;">
            <h4>${title}</h4>
            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 10px;">
        `;
        
        for (const [metric, value] of Object.entries(data)) {
            const formattedMetric = metric.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            let displayValue = value;
            let valueClass = '';
            
            if (typeof value === 'number') {
                if (metric.includes('time')) {
                    displayValue = `${value} sec`;
                } else if (metric.includes('rate') || metric.includes('success')) {
                    displayValue = `${value}%`;
                    // Color code based on value
                    if (value >= 95) valueClass = 'value-high';
                    else if (value >= 85) valueClass = 'value-medium';
                    else valueClass = 'value-low';
                } else if (metric.includes('throughput')) {
                    displayValue = `${value}/min`;
                }
            }
            
            html += `
            <div>
                <div class="smallmono" style="color: #666;">${formattedMetric}</div>
                <div class="${valueClass}" style="font-weight: bold; font-size: 1.1em;">${displayValue}</div>
            </div>
            `;
        }
        
        html += `
            </div>
        </div>
        `;
    }
    
    html += `</div>`;
    container.innerHTML = html;
}

  // Enhanced initialization
  document.addEventListener('DOMContentLoaded', function() {
    console.log('Dashboard initializing with Redis integration...');
    
    // Initialize event stream for real-time updates
    initEventStream();
    
    // Start auto-polling as fallback
    startPolling();
    
    // Add test Redis integration button if it exists
    const testButton = document.getElementById('testRedisBtn');
    if (testButton) {
      testButton.addEventListener('click', testRedisIntegration);
    }
    
    // Handle run test search button
    const runTestBtn = document.getElementById('runTestBtn');
    if (runTestBtn) {
      runTestBtn.addEventListener('click', async () => {
        const testQuery = document.getElementById('testQuery');
        const query = testQuery ? testQuery.value || 'machine learning algorithms' : 'machine learning algorithms';
        
        runTestBtn.disabled = true;
        runTestBtn.textContent = '🔄 Running...';
        
        try {
          const response = await fetch('/api/run_search', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query })
          });
          
          if (response.ok) {
            showNotification(`🚀 Test search started: "${query}"`, 'success');
          } else {
            showNotification('❌ Test search failed', 'error');
          }
        } catch (error) {
          console.error('Test search error:', error);
          showNotification('❌ Test search request failed', 'error');
        }
        
        setTimeout(() => {
          runTestBtn.disabled = false;
          runTestBtn.innerHTML = '🚀 <span class="hide-on-collapse">Run Test Search</span>';
        }, 1000);
      });
    }
    
    // Handle clear logs button
    const clearAllBtn = document.getElementById('clearAllBtn');
    if (clearAllBtn) {
      clearAllBtn.addEventListener('click', async () => {
        if (!confirm('Clear all logs?')) return;
        
        try {
          await fetch('/api/clear_logs', { method: 'POST' });
          refreshAll();
          showNotification('🗑️ All logs cleared', 'success');
        } catch (error) {
          showNotification('❌ Failed to clear logs', 'error');
        }
      });
    }
    
    // Handle metrics update button
    const updateMetricsBtn = document.getElementById('updateMetricsBtn');
    if (updateMetricsBtn) {
      updateMetricsBtn.addEventListener('click', async () => {
        try {
          await fetch('/api/system_metrics', { method: 'POST' });
          fetchSearchAnalytics(); // Refresh analytics
          showNotification('📊 System metrics updated', 'success');
        } catch (error) {
          showNotification('❌ Failed to update metrics', 'error');
        }
      });
    }
    
    // Handle auto-refresh toggle
    const autoToggle = document.getElementById('autoToggle');
    if (autoToggle) {
      autoToggle.addEventListener('change', (e) => {
        if (e.target.checked) {
          startPolling();
          showNotification('🔄 Auto-refresh enabled', 'info');
        } else {
          stopPolling();
          showNotification('⏸️ Auto-refresh disabled', 'info');
        }
      });
      
      // Set initial state
      autoToggle.checked = true;
    }
    
    // Handle system metrics collection toggle
    const collectToggle = document.getElementById('collectToggle');
    if (collectToggle) {
      collectToggle.addEventListener('change', async (e) => {
        if (e.target.checked) {
          await fetch('/api/system_metrics', { method: 'POST' });
          showNotification('📈 System metrics collection started', 'info');
        }
      });
    }
    
    console.log('Dashboard initialized successfully with Redis integration');
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