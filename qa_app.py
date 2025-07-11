import streamlit as st
from minio import Minio
import json
import tempfile
from sentence_transformers import SentenceTransformer, util
from transformers import pipeline
import os

# Optional: define cache dir inside container (persistent volume mount recommended)
MODEL_CACHE_DIR = "/app/models"
os.environ["TRANSFORMERS_CACHE"] = MODEL_CACHE_DIR
os.environ["SENTENCE_TRANSFORMERS_HOME"] = MODEL_CACHE_DIR


# === Load Models ===
@st.cache_resource
def load_models():
    embedder = SentenceTransformer("all-MiniLM-L6-v2")
    qa_pipeline = pipeline("question-answering", model="distilbert-base-uncased-distilled-squad")
    return embedder, qa_pipeline

embedder, qa_pipeline = load_models()

# === Connect to MinIO ===
client = Minio("minio:9000", access_key="minioadmin", secret_key="minioadmin", secure=False)

st.title("📚 Ask Questions About Academic Papers")

# === List available passage JSON files from MinIO ===
bucket = "passages"
json_files = [obj.object_name for obj in client.list_objects(bucket) if obj.object_name.endswith(".json")]

if not json_files:
    st.warning("No passage files found in MinIO.")
    st.stop()

selected_file = st.selectbox("Select a paper", json_files)

# === Download selected JSON from MinIO ===
response = client.get_object(bucket, selected_file)
with tempfile.NamedTemporaryFile(delete=False, suffix=".json") as tmp:
    for chunk in response.stream(32 * 1024):
        tmp.write(chunk)
    tmp.flush()
    with open(tmp.name, "r") as f:
        passages = json.load(f)

# === Show question input ===
question = st.text_input("Ask a question about the selected paper")

if question:
    texts = [p["text"] for p in passages]
    passage_embeddings = embedder.encode(texts, convert_to_tensor=True)
    question_embedding = embedder.encode(question, convert_to_tensor=True)

    # Find best matching passage
    scores = util.cos_sim(question_embedding, passage_embeddings)[0]
    best_idx = scores.argmax().item()
    best_passage = texts[best_idx]

    # Run QA
    result = qa_pipeline(question=question, context=best_passage)

    st.markdown("### ✅ Answer")
    st.write(result["answer"])

    st.markdown("### 📄 Source Passage")
    st.write(best_passage)
