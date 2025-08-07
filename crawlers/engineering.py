# engineering.py
from crawlers.base_engine import BaseSearchEngine
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urljoin
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

class EngineeringComCrawler(BaseSearchEngine):
    def __init__(self):
        super().__init__("Engineering.com", "https://www.engineering.com")

    def search(self, query: str, max_results: Optional[int] = None) -> List[Dict]:
        max_results = max_results or 10
        results = []
        
        logger.info(f"Searching Engineering.com for: {query}")
        
        # Strategy 1: Try to find the actual site structure first
        site_results = self._discover_site_structure(query, max_results)
        results.extend(site_results)
        
        # Strategy 2: DuckDuckGo search (without custom headers)
        if len(results) < 3:
            ddg_results = self._search_duckduckgo_simple(query, max_results - len(results))
            results.extend(ddg_results)
        
        # Strategy 3: Try alternative search engines
        if len(results) < 3:
            alt_results = self._search_alternative(query, max_results - len(results))
            results.extend(alt_results)

        results = self._deduplicate_results(results)[:max_results]
        
        if not results:
            logger.warning(f"Engineering.com search returned no results for query: {query}")
        else:
            logger.info(f"Engineering.com found {len(results)} results")

        return results

    def _discover_site_structure(self, query: str, max_results: int) -> List[Dict]:
        """Try to discover the actual structure of engineering.com"""
        try:
            results = []
            
            # First, let's see what's actually on the homepage
            logger.info("Discovering Engineering.com site structure...")
            response = self.make_request("https://www.engineering.com")
            
            if not response:
                logger.warning("Could not access engineering.com homepage")
                return []
            
            soup = BeautifulSoup(response.content, 'html.parser')
            
            # Look for navigation links, article links, etc.
            all_links = soup.find_all('a', href=True)
            logger.info(f"Found {len(all_links)} links on homepage")
            
            # Find potential article/content URLs
            content_urls = set()
            for link in all_links:
                href = link.get('href', '')
                if href:
                    # Convert relative URLs to absolute
                    if href.startswith('/'):
                        href = urljoin(self.base_url, href)
                    
                    # Look for URLs that might contain articles/content
                    if ('engineering.com' in href and 
                        any(path in href.lower() for path in [
                            'article', 'news', 'blog', 'post', 'story', 
                            'content', 'resources', 'technology', 'manufacturing'
                        ])):
                        content_urls.add(href)
            
            logger.info(f"Found {len(content_urls)} potential content URLs")
            
            # Try a few of these URLs to see if they work
            query_words = query.lower().split()
            for url in list(content_urls)[:5]:  # Try first 5 URLs
                try:
                    logger.info(f"Trying content URL: {url}")
                    response = self.make_request(url)
                    if response:
                        soup = BeautifulSoup(response.content, 'html.parser')
                        
                        # Look for articles/links on this page
                        page_links = soup.find_all('a', href=True)
                        for link in page_links:
                            if len(results) >= max_results:
                                break
                                
                            title = self.clean_text(link.get_text().strip())
                            href = link.get('href', '')
                            
                            if (title and len(title) > 10 and 
                                any(word in title.lower() for word in query_words)):
                                
                                full_url = urljoin(self.base_url, href) if href.startswith('/') else href
                                results.append({
                                    'title': title,
                                    'url': full_url,
                                    'snippet': f"Engineering content: {title}",
                                    'source': 'Engineering.com'
                                })
                                
                        if results:
                            break  # Found some results, no need to continue
                            
                except Exception as e:
                    logger.debug(f"Error with URL {url}: {e}")
                    continue
            
            logger.info(f"Site structure discovery returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Site structure discovery failed: {e}")
            return []

    def _search_duckduckgo_simple(self, query: str, max_results: int) -> List[Dict]:
        """Simple DuckDuckGo search without custom headers"""
        try:
            search_query = f"site:engineering.com {query}"
            search_url = f"https://duckduckgo.com/html/?q={quote_plus(search_query)}"
            
            logger.info(f"Trying DuckDuckGo search: {search_url}")
            
            # Use the existing make_request method without headers
            response = self.make_request(search_url)
            if not response:
                logger.warning("DuckDuckGo request failed")
                return []

            soup = BeautifulSoup(response.content, 'html.parser')
            results = []

            # Look for any links to engineering.com
            all_links = soup.find_all('a', href=True)
            logger.info(f"DuckDuckGo returned {len(all_links)} total links")
            
            engineering_links = 0
            for link in all_links:
                href = link.get('href', '')
                title = self.clean_text(link.get_text().strip())
                
                if 'engineering.com' in href and title and len(title) > 5:
                    engineering_links += 1
                    
                    # Skip DuckDuckGo redirect URLs
                    if '/l/?kh=' in href or 'duckduckgo.com' in href:
                        continue
                    
                    results.append({
                        'title': title,
                        'url': href,
                        'snippet': f"Engineering resource: {title}",
                        'source': 'Engineering.com'
                    })
                    
                    if len(results) >= max_results:
                        break
            
            logger.info(f"Found {engineering_links} engineering.com links, kept {len(results)} results")
            return results

        except Exception as e:
            logger.error(f"DuckDuckGo search failed: {e}")
            return []

    def _search_alternative(self, query: str, max_results: int) -> List[Dict]:
        """Try alternative search methods"""
        try:
            results = []
            
            # Try Bing search
            search_query = f"site:engineering.com {query}"
            bing_url = f"https://www.bing.com/search?q={quote_plus(search_query)}"
            
            logger.info(f"Trying Bing search: {bing_url}")
            response = self.make_request(bing_url)
            
            if response:
                soup = BeautifulSoup(response.content, 'html.parser')
                
                # Look for Bing result links
                for link in soup.find_all('a', href=True):
                    href = link.get('href', '')
                    title = self.clean_text(link.get_text().strip())
                    
                    if ('engineering.com' in href and title and len(title) > 5 and
                        not any(skip in href for skip in ['bing.com', 'microsoft.com'])):
                        
                        results.append({
                            'title': title,
                            'url': href,
                            'snippet': f"Engineering resource: {title}",
                            'source': 'Engineering.com'
                        })
                        
                        if len(results) >= max_results:
                            break
            
            logger.info(f"Alternative search returned {len(results)} results")
            return results
            
        except Exception as e:
            logger.error(f"Alternative search failed: {e}")
            return []

    def _deduplicate_results(self, results: List[Dict]) -> List[Dict]:
        seen_urls = set()
        seen_titles = set()
        unique_results = []
        
        for result in results:
            url = result['url']
            title = result['title'].lower()
            
            if url not in seen_urls and title not in seen_titles:
                seen_urls.add(url)
                seen_titles.add(title)
                unique_results.append(result)
                
        return unique_results

    def extract_content(self, url: str) -> Optional[str]:
        try:
            response = self.make_request(url)
            if not response:
                return None

            soup = BeautifulSoup(response.content, 'html.parser')

            # Remove unwanted elements
            for element in soup(['script', 'style', 'nav', 'header', 'footer']):
                element.decompose()

            # Try different content selectors
            content_selectors = [
                'article',
                'main', 
                '[class*="content"]',
                '[class*="article"]',
                '[class*="post"]',
                'body'
            ]
            
            content = None
            for selector in content_selectors:
                content_elem = soup.select_one(selector)
                if content_elem:
                    text = content_elem.get_text(separator=' ', strip=True)
                    if len(text) > 100:  # Make sure we got substantial content
                        content = text
                        break
            
            return self.clean_text(content)[:3000] if content else None

        except Exception as e:
            logger.error(f"Content extraction failed for {url}: {e}")
            return None