from typing import Dict, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from datetime import datetime
from dataclasses import dataclass
import re
import logging
from src.tools.web_scraper import WebScraper
from src.config import config

logger = logging.getLogger(__name__)


@dataclass
class ExtractedContact:
    """Represents a contact extracted from company pages"""
    name: str
    title: Optional[str] = None
    email: Optional[str] = None
    linkedin_url: Optional[str] = None
    source_page: str = "team"
    relevance_score: float = 0.0  # higher = more relevant for job outreach


class ScraperAgent:
    """
    Intelligent agent for scraping company websites with multiple fallback strategies
    """
    
    # strategy 1: subdomain patterns (careers.company.com)
    SUBDOMAIN_PATTERNS = {
        'careers': ['careers', 'jobs', 'join', 'recruiting', 'work'],
        'about': ['about', 'company', 'corporate'],
        'news': ['news', 'blog', 'press', 'media', 'newsroom'],
        'team': ['team', 'leadership', 'people']
    }
    
    # strategy 2: path patterns (/about, /careers, etc.)
    PATH_PATTERNS = {
        'about': [
            '/about',
            '/about-us',
            '/company',
            '/who-we-are',
            '/our-story',
            '/about/overview',
            '/en/about',
            '/en-us/about',
            '/us/en/about'
        ],
        'careers': [
            '/careers',
            '/careers/',
            '/careers/search',
            '/careers/search/',
            '/careers/jobs',
            '/careers/openings',
            '/jobs',
            '/jobs/',
            '/jobs/search',
            '/join-us',
            '/join',
            '/work-with-us',
            '/opportunities',
            '/working-here',
            '/careers/home',
            '/en/careers',
            '/en-us/careers',
            '/us/en/careers',
            '/about/careers',
            '/company/careers',
            '/open-positions',
            '/vacancies'
        ],
        'news': [
            '/news',
            '/blog',
            '/press',
            '/newsroom',
            '/media',
            '/stories',
            '/insights',
            '/en/news',
            '/en-us/news'
        ],
        'team': [
            '/team',
            '/leadership',
            '/our-team',
            '/people',
            '/about/leadership',
            '/company/leadership'
        ]
    }

    # common selectors for job listing containers (helps with js-rendered pages)
    JOB_LISTING_SELECTORS = [
        '[data-testid*="job"]',
        '[class*="job-list"]',
        '[class*="JobList"]',
        '[class*="careers-list"]',
        '[class*="opening"]',
        '[class*="position"]',
        '[class*="vacancy"]',
        '.jobs-container',
        '#jobs-list',
        '[role="list"]',
    ]

    # job titles relevant for outreach (higher relevance = better contact)
    RELEVANT_TITLES = {
        'high': [
            'recruiter', 'recruiting', 'talent acquisition', 'talent partner',
            'hiring manager', 'hr manager', 'human resources', 'people operations',
            'technical recruiter', 'engineering recruiter', 'university recruiter'
        ],
        'medium': [
            'engineering manager', 'eng manager', 'director of engineering',
            'vp of engineering', 'head of engineering', 'tech lead',
            'software manager', 'development manager', 'team lead',
            'cto', 'chief technology officer', 'vp engineering'
        ],
        'low': [
            'ceo', 'founder', 'co-founder', 'president', 'coo',
            'director', 'vice president', 'vp', 'head of'
        ]
    }

    def __init__(
        self,
        cache_dir: Optional[str] = None,
        request_delay: Optional[float] = None,
        max_retries: Optional[int] = None
    ):
        # Use config defaults if not provided
        cache_dir = cache_dir or config.scraper.cache_dir
        request_delay = request_delay if request_delay is not None else config.scraper.rate_limit
        max_retries = max_retries if max_retries is not None else config.scraper.max_retries

        self.scraper = WebScraper(cache_dir=cache_dir, request_delay=request_delay)
        self.max_retries = max_retries
        # default js rendering settings from config
        self._js_rendering = config.scraper.js_rendering
        self._scroll_page = True
        self._js_wait_time = config.scraper.js_wait_time
    
    def _normalize_url(self, url: str) -> str:
        """Ensure url has proper format"""
        if not url.startswith(('https://', 'http://')):
            url = 'https://' + url
        return url.rstrip('/')
    
    def _get_base_domain(self, url: str) -> str:
        netloc = urlparse(url).netloc.lower()
        if netloc.startswith("www."):
            netloc = netloc[4:]

        parts = netloc.split(".")
        # careers.microsoft.com -> microsoft.com
        if len(parts) >= 3:
            return ".".join(parts[-2:])
        return netloc

    
    def _try_subdomain_patterns(
        self, 
        base_domain: str, 
        page_type: str
    ) -> Optional[Dict]:
        """
        Try subdomain patterns: careers.microsoft.com, jobs.microsoft.com, etc.
        """
        if page_type not in self.SUBDOMAIN_PATTERNS:
            return None
        
        for subdomain in self.SUBDOMAIN_PATTERNS[page_type]:
            url = f"https://{subdomain}.{base_domain}"
            result = self.scraper.scrape_page(url)
            
            if result['success'] and result['text'] and len(result['text']) > 200:
                logger.info(f"Found via subdomain: {url}")
                return result
        
        return None
    
    def _try_path_patterns(
        self,
        base_url: str,
        page_type: str,
        use_js_rendering: bool = False
    ) -> Optional[Dict]:
        """
        Try path patterns: /careers, /about, etc.
        """
        if page_type not in self.PATH_PATTERNS:
            return None

        # get js settings (default to true if not set)
        js_rendering = getattr(self, '_js_rendering', True)
        scroll_page = getattr(self, '_scroll_page', True)
        js_wait_time = getattr(self, '_js_wait_time', 3000)

        for pattern in self.PATH_PATTERNS[page_type]:
            url = urljoin(base_url + '/', pattern.lstrip('/'))

            # use js rendering based on settings (especially for careers pages)
            use_js = js_rendering and (page_type == 'careers' or js_rendering)

            if use_js:
                result = self.scraper.scrape_page(
                    url,
                    wait_for_js=True,
                    scroll_page=scroll_page,
                    extra_wait_ms=js_wait_time
                )
            else:
                result = self.scraper.scrape_page(url)

            if result['success'] and result['text'] and len(result['text']) > 200:
                logger.info(f"Found via path: {url}")
                return result

        return None
    
    def _find_links_on_homepage(
        self, 
        homepage_html: str, 
        page_type: str
    ) -> List[str]:
        """
        Parse homepage HTML to find actual links to careers/about pages
        """
        keywords = {
            'careers': ['career', 'job', 'join', 'work with us', 'opportunities'],
            'about': ['about', 'company', 'who we are', 'our story'],
            'news': ['news', 'blog', 'press', 'media', 'newsroom'],
            'team': ['team', 'leadership', 'people', 'our team']
        }
        
        if page_type not in keywords:
            return []
        
        # simple regex to find links
        # format: <a href="...">text containing keywords</a>
        pattern = r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>'
        matches = re.findall(pattern, homepage_html, re.IGNORECASE)
        
        found_links = []
        for href, text in matches:
            text_lower = text.lower()
            if any(kw in text_lower for kw in keywords[page_type]):
                found_links.append(href)
        
        return found_links[:3]  # return top 3 matches
    
    def _scrape_with_fallback(
        self, 
        company_url: str, 
        base_domain: str, 
        page_type: str,
        homepage_html: Optional[str] = None
    ) -> Optional[Dict]:
        """
        Multi-strategy scraping with fallbacks:
        1. Try subdomain patterns (careers.company.com)
        2. Try path patterns (/careers)
        3. Parse homepage for actual links
        """
        logger.info(f"Searching for {page_type} page...")

        # strategy 1: Subdomain patterns
        logger.debug(f"Strategy 1: Trying subdomains...")
        result = self._try_subdomain_patterns(base_domain, page_type)
        if result:
            return result

        # strategy 2: Path patterns
        logger.debug(f"Strategy 2: Trying path patterns...")
        result = self._try_path_patterns(company_url, page_type)
        if result:
            return result

        # strategy 3: Parse homepage for actual links
        if homepage_html:
            logger.debug(f"Strategy 3: Parsing homepage for links...")
            links = self._find_links_on_homepage(homepage_html, page_type)
            
            for link in links:
                # make absolute URL
                if link.startswith('http'):
                    url = link
                else:
                    url = urljoin(company_url + '/', link.lstrip('/'))
                
                result = self.scraper.scrape_page(url)
                if result['success'] and result['text'] and len(result['text']) > 200:
                    logger.info(f"Found via homepage link: {url}")
                    return result

        logger.warning(f"Could not find {page_type} page")
        return None
    
    def scrape_company(
        self,
        company_url: str,
        pages_to_scrape: Optional[List[str]] = None,
        manual_urls: Optional[Dict[str, str]] = None,
        js_rendering: bool = True,
        scroll_page: bool = True,
        js_wait_time: int = 3000
    ) -> Dict:
        """
        Scrape multiple pages from a company website
        """
        # store settings for use in scraping methods
        self._js_rendering = js_rendering
        self._scroll_page = scroll_page
        self._js_wait_time = js_wait_time

        if js_rendering:
            logger.info(f"JS rendering: ON (wait: {js_wait_time}ms, scroll: {scroll_page})")
        else:
            logger.info(f"JS rendering: OFF (fast mode)")
        company_url = self._normalize_url(company_url)
        base_domain = self._get_base_domain(company_url)

        if pages_to_scrape is None:
            pages_to_scrape = ['about', 'careers', 'news', 'team']

        result = {
            'company_url': company_url,
            'company_name': self._extract_company_name(company_url),
            'scraped_at': datetime.now().isoformat(),
            'pages': {},
            'success_count': 0,
            'failed_pages': [],
            'metadata': {}
        }
        
        logger.info(f"{'='*60}")
        logger.info(f"Scraping company: {result['company_name']}")
        logger.info(f"Base domain: {base_domain}")

        # CHECK IF ALL PAGES HAVE MANUAL URLS
        all_manual = manual_urls and all(
            page_type in manual_urls for page_type in pages_to_scrape
        )

        if all_manual:
            logger.info("All pages have manual URLs - skipping auto-discovery")

        logger.info(f"{'='*60}")

        # get homepage only if we need auto-discovery
        homepage_html = None
        if not all_manual:
            logger.info("Fetching homepage for link discovery...")
            try:
                homepage_result = self.scraper.scrape_page(company_url)
                homepage_html = homepage_result.get('html', '') if homepage_result['success'] else None

                if homepage_html:
                    logger.info("Homepage fetched successfully")
                else:
                    logger.warning("Could not fetch homepage - will rely on manual URLs or patterns")
            except Exception as e:
                logger.error(f"Homepage fetch failed: {e}")
                if not manual_urls:
                    logger.warning("No manual URLs provided and homepage failed - scraping may fail")

        # now try to scrape each page type
        for page_type in pages_to_scrape:
            # check if manual url provided
            if manual_urls and page_type in manual_urls:
                manual_url = manual_urls[page_type]
                logger.info(f"Using manual URL for {page_type}: {manual_url}")

                # use js rendering based on settings (especially important for careers pages)
                use_js = self._js_rendering and (page_type == 'careers' or self._js_rendering)
                if use_js:
                    logger.debug(f"Using JavaScript rendering...")
                    if self._scroll_page:
                        logger.debug(f"Will scroll and wait {self._js_wait_time}ms for dynamic content...")

                scrape_result = self.scraper.scrape_page(
                    manual_url,
                    wait_for_js=use_js,
                    scroll_page=self._scroll_page if use_js else False,
                    extra_wait_ms=self._js_wait_time if use_js else 0,
                    wait_for_selector=self.JOB_LISTING_SELECTORS[0] if (use_js and page_type == 'careers') else None
                )

                if scrape_result['success'] and scrape_result['text'] and len(scrape_result['text']) > 200:
                    result['pages'][page_type] = {
                        'url': scrape_result['url'],
                        'title': scrape_result['title'],
                        'text': scrape_result['text'],
                        'html': scrape_result.get('html', ''),  # keep HTML for job extraction
                        'text_length': len(scrape_result['text']),
                        'scraped_at': scrape_result['scraped_at']
                    }
                    result['success_count'] += 1
                    logger.info(f"Successfully scraped manual URL ({len(scrape_result['text'])} chars)")
                else:
                    result['failed_pages'].append(page_type)
                    error_msg = scrape_result.get('error', 'Unknown error')
                    logger.error(f"Failed to scrape manual URL: {error_msg}")
            else:
                # use auto-discovery (only if homepage available)
                if homepage_html or not all_manual:
                    scrape_result = self._scrape_with_fallback(
                        company_url,
                        base_domain,
                        page_type,
                        homepage_html
                    )

                    if scrape_result:
                        result['pages'][page_type] = {
                            'url': scrape_result['url'],
                            'title': scrape_result['title'],
                            'text': scrape_result['text'],
                            'html': scrape_result.get('html', ''),  # keep html for extraction
                            'text_length': len(scrape_result['text']),
                            'scraped_at': scrape_result['scraped_at']
                        }
                        result['success_count'] += 1
                    else:
                        result['failed_pages'].append(page_type)
                else:
                    result['failed_pages'].append(page_type)
                    logger.warning(f"Skipping {page_type} - no manual URL and no homepage")

        result['metadata'] = {
            'total_pages_attempted': len(pages_to_scrape),
            'successful_pages': result['success_count'],
            'failed_pages': len(result['failed_pages']),
            'success_rate': f"{(result['success_count'] / len(pages_to_scrape)) * 100:.1f}%",
            'manual_urls_used': len(manual_urls) if manual_urls else 0,
            'all_manual': all_manual  # track if all pages were manual
        }

        # extract contacts from scraped pages
        logger.info("Extracting contacts from scraped pages...")
        contacts = self.extract_contacts_from_company_data(result)
        result['extracted_contacts'] = [
            {
                'name': c.name,
                'title': c.title,
                'email': c.email,
                'linkedin_url': c.linkedin_url,
                'source_page': c.source_page,
                'relevance_score': c.relevance_score
            }
            for c in contacts
        ]

        if contacts:
            logger.info(f"Found {len(contacts)} potential contacts:")
            for c in contacts[:5]:  # show top 5
                title_str = f" - {c.title}" if c.title else ""
                score_str = f" (relevance: {c.relevance_score:.1f})"
                logger.info(f"  {c.name}{title_str}{score_str}")
            if len(contacts) > 5:
                logger.info(f"  ... and {len(contacts) - 5} more")
        else:
            logger.warning("No contacts found - you may need to find contacts manually")

        # extract job listings from careers page
        logger.info("Extracting job listings from careers page...")
        jobs = []
        if 'careers' in result['pages']:
            careers_page = result['pages']['careers']
            careers_html = careers_page.get('html', '')
            careers_text = careers_page.get('text', '')

            logger.info(f"📄 Careers page captured: {len(careers_text)} chars text, {len(careers_html)} chars HTML")

            jobs = self.extract_job_listings(
                text=careers_text,
                html=careers_html,
                target_role=None  # will be filtered in workflow with actual target_role
            )

        result['extracted_jobs'] = jobs

        if jobs:
            jobs_with_urls = [j for j in jobs if j.get('url')]
            logger.info(f"Found {len(jobs)} job titles mentioned ({len(jobs_with_urls)} with URLs):")
            for job in jobs[:5]:
                url_indicator = " 🔗" if job.get('url') else ""
                logger.info(f"  • {job['title']}{url_indicator}")
            if len(jobs) > 5:
                logger.info(f"... and {len(jobs) - 5} more")
        else:
            logger.warning("No job listings extracted from text")
            if 'careers' in result['pages']:
                logger.info("Tip: The careers page was scraped with JS rendering enabled")
                logger.info("If jobs are still missing, the site may use complex JS frameworks")

        logger.info(f"{'='*60}")
        logger.info(f"Scraping complete: {result['success_count']}/{len(pages_to_scrape)} pages")
        logger.info(f"{'='*60}")

        return result
    
    def _extract_company_name(self, url: str) -> str:
        """Extract company name from URL"""
        domain = self._get_base_domain(url)
        return domain.split(".")[0].capitalize()
    
    def get_page_content(self, company_data: Dict, page_type: str) -> Optional[str]:
        """Extract text content from a specific page"""
        if page_type in company_data['pages']:
            return company_data['pages'][page_type]['text']
        return None
    
    def scrape_multiple_companies(
        self,
        company_urls: List[str],
        pages_to_scrape: Optional[List[str]] = None
    ) -> Dict[str, Dict]:
        """Scrape multiple companies"""
        results = {}
        for i, url in enumerate(company_urls, 1):
            print(f"\n\n{'#'*60}")
            print(f"Company {i}/{len(company_urls)}")
            print(f"{'#'*60}")

            company_data = self.scrape_company(url, pages_to_scrape)
            results[url] = company_data

        return results

    def extract_job_listings(
        self,
        text: str,
        html: Optional[str] = None,
        target_role: Optional[str] = None
    ) -> List[Dict]:
        """
        Extract job listings from careers page text/HTML.
        Returns list of jobs with: title, url (if found), location, match_score
        """
        html_length = len(html) if html else 0
        logger.info(f"🔍 extract_job_listings called: text_len={len(text)}, html_len={html_length}, target_role='{target_role}'")
        jobs = []
        seen_titles = set()

        # common job title patterns
        job_patterns = [
            # "Software Engineer" or "Senior Software Engineer"
            r'((?:Senior|Junior|Lead|Staff|Principal|Sr\.?|Jr\.?)?\s*(?:Software|Backend|Frontend|Full[- ]?Stack|DevOps|ML|AI|Data|Cloud|Platform|Infrastructure|Mobile|iOS|Android|Web|QA|Test|Security|SRE|Site Reliability)\s*(?:Engineer|Developer|Architect|Manager|Lead|Scientist|Analyst))',
            # "Engineering Manager" or "Director of Engineering"
            r'((?:Engineering|Technical|Software|Product)\s*(?:Manager|Director|Lead|Head))',
            # "Product Manager" or "Technical Program Manager"
            r'((?:Senior|Lead|Principal|Sr\.?)?\s*(?:Product|Program|Project|Technical Program)\s*Manager)',
            # Generic role patterns
            r'((?:Senior|Junior|Lead|Staff|Principal)?\s*(?:Recruiter|Designer|Researcher|Coordinator))',
        ]

        for pattern in job_patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            for match in matches:
                title = match.strip()
                title_lower = title.lower()

                # skip if already seen or too short
                if title_lower in seen_titles or len(title) < 5:
                    continue

                seen_titles.add(title_lower)

                # calculate match score against target role
                match_score = 0.0
                if target_role:
                    target_words = set(target_role.lower().split())
                    title_words = set(title_lower.split())
                    overlap = target_words & title_words
                    if overlap:
                        match_score = len(overlap) / len(target_words)

                jobs.append({
                    'title': title,
                    'match_score': match_score,
                    'url': None  # would need HTML parsing for job URLs
                })

        # extract job URLs and additional jobs from HTML if available
        if html:
            logger.info(f"   Searching for job URLs in HTML ({len(html)} chars)")

            # common patterns for job listing links - including major ATS systems
            job_url_patterns = [
                # Standard job paths
                r'href=["\']([^"\']*(?:/jobs?/|/careers?/|/positions?/|/openings?/)[^"\']*)["\']',
                # ATS query parameters
                r'href=["\']([^"\']*(?:job_id|jobId|position_id|req_id|requisition)[^"\']*)["\']',
                # Greenhouse ATS
                r'href=["\'](https?://boards\.greenhouse\.io/[^"\']+)["\']',
                r'href=["\'](https?://[^"\']*greenhouse[^"\']*jobs?[^"\']*)["\']',
                # Lever ATS
                r'href=["\'](https?://jobs\.lever\.co/[^"\']+)["\']',
                # Workday
                r'href=["\'](https?://[^"\']*workday[^"\']*job[^"\']*)["\']',
                r'href=["\'](https?://[^"\']*myworkdayjobs[^"\']*)["\']',
                # Ashby
                r'href=["\'](https?://jobs\.ashbyhq\.com/[^"\']+)["\']',
                # BambooHR
                r'href=["\'](https?://[^"\']*bamboohr[^"\']*jobs?[^"\']*)["\']',
                # Generic apply links
                r'href=["\']([^"\']*(?:/apply|/application)[^"\']*)["\']',
            ]

            found_urls = set()
            for pattern_idx, pattern in enumerate(job_url_patterns):
                urls = re.findall(pattern, html, re.IGNORECASE)
                # Filter out static assets (js, css, images)
                urls = [u for u in urls if not re.search(r'\.(js|css|png|jpg|svg|woff|ico)(\?|$)', u, re.I)]
                if urls:
                    logger.info(f"   Job URL pattern {pattern_idx + 1}: found {len(urls)} URLs")
                    for sample_url in urls[:2]:
                        logger.info(f"      Example: {sample_url[:80]}...")
                for url in urls[:30]:  # limit
                    if url in found_urls:
                        continue
                    found_urls.add(url)

            # Also look for job URLs in JavaScript/JSON data (common in SPAs like Nuxt/React)
            json_url_patterns = [
                # Greenhouse job IDs in JSON
                r'"url"\s*:\s*"(https?://[^"]*(?:greenhouse|lever|workday|ashby)[^"]*)"',
                r'"apply_url"\s*:\s*"([^"]+)"',
                r'"job_url"\s*:\s*"([^"]+)"',
                r'"href"\s*:\s*"(/careers/[^"]+)"',
                r'"link"\s*:\s*"(/jobs?/[^"]+)"',
                # Greenhouse/Lever embedded URLs
                r'greenhouse\.io/[^/]+/jobs/(\d+)',
                r'lever\.co/[^/]+/([a-f0-9-]+)',
            ]

            for pattern in json_url_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                if matches:
                    logger.info(f"   Found {len(matches)} URLs in JavaScript/JSON data")
                    for match in matches[:10]:
                        if match not in found_urls:
                            found_urls.add(match)
                            logger.info(f"      JS/JSON URL: {match[:60]}...")

                    # try to extract job title from URL
                    url_parts = url.lower().replace('-', ' ').replace('_', ' ').replace('/', ' ')

                    # match URL to existing job
                    matched = False
                    for job in jobs:
                        job_words = job['title'].lower().split()[:2]
                        if any(word in url_parts for word in job_words if len(word) > 3):
                            if job['url'] is None:
                                job['url'] = url
                            matched = True
                            break

                    # if URL contains job keywords but didn't match, try to extract title
                    if not matched:
                        for keyword in ['engineer', 'developer', 'manager', 'designer', 'analyst', 'scientist']:
                            if keyword in url_parts:
                                # extract potential title from URL path
                                path_parts = url.split('/')[-1].replace('-', ' ').replace('_', ' ')
                                if len(path_parts) > 5 and path_parts.lower() not in seen_titles:
                                    potential_title = path_parts.title()
                                    if len(potential_title) < 60:  # reasonable title length
                                        jobs.append({
                                            'title': potential_title,
                                            'match_score': 0.0,
                                            'url': url
                                        })
                                        seen_titles.add(path_parts.lower())
                                break

            # Log URL extraction results
            jobs_with_urls = [j for j in jobs if j.get('url')]
            jobs_without_urls = [j for j in jobs if not j.get('url')]
            logger.info(f"📊 Job URL extraction: {len(found_urls)} URLs found, {len(jobs_with_urls)} jobs matched, {len(jobs_without_urls)} jobs without URLs")
            if jobs_with_urls:
                for job in jobs_with_urls[:3]:
                    logger.info(f"   ✅ '{job['title']}' → {job['url'][:60]}...")

            # also look for job titles in common HTML structures
            job_title_html_patterns = [
                r'<h[1-4][^>]*class=["\'][^"\']*(?:job|position|role|title)[^"\']*["\'][^>]*>([^<]+)</h[1-4]>',
                r'<a[^>]*class=["\'][^"\']*(?:job|position|opening)[^"\']*["\'][^>]*>([^<]+)</a>',
                r'<div[^>]*class=["\'][^"\']*job-title[^"\']*["\'][^>]*>([^<]+)</div>',
                r'<span[^>]*class=["\'][^"\']*job-title[^"\']*["\'][^>]*>([^<]+)</span>',
            ]

            for pattern in job_title_html_patterns:
                matches = re.findall(pattern, html, re.IGNORECASE)
                for title in matches[:20]:
                    title = title.strip()
                    title_lower = title.lower()
                    if len(title) > 5 and len(title) < 80 and title_lower not in seen_titles:
                        # Check if it looks like a job title
                        job_keywords = ['engineer', 'developer', 'manager', 'designer', 'lead', 'analyst', 'scientist', 'architect', 'director']
                        if any(kw in title_lower for kw in job_keywords):
                            jobs.append({
                                'title': title,
                                'match_score': 0.0,
                                'url': None
                            })
                            seen_titles.add(title_lower)

        # sort by match score
        jobs.sort(key=lambda j: j['match_score'], reverse=True)

        # Final summary
        jobs_with_urls = [j for j in jobs if j.get('url')]
        logger.info(f"📊 Job extraction complete: {len(jobs)} jobs found, {len(jobs_with_urls)} have URLs")
        if jobs_with_urls:
            for job in jobs_with_urls[:3]:
                logger.info(f"   ✅ '{job['title']}' → {job['url'][:60]}...")
        elif html:
            logger.warning(f"   ⚠️ No URLs matched to jobs. HTML might use JavaScript or different URL structure.")

        return jobs[:20]  # return top 20

    def extract_contacts_from_text(
        self,
        text: str,
        html: Optional[str] = None,
        source_page: str = "team"
    ) -> List[ExtractedContact]:
        """
        Extract potential contacts from page text and HTML.

        Uses multiple strategies:
        1. Name + Title patterns (e.g., "John Smith, CEO")
        2. LinkedIn profile URLs
        3. Email patterns
        4. Structured data patterns
        """
        contacts = []
        seen_names = set()

        # strategy 1: extract linkedin URLs from HTML
        if html:
            linkedin_pattern = r'href=["\']?(https?://(?:www\.)?linkedin\.com/in/[a-zA-Z0-9_-]+)["\']?'
            linkedin_urls = re.findall(linkedin_pattern, html, re.IGNORECASE)

            for url in linkedin_urls[:10]:  # limit to first 10
                # try to extract name from URL
                name_part = url.split('/in/')[-1].rstrip('/')
                name_clean = name_part.replace('-', ' ').replace('_', ' ').title()

                if name_clean and len(name_clean) > 2 and name_clean not in seen_names:
                    contacts.append(ExtractedContact(
                        name=name_clean,
                        linkedin_url=url,
                        source_page=source_page,
                        relevance_score=0.3
                    ))
                    seen_names.add(name_clean)

        # strategy 2: extract name + title patterns from text
        name_title_patterns = [
            # "John Smith, CEO" or "John Smith - Engineering Manager"
            r'([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*[,\-–—]\s*([A-Za-z\s&]+(?:Manager|Director|Lead|Engineer|Recruiter|VP|CEO|CTO|CFO|COO|Officer|Head|President|Founder))',
            # "CEO: John Smith" or "Engineering Manager - Jane Doe"
            r'([A-Za-z\s]+(?:Manager|Director|Lead|Recruiter|VP|CEO|CTO|Head|Officer))\s*[:\-–—]\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})',
        ]

        for pattern in name_title_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if len(match) == 2:
                    # determine which is name and which is title
                    part1, part2 = match[0].strip(), match[1].strip()

                    # check if part1 looks like a title
                    is_part1_title = any(
                        title_word.lower() in part1.lower()
                        for titles in self.RELEVANT_TITLES.values()
                        for title_word in titles
                    )

                    if is_part1_title:
                        name, title = part2, part1
                    else:
                        name, title = part1, part2

                    # validate name looks like a name (2-4 words, title case)
                    name_words = name.split()

                    # Filter out job titles disguised as names
                    # Common patterns that are job titles, not names:
                    job_title_indicators = [
                        'engineer', 'developer', 'manager', 'director', 'lead', 'senior', 'junior',
                        'staff', 'principal', 'operations', 'safety', 'data', 'platform', 'autonomy',
                        'embedded', 'software', 'hardware', 'recruiting', 'time', 'systems', 'technical'
                    ]

                    name_lower = name.lower()
                    is_likely_job_title = any(indicator in name_lower for indicator in job_title_indicators)

                    # Also check if the "name" contains numbers or special chars (likely not a real name)
                    has_weird_chars = any(char.isdigit() or char in ['/', '#', '@'] for char in name)

                    if (2 <= len(name_words) <= 4 and
                        name not in seen_names and
                        not is_likely_job_title and
                        not has_weird_chars):
                        relevance = self._calculate_title_relevance(title)
                        contacts.append(ExtractedContact(
                            name=name,
                            title=title,
                            source_page=source_page,
                            relevance_score=relevance
                        ))
                        seen_names.add(name)

        # strategy 3: extract emails
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        emails = re.findall(email_pattern, text)

        # try to match emails to existing contacts or create new ones
        for email in emails[:10]:
            # skip generic emails
            if any(generic in email.lower() for generic in ['info@', 'contact@', 'support@', 'hello@', 'sales@', 'noreply@']):
                continue

            # try to extract name from email (firstname.lastname@)
            local_part = email.split('@')[0]
            if '.' in local_part:
                name_parts = local_part.split('.')
                name_guess = ' '.join(part.title() for part in name_parts[:2])

                if name_guess not in seen_names:
                    contacts.append(ExtractedContact(
                        name=name_guess,
                        email=email,
                        source_page=source_page,
                        relevance_score=0.4
                    ))
                    seen_names.add(name_guess)
            else:
                # check if we can attach this email to an existing contact
                for contact in contacts:
                    if contact.email is None:
                        name_lower = contact.name.lower().replace(' ', '')
                        if name_lower in email.lower() or email.split('@')[0].lower() in name_lower:
                            contact.email = email
                            contact.relevance_score += 0.2
                            break

        # sort by relevance score (highest first)
        contacts.sort(key=lambda c: c.relevance_score, reverse=True)

        return contacts[:15]  # return top 15 contacts

    def _calculate_title_relevance(self, title: str) -> float:
        """Calculate relevance score based on job title"""
        title_lower = title.lower()

        for keyword in self.RELEVANT_TITLES['high']:
            if keyword in title_lower:
                return 0.9

        for keyword in self.RELEVANT_TITLES['medium']:
            if keyword in title_lower:
                return 0.7

        for keyword in self.RELEVANT_TITLES['low']:
            if keyword in title_lower:
                return 0.5

        return 0.3

    def extract_contacts_from_company_data(
        self,
        company_data: Dict,
        target_role: Optional[str] = None
    ) -> List[ExtractedContact]:
        """
        Extract contacts from scraped company data.

        Prioritizes team/leadership page but also checks other pages.
        If target_role is provided, boosts relevance of matching titles.
        """
        all_contacts = []

        # priority order for contact extraction
        page_priority = ['team', 'about', 'careers', 'news']

        for page_type in page_priority:
            if page_type in company_data.get('pages', {}):
                page_data = company_data['pages'][page_type]
                text = page_data.get('text', '')
                html = page_data.get('html', '')  # may not always be available

                if text:
                    contacts = self.extract_contacts_from_text(
                        text=text,
                        html=html,
                        source_page=page_type
                    )
                    all_contacts.extend(contacts)

        # deduplicate by name
        seen_names = set()
        unique_contacts = []
        for contact in all_contacts:
            if contact.name.lower() not in seen_names:
                seen_names.add(contact.name.lower())
                unique_contacts.append(contact)

        # boost relevance for target role matches
        if target_role:
            role_keywords = target_role.lower().split()
            for contact in unique_contacts:
                if contact.title:
                    title_lower = contact.title.lower()
                    # check for role keyword matches
                    if any(kw in title_lower for kw in role_keywords):
                        contact.relevance_score += 0.2
                    # check for "manager" or "lead" in title when targeting roles
                    if any(mgr in title_lower for mgr in ['manager', 'lead', 'director', 'head']):
                        contact.relevance_score += 0.1

        # re-sort after boosting
        unique_contacts.sort(key=lambda c: c.relevance_score, reverse=True)

        return unique_contacts[:10]  # return top 10