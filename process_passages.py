from minio import Minio
import fitz  # PyMuPDF
import tempfile
import json
import nltk
import os
import re

nltk.download('punkt', download_dir='/usr/share/nltk_data')
nltk.data.path.append('/usr/share/nltk_data')

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

# === Process all PDFs in SOURCE_BUCKET ===
objects = client.list_objects(SOURCE_BUCKET)

for obj in objects:
    if not obj.object_name.endswith(".pdf"):
        continue

    pdf_filename = obj.object_name
    print(f"📄 Processing: {pdf_filename}")

    # Download PDF
    obj_data = client.get_object(SOURCE_BUCKET, pdf_filename)
    with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
        for chunk in obj_data.stream(32 * 1024):
            tmp_file.write(chunk)
        tmp_file.flush()

        # Extract text from PDF
        doc = fitz.open(tmp_file.name)
        full_text = "\n".join([page.get_text() for page in doc])

        # Clean up text
        full_text = re.sub(r'-\s*\n\s*', '', full_text)  # fix hyphenated line-breaks
        full_text = re.sub(r'\n+', '\n\n', full_text)    # normalize to paragraph spacing

    # === Split into passages by paragraph ===
    paragraphs = full_text.split("\n\n")
    passages = []

    for i, para in enumerate(paragraphs):
        clean_para = para.strip()
        if len(clean_para.split()) >= 20:  # ignore very short chunks
            passages.append({
                "paper": pdf_filename,
                "passage_id": f"{pdf_filename.replace('.pdf','')}_{i:04}",
                "text": clean_para
            })

    # === Save and upload JSON ===
    if passages:
        json_filename = pdf_filename.replace(".pdf", ".json")
        with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w") as json_file:
            json.dump(passages, json_file, indent=2)
            json_file_path = json_file.name

        client.fput_object(DEST_BUCKET, json_filename, json_file_path)
        os.remove(json_file_path)

        print(f"✅ Saved {len(passages)} passages for {pdf_filename}")
    else:
        print(f"⚠️ No usable text found in {pdf_filename}")
