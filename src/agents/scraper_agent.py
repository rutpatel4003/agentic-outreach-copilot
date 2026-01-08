from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
from datetime import datetime

from ..tools.web_scraper import WebScraper

class ScraperAgent:
    """
    Intelligent agent from scraping company websites
    Tries multiple URL patterns, handles errors, returns structured data
    """
    PAGE_PATTERNS = {
        'about': [
            '/about',
            '/about-us',
            '/company',
            '/who-we-are',
            '/our-story'
        ],
        'careers': [
            '/careers',
            '/jobs',
            '/join-us',
            '/work-with-us',
            '/opportunities'
        ],
        'news': [
            '/news',
            '/blog',
            '/press',
            '/newsroom',
            '/media'
        ],
        'team': [
            '/team',
            '/leadership',
            '/our-team',
            '/people'
        ]
    }

    def __init__(self, cache_dir: str='data/scraped_content', request_delay: float=2.0, max_retries: int=2):
        """
        Initialize the scraper agent
        """
        self.scraper = WebScraper(cache_dir=cache_dir, request_delay=request_delay)
        self.max_retries = max_retries
    
    def _normalize_url(self, url: str) -> str:
        """
        Ensure URL has proper format
        """
        if not url.startswith(('https://', 'http://')):
            url = 'https://' + url
        return url.rstrip('/')
    
    def _try_url_patterns(self, base_url: str, patterns: List[str]) -> Optional[Dict]:
        """
        Try multiple URL patterns until one works
        """
        for pattern in patterns:
            url = urljoin(base_url + '/', pattern.lstrip('/'))
            result = self.scraper.scrape_page(url)
            if result['success'] and result['text'] and len(result['text']) > 200:
                return result
            
        return None
    
    def scrape_company(self, company_url: str, pages_to_scrape: Optional[List[str]] = None) -> Dict:
        """
        Scrape multiple pages from a company website
        """
        company_url = self._normalize_url(company_url)

        if pages_to_scrape is None:
            pages_to_scrape = list(self.PAGE_PATTERNS.keys())

        result = {
            'company_url' : company_url,
            'company_name': self._extract_company_name(company_url),
            'scraped_at': datetime.now().isoformat(),
            'pages': {},
            'success_count': 0,
            'failed_pages': [],
            'metadata': {}
        }
        print(f"\n{'='*60}")
        print(f"Scraping company: {result['company_name']}")
        print(f"{'='*60}")

        for page_type in pages_to_scrape:
            if page_type not in self.PAGE_PATTERNS:
                print(f'Unknown page type: {page_type}')
                continue

            print(f"\nSearching for {page_type} page")
            patterns = self.PAGE_PATTERNS[page_type]
            scrape_result = self._try_url_patterns(company_url, patterns)

            if scrape_result:
                result['pages'][page_type] = {
                    'url': scrape_result['url'],
                    'title': scrape_result['title'],
                    'text': scrape_result['text'],
                    'text_length': len(scrape_result['text']),
                    'scraped_at': scrape_result['scraped_at']
                }

                result['success_count'] += 1
                print(f"Found {page_type} page: {scrape_result['url']}")
            else:
                result['failed_pages'].append(page_type)
                print(f'Could not find {page_type} page')

        result['metadata'] = {
            'total_pages_attempted': len(pages_to_scrape),
            'successful_pages': result['success_count'],
            'failed_pages': len(result['failed_pages']),
            'success_rate': f"{(result['success_count'] / len(pages_to_scrape)) * 100:.1f}%"
        }

        print(f"\n{'='*60}")
        print(f'Scraping complete: {result['success_count']}/{len(pages_to_scrape)} pages')
        print(f"{'='*60}\n")

        return result
    
    def _extract_company_name(self, url: str) -> str:
        """
        Extract company name from URL
        """
        domain = urlparse(url).netloc
        # remove www. and TLD
        name = domain.replace('www.', '').split('.')[0]
        return name.capitalize()
    
    def get_page_content(self, company_data: Dict, page_type: str) -> Optional[str]:
        """
        Extract text content from a specific page
        """
        if page_type in company_data['pages']:
            return company_data['pages'][page_type]['text']
        return None
    
    def scrape_multiple_companies(self, company_urls: List[str], pages_to_scrape: Optional[List[str]] = None) -> Dict[str, Dict]:
        """
        Scrape multiple companies
        """
        results = {}
        for i, url in enumerate(company_urls, 1):
            print(f"\n\n{'#'*60}")
            print(f"Company {i}/{len(company_urls)}")
            print(f"{'#'*60}")

            company_data = self.scrape_company(url, pages_to_scrape)
            results[url] = company_data

        return results
    