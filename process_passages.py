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

MIN_PARAGRAPH_WORDS = 20  # minimum words in a paragraph to consider
WINDOW_SIZE = 1           # number of paragraphs per passage
STEP = 1                  # sliding window step (overlap of WINDOW_SIZE-STEP)

# === Connect to MinIO ===
client = Minio(MINIO_URL, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False)

# === Ensure destination bucket exists ===
if not client.bucket_exists(DEST_BUCKET):
    client.make_bucket(DEST_BUCKET)

# === List all PDFs in SOURCE_BUCKET ===
objects = client.list_objects(SOURCE_BUCKET)

for obj in objects:
    try:
        if not obj.object_name.lower().endswith(".pdf"):
            continue

        pdf_filename = obj.object_name
        print(f"📄 Processing: {pdf_filename}")

        # Skip if JSON already exists (uncomment to enable)
        json_filename = pdf_filename.replace(".pdf", ".json")
        existing_objs = [o.object_name for o in client.list_objects(DEST_BUCKET)]
        if json_filename in existing_objs:
            print(f"⚠️ Skipping {pdf_filename}, already processed.")
            continue

        # Download PDF to temp file
        obj_data = client.get_object(SOURCE_BUCKET, pdf_filename)
        with tempfile.NamedTemporaryFile(delete=True, suffix=".pdf") as tmp_file:
            for chunk in obj_data.stream(32 * 1024):
                tmp_file.write(chunk)
            tmp_file.flush()

            # Extract text from PDF pages
            doc = fitz.open(tmp_file.name)
            full_text = "\n".join([page.get_text() for page in doc])

            # Clean text:
            full_text = re.sub(r'-\s*\n\s*', '', full_text)  # fix hyphenated line breaks
            full_text = re.sub(r'\n+', '\n\n', full_text)    # normalize to double newlines for paragraphs
            full_text = re.sub(r'[ \t]+', ' ', full_text)   # normalize spaces and tabs

        # Split into paragraphs and filter short ones
        paragraphs = [p.strip() for p in full_text.split("\n\n") if len(p.strip().split()) >= MIN_PARAGRAPH_WORDS]

        passages = []
        # Create overlapping passages from paragraphs
        for i in range(0, len(paragraphs), STEP):
            chunk_paras = paragraphs[i:i + WINDOW_SIZE]
            if not chunk_paras:
                continue
            combined_text = "\n\n".join(chunk_paras).strip()
            if len(combined_text.split()) >= MIN_PARAGRAPH_WORDS:
                passages.append({
                    "paper": pdf_filename,
                    "passage_id": f"{pdf_filename.replace('.pdf','')}_{i:04}",
                    "text": combined_text
                })

        # Save and upload JSON if we have passages
        if passages:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".json", mode="w") as json_file:
                json.dump(passages, json_file, indent=2)
                json_file_path = json_file.name

            client.fput_object(DEST_BUCKET, json_filename, json_file_path)
            os.remove(json_file_path)

            print(f"✅ Saved {len(passages)} passages for {pdf_filename}")
        else:
            print(f"⚠️ No usable text found in {pdf_filename}")

    except Exception as e:
        print(f"❌ Error processing {obj.object_name}: {e}")
