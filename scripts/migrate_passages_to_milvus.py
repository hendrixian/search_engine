#!/usr/bin/env python3
"""
Migration script to transfer passage data from MinIO buckets to Milvus vector database.
This script handles the transition from file-based storage to vector database storage.

Usage:
    python scripts/migrate_passages_to_milvus.py [--dry-run] [--batch-size 100]
"""

import os
import sys
import json
import io
import argparse
from datetime import datetime
from typing import List, Dict, Any
import logging


# Add parent directory to path to import modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
from minio import Minio
from database.milvus_manager import MilvusVectorManager

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('migration.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

class PassageMigrator:
    """Migrate passages from MinIO buckets to Milvus vector database"""
    
    def __init__(self):
        # MinIO configuration
        self.minio_endpoint = os.getenv("MINIO_ENDPOINT", "localhost:9000")
        self.minio_user = os.getenv("MINIO_ROOT_USER", "minioadmin")
        self.minio_password = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")
        self.minio_secure = os.getenv("MINIO_SECURE", "false").lower() == "true"
        
        # Milvus configuration
        self.milvus_host = os.getenv("MILVUS_HOST", "localhost")
        self.milvus_port = os.getenv("MILVUS_PORT", "19530")
        
        # Initialize clients
        self.minio_client = None
        self.milvus_manager = None
        
        # Migration statistics
        self.stats = {
            'files_processed': 0,
            'passages_migrated': 0,
            'errors': 0,
            'skipped': 0,
            'start_time': None,
            'end_time': None
        }
    
    def connect_services(self):
        """Connect to MinIO and Milvus services"""
        try:
            # Connect to MinIO
            logger.info("🔥 Connecting to MinIO...")
            self.minio_client = Minio(
                self.minio_endpoint,
                access_key=self.minio_user,
                secret_key=self.minio_password,
                secure=self.minio_secure
            )
            
            # Test MinIO connection
            list(self.minio_client.list_buckets())
            logger.info("✅ MinIO connected successfully")
            
            # Connect to Milvus
            logger.info("🔥 Connecting to Milvus vector database...")
            self.milvus_manager = MilvusVectorManager(
                host=self.milvus_host,
                port=self.milvus_port
            )
            
            if self.milvus_manager.connect():
                logger.info("✅ Milvus connected successfully")
                return True
            else:
                logger.error("❌ Failed to connect to Milvus")
                return False
                
        except Exception as e:
            logger.error(f"❌ Failed to connect to services: {e}")
            return False
    
    def extract_passages_from_minio(self, bucket_name="passages"):
        """Extract all passage data from MinIO bucket"""
        passages_data = []
        
        try:
            # Check if bucket exists
            if not self.minio_client.bucket_exists(bucket_name):
                logger.warning(f"⚠️ Bucket '{bucket_name}' does not exist")
                return passages_data
            
            logger.info(f"📂 Extracting passages from MinIO bucket: {bucket_name}")
            
            # List all objects in the passages bucket
            objects = self.minio_client.list_objects(bucket_name, recursive=True)
            
            for obj in objects:
                if obj.object_name.endswith('.json'):
                    try:
                        # Get object data
                        response = self.minio_client.get_object(bucket_name, obj.object_name)
                        
                        # Read JSON data
                        buffer = io.BytesIO()
                        for chunk in response.stream(32 * 1024):
                            buffer.write(chunk)
                        buffer.seek(0)
                        
                        # Parse JSON
                        file_data = json.load(buffer)
                        
                        # Extract paper ID from filename
                        paper_id = obj.object_name.replace('.json', '').split('/')[-1]
                        
                        # Process passages in the file
                        if isinstance(file_data, list):
                            for i, passage in enumerate(file_data):
                                passage_data = self._format_passage_for_milvus(
                                    passage, paper_id, i, obj.object_name
                                )
                                if passage_data:
                                    passages_data.append(passage_data)
                        
                        self.stats['files_processed'] += 1
                        
                        if self.stats['files_processed'] % 10 == 0:
                            logger.info(f"📄 Processed {self.stats['files_processed']} files, extracted {len(passages_data)} passages so far...")
                        
                    except Exception as e:
                        logger.error(f"❌ Error processing file {obj.object_name}: {e}")
                        self.stats['errors'] += 1
                        continue
            
            logger.info(f"✅ Extracted {len(passages_data)} passages from {self.stats['files_processed']} files")
            return passages_data
            
        except Exception as e:
            logger.error(f"❌ Failed to extract passages from MinIO: {e}")
            return passages_data
    
    def _format_passage_for_milvus(self, passage, paper_id, passage_index, file_path):
        """Format passage data for Milvus storage"""
        try:
            # Extract text content
            text = passage.get('text', '').strip()
            if not text or len(text) < 10:  # Skip very short passages
                self.stats['skipped'] += 1
                return None
            
            # Format passage data for Milvus
            formatted_passage = {
                'paper_id': paper_id,
                'text': text[:8191],  # Truncate if too long for Milvus schema
                'page_number': passage.get('page_number', 0),
                'passage_index': passage_index,
                'title': passage.get('title', 'Unknown Title')[:511],
                'authors': passage.get('authors', 'Unknown Authors')[:1023],
                'year': int(passage.get('year', 0)) if passage.get('year') else 0,
                'category': passage.get('category', 'unknown')[:99],
                'abstract': passage.get('abstract', '')[:2047],
                'file_path': file_path[:511],
            }
            
            return formatted_passage
            
        except Exception as e:
            logger.error(f"❌ Error formatting passage: {e}")
            self.stats['errors'] += 1
            return None
    
    def migrate_to_milvus(self, passages_data, batch_size=100, dry_run=False):
        """Migrate passages to Milvus vector database in batches"""
        if not passages_data:
            logger.warning("⚠️ No passages to migrate")
            return True
        
        if dry_run:
            logger.info(f"🧪 DRY RUN: Would migrate {len(passages_data)} passages to Milvus")
            return True
        
        try:
            total_passages = len(passages_data)
            logger.info(f"🚀 Starting migration of {total_passages} passages to Milvus (batch size: {batch_size})")
            
            # Process in batches
            for i in range(0, total_passages, batch_size):
                batch = passages_data[i:i + batch_size]
                batch_num = (i // batch_size) + 1
                
                logger.info(f"📦 Processing batch {batch_num}/{(total_passages + batch_size - 1) // batch_size} ({len(batch)} passages)")
                
                # Add batch to Milvus
                success = self.milvus_manager.add_passages(batch)
                
                if success:
                    self.stats['passages_migrated'] += len(batch)
                    logger.info(f"✅ Batch {batch_num} migrated successfully ({self.stats['passages_migrated']}/{total_passages} total)")
                else:
                    logger.error(f"❌ Failed to migrate batch {batch_num}")
                    self.stats['errors'] += 1
                    return False
            
            logger.info(f"🎉 Migration completed! Migrated {self.stats['passages_migrated']} passages")
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration failed: {e}")
            self.stats['errors'] += 1
            return False
    
    def verify_migration(self, sample_queries=None):
        """Verify migration by testing some searches"""
        if not sample_queries:
            sample_queries = [
                "machine learning algorithms",
                "deep neural networks", 
                "natural language processing",
                "computer vision",
                "data science"
            ]
        
        logger.info("🔍 Verifying migration with sample searches...")
        
        verification_results = {}
        
        for query in sample_queries:
            try:
                results = self.milvus_manager.search_passages(query, limit=5)
                verification_results[query] = {
                    'results_count': len(results),
                    'avg_similarity': sum(r.get('similarity_score', 0) for r in results) / len(results) if results else 0,
                    'success': len(results) > 0
                }
                logger.info(f"✅ Query '{query}': {len(results)} results (avg similarity: {verification_results[query]['avg_similarity']:.3f})")
                
            except Exception as e:
                logger.error(f"❌ Verification failed for query '{query}': {e}")
                verification_results[query] = {'success': False, 'error': str(e)}
        
        # Summary
        successful_queries = sum(1 for r in verification_results.values() if r.get('success', False))
        logger.info(f"📊 Verification completed: {successful_queries}/{len(sample_queries)} queries successful")
        
        return verification_results
    
    def print_migration_summary(self):
        """Print detailed migration summary"""
        duration = (self.stats['end_time'] - self.stats['start_time']).total_seconds()
        
        print("\n" + "="*60)
        print("🎯 MIGRATION SUMMARY")
        print("="*60)
        print(f"📊 Files processed: {self.stats['files_processed']}")
        print(f"🔄 Passages migrated: {self.stats['passages_migrated']}")
        print(f"⏭️  Passages skipped: {self.stats['skipped']}")
        print(f"❌ Errors encountered: {self.stats['errors']}")
        print(f"⏱️  Total duration: {duration:.2f} seconds")
        print(f"🚀 Migration rate: {self.stats['passages_migrated'] / duration:.1f} passages/second")
        print("="*60)
        
        # Get Milvus collection stats
        if self.milvus_manager:
            try:
                milvus_stats = self.milvus_manager.get_collection_stats()
                print(f"📚 Milvus collection: {milvus_stats.get('collection_name', 'N/A')}")
                print(f"🔢 Total passages in Milvus: {milvus_stats.get('total_passages', 'N/A')}")
                print(f"📐 Embedding dimension: {milvus_stats.get('embedding_dimension', 'N/A')}")
                print(f"📈 Index type: {milvus_stats.get('index_type', 'N/A')}")
            except Exception as e:
                print(f"⚠️  Could not retrieve Milvus stats: {e}")
        
        print("="*60 + "\n")
    
    def run_migration(self, dry_run=False, batch_size=100, bucket_name="passages"):
        """Run complete migration process"""
        self.stats['start_time'] = datetime.now()
        
        logger.info("🚀 Starting passage migration from MinIO to Milvus")
        logger.info(f"📝 Configuration:")
        logger.info(f"   - MinIO endpoint: {self.minio_endpoint}")
        logger.info(f"   - Milvus host: {self.milvus_host}:{self.milvus_port}")
        logger.info(f"   - Batch size: {batch_size}")
        logger.info(f"   - Dry run: {dry_run}")
        logger.info(f"   - Source bucket: {bucket_name}")
        
        try:
            # Step 1: Connect to services
            if not self.connect_services():
                logger.error("❌ Failed to connect to required services")
                return False
            
            # Step 2: Extract passages from MinIO
            logger.info("\n📂 Phase 1: Extracting passages from MinIO...")
            passages_data = self.extract_passages_from_minio(bucket_name)
            
            if not passages_data:
                logger.warning("⚠️ No passages found to migrate")
                return True
            
            # Step 3: Migrate to Milvus
            logger.info(f"\n🔄 Phase 2: Migrating {len(passages_data)} passages to Milvus...")
            migration_success = self.migrate_to_milvus(passages_data, batch_size, dry_run)
            
            if not migration_success:
                logger.error("❌ Migration failed")
                return False
            
            # Step 4: Verification (only if not dry run)
            if not dry_run:
                logger.info("\n🔍 Phase 3: Verifying migration...")
                verification_results = self.verify_migration()
            
            self.stats['end_time'] = datetime.now()
            
            # Print summary
            self.print_migration_summary()
            
            if not dry_run:
                logger.info("✅ Migration completed successfully!")
                logger.info("💡 You can now update your application to use Milvus vector search instead of MinIO buckets")
            else:
                logger.info("✅ Dry run completed successfully!")
                logger.info("💡 Run without --dry-run to perform actual migration")
            
            return True
            
        except Exception as e:
            logger.error(f"❌ Migration process failed: {e}")
            return False
        
        finally:
            # Cleanup connections
            if self.milvus_manager:
                self.milvus_manager.close_connection()


def main():
    """Main function with command line argument parsing"""
    parser = argparse.ArgumentParser(
        description="Migrate passage data from MinIO buckets to Milvus vector database"
    )
    parser.add_argument(
        '--dry-run', 
        action='store_true', 
        help='Perform a dry run without actually migrating data'
    )
    parser.add_argument(
        '--batch-size', 
        type=int, 
        default=100, 
        help='Number of passages to process in each batch (default: 100)'
    )
    parser.add_argument(
        '--bucket', 
        type=str, 
        default='passages', 
        help='MinIO bucket name containing passages (default: passages)'
    )
    parser.add_argument(
        '--verbose', 
        action='store_true', 
        help='Enable verbose logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Initialize and run migrator
    migrator = PassageMigrator()
    
    try:
        success = migrator.run_migration(
            dry_run=args.dry_run,
            batch_size=args.batch_size,
            bucket_name=args.bucket
        )
        
        if success:
            sys.exit(0)
        else:
            sys.exit(1)
            
    except KeyboardInterrupt:
        logger.info("\n🛑 Migration interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Unexpected error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()