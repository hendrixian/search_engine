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
