from minio import Minio
import pandas as pd
from elasticsearch import Elasticsearch
import os

# Connect to MinIO
minio_client = Minio(
    "minio:9000",  # or wherever your MinIO is hosted
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False
)

# Make sure bucket exists
bucket_name = "papers"
if not minio_client.bucket_exists(bucket_name):
    minio_client.make_bucket(bucket_name)

# Connect to Elasticsearch
es = Elasticsearch("http://elasticsearch:9200")

# Load CSV
papers = pd.read_csv("papers.csv")

for _, row in papers.iterrows():
    file_path = row["pdf_path"]
    filename = os.path.basename(file_path)

    # Upload to MinIO
    minio_client.fput_object(bucket_name, filename, file_path)

    # Generate public URL (adjust domain if using Nginx or S3 Gateway)
    minio_url = f"http://localhost:9000/{bucket_name}/{filename}"

    # Index into ES
    doc = {
        "title": row["title"],
        "authors": row["authors"],
        "year": int(row["year"]),
        "abstract": row["abstract"],
        "pdf_path": minio_url
    }
    es.index(index="academic-papers", id=row["id"], document=doc)

print("Indexing complete with MinIO support.")
