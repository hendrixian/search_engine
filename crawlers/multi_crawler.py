# multi_crawler.py
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from bs4 import BeautifulSoup
import requests
import re

from crawlers.geeksforgeeks import GeeksforGeeksCrawler
from crawlers.mathworld import MathWorldCrawler
from crawlers.engineering import EngineeringComCrawler


logger = logging.getLogger(__name__)

class MultiSiteCrawler:
    def __init__(self):
        self.crawlers = {
            'GeeksforGeeks': GeeksforGeeksCrawler(),
            'MathWorld': MathWorldCrawler(),
            'Engineering.com': EngineeringComCrawler()
        }
        self.max_workers = 3  # For parallel searching
    
    def search_web(self, query: str, max_results_per_site: Optional[int] = None) -> List[Dict]:
        """Search all sites in parallel and combine results"""
        all_results = []
        
        # Use ThreadPoolExecutor for parallel searching
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit search tasks for all crawlers
            future_to_crawler = {
                executor.submit(crawler.search, query, max_results_per_site): name
                for name, crawler in self.crawlers.items()
            }
            
            # Collect results as they complete
            for future in as_completed(future_to_crawler):
                crawler_name = future_to_crawler[future]
                try:
                    results = future.result(timeout=30)  # 30 second timeout per crawler
                    logger.info(f"{crawler_name} returned {len(results)} results")
                    all_results.extend(results)
                except Exception as e:
                    logger.error(f"{crawler_name} search failed: {e}")
        
        # Sort results by relevance (you can implement custom scoring here)
        return self._rank_results(all_results, query)
    
    def _rank_results(self, results: List[Dict], query: str) -> List[Dict]:
        """Rank results by relevance to query"""
        query_words = set(query.lower().split())
        
        def calculate_score(result):
            title = result.get('title', '').lower()
            snippet = result.get('snippet', '').lower()
            
            # Simple scoring based on query word matches
            title_matches = sum(1 for word in query_words if word in title)
            snippet_matches = sum(1 for word in query_words if word in snippet)
            
            # Weight title matches more heavily
            score = title_matches * 3 + snippet_matches
            
            # Bonus for exact phrase matches
            if query.lower() in title:
                score += 5
            if query.lower() in snippet:
                score += 2
            
            return score
        
        # Sort by score (descending)
        ranked_results = sorted(results, key=calculate_score, reverse=True)
        
        # Log ranking info
        for i, result in enumerate(ranked_results[:5]):
            logger.info(f"Rank {i+1}: {result['title'][:50]}... (Score: {calculate_score(result)})")
        
        return ranked_results
    
    def get_article_content(self, url: str) -> Optional[str]:
        """Extract content from any supported site"""
        for name, crawler in self.crawlers.items():
            if crawler.base_url.replace('https://', '').replace('www.', '') in url:
                return crawler.extract_content(url)
        
        # Fallback to generic extraction
        return self._generic_content_extraction(url)
    
    def _generic_content_extraction(self, url: str) -> Optional[str]:
        """Generic content extraction for unsupported sites"""
        try:
            response = requests.get(url, timeout=10, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            })
            response.raise_for_status()
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', '.ad']):
                tag.decompose()
            
            # Try to find main content
            main = soup.find(['main', 'article', '.content', '.post']) or soup.body
            if main:
                text = main.get_text(separator=' ', strip=True)
                return re.sub(r'\s+', ' ', text)[:3000]
            
            return None
            
        except Exception as e:
            logger.error(f"Generic extraction failed: {e}")
            return None
