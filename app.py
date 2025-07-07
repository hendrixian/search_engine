import streamlit as st
from elasticsearch import Elasticsearch

es = Elasticsearch("http://elasticsearch:9200")

st.title("Academic Paper Search Engine")

query = st.text_input("Enter search query")

if query:
    res = es.search(index="academic-papers", query={
        "multi_match": {
            "query": query,
            "fields": ["title^3", "abstract", "authors"]
        }
    })

    total_results = res['hits']['total']['value']
    st.write(f"Found {total_results} results.")

    for hit in res['hits']['hits']:
        source = hit["_source"]

        # Custom HTML block for each paper
        html_content = f"""
        <div style="
            border: 1px solid #ddd; 
            padding: 15px; 
            margin-bottom: 15px; 
            border-radius: 8px; 
            background-color: #f9f9f9;">
            <h3 style="color: #2c3e50;">{source['title']}</h3>
            <p style="font-size: 0.9em; color: #555;">
                <strong>Authors:</strong> {source['authors']} | 
                <strong>Year:</strong> {source['year']}
            </p>
            <p style="font-size: 1em; color: #333;">{source['abstract']}</p>
            <a href="{source['pdf_path']}" target="_blank" style="text-decoration:none;">
                📄<strong>View PDF</strong>
            </a>
        </div>
        """
        st.markdown(html_content, unsafe_allow_html=True)
