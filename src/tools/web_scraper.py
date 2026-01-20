import os
import time
import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List
from urllib.parse import urljoin, urlparse
import asyncio
import sys
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from bs4 import BeautifulSoup
import trafilatura


class WebScraper:
    """
    Robust web scraper with caching, rate limiting and error handling
    """
    def __init__(self, cache_dir: str='data/scraped_content', cache_expiry_days: int=7, request_delay: float=2.0, timeout: int=15000, headless: bool=True):
        """
        Initialize the scraper

        Args:
            timeout: Page load timeout in milliseconds (default 15000ms = 15 seconds)
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

    def scrape_page(
        self,
        url: str,
        use_cache: bool = True,
        wait_for_selector: Optional[str] = None,
        wait_for_js: bool = False,
        scroll_page: bool = False,
        extra_wait_ms: int = 0
    ) -> Dict:
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
            print(f'Fetching: {url}')
            js_mode = " (JS rendering)" if wait_for_js else ""
            print(f'  ├─ Mode: Playwright{js_mode}')

            with sync_playwright() as p:
                print(f'  ├─ Launching browser...')
                browser = p.chromium.launch(
                    headless=self.headless,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                        '--no-sandbox'
                    ]
                )
                context = browser.new_context(
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    viewport={'width': 1920, 'height': 1080},
                    locale='en-US',
                    timezone_id='America/New_York',
                    permissions=['geolocation'],
                    extra_http_headers={
                        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                        'Accept-Language': 'en-US,en;q=0.9',
                        'Accept-Encoding': 'gzip, deflate, br',
                        'DNT': '1',
                        'Connection': 'keep-alive',
                        'Upgrade-Insecure-Requests': '1'
                    }
                )
                page = context.new_page()

                # add stealth JavaScript to hide automation
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {
                        get: () => undefined
                    });

                    // Hide Chrome automation
                    window.navigator.chrome = {
                        runtime: {}
                    };

                    // Mock plugins and permissions
                    Object.defineProperty(navigator, 'plugins', {
                        get: () => [1, 2, 3, 4, 5]
                    });

                    Object.defineProperty(navigator, 'languages', {
                        get: () => ['en-US', 'en']
                    });
                """)

                # choose wait strategy based on JS rendering needs
                wait_strategy = 'networkidle' if wait_for_js else 'domcontentloaded'
                print(f'  ├─ Navigating (wait: {wait_strategy})...')

                # Try with preferred wait strategy, fallback if timeout
                response = None
                try:
                    response = page.goto(url, wait_until=wait_strategy, timeout=self.timeout)
                except PlaywrightTimeout:
                    if wait_strategy == 'networkidle':
                        # networkidle can timeout on slow sites, fallback to domcontentloaded
                        print(f'  ├─ ⚠️ Networkidle timeout, trying domcontentloaded...')
                        try:
                            response = page.goto(url, wait_until='domcontentloaded', timeout=self.timeout)
                        except PlaywrightTimeout:
                            result['error'] = f"Timeout ({self.timeout}ms) on both networkidle and domcontentloaded"
                            print(f'  └─ ❌ Timeout error: {result["error"]}')
                            browser.close()
                            return result
                    else:
                        result['error'] = f"Timeout ({self.timeout}ms)"
                        print(f'  └─ ❌ Timeout error')
                        browser.close()
                        return result

                if response is None:
                    result['error'] = "No response from server"
                    print(f'  └─ ❌ No response')
                    browser.close()
                    return result

                # accept various success codes
                if response.status >= 400:
                    result['error'] = f"HTTP {response.status}"
                    print(f'  └─ ❌ HTTP {response.status}')
                    browser.close()
                    return result

                print(f'  ├─ Response: HTTP {response.status}')

                # wait for specific selector if provided
                if wait_for_selector:
                    print(f'  ├─ Waiting for selector: {wait_for_selector}')
                    try:
                        page.wait_for_selector(wait_for_selector, timeout=self.timeout)
                    except PlaywrightTimeout:
                        print(f'  ├─ ⚠️ Selector not found, continuing anyway')
                else:
                    print(f'  ├─ Waiting for body...')
                    page.wait_for_selector('body', timeout=self.timeout)

                # scroll page to trigger lazy loading (useful for job listings)
                if scroll_page:
                    print(f'  ├─ Scrolling page to load dynamic content...')
                    page.evaluate('''
                        async () => {
                            await new Promise((resolve) => {
                                let totalHeight = 0;
                                const distance = 300;
                                const timer = setInterval(() => {
                                    window.scrollBy(0, distance);
                                    totalHeight += distance;
                                    if (totalHeight >= document.body.scrollHeight) {
                                        clearInterval(timer);
                                        resolve();
                                    }
                                }, 100);
                                // Safety timeout
                                setTimeout(() => { clearInterval(timer); resolve(); }, 5000);
                            });
                        }
                    ''')
                    # wait a bit after scrolling for content to load
                    page.wait_for_timeout(1000)

                # extra wait for JS rendering
                if extra_wait_ms > 0:
                    print(f'  ├─ Extra wait: {extra_wait_ms}ms')
                    page.wait_for_timeout(extra_wait_ms)

                # get content
                print(f'  ├─ Extracting content...')
                html = page.content()
                title = page.title()
                browser.close()
                print(f'  ├─ Browser closed')

                # extract clean text 
                print(f'  ├─ Parsing with Trafilatura...')
                clean_text = trafilatura.extract(
                    html, include_comments=False, include_tables=True, no_fallback=False
                )

                if not clean_text:
                    print(f'  ├─ Trafilatura failed, using BeautifulSoup...')
                    soup = BeautifulSoup(html, 'html.parser')
                    for script in soup(['script', 'style', 'nav', 'footer', 'header']):
                        script.decompose()
                    clean_text = soup.get_text(separator='\n', strip=True)

                # check for 404 content even if status was 200
                if clean_text and title:
                    title_lower = title.lower()
                    text_lower = clean_text[:500].lower()  # check first 500 chars

                    # common 404 patterns
                    not_found_patterns = [
                        '404', 'not found', 'page not found', 'page doesn\'t exist',
                        'can\'t find', 'cannot find', 'no longer available',
                        'sorry, the page', 'error 404'
                    ]

                    # check if multiple patterns match (stronger signal)
                    matches = sum(1 for pattern in not_found_patterns if pattern in title_lower or pattern in text_lower)

                    if matches >= 2:  # at least 2 patterns = likely 404
                        result['error'] = "404 content detected (page not found)"
                        print(f'  └─ ❌ 404 content detected')
                        return result

                result['html'] = html
                result['text'] = clean_text
                result['title'] = title
                result['success'] = True

                print(f'  └─ ✅ Success: {len(clean_text)} chars extracted')

                if use_cache:
                    self._save_to_cache(url, result)

                return result
            
        except PlaywrightTimeout as e:
            result['error'] = f'Timeout: {str(e)}'
            print(f'  └─ ❌ Timeout error: {e}')

        except Exception as e:
            result['error'] = str(e)
            print(f'  └─ ❌ Error: {e}')
            import traceback
            print(traceback.format_exc())

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
    

