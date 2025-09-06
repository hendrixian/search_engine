# database/milvus_manager.py
import os
import json
import time
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import logging

from pymilvus import (
    connections, 
    Collection, 
    FieldSchema, 
    CollectionSchema, 
    DataType,
    utility
)
from sentence_transformers import SentenceTransformer

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MilvusVectorManager:
    """Enhanced Milvus manager for academic passage storage and retrieval"""
    
    def __init__(self, host=None, port=None):
        self.host = host or os.getenv('MILVUS_HOST', 'milvus-standalone')
        self.port = port or os.getenv('MILVUS_PORT', '19530')
        self.collection_name = 'academic_passages'
        self.collection = None
        self.embedder = None
        self.embedding_dim = 384  # all-MiniLM-L6-v2 dimension
        self.is_connected = False
        
    def connect(self):
        """Connect to Milvus database"""
        try:
            connections.connect("default", host=self.host, port=self.port)
            self.is_connected = True
            logger.info(f"✅ Connected to Milvus at {self.host}:{self.port}")
            
            # Initialize collection
            self._initialize_collection()
            
            # Load embedder
            self._load_embedder()
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to connect to Milvus: {e}")
            self.is_connected = False
            return False
    
    def _load_embedder(self):
        """Load sentence transformer model for embeddings"""
        try:
            logger.info("🔥 Loading SentenceTransformer model for embeddings...")
            self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ SentenceTransformer model loaded")
        except Exception as e:
            logger.error(f"❌ Failed to load embedder: {e}")
            self.embedder = None
    
    def _initialize_collection(self):
        """Initialize or connect to the academic passages collection"""
        try:
            # Check if collection exists
            if utility.has_collection(self.collection_name):
                logger.info(f"📚 Collection '{self.collection_name}' exists, connecting...")
                self.collection = Collection(self.collection_name)
                
                # Check if schema matches (13 fields means old schema with year)
                schema = self.collection.schema
                if len(schema.fields) == 13:  # Old schema with year field
                    logger.warning(f"⚠️ Old schema detected (13 fields), recreating collection without year field...")
                    self._recreate_collection()
                else:
                    logger.info(f"✅ Schema matches current requirements ({len(schema.fields)} fields)")
            else:
                logger.info(f"🏗️ Creating new collection '{self.collection_name}'...")
                self._create_collection()
            
            # Load collection into memory for search
            self.collection.load()
            logger.info(f"✅ Collection '{self.collection_name}' ready for operations")
            
        except Exception as e:
            logger.error(f"❌ Failed to initialize collection: {e}")
            raise
    
    def _create_collection(self):
        """Create the academic passages collection with proper schema"""
        fields = [
            FieldSchema(name="id", dtype=DataType.VARCHAR, is_primary=True, max_length=100),
            FieldSchema(name="paper_id", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="passage_text", dtype=DataType.VARCHAR, max_length=8192),
            FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=self.embedding_dim),
            FieldSchema(name="page_number", dtype=DataType.INT64),
            FieldSchema(name="passage_index", dtype=DataType.INT64),
            FieldSchema(name="title", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="authors", dtype=DataType.VARCHAR, max_length=1024),
            FieldSchema(name="category", dtype=DataType.VARCHAR, max_length=100),
            FieldSchema(name="abstract", dtype=DataType.VARCHAR, max_length=2048),
            FieldSchema(name="file_path", dtype=DataType.VARCHAR, max_length=512),
            FieldSchema(name="created_at", dtype=DataType.VARCHAR, max_length=50),
        ]
        
        schema = CollectionSchema(
            fields=fields,
            description="Academic paper passages with vector embeddings for semantic search"
        )
        
        self.collection = Collection(
            name=self.collection_name,
            schema=schema,
            using='default'
        )
        
        # Create index for vector field
        index_params = {
            "metric_type": "COSINE",
            "index_type": "HNSW",
            "params": {"M": 16, "efConstruction": 256}
        }
        
        self.collection.create_index("embedding", index_params)
        logger.info("✅ Collection created with HNSW index")
    
    def _recreate_collection(self):
        """Drop and recreate the collection with new schema"""
        try:
            logger.warning(f"🗑️ Dropping existing collection '{self.collection_name}'...")
            utility.drop_collection(self.collection_name)
            logger.info(f"✅ Collection '{self.collection_name}' dropped")
            
            # Create new collection with updated schema
            logger.info(f"🏗️ Creating new collection '{self.collection_name}' with updated schema...")
            self._create_collection()
            
        except Exception as e:
            logger.error(f"❌ Failed to recreate collection: {e}")
            raise
    
    def add_passages(self, passages_data: List[Dict[str, Any]]) -> bool:
        """
        Add passages to Milvus vector database
        
        Args:
            passages_data: List of passage dictionaries with metadata
            
        Returns:
            bool: Success status
        """
        if not self.is_connected or not self.embedder:
            logger.error("❌ Milvus not connected or embedder not loaded")
            return False
        
        try:
            # Prepare data for insertion
            ids = []
            paper_ids = []
            passage_texts = []
            embeddings = []
            page_numbers = []
            passage_indices = []
            titles = []
            authors_list = []
            categories = []
            abstracts = []
            file_paths = []
            created_ats = []
            
            logger.info(f"🔄 Processing {len(passages_data)} passages for vector embedding...")
            
            for i, passage in enumerate(passages_data):
                # Generate unique ID
                passage_id = f"{passage.get('paper_id', 'unknown')}_{i}"
                ids.append(passage_id)
                
                # Extract metadata
                paper_ids.append(passage.get('paper_id', ''))
                passage_text = passage.get('text', '')
                passage_texts.append(passage_text[:8191])  # Truncate if too long
                page_numbers.append(passage.get('page_number', 0))
                passage_indices.append(i)
                titles.append(passage.get('title', '')[:511])
                authors_list.append(passage.get('authors', '')[:1023])
                categories.append(passage.get('category', 'unknown')[:99])
                abstracts.append(passage.get('abstract', '')[:2047])
                file_paths.append(passage.get('file_path', '')[:511])
                created_ats.append(datetime.now().isoformat())
                
                # Generate embedding
                if passage_text.strip():
                    embedding = self.embedder.encode(passage_text).tolist()
                else:
                    embedding = [0.0] * self.embedding_dim  # Zero embedding for empty text
                embeddings.append(embedding)
            
            # Insert data into Milvus
            logger.info(f"💾 Inserting {len(ids)} passages into Milvus...")
            
            entities = [
                ids, paper_ids, passage_texts, embeddings, page_numbers,
                passage_indices, titles, authors_list, categories,
                abstracts, file_paths, created_ats
            ]
            
            insert_result = self.collection.insert(entities)
            
            # Flush to ensure data persistence
            self.collection.flush()
            
            logger.info(f"✅ Successfully inserted {len(insert_result.primary_keys)} passages")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add passages to Milvus: {e}")
            return False
    
    def search_passages(self, query: str, limit: int = 10, similarity_threshold: float = 0.7) -> List[Dict[str, Any]]:
        """
        Search for similar passages using vector similarity
        
        Args:
            query: Search query string
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of matching passages with metadata and scores
        """
        if not self.is_connected or not self.embedder:
            logger.error("❌ Milvus not connected or embedder not loaded")
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.embedder.encode(query).tolist()
            
            # Define search parameters
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 128}
            }
            
            # Perform vector search
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=limit,
                output_fields=[
                    "paper_id", "passage_text", "page_number", "passage_index",
                    "title", "authors", "category", "abstract", "file_path"
                ]
            )
            
            # Process results
            passages = []
            for hits in results:
                for hit in hits:
                    # Filter by similarity threshold
                    similarity_score = hit.score
                    if similarity_score >= similarity_threshold:
                        passage_data = {
                            'id': hit.id,
                            'paper_id': hit.entity.get('paper_id'),
                            'text': hit.entity.get('passage_text'),
                            'page_number': hit.entity.get('page_number'),
                            'passage_index': hit.entity.get('passage_index'),
                            'title': hit.entity.get('title'),
                            'authors': hit.entity.get('authors'),
                            'year': hit.entity.get('year'),
                            'category': hit.entity.get('category'),
                            'abstract': hit.entity.get('abstract'),
                            'file_path': hit.entity.get('file_path'),
                            'similarity_score': float(similarity_score),
                            'distance': float(hit.distance)
                        }
                        passages.append(passage_data)
            
            logger.info(f"🔍 Found {len(passages)} passages above similarity threshold {similarity_threshold}")
            return passages
            
        except Exception as e:
            logger.error(f"❌ Failed to search passages: {e}")
            return []
    
    def get_collection_stats(self) -> Dict[str, Any]:
        """Get statistics about the collection"""
        if not self.is_connected:
            return {'error': 'Not connected to Milvus'}
        
        try:
            # Get collection statistics
            stats = self.collection.get_collection_stats()
            num_entities = self.collection.num_entities
            
            return {
                'collection_name': self.collection_name,
                'total_passages': num_entities,
                'index_type': 'HNSW',
                'embedding_dimension': self.embedding_dim,
                'similarity_metric': 'COSINE',
                'collection_stats': stats,
                'status': 'healthy'
            }
            
        except Exception as e:
            return {
                'collection_name': self.collection_name,
                'error': str(e),
                'status': 'error'
            }
    
    def delete_by_paper_id(self, paper_id: str) -> bool:
        """Delete all passages for a specific paper"""
        try:
            expr = f'paper_id == "{paper_id}"'
            self.collection.delete(expr)
            logger.info(f"🗑️ Deleted passages for paper_id: {paper_id}")
            return True
        except Exception as e:
            logger.error(f"❌ Failed to delete passages for {paper_id}: {e}")
            return False
    
    def hybrid_search(self, query: str, filters: Dict[str, Any] = None, limit: int = 10) -> List[Dict[str, Any]]:
        """
        Enhanced search with filtering capabilities
        
        Args:
            query: Search query
            filters: Dictionary of filters (category, etc.)
            limit: Maximum results
            
        Returns:
            Filtered search results
        """
        try:
            # Build filter expression
            filter_expr = None
            if filters:
                filter_conditions = []
                if 'category' in filters:
                    filter_conditions.append(f'category == "{filters["category"]}"')
                
                if filter_conditions:
                    filter_expr = " && ".join(filter_conditions)
            
            # Generate query embedding
            query_embedding = self.embedder.encode(query).tolist()
            
            # Search with filters
            search_params = {
                "metric_type": "COSINE",
                "params": {"ef": 128}
            }
            
            results = self.collection.search(
                data=[query_embedding],
                anns_field="embedding",
                param=search_params,
                limit=limit,
                expr=filter_expr,
                output_fields=[
                    "paper_id", "passage_text", "page_number", "title", 
                    "authors", "category", "abstract"
                ]
            )
            
            # Process and return results
            passages = []
            for hits in results:
                for hit in hits:
                    passages.append({
                        'id': hit.id,
                        'text': hit.entity.get('passage_text'),
                        'title': hit.entity.get('title'),
                        'similarity_score': float(hit.score),
                        'metadata': {
                            'paper_id': hit.entity.get('paper_id'),
                            'authors': hit.entity.get('authors'),
                            'year': hit.entity.get('year'),
                            'category': hit.entity.get('category')
                        }
                    })
            
            return passages
            
        except Exception as e:
            logger.error(f"❌ Hybrid search failed: {e}")
            return []
    
    def close_connection(self):
        """Close Milvus connection"""
        try:
            connections.disconnect("default")
            self.is_connected = False
            logger.info("✅ Milvus connection closed")
        except Exception as e:
            logger.error(f"❌ Error closing Milvus connection: {e}")