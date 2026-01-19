import os
import time
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import trafilatura

class WebScraper:
    """
    Robust web scraper with caching, rate limiting and error handling
    """
    def __init__(self, cache_dir: str='data/scraped_content', cache_expiry_days: int=7, request_delay: float=2.0, timeout: int=30000, headless: bool=True):
        """
        Initialize the scraper
        """
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.expiry = cache_expiry_days
        self.request_delay = request_delay
        self.timeout = timeout
        self.headless = headless
        self.last_request_time = 0

    def _rate_limit(self):
        """
        Enforce rate limiting between requests
        """
        elapsed = time.time() - self.last_request_time
        if elapsed < self.request_delay:
            time.sleep(self.request_delay - elapsed)
        self.last_request_time = time.time()

    def _get_cache_path(self, url: str) -> Path:
        """
        Generate cache file path from url
        """
        url_hash = hashlib.md5(url.encode()).hexdigest()
        domain = urlparse(url).netloc.replace('.', '_')
        return self.cache_dir / f"{domain}_{url_hash}.json"
    
    def _is_cache_valid(self, cache_path: Path) -> bool:
        """
        Check if cached content is still valid
        """
        if not cache_path.exists():
            return False
        file_time = datetime.fromtimestamp(cache_path.stat().st_mtime)
        expiry_time = datetime.now() - timedelta(days=self.expiry)

        return file_time > expiry_time
    
    def _load_from_cache(self, url: str) -> Optional[Dict]:
        """
        Load content if cache valid
        """
        cache_path = self._get_cache_path(url)
        if self._is_cache_valid(cache_path):
            try:
                with open(cache_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    print(f'Loaded data from cache: {url}')
                    return data
            except Exception as e:
                print(f'Cache read error: {e}')
                return None
            
        return None
    
    def _save_to_cache(self, url: str, data: Dict):
        """
        Save content to cache
        """
        cache_path = self._get_cache_path(url)
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"Saved to cache: {url}")
        except Exception as e:
            print(f'Cache writing error: {e}')

    def scrape_page(self, url: str, use_cache: bool = True, wait_for_selector: Optional[str] = None) -> Optional[Dict[str, any]]:
        """
        Scrape a single page and extract clean content
        """
        if use_cache:
            cached = self._load_from_cache(url)
            if cached:
                return cached
            
        self._rate_limit()
        result = {
            'url': url,
            'html': None,
            'text': None,
            'title': None,
            'scraped_at': datetime.now().isoformat(),
            'success': False,
            'error': None
        }

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=self.headless)
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                )
                page = context.new_page()

                print(f'Fetching: {url}')
                response = page.goto(url, wait_until='domcontentloaded', timeout = self.timeout)
                if response.status != 200:
                    result['error'] = f"HTTP {response.status}"
                    return result
                
                if wait_for_selector: # wait if specific content is required
                    page.wait_for_selector(wait_for_selector, timeout=self.timeout)

                else:
                    page.wait_for_selector('body', timeout = self.timeout)
                
                # get content
                html = page.content()
                title = page.title()
                browser.close()

                # extract clean text 
                clean_text  = trafilatura.extract(
                    html, include_comments=False, include_tables=True, no_fallback=False
                )

                if not clean_text:
                    soup = BeautifulSoup(html, 'html.parser')
                    # remove script and style elements
                    for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                        script.decompose()
                    clean_text = soup.get_text(separator='\n', strip=True)

                result['html'] = html
                result['text'] = clean_text
                result['title'] = title
                result['success'] = True

                print(f'Successfully scraped: {url} ({len(clean_text)} chars)')

                if use_cache:
                    self._save_to_cache(url, result)

                return result
            
        except PlaywrightTimeout:
            result['error'] = 'Timeout: Page took too long to load'
            print(f'Timeout: {url}')

        except Exception as e:
            result['error'] = str(e)
            print(f'Error scraping {url}: {e}')

        return result
    
    def scrape_multiple(self, urls: List[str], use_cache: bool = True) -> Dict[str, Dict]:
        """
        Scrape multiple urls with rate limiting
        """
        results = {}
        for i, url in enumerate(urls, 1):
            print(f'\n[{i}/{len(urls)}] Processing: {url}')
            result = self.scrape_page(url, use_cache=use_cache)
            results[url] = result

        return results
    
    def extract_links(self, html: str, base_url: str) -> List[str]:
        """
        Extract all links from html
        """
        soup = BeautifulSoup(html, 'html.parser')
        links = []
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            absolute_url = urljoin(base_url, href)
            links.append(absolute_url)

        return list(set(links))
    

