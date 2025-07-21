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
from minstral import call_mistral

# === Model cache directories inside Docker container ===
MODEL_CACHE_DIR = "/app/models"
os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODEL_CACHE_DIR

# === Load models only once ===
@st.cache_resource
def load_models():
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    qa_pipeline = pipeline("question-answering", model="deepset/roberta-base-squad2")  # <-- improved model
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

                buffer = io.BytesIO()
                for chunk in resp.stream(32 * 1024):
                    buffer.write(chunk)
                buffer.seek(0)

                data = json.load(buffer)
                passages.extend(data)
    except Exception as e:
        st.error(f"Error accessing passages from MinIO: {e}")
        st.stop()

    if not passages:
        st.warning("No passage data available for QA.")
    else:
        texts = [p["text"].replace("\n", " ").strip() for p in passages]
        passage_embeddings = embedder.encode(texts, convert_to_tensor=True)
        query_embedding = embedder.encode(query, convert_to_tensor=True)

        scores = util.cos_sim(query_embedding, passage_embeddings)[0]

        # 🔥 Use top-k passages instead of just best one
        top_k = 3
        top_indices = torch.topk(scores, k=top_k).indices.tolist()

        # Combine top-k relevant paragraphs into a context window (token-limited)
        tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2")
        max_tokens = 600
        context = ""
        included = []

        for i in top_indices:
            chunk = texts[i]
            temp = context + "\n\n" + chunk if context else chunk
            if len(tokenizer(temp)["input_ids"]) <= max_tokens:
                context = temp
                included.append(chunk)
            else:
                break

        # Call Mistral for a paraphrased, fluent answer
        answer = call_mistral(query, context)

        st.markdown("### ✅ Answer")
        st.write(answer)

        st.markdown("### 📄 Source Passages")
        for passage in included:
            st.write(passage)
