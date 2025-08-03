# web_crawler.py - Enhanced version with better search capabilities

import requests
from bs4 import BeautifulSoup
import time
import random
from urllib.parse import urljoin, quote_plus, urlparse
import re
from typing import List, Dict, Optional
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
import json

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseSearchEngine:
    """Base class for all search engines with common functionality"""
    
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.max_retries = 3
        self.timeout = 15
    
    def delay(self, min_delay=1, max_delay=3):
        """Add random delay to be respectful to servers"""
        time.sleep(random.uniform(min_delay, max_delay))
    
    def clean_text(self, text: str) -> str:
        """Clean and normalize text content"""
        if not text:
            return ""
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        return text
    
    def make_request(self, url: str, retries: int = None) -> Optional[requests.Response]:
        """Make HTTP request with retry logic"""
        if retries is None:
            retries = self.max_retries
            
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    self.delay(2, 5)  # Longer delay on retry
                else:
                    logger.error(f"All retry attempts failed for {url}")
        return None

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

class EngineeringComCrawler(BaseSearchEngine):
    def __init__(self):
        super().__init__("Engineering.com", "https://www.engineering.com")

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        max_results = max_results or 10
        results = []

        # Strategy 1: Browse articles section
        results.extend(self._browse_articles(query, max_results))

        # Strategy 2: DuckDuckGo fallback
        if len(results) < max_results // 2:
            results.extend(self._search_duckduckgo(query, max_results - len(results)))

        # Strategy 3: Internal search fallback (disabled)
        if len(results) < 3:
            logger.warning("Engineering.com internal search disabled due to 403 blocking.")
            # Optionally add stubbed internal call here
            # results.extend(self._search_internal(query, max_results - len(results)))

        return self._deduplicate_results(results)[:max_results]

    def _search_internal(self, query: str, max_results: int) -> List[Dict]:
        """Disabled: Engineering.com blocks internal search (403)."""
        logger.warning("Engineering.com internal search blocked (403). Skipping strategy.")
        return []

    def _browse_articles(self, query: str, max_results: int) -> List[Dict]:
        try:
            results = []
            query_words = set(query.lower().split())
            articles_url = "https://www.engineering.com/articles"
            response = self.make_request(articles_url)

            if not response:
                return []

            soup = BeautifulSoup(response.content, 'html.parser')

            for link in soup.find_all('a', href=True):
                if len(results) >= max_results:
                    break

                href = link.get('href', '')
                title = self.clean_text(link.get_text())

                if (
                    href and title and len(title) > 10 and
                    any(word in title.lower() for word in query_words)
                ):
                    full_url = urljoin(self.base_url, href)
                    results.append({
                        'title': title,
                        'url': full_url,
                        'snippet': f"Engineering topic: {title}",
                        'source': 'Engineering.com'
                    })

            return results

        except Exception as e:
            logger.error(f"Engineering.com article browsing failed: {e}")
            return []

    def _search_duckduckgo(self, query: str, max_results: int) -> List[Dict]:
        try:
            search_query = f"site:engineering.com {query}"
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

                    if 'engineering.com' in url and title:
                        results.append({
                            'title': title,
                            'url': url,
                            'snippet': f"Engineering resource: {title}",
                            'source': 'Engineering.com'
                        })

                except Exception:
                    continue

            return results

        except Exception as e:
            logger.error(f"Engineering.com DuckDuckGo search failed: {e}")
            return []

    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        seen_urls = set()
        unique_results = []
        for result in results:
            url = result['url']
            if url not in seen_urls:
                seen_urls.add(url)
                unique_results.append(result)
        return unique_results

    def extract_content(self, url: str) -> Optional[str]:
        try:
            response = self.make_request(url)
            if not response:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')

            for element in soup(['script', 'style', 'nav', 'header', 'footer', '.ad']):
                element.decompose()

            article = soup.find(['article', 'main', '.article-content', '.post-content'])
            if article:
                text = article.get_text(separator=' ', strip=True)
                return self.clean_text(text)[:3000]

            return None

        except Exception as e:
            logger.error(f"Engineering.com content extraction failed: {e}")
            return None

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

if __name__ == "__main__":
    # Test the crawler
    crawler = MultiSiteCrawler()
    results = crawler.search_web("python machine learning", max_results_per_site=3)
    
    print(f"Found {len(results)} results:")
    for i, result in enumerate(results, 1):
        print(f"\n{i}. {result['title']}")
        print(f"   URL: {result['url']}")
        print(f"   Snippet: {result['snippet'][:100]}...")
        print(f"   Source: {result['source']}")
        
        # Test content extraction
        if i == 1:  # Test first result
            content = crawler.get_article_content(result['url'])
            if content:
                print(f"   Content preview: {content[:200]}...")