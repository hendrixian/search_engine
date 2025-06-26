from elasticsearch import Elasticsearch
import pandas as pd

es = Elasticsearch("http://elasticsearch:9200")

# Read preprocessed data
papers = pd.read_csv("papers.csv")  # or load from preprocessing output

for _, row in papers.iterrows():
    doc = {
        "title": row["title"],
        "authors": row["authors"],
        "year": int(row["year"]),
        "abstract": row["abstract"],
        "pdf_path": row["pdf_path"]
    }
    es.index(index="academic-papers", id=row["id"], document=doc)

print("Indexing complete.")
