# base_engine.py
import requests
import time
import random
import re
import logging
from urllib.parse import urljoin
from typing import Optional

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BaseSearchEngine:
    def __init__(self, name: str, base_url: str):
        self.name = name
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)...',
            'Accept': 'text/html,...',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
        self.max_retries = 3
        self.timeout = 15

    def delay(self, min_delay=1, max_delay=3):
        time.sleep(random.uniform(min_delay, max_delay))

    def clean_text(self, text: str) -> str:
        return re.sub(r'\s+', ' ', text.strip()) if text else ""

    def make_request(self, url: str, retries: int = None) -> Optional[requests.Response]:
        retries = retries or self.max_retries
        for attempt in range(retries):
            try:
                response = self.session.get(url, timeout=self.timeout)
                response.raise_for_status()
                return response
            except requests.RequestException as e:
                logger.warning(f"Request failed (attempt {attempt + 1}/{retries}): {e}")
                if attempt < retries - 1:
                    self.delay(2, 5)
                else:
                    logger.error(f"All retry attempts failed for {url}")
        return None
