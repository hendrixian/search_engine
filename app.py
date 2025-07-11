import streamlit as st
from elasticsearch import Elasticsearch
from minio import Minio
import json
import tempfile
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
import os

# === Model cache directories inside Docker container ===
MODEL_CACHE_DIR = "/app/models"
os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODEL_CACHE_DIR

# === Load models only once ===
@st.cache_resource
def load_models():
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    qa_pipeline = pipeline("question-answering", model="distilbert-base-uncased-distilled-squad")
    return embedder, qa_pipeline

embedder, qa_pipeline = load_models()

# === Connect to Elasticsearch ===
es = Elasticsearch("http://elasticsearch:9200")

# === Connect to MinIO ===
minio_client = Minio("minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)

st.title("🔎 Unified Academic Search + Question Answering")

query = st.text_input("Enter a keyword or ask a question about academic content")

if query:
    # --- Part 1: Metadata Search ---
    es_result = es.search(index="academic-papers", query={
        "multi_match": {
            "query": query,
            "fields": ["title^3", "abstract", "authors"]
        }
    })

    total_results = es_result['hits']['total']['value']
    st.markdown(f"### 🔍 Found {total_results} result(s) in metadata")

    for hit in es_result['hits']['hits']:
        source = hit["_source"]
        st.markdown(f"""
        <div style="border: 1px solid #ccc; padding: 10px; border-radius: 8px; margin-bottom: 10px;">
            <h4>{source['title']}</h4>
            <p><strong>Authors:</strong> {source['authors']} | <strong>Year:</strong> {source['year']}</p>
            <p>{source['abstract']}</p>
            <a href="{source['pdf_path']}" target="_blank">📄 View PDF</a>
        </div>
        """, unsafe_allow_html=True)

    # --- Part 2: QA over full passages ---
    st.markdown("---")
    st.markdown("### 🧠 Answering from full PDF content...")

    passages = []
    try:
        objects = minio_client.list_objects("passages")
        for obj in objects:
            if obj.object_name.endswith(".json"):
                resp = minio_client.get_object("passages", obj.object_name)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp_file:
                    for chunk in resp.stream(32 * 1024):
                        tmp_file.write(chunk)
                    tmp_file.flush()
                    with open(tmp_file.name, "r") as f:
                        data = json.load(f)
                        passages.extend(data)
    except Exception as e:
        st.error(f"Error accessing passages from MinIO: {e}")
        st.stop()

    if not passages:
        st.warning("No passage data available for QA.")
    else:
        texts = [p["text"] for p in passages]
        passage_embeddings = embedder.encode(texts, convert_to_tensor=True)
        query_embedding = embedder.encode(query, convert_to_tensor=True)

        scores = util.cos_sim(query_embedding, passage_embeddings)[0]
        best_idx = scores.argmax().item()
        best_passage = texts[best_idx]

        result = qa_pipeline(question=query, context=best_passage)

        st.markdown("### ✅ Answer")
        st.write(result["answer"])

        st.markdown("### 📄 Source Passage")
        st.write(best_passage)
