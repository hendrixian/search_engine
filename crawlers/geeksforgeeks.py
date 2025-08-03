# geeksforgeeks.py
from crawlers.base_engine import BaseSearchEngine
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class GeeksforGeeksCrawler(BaseSearchEngine):
    def __init__(self):
        super().__init__("GeeksforGeeks", "https://www.geeksforgeeks.org")
    
    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        max_results = max_results or 10  # Ensure it's an int
        """Enhanced GeeksforGeeks search with multiple strategies"""
        results = []
        
        # Strategy 1: Direct site search
        results.extend(self._search_direct(query, max_results))
        
        # Strategy 2: If not enough results, try DuckDuckGo (less blocking than Google)
        if len(results) < max_results // 2:
            results.extend(self._search_duckduckgo(query, max_results - len(results)))
        
        # Strategy 3: Browse popular categories if still not enough
        if len(results) < 3:
            results.extend(self._browse_categories(query, max_results - len(results)))
        
        return self._deduplicate_results(results)[:max_results]
    
    def _search_direct(self, query: str, max_results: int) -> List[Dict]:
        """Try GeeksforGeeks internal search"""
        try:
            # Try multiple search URL patterns
            search_urls = [
                f"https://www.geeksforgeeks.org/search/{quote_plus(query)}/",
                f"https://www.geeksforgeeks.org/?s={quote_plus(query)}",
            ]
            
            for search_url in search_urls:
                logger.info(f"Trying GeeksforGeeks direct search: {search_url}")
                response = self.make_request(search_url)
                
                if not response:
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                results = []
                
                # Multiple selectors for different page layouts
                selectors = [
                    'article.search-result',
                    '.search-result-item', 
                    'div[data-post-id]',
                    'article',
                    '.post-item',
                    '.article-container',
                    'div.head a[href*="/"]'  # Generic article links
                ]
                
                for selector in selectors:
                    elements = soup.select(selector)
                    if elements:
                        logger.info(f"Found {len(elements)} elements with selector: {selector}")
                        results.extend(self._parse_search_elements(elements, max_results))
                        break
                
                if results:
                    return results[:max_results]
                    
                self.delay()
            
            return []
            
        except Exception as e:
            logger.error(f"Direct search failed: {e}")
            return []
    
    def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        """Use DuckDuckGo which is less likely to block scraping"""
        try:
            search_query = f"site:geeksforgeeks.org {query}"
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(search_query)}"
            
            response = self.make_request(search_url)
            if not response:
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            results = []
            
            # DuckDuckGo result selectors
            for result_div in soup.find_all('div', class_='result')[:max_results]:
                try:
                    title_elem = result_div.find('a', class_='result__a')
                    if not title_elem:
                        continue
                    
                    title = self.clean_text(title_elem.get_text())
                    url = title_elem.get('href', '')
                    
                    # Extract snippet
                    snippet_elem = result_div.find('a', class_='result__snippet')
                    snippet = self.clean_text(snippet_elem.get_text()) if snippet_elem else ""
                    
                    if 'geeksforgeeks.org' in url and title:
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': snippet,
                            'source': 'GeeksforGeeks'
                        })
                
                except Exception as e:
                    logger.warning(f"Error parsing DuckDuckGo result: {e}")
                    continue
            
            return results
            
        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []
    
    def _browse_categories(self, query: str, max_results: int) -> List[Dict]:
        """Browse GeeksforGeeks categories to find relevant articles"""
        try:
            # Popular category pages that might have relevant content
            category_urls = [
                "https://www.geeksforgeeks.org/fundamentals-of-algorithms/",
                "https://www.geeksforgeeks.org/data-structures/",
                "https://www.geeksforgeeks.org/python-programming-language/",
                "https://www.geeksforgeeks.org/java/",
                "https://www.geeksforgeeks.org/machine-learning/",
                "https://www.geeksforgeeks.org/artificial-intelligence/",
            ]
            
            results = []
            query_words = set(query.lower().split())
            
            for category_url in category_urls:
                if len(results) >= max_results:
                    break
                    
                response = self.make_request(category_url)
                if not response:
                    continue
                
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Find article links in the category page
                for link in soup.find_all('a', href=True):
                    if len(results) >= max_results:
                        break
                        
                    href = link.get('href', '')
                    title = self.clean_text(link.get_text())
                    
                    # Check if link seems relevant and is an article
                    if (href.startswith('/') and 
                        len(href.split('/')) > 2 and 
                        title and 
                        len(title) > 10 and
                        any(word in title.lower() for word in query_words)):
                        
                        full_url = urljoin(self.base_url, href)
                        results.append({
                            'title': title,
                            'url': full_url,
                            'snippet': f"From {category_url.split('/')[-2].replace('-', ' ').title()} category",
                            'source': 'GeeksforGeeks'
                        })
                
                self.delay(0.5, 1.5)  # Shorter delay for category browsing
            
            return results
            
        except Exception as e:
            logger.error(f"Category browsing failed: {e}")
            return []
    
    def _parse_search_elements(self, elements, max_results: int) -> List[Dict]:
        """Parse search result elements into standardized format"""
        results = []
        
        for element in elements[:max_results * 2]:  # Parse more than needed to filter later
            try:
                # Extract title
                title = ""
                title_selectors = ['h1', 'h2', 'h3', 'h4', '.title', '.post-title', 'a']
                for selector in title_selectors:
                    title_elem = element.find(selector)
                    if title_elem:
                        title = self.clean_text(title_elem.get_text())
                        break
                
                if not title or len(title) < 5:
                    continue
                
                # Extract URL
                url = ""
                link_elem = element.find('a', href=True)
                if link_elem:
                    url = urljoin(self.base_url, link_elem['href'])
                else:
                    continue
                
                # Extract snippet
                snippet = ""
                snippet_selectors = ['p', '.excerpt', '.description', '.summary', '.content']
                for selector in snippet_selectors:
                    snippet_elem = element.find(selector)
                    if snippet_elem:
                        snippet = self.clean_text(snippet_elem.get_text())[:200]
                        break
                
                results.append({
                    'title': title,
                    'url': url,
                    'snippet': snippet,
                    'source': 'GeeksforGeeks'
                })
                
            except Exception as e:
                logger.warning(f"Error parsing element: {e}")
                continue
        
        return results
    
    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        """Remove duplicate results based on URL"""
        seen_urls = set()
        unique_results = []
        
        for result in results:
            url = result['url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        
        return unique_results
    
    def extract_content(self, url: str) -> Optional[str]:
        """Extract article content with better parsing"""
        try:
            response = self.make_request(url)
            if not response:
                return None
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer', 
                                '.ad', '.advertisement', '.social-share', '.comments']):
                element.decompose()
            
            # Try multiple content selectors
            content_selectors = [
                '.article-container .content',
                'article .content',
                '.post-content',
                '.entry-content',
                'main article',
                '.article-body',
                '[data-article-body]'
            ]
            
            content = ""
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    content = content_elem.get_text(separator=' ', strip=True)
                    break
            
            # Fallback to main content area
            if not content:
                main = soup.find('main') or soup.find('article')
                if main:
                    content = main.get_text(separator=' ', strip=True)
            
            return self.clean_text(content)[:3000] if content else None
            
        except Exception as e:
            logger.error(f"Content extraction failed for {url}: {e}")
            return None
