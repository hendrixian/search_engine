import time
import requests
import xml.etree.ElementTree as ET
from minio import Minio
from io import BytesIO

# ---------------------------
# CONFIG
# ---------------------------

MINIO_ENDPOINT = "minio:9000"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
MINIO_BUCKET = "papers"

BATCH_SIZE = 100       # Number of papers per API request
DELAY = 3              # Seconds between requests to avoid rate-limiting

ARXIV_CATEGORIES = [
    "astro-ph", "cond-mat", "cs", "econ", "eess", "hep-ex", "hep-lat", "hep-ph",
    "hep-th", "math", "math-ph", "nlin", "nucl-ex", "nucl-th", "physics",
    "q-bio", "q-fin", "stat", "gr-qc"
]

# ---------------------------
# FUNCTIONS
# ---------------------------

def get_arxiv_entries(category, start=0, max_results=100):
    """Fetch entries from arXiv API for a category with pagination"""
    url = f"http://export.arxiv.org/api/query?search_query=cat:{category}&start={start}&max_results={max_results}"
    response = requests.get(url)
    if response.status_code != 200:
        print(f"❌ Error fetching arXiv entries: {response.status_code}")
        return []
    root = ET.fromstring(response.text)
    entries = []
    for entry in root.findall("{http://www.w3.org/2005/Atom}entry"):
        pdf_link = None
        for link in entry.findall("{http://www.w3.org/2005/Atom}link"):
            if link.attrib.get("title") == "pdf":
                pdf_link = link.attrib["href"]
        if pdf_link:
            entries.append(pdf_link)
    return entries

def upload_to_minio(client, file_name, file_bytes):
    """Upload a file to MinIO"""
    client.put_object(
        MINIO_BUCKET,
        file_name,
        BytesIO(file_bytes),
        length=len(file_bytes),
        content_type="application/pdf"
    )
    print(f"✅ Uploaded: {file_name}")

def already_uploaded(client):
    """Return a set of file names already in the MinIO bucket"""
    existing_files = set()
    for obj in client.list_objects(MINIO_BUCKET):
        existing_files.add(obj.object_name)
    return existing_files

# ---------------------------
# MAIN
# ---------------------------

def main():
    client = Minio(
        MINIO_ENDPOINT,
        access_key=MINIO_ACCESS_KEY,
        secret_key=MINIO_SECRET_KEY,
        secure=False
    )
    
    # Create bucket if not exists
    if not client.bucket_exists(MINIO_BUCKET):
        client.make_bucket(MINIO_BUCKET)

    uploaded_files = already_uploaded(client)
    print(f"ℹ️ {len(uploaded_files)} files already in MinIO, skipping them.")

    for category in ARXIV_CATEGORIES:
        print(f"📂 Fetching category: {category}")
        start = 0
        while True:
            pdf_links = get_arxiv_entries(category, start=start, max_results=BATCH_SIZE)
            if not pdf_links:
                break
            for url in pdf_links:
                file_name = url.split("/")[-1] + ".pdf"
                if file_name in uploaded_files:
                    print(f"⚠️ Already uploaded, skipping: {file_name}")
                    continue
                print(f"⬇️ Downloading {url}")
                try:
                    pdf_data = requests.get(url).content
                    upload_to_minio(client, file_name, pdf_data)
                    uploaded_files.add(file_name)
                except Exception as e:
                    print(f"❌ Failed to download {url}: {e}")
            start += BATCH_SIZE
            time.sleep(DELAY)

if __name__ == "__main__":
    main()