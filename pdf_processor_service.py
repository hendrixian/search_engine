#!/usr/bin/env python3
# pdf_processor_service.py
"""
Dedicated PDF Processing Service for MinIO Webhook Integration
This service runs separately and handles PDF metadata extraction
"""

import os
import sys
import time
import logging
import urllib.parse
from flask import Flask, request, jsonify
from minio import Minio
from pdf_extractor import PDFMetadataExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Flask app
app = Flask(__name__)

# Configuration
MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
MINIO_ACCESS_KEY = os.getenv('MINIO_ROOT_USER', 'minioadmin')
MINIO_SECRET_KEY = os.getenv('MINIO_ROOT_PASSWORD', 'minioadmin')
CSV_FILE_PATH = os.getenv('CSV_FILE_PATH', 'papers.csv')

# Initialize MinIO client
minio_client = None
pdf_extractor = None

def initialize_services():
    """Initialize MinIO client and PDF extractor"""
    global minio_client, pdf_extractor
    
    try:
        # Initialize MinIO client
        logger.info(f"🔗 Connecting to MinIO at {MINIO_ENDPOINT}")
        minio_client = Minio(
            MINIO_ENDPOINT,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
            secure=False
        )
        
        # Test connection
        buckets = list(minio_client.list_buckets())
        logger.info(f"✅ MinIO connected successfully. Found {len(buckets)} buckets")
        
        # Initialize PDF extractor
        pdf_extractor = PDFMetadataExtractor(csv_file=CSV_FILE_PATH)
        logger.info("✅ PDF extractor initialized")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to initialize services: {e}")
        return False

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'pdf-processor',
        'minio_connected': minio_client is not None,
        'pdf_extractor_ready': pdf_extractor is not None
    })

@app.route('/webhook/minio', methods=['POST'])
def minio_webhook():
    """Handle MinIO webhook events for PDF uploads"""
    try:
        # Parse webhook data
        webhook_data = request.get_json()
        
        if not webhook_data:
            logger.error("❌ No webhook data received")
            return jsonify({'error': 'No webhook data received'}), 400
        
        logger.info(f"📨 Received MinIO webhook: {webhook_data.get('EventName', 'Unknown Event')}")
        
        # Extract event information
        event_name = webhook_data.get('EventName', '')
        records = webhook_data.get('Records', [])
        
        if not records:
            logger.error("❌ No records in webhook")
            return jsonify({'error': 'No records in webhook'}), 400
        
        processed_files = 0
        
        # Process each record
        for record in records:
            try:
                # Extract file information
                s3_info = record.get('s3', {})
                bucket_name = s3_info.get('bucket', {}).get('name', '')
                object_key = s3_info.get('object', {}).get('key', '')
                
                # URL decode the object key to handle spaces and special characters
                decoded_object_key = urllib.parse.unquote_plus(object_key)
                
                logger.info(f"🔍 Processing file: {bucket_name}/{object_key}")
                logger.info(f"🔍 Decoded filename: {decoded_object_key}")
                
                # Check if it's a PDF file (use decoded name)
                if not decoded_object_key.lower().endswith('.pdf'):
                    logger.info(f"⏭️ Skipping non-PDF file: {decoded_object_key}")
                    continue
                
                # Check if it's a PUT (upload) event
                if 's3:ObjectCreated' not in event_name:
                    logger.info(f"⏭️ Skipping non-upload event: {event_name}")
                    continue
                
                # Process the PDF using the decoded filename
                success = process_uploaded_pdf(bucket_name, decoded_object_key)
                
                if success:
                    logger.info(f"✅ Successfully processed PDF: {decoded_object_key}")
                    processed_files += 1
                else:
                    logger.error(f"❌ Failed to process PDF: {decoded_object_key}")
                    
            except Exception as e:
                logger.error(f"❌ Error processing record: {e}")
                continue
        
        return jsonify({
            'status': 'success',
            'message': f'Webhook processed successfully. Processed {processed_files} PDF files.',
            'processed_files': processed_files,
            'total_records': len(records)
        }), 200
        
    except Exception as e:
        logger.error(f"❌ Webhook processing error: {e}")
        return jsonify({'error': str(e)}), 500

