# pdf_extractor.py
import os
import re
import csv
import logging
from typing import Dict, Optional
from datetime import datetime
from pathlib import Path

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pdfplumber
    PDFPLUMBER_AVAILABLE = True
except ImportError:
    PDFPLUMBER_AVAILABLE = False

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PDFMetadataExtractor:
    """Extract metadata from PDF files for academic papers"""
    
    def __init__(self, csv_file: str = "papers.csv"):
        self.csv_file = csv_file
        
    def extract_pdf_metadata(self, pdf_path: str) -> Dict[str, str]:
        """Extract comprehensive metadata from a PDF file"""
        try:
            logger.info(f"🔍 Extracting metadata from: {pdf_path}")
            
            # Basic file info
            file_info = self._get_file_info(pdf_path)
            
            # Extract metadata using available libraries
            metadata = {}
            
            if PYMUPDF_AVAILABLE:
                pymupdf_data = self._extract_with_pymupdf(pdf_path)
                metadata.update(pymupdf_data)
            
            if PDFPLUMBER_AVAILABLE:
                pdfplumber_data = self._extract_with_pdfplumber(pdf_path)
                metadata.update(pdfplumber_data)
            
            # Combine and clean the data
            final_metadata = self._process_metadata(file_info, metadata)
            
            logger.info(f"✅ Successfully extracted metadata for: {final_metadata.get('title', 'Unknown')}")
            return final_metadata
            
        except Exception as e:
            logger.error(f"❌ Failed to extract metadata from {pdf_path}: {e}")
            return self._create_fallback_metadata(pdf_path)
    
    def _get_file_info(self, pdf_path: str) -> Dict[str, str]:
        """Get basic file information"""
        try:
            file_path = Path(pdf_path)
            stat = file_path.stat()
            
            return {
                'filename': file_path.name,
                'file_size': stat.st_size,
                'created_date': datetime.fromtimestamp(stat.st_ctime).isoformat(),
                'modified_date': datetime.fromtimestamp(stat.st_mtime).isoformat()
            }
        except Exception as e:
            logger.warning(f"⚠️ Could not get file info: {e}")
            return {'filename': os.path.basename(pdf_path)}
    
    def _extract_with_pymupdf(self, pdf_path: str) -> Dict[str, str]:
        """Extract metadata using PyMuPDF"""
        try:
            doc = fitz.open(pdf_path)
            
            # Get PDF metadata
            metadata = doc.metadata or {}
            
            # Extract first page text for title/abstract detection
            first_page_text = ""
            full_text_sample = ""
            
            if len(doc) > 0:
                first_page_text = doc[0].get_text()
                
                # Extract text from first 3 pages for abstract detection
                for page_num in range(min(3, len(doc))):
                    full_text_sample += doc[page_num].get_text() + "\n"
            
            page_count = len(doc)
            doc.close()
            
            return {
                'pdf_title': metadata.get('title', ''),
                'pdf_author': metadata.get('author', ''),
                'pdf_subject': metadata.get('subject', ''),
                'page_count': page_count,
                'first_page_text': first_page_text[:2000],  # Limit size
                'full_text_sample': full_text_sample[:5000]  # First 5000 chars
            }
            
        except Exception as e:
            logger.warning(f"⚠️ PyMuPDF extraction failed: {e}")
            return {}
    
    def _extract_with_pdfplumber(self, pdf_path: str) -> Dict[str, str]:
        """Extract metadata using pdfplumber"""
        try:
            with pdfplumber.open(pdf_path) as pdf:
                # Get first page for title extraction
                first_page_text = ""
                if len(pdf.pages) > 0:
                    first_page_text = pdf.pages[0].extract_text() or ""
                
                return {
                    'plumber_first_page': first_page_text[:2000],
                    'total_pages': len(pdf.pages)
                }
                
        except Exception as e:
            logger.warning(f"⚠️ pdfplumber extraction failed: {e}")
            return {}
    
    def _process_metadata(self, file_info: Dict, extracted_data: Dict) -> Dict[str, str]:
        """Process and combine metadata from different sources"""
        
        # Extract title (priority: PDF metadata > first page detection)
        title = self._extract_title(extracted_data)
        
        # Extract authors
        authors = self._extract_authors(extracted_data)
        
        # Extract abstract
        abstract = self._extract_abstract(extracted_data)
        
        return {
            'title': title,
            'authors': authors,
            'abstract': abstract,
            'pdf_path': file_info.get('filename', ''),
            'page_count': extracted_data.get('page_count', extracted_data.get('total_pages', 0)),
            'file_size': file_info.get('file_size', 0),
            'extraction_date': datetime.now().isoformat()
        }
    
    def _extract_title(self, data: Dict) -> str:
        """Extract title from PDF"""
        
        # Try PDF metadata first
        pdf_title = data.get('pdf_title', '').strip()
        if pdf_title and len(pdf_title) > 5:
            return self._clean_text(pdf_title)
        
        # Try to extract from first page text
        first_page = data.get('first_page_text', '') or data.get('plumber_first_page', '')
        
        if first_page:
            # Look for title patterns (usually the first large text block)
            lines = first_page.split('\n')
            for line in lines[:10]:  # Check first 10 lines
                line = line.strip()
                if len(line) > 10 and len(line) < 200:  # Reasonable title length
                    # Skip common headers
                    skip_words = ['abstract', 'introduction', 'page', 'doi:', 'arxiv:', 'www.', 'http']
                    if not any(skip in line.lower() for skip in skip_words):
                        return self._clean_text(line)
        
        return "Unknown Title"
    
    def _extract_authors(self, data: Dict) -> str:
        """Extract authors from PDF"""
        
        # Try PDF metadata first
        pdf_author = data.get('pdf_author', '').strip()
        if pdf_author:
            return self._clean_text(pdf_author)
        
        # Try to extract from first page text
        first_page = data.get('first_page_text', '') or data.get('plumber_first_page', '')
        
        if first_page:
            # Common author patterns
            author_patterns = [
                r'(?i)authors?[:\s]+([^\n]+)',
                r'(?i)by[:\s]+([^\n]+)',
                r'([A-Z][a-z]+ [A-Z][a-z]+(?:,\s*[A-Z][a-z]+ [A-Z][a-z]+)*)'  # Name patterns
            ]
            
            for pattern in author_patterns:
                matches = re.findall(pattern, first_page)
                if matches:
                    authors = matches[0] if isinstance(matches[0], str) else matches[0][0]
                    if len(authors) < 200:  # Reasonable length
                        return self._clean_text(authors)
        
        return "Unknown Authors"
    
    def _extract_abstract(self, data: Dict) -> str:
        """Extract abstract from PDF"""
        
        full_text = data.get('full_text_sample', '')
        first_page = data.get('first_page_text', '') or data.get('plumber_first_page', '')
        
        # Debug: log first 500 chars to see what we're working with
        if full_text:
            logger.info(f"🔍 Full text sample (first 500 chars): {full_text[:500]}")
        
        # Try full text first
        if full_text:
            abstract = self._find_abstract_in_text(full_text)
            if abstract:
                return abstract
        
        # Try first page as fallback
        if first_page:
            abstract = self._find_abstract_in_text(first_page)
            if abstract:
                return abstract
        
        return "No abstract available"
    
    def _find_abstract_in_text(self, text: str) -> Optional[str]:
        """Find abstract in given text using multiple patterns"""
        
        # Enhanced abstract patterns (including textbook patterns)
        abstract_patterns = [
            # Standard abstract patterns
            r'(?i)abstract[:\s]+(.*?)(?=\n\s*\n|\n\s*(?:keywords|introduction|1\.|i\.|key words))',
            r'(?i)summary[:\s]+(.*?)(?=\n\s*\n|\n\s*(?:keywords|introduction|1\.|i\.))',
            
            # More flexible patterns
            r'(?i)abstract[:\s\n]+(.*?)(?=\n\s*(?:keywords|introduction|1\s|i\s|key words))',
            r'(?i)abstract[:\s\n]+(.*?)(?=\n\s*[A-Z][a-z]+:)',  # Next section header
            
            # Look for paragraph after "Abstract" keyword
            r'(?i)abstract[:\s\n]+([^.]+\.[^.]+\.)',  # At least 2 sentences
            
            # Academic paper patterns
            r'(?i)(?:abstract|summary)[:\s\n]+((?:[A-Z][^.!?]*[.!?]\s*){2,})',  # Multiple sentences starting with capital
            
            # Textbook patterns - Preface
            r'(?i)preface[:\s\n]+(.*?)(?=\n\s*(?:acknowledgments?|contents|chapter|introduction))',
            r'(?i)preface[:\s\n]+((?:[A-Z][^.!?]*[.!?]\s*){2,})',  # Multiple sentences in preface
            
            # Textbook patterns - Introduction/Overview
            r'(?i)(?:introduction|overview)[:\s\n]+(.*?)(?=\n\s*(?:chapter|contents|1\.))',
            r'(?i)(?:this book|this text)[^.]*\.([^.]*\.){1,3}',  # Description of the book
            
            # Publisher description patterns
            r'(?i)(?:description|overview)[:\s\n]+((?:[A-Z][^.!?]*[.!?]\s*){2,})',
        ]
        
        for pattern in abstract_patterns:
            matches = re.findall(pattern, text, re.DOTALL | re.MULTILINE)
            if matches:
                abstract = matches[0].strip()
                # Clean and validate
                abstract = re.sub(r'\s+', ' ', abstract)  # Normalize whitespace
                abstract = abstract.replace('\n', ' ')
                
                # Check if it looks like a real abstract
                if 20 < len(abstract) < 3000:  # More flexible length
                    # Additional quality checks
                    if not self._is_likely_abstract(abstract):
                        continue
                    
                    logger.info(f"✅ Found abstract: {abstract[:100]}...")
                    return self._clean_text(abstract)
        
        return None
    
    def _is_likely_abstract(self, text: str) -> bool:
        """Check if text is likely to be an abstract"""
        text_lower = text.lower()
        
        # Skip if it contains common non-abstract indicators
        skip_indicators = [
            'page', 'figure', 'table', 'chapter', 'section',
            'copyright', '©', 'isbn', 'doi:', 'arxiv:', 'www.',
            'http', 'published', 'journal', 'conference'
        ]
        
        for indicator in skip_indicators:
            if indicator in text_lower:
                return False
        
        # Positive indicators for abstracts/descriptions
        positive_indicators = [
            # Academic paper indicators
            'this paper', 'this study', 'we present', 'we propose',
            'this work', 'we show', 'results show', 'method',
            'approach', 'algorithm', 'analysis', 'research',
            
            # Textbook indicators
            'this book', 'this text', 'this edition', 'students',
            'readers', 'course', 'chapter', 'covers', 'provides',
            'designed', 'comprehensive', 'introduction', 'concepts'
        ]
        
        positive_count = sum(1 for indicator in positive_indicators if indicator in text_lower)
        
        # Should have at least one positive indicator or be reasonably long
        return positive_count > 0 or len(text) > 100
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        
        # Remove common PDF artifacts
        text = re.sub(r'[^\x00-\x7F]+', '', text)  # Remove non-ASCII
        text = re.sub(r'\s*\n\s*', ' ', text)  # Normalize line breaks
        
        return text[:500]  # Limit length
    
    def _create_fallback_metadata(self, pdf_path: str) -> Dict[str, str]:
        """Create fallback metadata when extraction fails"""
        filename = os.path.basename(pdf_path)
        return {
            'title': f"Document: {filename}",
            'authors': "Unknown Authors",
            'abstract': "Metadata extraction failed",
            'pdf_path': filename,
            'page_count': 0,
            'file_size': 0,
            'extraction_date': datetime.now().isoformat()
        }
    
    def add_to_csv(self, metadata: Dict[str, str]) -> bool:
        """Add extracted metadata to papers.csv"""
        try:
            # Generate new ID
            new_id = self._get_next_id()
            
            # Prepare row data
            row_data = {
                'id': new_id,
                'title': metadata.get('title', 'Unknown Title'),
                'authors': metadata.get('authors', 'Unknown Authors'),
                'abstract': metadata.get('abstract', 'No abstract available'),
                'pdf_path': f"papers/{metadata.get('pdf_path', '')}"
            }
            
            # Check if CSV exists and has headers
            csv_exists = os.path.exists(self.csv_file)
            
            with open(self.csv_file, 'a', newline='', encoding='utf-8') as csvfile:
                fieldnames = ['id', 'title', 'authors', 'abstract', 'pdf_path']
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                # Write header if file is new
                if not csv_exists:
                    writer.writeheader()
                
                writer.writerow(row_data)
            
            logger.info(f"✅ Added to CSV: ID {new_id} - {row_data['title']}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Failed to add to CSV: {e}")
            return False
    
    def _get_next_id(self) -> int:
        """Get the next available ID for the CSV"""
        try:
            if not os.path.exists(self.csv_file):
                return 1
            
            with open(self.csv_file, 'r', encoding='utf-8') as csvfile:
                reader = csv.DictReader(csvfile)
                max_id = 0
                for row in reader:
                    try:
                        max_id = max(max_id, int(row['id']))
                    except (ValueError, KeyError):
                        continue
                return max_id + 1
                
        except Exception as e:
            logger.warning(f"⚠️ Could not determine next ID: {e}")
            return 1
    
    def process_pdf_file(self, pdf_path: str) -> bool:
        """Complete processing pipeline for a PDF file"""
        try:
            logger.info(f"🚀 Starting PDF processing: {pdf_path}")
            
            # Extract metadata
            metadata = self.extract_pdf_metadata(pdf_path)
            
            # Add to CSV
            success = self.add_to_csv(metadata)
            
            if success:
                logger.info(f"🎉 Successfully processed: {pdf_path}")
                return True
            else:
                logger.error(f"❌ Failed to process: {pdf_path}")
                return False
                
        except Exception as e:
            logger.error(f"❌ Error processing {pdf_path}: {e}")
            return False
