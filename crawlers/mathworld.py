# mathworld.py
from crawlers.base_engine import BaseSearchEngine
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class MathWorldCrawler(BaseSearchEngine):
    def __init__(self):
        super().__init__("MathWorld", "https://mathworld.wolfram.com")
    
    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        max_results = max_results or 10  # Ensure it's an int
        """Enhanced MathWorld search"""
        results = []
        
        # Strategy 1: Use Wolfram's search if available
        results.extend(self._search_wolfram_direct(query, max_results))
        
        # Strategy 2: Browse alphabetical index
        if len(results) < max_results // 2:
            results.extend(self._browse_alphabetical(query, max_results - len(results)))
        
        # Strategy 3: Use DuckDuckGo as fallback
        if len(results) < 3:
            results.extend(self._search_duckduckgo(query, max_results - len(results)))
        
        return self._deduplicate_results(results)[:max_results]
    
    def _search_wolfram_direct(self, query: str, max_results: int) -> List[Dict]:
        """Try direct Wolfram search"""
        try:
            search_url = f"https://mathworld.wolfram.com/search/?query={quote_plus(query)}"
            response = self.make_request(search_url)
            
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            
            # Look for search results
            for link in soup.find_all('a', href=True):
                href = link.get('href', '')
                title = self.clean_text(link.get_text())
                
                if (href.startswith('/') and 
                    '.html' in href and 
                    title and 
                    len(title) > 3):
                    
                    full_url = urljoin(self.base_url, href)
                    results.append({
                        'title': title,
                        'url': full_url,
                        'snippet': f"Mathematical concept: {title}",
                        'source': 'MathWorld'
                    })
                    
                    if len(results) >= max_results:
                        break
            
            return results
            
        except Exception as e:
            logger.error(f"MathWorld direct search failed: {e}")
            return []
    
    def _browse_alphabetical(self, query: str, max_results: int) -> List[Dict]:
        """Browse MathWorld's alphabetical index"""
        try:
            results = []
            query_words = set(query.lower().split())
            
            # Get first letter of query to browse relevant section
            first_letter = query[0].upper() if query else 'A'
            index_url = f"https://mathworld.wolfram.com/letters/{first_letter}.html"
            
            response = self.make_request(index_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            for link in soup.find_all('a', href=True):
                if len(results) >= max_results:
                    break
                    
                href = link.get('href', '')
                title = self.clean_text(link.get_text())
                
                if (href.endswith('.html') and 
                    title and 
                    len(title) > 3 and
                    any(word in title.lower() for word in query_words)):
                    
                    full_url = urljoin(self.base_url, href)
                    results.append({
                        'title': title,
                        'url': full_url,
                        'snippet': f"Mathematical topic: {title}",
                        'source': 'MathWorld'
                    })
            
            return results
            
        except Exception as e:
            logger.error(f"MathWorld alphabetical browsing failed: {e}")
            return []
    
    def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        """DuckDuckGo search for MathWorld"""
        try:
            search_query = f"site:mathworld.wolfram.com {query}"
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(search_query)}"
            
            response = self.make_request(search_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            
            for result_div in soup.find_all('div', class_='result')[:max_results]:
                try:
                    title_elem = result_div.find('a', class_='result__a')
                    if not title_elem:
                        continue
                    
                    title = self.clean_text(title_elem.get_text())
                    url = title_elem.get('href', '')
                    
                    if 'mathworld.wolfram.com' in url and title:
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': f"Mathematical reference: {title}",
                            'source': 'MathWorld'
                        })
                
                except Exception as e:
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"MathWorld DuckDuckGo search failed: {e}")
            return []
    
    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicates"""
        seen_urls = set()
        unique_results = []
        
        for result in results:
            url = result['url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        return unique_results
    
    def extract_content(self, url: str) -> Optional[str]:
        """Extract MathWorld article content"""
        try:
            response = self.make_request(url)
            if not response:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # MathWorld specific content extraction
            main = soup.find('div', {'id': 'mainContent'}) or soup.find('main')
            if main:
                # Remove navigation and ads
                for element in main(['script', 'style', '.ad', '.navigation']):
                    element.decompose()
                
                text = main.get_text(separator=' ', strip=True)
                return self.clean_text(text)[:3000]
            
            return None
            
        except Exception as e:
            logger.error(f"MathWorld content extraction failed: {e}")
            return None