def process_uploaded_pdf(bucket_name: str, object_key: str) -> bool:
    """Process a newly uploaded PDF file from MinIO"""
    try:
        if not minio_client:
            logger.error("❌ MinIO client not available")
            return False
        
        if not pdf_extractor:
            logger.error("❌ PDF extractor not available")
            return False
        
        # Create temporary file path
        temp_pdf_path = f"/tmp/{object_key.replace('/', '_')}"
        
        try:
            logger.info(f"📥 Downloading PDF from MinIO: {bucket_name}/{object_key}")
            # Use URL-decoded object key for actual MinIO operations
            actual_object_key = urllib.parse.unquote_plus(object_key) if '+' in object_key or '%' in object_key else object_key
            logger.info(f"📥 Using actual object key: {actual_object_key}")
            minio_client.fget_object(bucket_name, actual_object_key, temp_pdf_path)
            
            # Extract metadata
            logger.info(f"🔍 Extracting metadata from: {temp_pdf_path}")
            metadata = pdf_extractor.extract_pdf_metadata(temp_pdf_path)
            
            # Update metadata with correct path
            metadata['pdf_path'] = os.path.basename(object_key)  # Just filename
            
            # Add to CSV
            success = pdf_extractor.add_to_csv(metadata)
            
            if success:
                logger.info(f"🎉 PDF processed and added to papers.csv: {metadata.get('title', 'Unknown')}")
                
                # Log the extracted metadata
                logger.info(f"📋 Extracted metadata:")
                logger.info(f"   Title: {metadata.get('title', 'N/A')}")
                logger.info(f"   Authors: {metadata.get('authors', 'N/A')}")
                logger.info(f"   Abstract: {metadata.get('abstract', 'N/A')[:100]}...")
                
                return True
            else:
                logger.error(f"❌ Failed to add PDF metadata to papers.csv")
                return False
                
        finally:
            # Clean up temporary file
            if os.path.exists(temp_pdf_path):
                os.remove(temp_pdf_path)
                logger.info(f"🧹 Cleaned up temporary file: {temp_pdf_path}")
        
    except Exception as e:
        logger.error(f"❌ Error processing uploaded PDF {object_key}: {e}")
        return False

@app.route('/api/process-pdf/<path:object_key>', methods=['POST'])
def manual_process_pdf(object_key):
    """Manually trigger PDF processing for testing"""
    try:
        bucket_name = request.args.get('bucket', 'papers')
        logger.info(f"🔧 Manual processing requested for: {bucket_name}/{object_key}")
        
        success = process_uploaded_pdf(bucket_name, object_key)
        
        if success:
            return jsonify({
                'status': 'success',
                'message': f'PDF {object_key} processed successfully'
            }), 200
        else:
            return jsonify({
                'status': 'error',
                'message': f'Failed to process PDF {object_key}'
            }), 500
            
    except Exception as e:
        logger.error(f"❌ Manual processing error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get service status"""
    try:
        # Check CSV file
        csv_exists = os.path.exists(CSV_FILE_PATH)
        csv_writable = os.access(CSV_FILE_PATH, os.W_OK) if csv_exists else os.access(os.path.dirname(CSV_FILE_PATH), os.W_OK)
        
        # Count papers in CSV
        paper_count = 0
        if csv_exists:
            try:
                with open(CSV_FILE_PATH, 'r') as f:
                    paper_count = sum(1 for line in f) - 1  # Subtract header
            except:
                paper_count = 0
        
        return jsonify({
            'service': 'pdf-processor',
            'status': 'running',
            'minio_connected': minio_client is not None,
            'pdf_extractor_ready': pdf_extractor is not None,
            'csv_file': {
                'path': CSV_FILE_PATH,
                'exists': csv_exists,
                'writable': csv_writable,
                'paper_count': paper_count
            },
            'endpoints': {
                'webhook': '/webhook/minio',
                'manual_process': '/api/process-pdf/<object_key>',
                'health': '/health',
                'status': '/api/status'
            }
        })
        
    except Exception as e:
        logger.error(f"❌ Status check error: {e}")
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    logger.info("🚀 Starting PDF Processor Service...")
    
    # Initialize services
    if not initialize_services():
        logger.error("❌ Failed to initialize services. Exiting.")
        sys.exit(1)
    
    logger.info("✅ PDF Processor Service initialized successfully")
    logger.info(f"📡 Webhook endpoint: http://0.0.0.0:5002/webhook/minio")
    logger.info(f"📋 CSV file: {CSV_FILE_PATH}")
    logger.info(f"🔗 MinIO endpoint: {MINIO_ENDPOINT}")
    
    # Start Flask app
    app.run(host='0.0.0.0', port=5002, debug=False)
