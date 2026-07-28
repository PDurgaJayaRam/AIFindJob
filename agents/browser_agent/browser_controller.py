"""Browser Controller - CloakBrowser wrapper for AI agent."""
from __future__ import annotations

import os
import sys
import json
import time
import base64
import asyncio
import logging
from typing import List, Dict, Any, Optional
from playwright.async_api import Page, Browser, BrowserContext, async_playwright

logger = logging.getLogger(__name__)

# Windows fix: ensure ProactorEventLoop for subprocess support
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

# Lazy import to avoid circular dependency
_models_cache = None
def _get_models():
    global _models_cache
    if _models_cache is None:
        from agents.vision_scraper import models as m
        _models_cache = m
    return _models_cache


class BrowserController:
    """Controls browser for AI agent interaction using CloakBrowser stealth."""

    def __init__(self, headless: bool = False, proxy: str = None):
        self.headless = headless
        self.proxy = proxy or os.environ.get("BROWSER_PROXY", None)
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self._action_log = []
        self._network_responses = []
        self._extraction_stats = {}  # {portal: {attempts, jobs, zeros, last_zero}}

    async def start(self):
        """Launch browser with stealth. Uses CloakBrowser if available, falls back to raw Playwright."""
        try:
            from cloakbrowser import launch_async
            logger.info("Launching CloakBrowser (headless=%s, proxy=%s)...", self.headless, bool(self.proxy))
            # Build CloakBrowser launch kwargs — residential proxy is key for Cloudflare/IP-blocked sites
            cb_kwargs = {
                "headless": self.headless,
                "humanize": True,       # human-like mouse, keyboard, scroll
                "geoip": bool(self.proxy),  # auto-match timezone/locale to proxy exit IP
            }
            if self.proxy:
                cb_kwargs["proxy"] = self.proxy
            # Timeout CloakBrowser launch at 20s — update checks can hang
            self.browser = await asyncio.wait_for(
                launch_async(**cb_kwargs),
                timeout=20,
            )
            logger.info("CloakBrowser launched OK (proxy=%s)", bool(self.proxy))
        except Exception as e:
            logger.warning("CloakBrowser failed (%s), falling back to raw Playwright", e)
            pw = await async_playwright().start()
            # Get stealth args if available
            try:
                from cloakbrowser import get_default_stealth_args
                extra_args = get_default_stealth_args()
            except Exception:
                extra_args = [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-features=IsolateOrigins,site-per-process",
                ]
            launch_kwargs = {"headless": self.headless, "args": extra_args}
            if self.proxy:
                launch_kwargs["proxy"] = self.proxy
            self.browser = await pw.chromium.launch(**launch_kwargs)
            logger.info("Raw Playwright launched OK (proxy=%s)", bool(self.proxy))

        # Create browser context with randomized viewport and locale
        import random
        width = random.randint(1200, 1600)
        height = random.randint(800, 1000)
        locales = ["en-US", "en-GB", "en-IN"]
        accept_languages = ["en-US,en;q=0.9", "en-GB,en;q=0.9", "en-IN,en;q=0.9,en-IN;q=0.8"]

        # CloakBrowser already patches navigator.webdriver, plugins, languages, platform,
        # and chrome.runtime at the C++ source level — no need for JS injection.
        # Only set viewport, locale, and accept-language here.
        self.context = await self.browser.new_context(
            viewport={"width": width, "height": height},
            locale=random.choice(locales),
            timezone_id="Asia/Kolkata",
            extra_http_headers={"Accept-Language": random.choice(accept_languages)},
        )
        self.page = await self.context.new_page()

        logger.info("Browser context created (viewport=%dx%d)", width, height)

        # Network response interception — capture API responses for job data
        self._network_responses = []
        self.page.on("response", self._on_response)

    def _on_response(self, response):
        """Callback for every network response. Stores responses for later parsing."""
        try:
            url = response.url
            content_type = response.headers.get("content-type", "")
            status = response.status
            if status != 200:
                return
            if "json" not in content_type and "javascript" not in content_type:
                return
            # Only capture responses that look like job search APIs
            api_patterns = [
                "/api/", "/jobapi/", "/searchapi/", "/rpc/", "/gql",
                "search", "jobs", "results", "listing",
            ]
            if any(p in url.lower() for p in api_patterns):
                self._network_responses.append(response)
        except Exception:
            pass

    def clear_intercepted(self):
        """Clear intercepted responses before navigating to a new page."""
        self._network_responses.clear()

    async def get_intercepted_jobs(self, portal: str) -> List[Dict[str, Any]]:
        """Parse intercepted network responses for job data."""
        if not self._network_responses:
            return []

        portal_domains = {
            "naukri": ["naukri.com"],
            "indeed": ["indeed.com", "indeed.co"],
            "linkedin": ["linkedin.com"],
            "shine": ["shine.com"],
            "glassdoor": ["glassdoor."],
            "foundit": ["foundit.in"],
            "timesjobs": ["timesjobs.com"],
        }
        domains = portal_domains.get(portal, [portal])
        relevant = [r for r in self._network_responses if any(d in r.url for d in domains)]

        for resp in reversed(relevant):
            try:
                body = await resp.json()
                jobs = self._extract_jobs_from_json(body, portal)
                if jobs:
                    return jobs
            except Exception:
                continue

        return []

    def _extract_jobs_from_json(self, data: Any, portal: str) -> List[Dict]:
        """Recursively search JSON response for job-like objects."""
        jobs = []

        if isinstance(data, dict):
            # Check if this dict looks like a job
            if self._is_job_object(data):
                jobs.append(self._normalize_job(data, portal))
            # Check common API response wrappers
            for key in ["jobs", "results", "data", "items", "listings", "positions",
                        "jobList", "jobResults", "searchResults", "content"]:
                if key in data:
                    nested = data[key]
                    if isinstance(nested, list):
                        for item in nested:
                            if isinstance(item, dict) and self._is_job_object(item):
                                jobs.append(self._normalize_job(item, portal))
                            elif isinstance(item, dict):
                                jobs.extend(self._extract_jobs_from_json(item, portal))
                    elif isinstance(nested, dict):
                        jobs.extend(self._extract_jobs_from_json(nested, portal))
            # Recurse into unknown dict values
            if not jobs:
                for val in data.values():
                    if isinstance(val, (dict, list)):
                        jobs.extend(self._extract_jobs_from_json(val, portal))
                        if jobs:
                            break

        elif isinstance(data, list):
            for item in data:
                if isinstance(item, dict) and self._is_job_object(item):
                    jobs.append(self._normalize_job(item, portal))
                elif isinstance(item, dict):
                    jobs.extend(self._extract_jobs_from_json(item, portal))

        return jobs[:50]  # Cap at 50

    def _is_job_object(self, obj: dict) -> bool:
        """Check if a dict looks like a job listing."""
        keys = set(obj.keys())
        job_keys = {"title", "jobTitle", "job_title", "position", "designation",
                     "company", "companyName", "company_name", "employer",
                     "location", "jobLocation", "job_location"}
        matches = keys & job_keys
        return len(matches) >= 1  # At least title or company

    def _normalize_job(self, obj: dict, portal: str) -> Dict:
        """Normalize a JSON job object to our standard format."""
        title = (obj.get("title") or obj.get("jobTitle") or obj.get("job_title")
                 or obj.get("position") or obj.get("designation") or "")
        company = (obj.get("company") or obj.get("companyName") or obj.get("company_name")
                   or obj.get("employer") or "Unknown")
        location = (obj.get("location") or obj.get("jobLocation") or obj.get("job_location")
                    or obj.get("city") or "Not specified")
        desc = (obj.get("description") or obj.get("jobDescription") or obj.get("job_description")
                or obj.get("snippet") or "")
        url = (obj.get("url") or obj.get("jobUrl") or obj.get("job_url")
               or obj.get("applyUrl") or obj.get("apply_url") or obj.get("link") or "")
        salary = (obj.get("salary") or obj.get("salaryRange") or obj.get("salary_range")
                  or "Not specified")
        exp = (obj.get("experience") or obj.get("experienceRequired")
               or obj.get("experience_required") or "Not specified")

        return {
            "title": title.strip() if isinstance(title, str) else str(title),
            "company": company.strip() if isinstance(company, str) else str(company),
            "location": location.strip() if isinstance(location, str) else str(location),
            "description": desc.strip() if isinstance(desc, str) else str(desc),
            "source_url": url,
            "apply_url": url,
            "salary": str(salary),
            "experience": str(exp),
            "source": portal,
            "extraction_method": "api_intercept",
        }

    async def close(self):
        """Close browser. Safe to call multiple times."""
        if self.browser:
            try:
                await self.browser.close()
            except Exception:
                pass
            self.browser = None
            self.context = None
            self.page = None

    async def go_to(self, url: str, timeout: int = 30000) -> str:
        """Navigate to URL with retry logic."""
        # Live monitor: update status before navigation
        try:
            from agents.browser_agent.live_monitor import live_monitor
            live_monitor.update_status(url=url, action=f"Navigating to {url[:50]}...")
        except Exception:
            pass

        for attempt in range(2):
            try:
                if not self.page:
                    return "Navigation failed: Page is None"
                await self.page.goto(url, timeout=timeout, wait_until="domcontentloaded")
                await self.page.wait_for_timeout(1000)

                # Live monitor: capture screenshot after navigation
                try:
                    from agents.browser_agent.live_monitor import live_monitor
                    live_monitor.update_status(url=url, action=f"Loaded: {url[:50]}...")
                    await live_monitor.set_screenshot(self.page)
                except Exception:
                    pass

                return f"Navigated to {url}"
            except Exception as e:
                error_msg = str(e)
                if "closed" in error_msg.lower():
                    return f"Navigation failed: Browser closed - {e}"
                if attempt == 0:
                    await self.page.wait_for_timeout(500)
                    continue
                return f"Navigation failed: {e}"

    async def take_screenshot(self, full_page: bool = False, path: str = None) -> str:
        """Take screenshot and return base64 encoded image."""
        try:
            if self.is_browser_crashed():
                return "screenshot_error: Browser is not running"
            screenshot_bytes = await self.page.screenshot(full_page=full_page)
            b64 = base64.b64encode(screenshot_bytes).decode('utf-8')
            if path:
                os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
                with open(path, 'wb') as f:
                    f.write(screenshot_bytes)
            return b64
        except Exception as e:
            return f"screenshot_error: {e}"

    async def is_screenshot_error(self, result: str) -> bool:
        """Check if screenshot result is an error."""
        return isinstance(result, str) and result.startswith("screenshot_error:")

    async def get_page_content(self, max_chars: int = 8000) -> str:
        """Get page text content."""
        try:
            content = await self.page.evaluate("""() => {
                const clone = document.body.cloneNode(true);
                const remove = clone.querySelectorAll('script, style, noscript, iframe, svg, img');
                remove.forEach(el => el.remove());
                return clone.innerText;
            }""")
            return content[:max_chars]
        except Exception as e:
            return f"Error getting content: {e}"

    async def get_clickable_elements(self) -> List[Dict[str, str]]:
        """Get list of clickable elements with selectors."""
        try:
            elements = await self.page.evaluate("""() => {
                const clickables = document.querySelectorAll('a, button, [role="button"], input[type="submit"], .close, .dismiss, [aria-label*="close"], [aria-label*="Close"], [aria-label*="dismiss"], [class*="close"], [class*="dismiss"], [class*="popup"], [class*="modal"]');
                const result = [];
                clickables.forEach((el, i) => {
                    if (el.offsetParent !== null) {
                        const text = el.innerText?.trim() || el.getAttribute('aria-label') || el.value || '';
                        const tag = el.tagName.toLowerCase();
                        const classes = el.className || '';
                        const id = el.id || '';
                        let selector = tag;
                        if (id) selector += `#${id}`;
                        else if (classes) selector += `.${classes.split(' ').slice(0, 2).join('.')}`;
                        result.push({
                            index: i,
                            tag: tag,
                            text: text.substring(0, 80),
                            selector: selector,
                            href: el.href || '',
                            visible: true
                        });
                    }
                });
                return result.slice(0, 50);
            }""")
            return elements
        except Exception as e:
            return [{"error": str(e)}]

    async def click_element(self, selector: str) -> str:
        """Click element by selector or text."""
        try:
            try:
                await self.page.click(selector, timeout=5000)
                await self.page.wait_for_timeout(800)
                return f"Clicked selector: {selector}"
            except:
                # Try by text content
                clicked = await self.page.evaluate(f"""() => {{
                    const elements = document.querySelectorAll('a, button, [role="button"], span, div');
                    for (const el of elements) {{
                        if (el.innerText?.trim() === "{selector}" || el.innerText?.trim().includes("{selector}")) {{
                            el.click();
                            return true;
                        }}
                    }}
                    return false;
                }}""")
                await self.page.wait_for_timeout(800)
                if clicked:
                    return f"Clicked element with text: {selector}"
                return f"Element not found: {selector}"
        except Exception as e:
            return f"Click failed: {e}"

    async def click_by_index(self, index: int) -> str:
        """Click element by index from get_clickable_elements."""
        try:
            result = await self.page.evaluate(f"""() => {{
                const clickables = document.querySelectorAll('a, button, [role="button"], input[type="submit"], .close, .dismiss, [aria-label*="close"], [aria-label*="Close"], [class*="close"], [class*="dismiss"]');
                const visible = Array.from(clickables).filter(el => el.offsetParent !== null);
                if (visible[{index}]) {{
                    visible[{index}].click();
                    return 'Clicked element at index {index}';
                }}
                return 'No element at index {index}';
            }}""")
            await self.page.wait_for_timeout(800)
            return result
        except Exception as e:
            return f"Click by index failed: {e}"

    async def type_text(self, selector: str, text: str) -> str:
        """Type text into input field."""
        try:
            await self.page.fill(selector, text)
            return f"Typed '{text}' into {selector}"
        except Exception as e:
            return f"Type failed: {e}"

    async def scroll(self, direction: str = "down", amount: int = 500) -> str:
        """Scroll page."""
        try:
            if direction == "down":
                await self.page.evaluate(f"""() => {{
                    window.scrollBy(0, {amount});
                    // Also try scrolling the main content area for sites with fixed headers
                    const main = document.querySelector('main, .main, #main-content, .search-results-list, .jobs-search-results-list, .job-list');
                    if (main) main.scrollBy(0, {amount});
                }}""")
            elif direction == "up":
                await self.page.evaluate(f"window.scrollBy(0, -{amount})")
            elif direction == "bottom":
                await self.page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            await self.page.wait_for_timeout(1500)
            return f"Scrolled {direction} by {amount}px"
        except Exception as e:
            return f"Scroll failed: {e}"

    async def wait(self, seconds: int = 2) -> str:
        """Wait for page to load."""
        await self.page.wait_for_timeout(seconds * 1000)
        return f"Waited {seconds} seconds"

    async def extract_jobs(self) -> List[Dict[str, Any]]:
        """Extract job listings from current page using robust multi-strategy approach."""
        try:
            url = await self.get_url()
            source = 'web'
            if 'naukri.com' in url: source = 'naukri'
            elif 'linkedin.com' in url: source = 'linkedin'
            elif 'indeed.co' in url or 'indeed.com' in url: source = 'indeed'
            elif 'cutshort.io' in url: source = 'cutshort'
            elif 'glassdoor.' in url: source = 'glassdoor'
            elif 'foundit.in' in url: source = 'foundit'
            elif 'timesjobs.com' in url: source = 'timesjobs'
            elif 'shine.com' in url: source = 'shine'

            if source == 'naukri':
                jobs = await self._extract_naukri_jobs()
            elif source == 'linkedin':
                jobs = await self._extract_linkedin_jobs()
            elif source == 'indeed':
                jobs = await self._extract_indeed_jobs()
            elif source == 'cutshort':
                jobs = await self._extract_cutshort_jobs()
            elif source == 'foundit':
                jobs = await self._extract_foundit_jobs()
            elif source == 'timesjobs':
                jobs = await self._extract_timesjobs_jobs()
            elif source == 'shine':
                jobs = await self._extract_shine_jobs()
            elif source == 'glassdoor':
                jobs = await self._extract_glassdoor_jobs()
            else:
                jobs = await self._extract_generic_jobs()

            self._record_extraction(source, len(jobs))
            return jobs
        except Exception as e:
            print(f"Extract jobs error: {e}")
            return []

    def _record_extraction(self, portal: str, count: int):
        """Track extraction health per portal."""
        import time
        if portal not in self._extraction_stats:
            self._extraction_stats[portal] = {"attempts": 0, "jobs": 0, "zeros": 0, "last_zero": 0}
        stats = self._extraction_stats[portal]
        stats["attempts"] += 1
        stats["jobs"] += count
        if count == 0:
            stats["zeros"] += 1
            stats["last_zero"] = time.time()

    def is_portal_healthy(self, portal: str) -> bool:
        """Check if a portal has been returning results. Auto-recovers after 5 min cooldown."""
        import time
        stats = self._extraction_stats.get(portal)
        if not stats:
            return True  # No data yet, assume healthy
        # Auto-recover: if last zero was >5 min ago, reset zero count
        if stats["zeros"] > 5 and stats.get("last_zero", 0) > 0:
            if time.time() - stats["last_zero"] > 300:  # 5 min cooldown
                stats["zeros"] = 0
                stats["attempts"] = 0
                return True
        if stats["attempts"] < 5:
            return True  # Not enough data
        return stats["zeros"] <= 5

    def get_portal_health(self) -> Dict:
        """Return extraction stats for all portals."""
        return dict(self._extraction_stats)

    async def _extract_naukri_jobs(self) -> List[Dict[str, Any]]:
        """Extract Naukri jobs - only individual job detail pages, no category/nav links."""
        jobs = await self.page.evaluate(r"""() => {
            const jobs = [];
            const seenUrls = new Set();

            // Only find links that are INDIVIDUAL job detail pages
            // Naukri job URLs look like: /job-listings-<title>-<company>-<location>-<exp>-<id>
            const allLinks = document.querySelectorAll('a[href*="/job-listings-"]');
            for (const link of allLinks) {
                const href = link.href || '';
                if (!href || seenUrls.has(href)) continue;

                // Must be a real job listing URL (contains job-listings- pattern)
                if (!href.includes('/job-listings-')) continue;

                const title = link.innerText?.trim() || '';
                if (!title || title.length < 3 || title.length > 200) continue;

                // Skip obvious non-job titles
                const lower = title.toLowerCase();
                if (lower.includes('view all') || lower.includes('see all') ||
                    lower.includes('search') || lower.includes('login') ||
                    lower.includes('register') || lower.includes('download') ||
                    lower.includes('apply with')) continue;

                seenUrls.add(href);

                // Walk up DOM to find the job card container
                let card = link.closest('div[class*="job"], article, div[class*="tuple"], div[class*="card"], li[class*="job"], section[class*="job"], div[class*="Srp"], div[class*="srp"], div[class*="jobTuple"], div[class*="job-tuple"]');
                if (!card) card = link.parentElement;
                if (!card) card = link.parentElement?.parentElement;
                if (!card) card = link.parentElement?.parentElement?.parentElement;

                let company = '';
                let location = 'Not specified';
                let experience = 'Not specified';
                let salary = 'Not specified';
                let description = '';
                let posted_text = '';

                if (card) {
                    const lines = card.innerText?.split('\n').map(l => l.trim()).filter(l => l.length > 0) || [];

                    // Find company name - look for company-like text
                    for (const line of lines) {
                        if (line === title) continue;
                        const lowerLine = line.toLowerCase();
                        // Skip UI elements, metadata, etc.
                        if (line.length < 2 || line.length > 80) continue;
                        if (line.includes('days ago') || line.includes('Apply') || line.includes('Actively') ||
                            line.includes('Posted') || line.includes('saved') || line.includes('bookmark') ||
                            lowerLine.includes('job') || lowerLine.includes('location') ||
                            lowerLine.includes('experience') || lowerLine.includes('salary') ||
                            lowerLine.includes('skills') || lowerLine.includes('description') ||
                            lowerLine.includes('role') || lowerLine.includes('industry') ||
                            lowerLine.includes('education') || lowerLine.includes('apply now') ||
                            lowerLine.includes('view details') || lowerLine.includes(' recruiter') ||
                            lowerLine.match(/^(remote|hybrid|on-site)$/i) ||
                            lowerLine.match(/^\d+/)) continue;
                        // Company names typically: start with capital, contain letters/spaces/dots/&
                        if (/^[A-Z][a-zA-Z\s.&()'\-]+$/.test(line)) {
                            company = line;
                            break;
                        }
                    }

                    // Find posting date
                    for (const line of lines) {
                        const lowerLine = line.toLowerCase();
                        if (lowerLine.match(/\d+\s*(?:day|hour|minute|week|month)s?\s*ago/i) ||
                            lowerLine.match(/posted\s+/i) ||
                            lowerLine === 'just posted' || lowerLine === 'today' || lowerLine === 'yesterday' ||
                            lowerLine.match(/(?:\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})/i)) {
                            posted_text = line.replace(/^posted\s*/i, '').trim();
                            break;
                        }
                    }

                    // Find location
                    const cityKeywords = ['hyderabad', 'bangalore', 'bengaluru', 'chennai', 'mumbai', 'delhi', 'pune',
                        'kolkata', 'noida', 'gurgaon', 'gurugram', 'kochi', 'vizag', 'visakhapatnam',
                        'telangana', 'andhra pradesh', 'karnataka', 'tamil nadu', 'maharashtra',
                        'india', 'remote', 'work from home', 'ahmedabad', 'jaipur', 'lucknow',
                        'chandigarh', 'coimbatore', 'mangalore', 'mysore', 'thiruvananthapuram'];
                    for (const line of lines) {
                        const lowerLine = line.toLowerCase();
                        if (cityKeywords.some(city => lowerLine.includes(city))) {
                            if (!lowerLine.includes('job') && !lowerLine.includes('salary') &&
                                !lowerLine.includes('experience') && !lowerLine.includes('skills') &&
                                !lowerLine.includes('description') && line.length < 100) {
                                location = line;
                                break;
                            }
                        }
                    }

                    // Find experience
                    for (const line of lines) {
                        if (line.match(/\d[\s-]*[\d+]*\s*y(?:ears?|rs?)/i) ||
                            line.match(/fresher/i) ||
                            line.match(/^0[\s-]*[-–]\s*\d/i)) {
                            experience = line;
                            break;
                        }
                    }

                    // Find salary
                    for (const line of lines) {
                        if (line.includes('\u20b9') || line.match(/lac|lakh|k\/yr|per annum|PA\b/i)) {
                            salary = line;
                            break;
                        }
                    }

                    // Find description — collect multiple lines from card
                    const descLines = [];
                    const skipDesc = ['view all', 'see all', 'search', 'login', 'register',
                        'save job', 'share', 'report', 'apply now', 'apply with',
                        'easy apply', 'sign in', 'similar jobs', 'more jobs'];
                    for (const line of lines) {
                        if (line === title || line === company || line === location) continue;
                        if (line.length < 20 || line.length > 500) continue;
                        const ll = line.toLowerCase();
                        if (skipDesc.some(s => ll === s || ll.startsWith(s + ' '))) continue;
                        if (ll.match(/^(full[\s-]?time|part[\s-]?time|internship|contract|fresher|remote|hybrid)$/i)) continue;
                        if (line.match(/^[\d,]+\s*(results?|jobs?|positions?)$/i)) continue;
                        descLines.push(line);
                        if (descLines.join(' ').length > 600) break;
                    }
                    description = descLines.join('\n').substring(0, 1500);
                }

                jobs.push({
                    title,
                    company: company || 'Unknown',
                    location,
                    source: 'naukri',
                    source_url: href,
                    apply_url: href,
                    salary,
                    description,
                    experience_required: experience,
                    posted_text
                });
            }

            return jobs;
        }""")

        # Validate and deduplicate
        validated = []
        seen_titles = set()
        for job in jobs:
            title = job.get('title', '').strip()
            if not title or len(title) < 3:
                continue
            # Skip category/navigation garbage
            lower = title.lower().strip()
            if lower in ['jobs', 'search', 'login', 'register', 'download', 'fresher jobs',
                         'engineering jobs', 'internet', 'internship', 'data science jobs'] or \
               lower.startswith('jobs in') or lower.startswith('posted by') or \
               lower.startswith('•') or 'talent cloud' in lower or \
               'product based' in lower or 'product companies' in lower:
                continue
            title_key = lower
            if title_key in seen_titles:
                continue
            seen_titles.add(title_key)
            validated.append(job)

        return validated[:50]  # Increased from 30 to 50 for better coverage

    async def _extract_linkedin_jobs(self) -> List[Dict[str, Any]]:
        """Extract LinkedIn jobs - uses /jobs/view/<id> pattern."""
        jobs = await self.page.evaluate(r"""() => {
            const jobs = [];
            const seenUrls = new Set();
            // LinkedIn uses specific card structures
            const allLinks = document.querySelectorAll('a[href*="/jobs/view/"], a[href*="/job/view/"], a[data-job-id]');
            
            for (const link of allLinks) {
                const href = link.href || '';
                const text = link.innerText?.trim() || '';
                
                if (!href || seenUrls.has(href)) continue;
                if (text.length < 4 || text.length > 150) continue;
                
                // Skip navigation/footer links
                if (text.toLowerCase().includes('sign in') || text.toLowerCase().includes('join now') || 
                    text.toLowerCase().includes('login') || text.toLowerCase().includes('register')) continue;
                
                seenUrls.add(href);
                
                // Try to find job card for context
                let card = link.closest('div[data-job-id], div[class*="job"], article, li');
                let company = '';
                let location = 'Not specified';
                let experience = 'Not specified';
                let posted_text = '';

                let lines = [];
                if (card) {
                    lines = card.innerText?.split('\n').map(l => l.trim()).filter(l => l.length > 0) || [];
                    for (const line of lines) {
                        if (line === text) continue;
                        if (line.length > 2 && line.length < 80 && /^[A-Z][a-zA-Z\s.&()'\-]+$/.test(line)) {
                            company = line;
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.toLowerCase().includes('hyderabad') || line.toLowerCase().includes('bangalore') ||
                            line.toLowerCase().includes('chennai') || line.toLowerCase().includes('mumbai') ||
                            line.toLowerCase().includes('delhi') || line.toLowerCase().includes('pune') ||
                            line.toLowerCase().includes('remote') || line.toLowerCase().includes('india')) {
                            location = line;
                            break;
                        }
                    }
                    // Extract experience from card
                    for (const line of lines) {
                        if (line.match(/\d[\s-]*[\d+]*\s*y(?:ears?|rs?)/i) ||
                            line.match(/fresher/i) ||
                            line.match(/^0[\s-]*[-–]\s*\d/i) ||
                            line.match(/\d+\+\s*years?/i)) {
                            experience = line;
                            break;
                        }
                    }
                    // Extract posting date
                    for (const line of lines) {
                        const ll = line.toLowerCase();
                        if (ll.match(/\d+\s*(?:day|hour|minute|week|month)s?\s*ago/i) ||
                            ll.match(/reposted?\s+\d/i) ||
                            ll === 'just posted' || ll === 'today' || ll === 'yesterday' ||
                            ll.match(/(?:\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})/i)) {
                            posted_text = line.replace(/^(?:re)?posted\s*/i, '').trim();
                            break;
                        }
                    }
                }

                // Try to extract description from card
                let description = '';
                if (card) {
                    const descLines = [];
                    const skipWords = ['view all', 'see all', 'search', 'login', 'register', 'apply now', 'easy apply', 'sign in', 'similar jobs'];
                    for (const line of lines) {
                        if (line === text || line === company || line === location) continue;
                        if (line.length < 30 || line.length > 600) continue;
                        const ll = line.toLowerCase();
                        if (skipWords.some(s => ll === s || ll.startsWith(s + ' '))) continue;
                        if (ll.match(/^(full[\s-]?time|part[\s-]?time|internship|contract|remote|hybrid)$/i)) continue;
                        descLines.push(line);
                        if (descLines.join(' ').length > 600) break;
                    }
                    description = descLines.join('\n').substring(0, 1500);
                }

                jobs.push({
                    title: text,
                    company: company || 'Unknown',
                    location: location,
                    source: 'linkedin',
                    source_url: href,
                    apply_url: href,
                    salary: 'Not specified',
                    description: description,
                    experience_required: experience,
                    posted_text
                });
            }
            
            return jobs;
        }""")
        
        # If no jobs found via links, try generic extraction
        if not jobs or len(jobs) == 0:
            return await self._extract_generic_jobs()
        
        validated = []
        seen = set()
        for job in jobs:
            key = job.get('title', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                validated.append(job)
        return validated[:50]  # Increased from 30 to 50 for better coverage

    async def _extract_indeed_jobs(self) -> List[Dict[str, Any]]:
        """Extract Indeed jobs - uses job listing URL patterns."""
        jobs = await self._extract_with_patterns([
            r'/viewjob\?jk=',
            r'/pagead/',
            r'indeed\.com/rc/clk',
            r'/jobs\?q=',
            r'jk=[a-f0-9]+',
        ], 'indeed')

        # If no jobs found, try generic extraction as fallback
        if not jobs:
            return await self._extract_generic_jobs()
        return jobs

    async def _extract_cutshort_jobs(self) -> List[Dict[str, Any]]:
        """Extract CutShort jobs - uses /jobs/<id>-<slug> pattern."""
        jobs = await self._extract_with_patterns([
            r'/jobs/\d+-',
            r'/jobs/\d+',
        ], 'cutshort')

        # If no jobs found, try generic extraction as fallback
        if not jobs:
            return await self._extract_generic_jobs()
        return jobs

    async def _extract_foundit_jobs(self) -> List[Dict[str, Any]]:
        """Extract Foundit jobs from SPA cards (.srpCardsWrapper). No hyperlinks on cards."""
        jobs = await self.page.evaluate("""() => {
            const cards = document.querySelectorAll('.srpCardsWrapper');
            const jobs = [];
            const seen = new Set();
            for (const card of cards) {
                const lines = card.innerText?.split('\\n').map(l => l.trim()).filter(l => l.length > 0) || [];
                if (lines.length < 2) continue;
                // First line is title
                const title = lines[0];
                if (!title || title.length < 4 || title.length > 150) continue;
                // Skip non-job entries
                const tl = title.toLowerCase();
                if (['showing', 'no result', 'sorry', 'login', 'register'].some(s => tl.startsWith(s))) continue;

                // Second line is company
                let company = lines[1] || 'Unknown';
                if (company.includes('confidential') || company.includes('Company name')) company = 'Confidential';

                // Remaining lines: location, experience, posted date, etc.
                let location = 'Not specified';
                let experience = 'Not specified';
                let posted_text = '';
                let salary = 'Not specified';
                const cityKeywords = ['hyderabad', 'bangalore', 'bengaluru', 'chennai', 'mumbai', 'delhi', 'pune',
                    'kolkata', 'gurgaon', 'noida', 'remote', 'india', 'ahmedabad', 'jaipur'];
                const expPattern = /^\\d+\\s*-\\s*\\d+\\s*years?$/i;
                const fresherPattern = /^fresher$/i;
                const postedPattern = /(?:posted|ago|days?|hours?|minutes?|weeks?|months?)/i;
                const salaryPattern = /(?:INR|LPA|\\d+\\s*-\\s*\\d+)/i;

                for (let i = 2; i < lines.length; i++) {
                    const line = lines[i];
                    const ll = line.toLowerCase();
                    if (!location.match(/^(?:\\d|Not)/) && cityKeywords.some(c => ll.includes(c))) {
                        location = line;
                    } else if (expPattern.test(line) || fresherPattern.test(line)) {
                        experience = line;
                    } else if (salaryPattern.test(line)) {
                        salary = line;
                    } else if (postedPattern.test(line)) {
                        posted_text = line.replace(/^posted\\s*/i, '').trim();
                    }
                }

                // Generate a search URL for the job detail
                const searchUrl = 'https://www.foundit.in/srp/results?query=' + encodeURIComponent(title);

                const key = title + '|' + company;
                if (seen.has(key)) continue;
                seen.add(key);

                jobs.push({
                    title, company, location, experience, salary,
                    description: '',
                    source: 'foundit',
                    source_url: searchUrl,
                    apply_url: searchUrl,
                    posted_text
                });
            }
            return jobs;
        }""")

        if not jobs:
            # Fallback to link-based extraction
            return await self._extract_with_patterns([
                r'/job-details/',
                r'/srdc/jobs/',
                r'/job/\d+',
                r'/jobs/\d+',
            ], 'foundit')
        return jobs

    async def _extract_timesjobs_jobs(self) -> List[Dict[str, Any]]:
        """Extract TimesJobs jobs using dedicated JS extraction."""
        jobs = await self.page.evaluate(r"""() => {
            const jobs = [];
            const seenUrls = new Set();
            const cards = document.querySelectorAll(
                'li.clearfix.job-bx, div.job-bx, li[class*="job-bx"], ' +
                'div[class*="srpJob"], div[class*="job-listing"], ' +
                'ul[class*="job"] li, div.new-joblist li, ' +
                'div[class*="job-card"], div[class*="jobCard"], li[class*="result-card"], ' +
                'div[class*="search-result"], article[class*="job"]'
            );
            cards.forEach(card => {
                const titleEl = card.querySelector(
                    'h2 a, h3 a, a[class*="job-title"], a[class*="title"], ' +
                    '.joblist-comp-name + a, a[href*="job-detail"], a[title], h2, h3'
                );
                const companyEl = card.querySelector(
                    'h3.joblist-comp-name, span.company-name, [class*="company"], a[class*="company"]'
                );
                const locEl = card.querySelector(
                    'span[class*="location"], [class*="loc"], li.location, span.loc'
                );
                const descEl = card.querySelector(
                    'ul.list-job-dtl li, p[class*="desc"], [class*="description"], span.job-desc'
                );
                const expEl = card.querySelector(
                    'span.exp, li.exp, [class*="experience"], [class*="exp"]'
                );
                const salaryEl = card.querySelector(
                    'span.salary, li.salary, [class*="salary"]'
                );
                if (titleEl) {
                    const title = titleEl.innerText?.trim() || '';
                    const href = titleEl.href || titleEl.querySelector('a')?.href || '';
                    if (title && title.length > 3 && title.length < 150 && !seenUrls.has(href)) {
                        seenUrls.add(href);
                        jobs.push({
                            title,
                            company: companyEl?.innerText?.trim() || 'Unknown',
                            location: locEl?.innerText?.trim() || '',
                            source: 'timesjobs',
                            source_url: href,
                            apply_url: href,
                            salary: salaryEl?.innerText?.trim() || '',
                            description: descEl?.innerText?.trim() || '',
                            experience_required: expEl?.innerText?.trim() || '',
                        });
                    }
                }
            });
            // Fallback: try generic link extraction
            if (jobs.length === 0) {
                document.querySelectorAll('a[href*="/job-detail/"]').forEach(link => {
                    const href = link.href || '';
                    const text = link.innerText?.trim() || '';
                    if (text.length > 3 && text.length < 150 && !seenUrls.has(href)) {
                        seenUrls.add(href);
                        jobs.push({
                            title: text,
                            company: 'Unknown',
                            location: '',
                            source: 'timesjobs',
                            source_url: href,
                            apply_url: href,
                            salary: '',
                            description: '',
                            experience_required: '',
                        });
                    }
                });
            }
            return jobs;
        }""")

        # If no jobs found, try generic extraction as fallback
        if not jobs:
            return await self._extract_generic_jobs()
        return jobs

    async def _extract_shine_jobs(self) -> List[Dict[str, Any]]:
        """Extract Shine jobs - uses /job-details/ or /job/<id> pattern."""
        # Try specific patterns first — /job-search/ removed (matches category pages, not actual jobs)
        jobs = await self._extract_with_patterns([
            r'/job-details/',
            r'/job/\d+',
            r'/jobs/\d+',
        ], 'shine')

        # If no jobs found, try generic extraction as fallback
        if not jobs:
            return await self._extract_generic_jobs()
        return jobs

    async def _extract_glassdoor_jobs(self) -> List[Dict[str, Any]]:
        """Extract Glassdoor jobs - handles login modal and extracts visible jobs."""
        jobs = await self.page.evaluate(r"""() => {
            const jobs = [];
            const seenUrls = new Set();
            // Glassdoor uses specific selectors
            const allLinks = document.querySelectorAll('a[href*="/job-listing/"], a[data-job-listing]');
            
            for (const link of allLinks) {
                const href = link.href || '';
                const text = link.innerText?.trim() || '';
                
                if (!href || seenUrls.has(href)) continue;
                if (text.length < 4 || text.length > 150) continue;
                
                seenUrls.add(href);
                
                // Try to find job card for context
                let card = link.closest('div[class*="job"], div[class*="card"], article, li, section');
                let company = '';
                let location = 'Not specified';
                let experience = 'Not specified';
                let salary = 'Not specified';
                
                let posted_text = '';

                let lines = [];
                if (card) {
                    lines = card.innerText?.split('\n').map(l => l.trim()).filter(l => l.length > 0) || [];
                    for (const line of lines) {
                        if (line === text) continue;
                        if (line.length > 2 && line.length < 80 && /^[A-Z][a-zA-Z\s.&()'\-]+$/.test(line)) {
                            company = line;
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.toLowerCase().includes('hyderabad') || line.toLowerCase().includes('bangalore') ||
                            line.toLowerCase().includes('chennai') || line.toLowerCase().includes('mumbai') ||
                            line.toLowerCase().includes('delhi') || line.toLowerCase().includes('pune') ||
                            line.toLowerCase().includes('remote') || line.toLowerCase().includes('india')) {
                            location = line;
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.match(/\d[\s-]*[\d+]*\s*y(?:ears?|rs?)/i) || line.match(/fresher/i)) {
                            experience = line;
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.includes('\u20b9') || line.match(/lac|lakh|k\/yr|per annum|PA\b/i)) {
                            salary = line;
                            break;
                        }
                    }
                    // Extract posting date — Glassdoor uses short format like "2d ago", "30d+"
                    for (const line of lines) {
                        const ll = line.toLowerCase();
                        if (ll.match(/\d+\s*(?:day|hour|minute|week|month)s?\s*ago/i) ||
                            ll.match(/\d+d(?:\+|\s|$)/i) ||
                            ll.match(/posted\s+/i) ||
                            ll === 'just posted' || ll === 'today' || ll === 'yesterday' ||
                            ll.match(/(?:\d{1,2}\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\s+\d{1,2})/i)) {
                            posted_text = line.replace(/^posted\s*/i, '').trim();
                            break;
                        }
                    }
                }

                // Try to extract description from card
                let description = '';
                if (card) {
                    const descLines = [];
                    const skipWords = ['view all', 'see all', 'search', 'login', 'register', 'apply now', 'sign in', 'similar jobs', 'report job'];
                    for (const line of lines) {
                        if (line === text || line === company || line === location) continue;
                        if (line.length < 30 || line.length > 600) continue;
                        const ll = line.toLowerCase();
                        if (skipWords.some(s => ll === s || ll.startsWith(s + ' '))) continue;
                        descLines.push(line);
                        if (descLines.join(' ').length > 600) break;
                    }
                    description = descLines.join('\n').substring(0, 1500);
                }

                jobs.push({
                    title: text,
                    company: company || 'Unknown',
                    location: location,
                    source: 'glassdoor',
                    source_url: href,
                    apply_url: href,
                    salary: salary,
                    description: description,
                    experience_required: experience,
                    posted_text
                });
            }
            
            return jobs;
        }""");
        
        validated = []
        seen = set()
        for job in jobs:
            key = job.get('title', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                validated.append(job)
        return validated[:30]

    async def _extract_with_patterns(self, patterns: List[str], source: str) -> List[Dict[str, Any]]:
        """Extract jobs using regex URL patterns - shared logic for all portals."""
        pattern_js = json.dumps(patterns)
        jobs = await self.page.evaluate(f"""() => {{
            const jobs = [];
            const seenUrls = new Set();
            const patterns = {pattern_js};

            // Find all links and match against job URL patterns
            const allLinks = document.querySelectorAll('a[href]');
            for (const link of allLinks) {{
                const href = link.href || '';
                const text = link.innerText?.trim() || '';

                // Match URL against patterns
                let isJobLink = false;
                for (const pattern of patterns) {{
                    if (new RegExp(pattern).test(href)) {{
                        isJobLink = true;
                        break;
                    }}
                }}
                if (!isJobLink) continue;
                if (seenUrls.has(href)) continue;

                // Title must look like a job title
                if (text.length < 4 || text.length > 150) continue;
                const skipKeywords = ['view all', 'see all', 'search', 'login', 'register',
                    'download', 'apply with', 'post job', 'recruiter', 'talent cloud',
                    'salary', 'salaries', 'salary search', 'jobs in', 'job search',
                    'view all jobs', 'see all jobs', 'skip to main'];
                const lowerText = text.toLowerCase();
                if (skipKeywords.some(kw => lowerText.includes(kw))) continue;

                // Reject category/suggestion links like "2d Animation Jobs In Chennai" or "SQL jobs in Hyderabad"
                if (lowerText.match(/jobs\\s+in\\s+\\w+/i)) continue;
                if (lowerText.match(/^[\\w\\s]+\\s+jobs\\s+in\\s+/i)) continue;
                if (lowerText.match(/\\d+[,.]?\\d*\\s+(fresher|data entry|work from home)/i)) continue;

                // Reject pages that are clearly not job listings (error pages, nav items)
                if (text === '404' || text === '403' || text === '500') continue;
                if (lowerText.match(/^(home|about|contact|help|faq|privacy|terms|blog)$/i)) continue;

                const jobKeywords = ['developer', 'engineer', 'analyst', 'manager', 'consultant',
                    'architect', 'specialist', 'designer', 'lead', 'senior', 'junior',
                    'intern', 'trainee', 'associate', 'coordinator', 'administrator',
                    'tester', 'qa', 'devops', 'full stack', 'backend', 'frontend',
                    'data', 'ml', 'ai', 'cloud', 'security', 'network', 'system',
                    'product', 'project', 'program', 'business', 'technical',
                    'software', 'hardware', 'mobile', 'web', 'appian', 'java',
                    'python', 'react', 'angular', 'node', 'sql', 'fresher'];
                const hasJobKeyword = jobKeywords.some(kw => lowerText.includes(kw));
                if (!hasJobKeyword) continue;

                seenUrls.add(href);

                // Try to find parent card for context
                let card = link.closest('div[class*="job"], div[class*="card"], article, li, section, div[class*="result"], div[class*="listing"]');
                if (!card) card = link.parentElement;
                if (!card) card = link.parentElement?.parentElement;

                let company = '';
                let location = 'Not specified';
                let experience = 'Not specified';
                let salary = 'Not specified';
                let description = '';
                let posted_text = '';

                if (card) {{
                    const lines = card.innerText?.split('\\n').map(l => l.trim()).filter(l => l.length > 0) || [];

                    // Find company name
                    for (const line of lines) {{
                        if (line === text) continue;
                        if (line.length < 2 || line.length > 80) continue;
                        if (/^[A-Z][a-zA-Z\\s.&()\\'\\-]+$/.test(line) &&
                            !line.toLowerCase().includes('job') &&
                            !line.toLowerCase().includes('apply') &&
                            !line.toLowerCase().includes('location')) {{
                            company = line;
                            break;
                        }}
                    }}

                    // Extract posting date
                    for (const line of lines) {{
                        const ll = line.toLowerCase();
                        if (ll.match(/\\d+\\s*(?:day|hour|minute|week|month)s?\\s*ago/i) ||
                            ll.match(/posted\\s+/i) ||
                            ll === 'just posted' || ll === 'today' || ll === 'yesterday' ||
                            ll.match(/(?:\\d{{1,2}}\\s+(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\\s+\\d{{1,2}})/i)) {{
                            posted_text = line.replace(/^posted\\s*/i, '').trim();
                            break;
                        }}
                    }}

                    // Find location
                    const cityKeywords = ['hyderabad', 'bangalore', 'bengaluru', 'chennai', 'mumbai', 'delhi', 'pune',
                        'kolkata', 'noida', 'gurgaon', 'gurugram', 'kochi', 'vizag', 'visakhapatnam',
                        'telangana', 'andhra pradesh', 'karnataka', 'tamil nadu', 'maharashtra',
                        'india', 'remote', 'work from home', 'ahmedabad', 'jaipur', 'lucknow'];
                    for (const line of lines) {{
                        const lowerLine = line.toLowerCase();
                        if (cityKeywords.some(city => lowerLine.includes(city))) {{
                            location = line;
                            break;
                        }}
                    }}

                    // Find experience
                    for (const line of lines) {{
                        if (line.match(/\\d[\\s-]*[\\d+]*\\s*y(?:ears?|rs?)/i) ||
                            line.match(/fresher/i) ||
                            line.match(/^0[\\s-]*[-–]\\s*\\d/i)) {{
                            experience = line;
                            break;
                        }}
                    }}

                    // Find salary
                    for (const line of lines) {{
                        if (line.includes('\\u20b9') || line.match(/lac|lakh|k\\/yr|per annum|PA\\b/i)) {{
                            salary = line;
                            break;
                        }}
                    }}

                    // Find description — collect lines that look like job content
                    const descLines = [];
                    const skipDesc = ['view all', 'see all', 'search', 'login', 'register',
                        'save job', 'share', 'report', 'posted', 'apply now', 'apply with',
                        'easy apply', 'sign in', 'similar jobs', 'more jobs'];
                    for (const line of lines) {{
                        if (line === text || line === company || line === location) continue;
                        if (line.length < 30 || line.length > 500) continue;
                        const ll = line.toLowerCase();
                        if (skipDesc.some(s => ll === s || ll.startsWith(s + ' '))) continue;
                        if (ll.match(/^(full[\\s-]?time|part[\\s-]?time|internship|contract|fresher|remote|hybrid)$/i)) continue;
                        if (line.match(/^[\\d,]+\\s*(results?|jobs?|positions?)$/i)) continue;
                        descLines.push(line);
                        if (descLines.join(' ').length > 500) break;
                    }}
                    description = descLines.join('\\n').substring(0, 1500);
                }}

                jobs.push({{
                    title: text,
                    company: company || 'Unknown',
                    location: location,
                    source: '{source}',
                    source_url: href,
                    apply_url: href,
                    salary: salary,
                    description: description,
                    experience_required: experience,
                    posted_text
                }});
            }}

            return jobs;
        }}""")

        # Validate and deduplicate
        validated = []
        seen = set()
        for job in jobs:
            key = job.get('title', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                validated.append(job)
        return validated[:30]

    async def _extract_generic_jobs(self) -> List[Dict[str, Any]]:
        """Fallback: extract jobs using link-based detection for any site."""
        jobs = await self.page.evaluate(r"""() => {
            const jobs = [];
            const seenUrls = new Set();
            const url = window.location.href;

            let source = 'web';
            if (url.includes('naukri.com')) source = 'naukri';
            else if (url.includes('linkedin.com')) source = 'linkedin';
            else if (url.includes('indeed.co') || url.includes('indeed.com')) source = 'indeed';
            else if (url.includes('cutshort.io')) source = 'cutshort';
            else if (url.includes('glassdoor.')) source = 'glassdoor';
            else if (url.includes('foundit.in')) source = 'foundit';
            else if (url.includes('timesjobs.com')) source = 'timesjobs';
            else if (url.includes('shine.com')) source = 'shine';

            // Portal-specific URL patterns for job detail pages
            const jobUrlPatterns = [
                '/job/', '/jobs/', '/career/', '/position/', '/vacancy/', '/opening/',
                '/job-details', '/jobdetails', '/job-description',
                '/jd/', '/view-job/', '/apply-job/',
                // Cutshort: /jobs/<id>-<slug>
                /\/jobs\/\d+-/,
                // Foundit: /job-details/ or /srdc/jobs/
                /\/job-details\//, /\/srdc\/jobs\//,
                // TimesJobs: /job-detail/ or /jobs/<keyword>-jobs-<id>
                /\/job-detail\//, /\/jobs\/.*-jobs-\d+/,
                // Shine: /job-details/ or /job/
                /\/job-details\//, /\/job\/\d+/,
            ];

            // Find links that look like individual job pages
            const allLinks = document.querySelectorAll('a[href]');
            for (const link of allLinks) {
                const href = link.href || '';
                const text = link.innerText?.trim() || '';

                // Must be a job detail link
                let isJobLink = false;
                for (const pattern of jobUrlPatterns) {
                    if (typeof pattern === 'string') {
                        if (href.includes(pattern)) { isJobLink = true; break; }
                    } else {
                        if (pattern.test(href)) { isJobLink = true; break; }
                    }
                }
                if (!isJobLink) continue;
                if (seenUrls.has(href)) continue;

                // Title must look like a job title
                if (text.length < 4 || text.length > 120) continue;
                const jobKeywords = ['developer', 'engineer', 'analyst', 'manager', 'consultant',
                    'architect', 'specialist', 'designer', 'lead', 'senior', 'junior',
                    'intern', 'trainee', 'associate', 'coordinator', 'administrator',
                    'tester', 'qa', 'devops', 'full stack', 'backend', 'frontend',
                    'data', 'ml', 'ai', 'cloud', 'security', 'network', 'system',
                    'product', 'project', 'program', 'business', 'technical',
                    'software', 'hardware', 'mobile', 'web', 'appian', 'java',
                    'python', 'react', 'angular', 'node', 'sql', 'fresher'];
                const hasJobKeyword = jobKeywords.some(kw => text.toLowerCase().includes(kw));
                if (!hasJobKeyword) continue;

                seenUrls.add(href);

                // Try to find parent card for context
                let card = link.closest('div, article, li, section');
                let company = '';
                let location = '';
                let experience = '';
                let salary = '';
                let posted_text = '';

                if (card) {
                    const lines = card.innerText?.split('\n').map(l => l.trim()).filter(l => l.length > 0) || [];
                    for (const line of lines) {
                        if (line === text) continue;
                        if (line.length > 2 && line.length < 80 &&
                            /^[A-Z][a-zA-Z\s.&()'\-]+$/.test(line) &&
                            !line.toLowerCase().includes('job') &&
                            !line.toLowerCase().includes('apply') &&
                            !line.toLowerCase().includes('location')) {
                            company = line;
                            break;
                        }
                    }
                    // Extract posting date
                    for (const line of lines) {
                        const ll = line.toLowerCase();
                        if (ll.match(/\d+\s*(?:day|hour|minute|week|month)s?\s*ago/i) ||
                            ll.match(/posted\s+/i) ||
                            ll === 'just posted' || ll === 'today' || ll === 'yesterday') {
                            posted_text = line.replace(/^posted\s*/i, '').trim();
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.toLowerCase().includes('hyderabad') || line.toLowerCase().includes('bangalore') ||
                            line.toLowerCase().includes('chennai') || line.toLowerCase().includes('mumbai') ||
                            line.toLowerCase().includes('delhi') || line.toLowerCase().includes('pune') ||
                            line.toLowerCase().includes('remote')) {
                            location = line;
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.match(/\d[\s-]*[\d+]*\s*y(?:ears?|rs?)/i) ||
                            line.match(/fresher/i) ||
                            line.match(/^0[\s-]*[-–]\s*\d/i)) {
                            experience = line;
                            break;
                        }
                    }
                    for (const line of lines) {
                        if (line.includes('\u20b9') || line.match(/lac|lakh|k\/yr|per annum|PA\b/i)) {
                            salary = line;
                            break;
                        }
                    }
                }

                jobs.push({
                    title: text,
                    company: company || 'Unknown',
                    location: location || 'Not specified',
                    source,
                    source_url: href,
                    apply_url: href,
                    salary: salary || 'Not specified',
                    description: '',
                    experience_required: experience || 'Not specified',
                    posted_text
                });
            }

            return jobs;
        }""")

        validated = []
        seen = set()
        for job in jobs:
            key = job.get('title', '').lower().strip()
            if key and key not in seen:
                seen.add(key)
                validated.append(job)
        return validated[:30]

    async def get_url(self) -> str:
        """Get current URL."""
        return self.page.url

    def log_action(self, action: str, result: str):
        """Log an action."""
        self._action_log.append({"action": action, "result": result, "time": time.time()})

    def get_action_log(self) -> List[Dict]:
        """Get action log."""
        return self._action_log

    def click_at_coordinates(self, x: int, y: int) -> "ActionResult":
        """Click at screen coordinates using PyAutoGUI."""
        m = _get_models()
        start_time = time.time()
        if not PYAUTOGUI_AVAILABLE:
            return m.ActionResult(
                success=False,
                action_type=m.ActionType.CLICK,
                message="PyAutoGUI not available",
                execution_time_ms=0,
                error="Module not installed",
            )
        try:
            pyautogui.click(x, y)
            time.sleep(0.5)
            execution_time = int((time.time() - start_time) * 1000)
            return m.ActionResult(
                success=True,
                action_type=m.ActionType.CLICK,
                message=f"Clicked at ({x}, {y})",
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return m.ActionResult(
                success=False,
                action_type=m.ActionType.CLICK,
                message=f"Failed to click at ({x}, {y})",
                execution_time_ms=execution_time,
                error=str(e),
            )

    def type_text_at_coordinates(self, x: int, y: int, text: str) -> "ActionResult":
        """Click at coordinates and type text using PyAutoGUI."""
        m = _get_models()
        start_time = time.time()
        if not PYAUTOGUI_AVAILABLE:
            return m.ActionResult(
                success=False,
                action_type=m.ActionType.TYPE,
                message="PyAutoGUI not available",
                execution_time_ms=0,
                error="Module not installed",
            )
        try:
            pyautogui.click(x, y)
            time.sleep(0.3)
            pyautogui.typewrite(text, interval=0.05)
            time.sleep(0.5)
            execution_time = int((time.time() - start_time) * 1000)
            return m.ActionResult(
                success=True,
                action_type=m.ActionType.TYPE,
                message=f"Typed '{text}' at ({x}, {y})",
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return m.ActionResult(
                success=False,
                action_type=m.ActionType.TYPE,
                message=f"Failed to type at ({x}, {y})",
                execution_time_ms=execution_time,
                error=str(e),
            )

    def scroll_page(self, direction: str = "down", amount: int = 500) -> "ActionResult":
        """Scroll page using PyAutoGUI."""
        m = _get_models()
        start_time = time.time()
        if not PYAUTOGUI_AVAILABLE:
            return m.ActionResult(
                success=False,
                action_type=m.ActionType.SCROLL,
                message="PyAutoGUI not available",
                execution_time_ms=0,
                error="Module not installed",
            )
        try:
            if direction == "down":
                pyautogui.scroll(-amount)
            elif direction == "up":
                pyautogui.scroll(amount)
            elif direction == "bottom":
                pyautogui.hotkey("ctrl", "end")
            time.sleep(1.5)
            execution_time = int((time.time() - start_time) * 1000)
            return m.ActionResult(
                success=True,
                action_type=m.ActionType.SCROLL,
                message=f"Scrolled {direction} by {amount}",
                execution_time_ms=execution_time,
            )
        except Exception as e:
            execution_time = int((time.time() - start_time) * 1000)
            return m.ActionResult(
                success=False,
                action_type=m.ActionType.SCROLL,
                message=f"Failed to scroll {direction}",
                execution_time_ms=execution_time,
                error=str(e),
            )

    async def get_page_state(self) -> "PageState":
        """Get current page state including viewport and popup detection."""
        m = _get_models()
        try:
            url = await self.get_url()
            title = await self.page.title()
            viewport = self.page.viewport_size
            has_popup = await self.page.evaluate("""() => {
                const overlays = document.querySelectorAll(
                    '[class*="popup"], [class*="modal"], [class*="overlay"], ' +
                    '[class*="dialog"], [class*="banner"], [class*="cookie"], ' +
                    '[role="dialog"], [role="alertdialog"]'
                );
                return overlays.length > 0;
            }""")
            popup_type = None
            if has_popup:
                popup_type = await self.page.evaluate("""() => {
                    const popup = document.querySelector(
                        '[class*="cookie"], [class*="banner"]'
                    );
                    if (popup) return 'cookie_banner';
                    const dialog = document.querySelector('[role="dialog"]');
                    if (dialog) return 'dialog';
                    const modal = document.querySelector('[class*="modal"]');
                    if (modal) return 'modal';
                    return 'unknown';
                }""")
            return m.PageState(
                url=url,
                title=title,
                is_loaded=True,
                has_popup=has_popup,
                popup_type=popup_type,
                viewport_width=viewport.get("width", 1400) if viewport else 1400,
                viewport_height=viewport.get("height", 900) if viewport else 900,
            )
        except Exception as e:
            return m.PageState(
                url="",
                title="",
                is_loaded=False,
                has_popup=False,
                viewport_width=1400,
                viewport_height=900,
            )

    def is_browser_crashed(self) -> bool:
        """Check if browser process has crashed or become unresponsive."""
        try:
            if not self.browser or not self.page:
                return True
            # Try a lightweight check — if the connection is dead, this will fail
            if hasattr(self.page, 'is_closed') and self.page.is_closed():
                return True
            if hasattr(self.context, 'pages') and not self.context.pages:
                return True
            return False
        except Exception:
            return True

    async def close_extra_tabs(self) -> int:
        """Close all tabs/pages except the main page. Returns number of tabs closed."""
        if not self.context or not self.page:
            return 0
        closed = 0
        pages = list(self.context.pages)
        for p in pages:
            if p != self.page:
                try:
                    await p.close()
                    closed += 1
                except Exception:
                    pass
        if closed:
            logger.info(f"Closed {closed} extra tab(s)")
            print(f"[BROWSER] Closed {closed} extra tab(s)", flush=True)
        return closed
