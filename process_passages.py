from minio import Minio
import fitz  # PyMuPDF
import tempfile
import json
import nltk
import os

nltk.download('punkt')
from nltk.tokenize import sent_tokenize

# === Configuration ===
MINIO_URL = "minio:9000"
ACCESS_KEY = "minioadmin"
SECRET_KEY = "minioadmin"
SOURCE_BUCKET = "papers"
DEST_BUCKET = "passages"

# === Connect to MinIO ===
client = Minio(MINIO_URL, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False)

# === Ensure destination bucket exists ===
if not client.bucket_exists(DEST_BUCKET):
    client.make_bucket(DEST_BUCKET)

# === Example: Process 1 PDF ===
pdf_filename = "C++ object orianted programming.pdf"  # replace with your actual file name in MinIO

# Download PDF to temp file
obj = client.get_object(SOURCE_BUCKET, pdf_filename)

with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
    for chunk in obj.stream(32 * 1024):
        tmp_file.write(chunk)
    tmp_file.flush()

    # Extract text from PDF
    doc = fitz.open(tmp_file.name)
    full_text = "\n".join([page.get_text() for page in doc])

# === Split text into passages ===
sentences = sent_tokenize(full_text)
chunk_size = 3
passages = []

for i in range(0, len(sentences), chunk_size):
    chunk = " ".join(sentences[i:i + chunk_size])
    if chunk.strip():  # skip empty chunks
        passages.append({
            "paper": pdf_filename,
            "passage_id": f"{pdf_filename.replace('.pdf','')}_{i//chunk_size:04}",
            "text": chunk.strip()
        })

# === Save to JSON ===
json_filename = pdf_filename.replace(".pdf", ".json")
with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w") as json_file:
    json.dump(passages, json_file, indent=2)
    json_file_path = json_file.name

# === Upload JSON to MinIO ===
client.fput_object(DEST_BUCKET, json_filename, json_file_path)

print(f"✅ Extracted and saved {len(passages)} passages from {pdf_filename}")
os.remove(json_file_path)  # optional: clean up
