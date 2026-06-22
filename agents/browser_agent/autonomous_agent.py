"""Autonomous Browser Agent - Efficient job search with Mistral + DOM extraction.

Architecture:
  Step 3.5 (Brain) = Planning, keywords, matching, scoring
  Mistral (Eyes) = Visual interaction ONLY (click filters, scroll, select jobs)
  DOM Extraction = Fast data extraction (job details from HTML)

Efficient Flow:
  1. Brain creates plan (keywords, portals)
  2. Navigate to portal, search with keywords
  3. Close popups, check listings visible
  4. DOM extracts job listings (fast, no API cost)
  5. Open detail pages for enrichment
  6. DOM extracts full job details from detail page
  7. Post-scrape filter: reject non-tech, senior roles, wrong location
  8. Repeat for next portal
"""
import json
import re
import time
import random
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
import logging
from ai.ai_client import get_ai_client
from agents.browser_agent.browser_controller import BrowserController

logger = logging.getLogger(__name__)


def _parse_posted_date(text: str) -> Optional[datetime]:
    """Convert relative/absolute date text to datetime. Returns None if unrecognizable."""
    if not text:
        return None
    t = text.strip().lower()
    now = datetime.utcnow()

    # Relative patterns: "2 days ago", "3 hours ago", "5 weeks ago", "1 month ago"
    m = re.search(r'(\d+)\s*(minute|hour|day|week|month)s?\s*ago', t)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        if unit == 'minute':
            return now - timedelta(minutes=num)
        elif unit == 'hour':
            return now - timedelta(hours=num)
        elif unit == 'day':
            return now - timedelta(days=num)
        elif unit == 'week':
            return now - timedelta(weeks=num)
        elif unit == 'month':
            return now - timedelta(days=num * 30)

    # "just posted", "today", "just now"
    if any(w in t for w in ['just posted', 'just now', 'today']):
        return now

    # "yesterday"
    if 'yesterday' in t:
        return now - timedelta(days=1)

    # Absolute: "15 May", "May 15", "15 May 2026", "May 15, 2026"
    months = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
              'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12}
    # "15 May 2026" or "15 May"
    m = re.search(r'(\d{1,2})\s+(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s,]*(\d{4})?', t)
    if m:
        day = int(m.group(1))
        month = months.get(m.group(2)[:3])
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            return datetime(year, month, day)
        except:
            pass

    # "May 15, 2026" or "May 15"
    m = re.search(r'(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+(\d{1,2})[\s,]*(\d{4})?', t)
    if m:
        month = months.get(m.group(1)[:3])
        day = int(m.group(2))
        year = int(m.group(3)) if m.group(3) else now.year
        try:
            return datetime(year, month, day)
        except:
            pass

    # "posted X days ago" without the "ago" (some portals)
    m = re.search(r'posted\s+(\d+)\s*(minute|hour|day|week|month)', t)
    if m:
        num = int(m.group(1))
        unit = m.group(2)
        if unit == 'day':
            return now - timedelta(days=num)
        elif unit == 'week':
            return now - timedelta(weeks=num)
        elif unit == 'hour':
            return now - timedelta(hours=num)

    # Glassdoor short format: "2d", "30d+", "6d ago"
    m = re.search(r'(\d+)\s*d(?:\+|\s|$|ago)', t)
    if m:
        return now - timedelta(days=int(m.group(1)))

    return None


class AutonomousAgent:
    """Efficient job search agent - Mistral for UI, DOM for data."""

    def __init__(self, headless: bool = False, proxy: str = None):
        self.ai = get_ai_client()
        self.browser = BrowserController(headless=headless, proxy=proxy)
        self._log_entries = []
        self._brain_context = {}

    def _log(self, message: str):
        self._log_entries.append(message)
        logger.info(message)

    async def _mistral_action(self, instruction: str, screenshot_b64: str = None) -> Dict:
        """Ask Mistral to perform a visual action (click, scroll, select)."""
        try:
            prompt = f"""You are a browser automation agent. Execute this action:

INSTRUCTION: {instruction}

Current URL: {self.browser.page.url if self.browser.page else 'unknown'}

Respond with ONLY a JSON object:
{{
  "action": "click|scroll|select|type|wait|done",
  "target": "What to click/select (text, label, or description)",
  "value": "Value to type or select (if applicable)",
  "success": true/false,
  "message": "What you did or why it failed"
}}"""

            messages = [
                {"role": "system", "content": "You are a browser automation agent. Respond with JSON only."},
                {"role": "user", "content": prompt}
            ]

            # Add screenshot if provided
            if screenshot_b64:
                messages[1]["content"] = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{screenshot_b64}"}}
                ]

            response = await self.ai.chat_completion(
                messages=messages,
                model="mistralai/mistral-large-3-675b-instruct-2512",
                temperature=0.1,
                max_tokens=200,
            )

            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                return json.loads(json_match.group())

        except Exception as e:
            self._log(f"Mistral action error: {e}")

        return {"action": "wait", "success": False, "message": "Could not process"}

    async def _click_element(self, selectors: List[str], timeout: int = 3000) -> bool:
        """Try to click an element using multiple selectors."""
        for selector in selectors:
            try:
                await self.browser.page.click(selector, timeout=timeout)
                self._log(f"Clicked: {selector}")
                return True
            except:
                continue
        return False

    async def _extract_jobs_from_listing(self) -> List[Dict]:
        """Extract job listings from current page using DOM (fast, no API cost)."""
        try:
            jobs = await self.browser.extract_jobs()
            if jobs:
                self._log(f"DOM extracted {len(jobs)} jobs from listing")
                return jobs
        except Exception as e:
            self._log(f"DOM extraction error: {e}")

        return []

    async def _open_job_and_extract(self, job_url: str) -> Dict:
        """Open a job page and extract details using DOM (fast). Skips Cloudflare-blocked URLs."""
        # Skip known Cloudflare-blocked portals — but only if URL still looks like the
        # original portal after redirect (allow if redirected to job content)
        is_glassdoor = "glassdoor" in job_url.lower()

        for attempt in range(3):  # Retry twice on failure
            new_page = None
            try:
                new_page = await self.browser.context.new_page()
                try:
                    await new_page.goto(job_url, wait_until='domcontentloaded', timeout=45000)
                except Exception as nav_err:
                    if attempt < 2:
                        await asyncio.sleep(2 + attempt * 2)
                        if new_page:
                            try: await new_page.close()
                            except: pass
                        continue
                    raise

                # Check if we landed on a Cloudflare challenge or login page
                page_url = new_page.url
                page_title = ""
                try:
                    page_title = (await new_page.title()).lower()
                except:
                    pass
                # Skip if stuck on challenge page
                if "challenge" in page_url or "cdn-cgi" in page_url or "glassdoor.com/verify" in page_url:
                    await new_page.close()
                    return {}

                # Check page content for Cloudflare block
                try:
                    quick_content = (await new_page.content()).lower()
                    if "humans only" in quick_content or "ray id:" in quick_content and "cloudflare" in quick_content:
                        await new_page.close()
                        return {}
                except:
                    pass

                # If redirected to login/signin, try to grab whatever is visible
                if "login" in page_url or "signin" in page_url or "auth" in page_url:
                    pass  # Still try to extract — some pages show partial content

                await asyncio.sleep(2)

                # Extract using DOM — multi-strategy for all portals
                job_data = await new_page.evaluate("""() => {
                const data = {
                    title: '',
                    company: '',
                    location: '',
                    description: '',
                    requirements: [],
                    skills: [],
                    experience: '',
                    salary: '',
                    posted_text: '',
                    apply_url: window.location.href
                };

                // Get title — try multiple selectors
                for (const sel of [
                    'h1', '[class*="job-title"]', '[class*="jobTitle"]',
                    '[data-testid="job-title"]', '[class*="jd-title"]',
                    '.job-title', '#job-title'
                ]) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 3) { data.title = el.innerText.trim(); break; }
                }

                // Get company
                for (const sel of [
                    '[class*="company"]', '[class*="employer"]',
                    '[data-testid="company-name"]', '[class*="companyName"]',
                    'a[class*="company"]'
                ]) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 1) { data.company = el.innerText.trim(); break; }
                }

                // Get location
                for (const sel of [
                    '[class*="location"]', '[data-testid="location"]',
                    '[class*="jobLocation"]'
                ]) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 1) { data.location = el.innerText.trim(); break; }
                }

                // Get description — try specific selectors first, then fallback to body
                // Portal-specific selectors + generic ones
                const descSelectors = [
                    // Naukri
                    '[class*="job-description"]', '[class*="jobDescription"]',
                    '[class*="jd-desc"]', '[class*="jdHeader"] + div',
                    '[class*="naukri-description"]', '[id*="jobDescription"]',
                    // LinkedIn
                    '[class*="description__text"]', '[class*="show-more-less-html"]',
                    '[class*="jobs-description"]', '.jobs-box__html-content',
                    // Indeed
                    '[class*="jobsearch-jobDescriptionText"]', '#jobDescriptionText',
                    '[class*="job-description"]',
                    // Foundit/monster
                    '[class*="job-detail"]', '[class*="jobDetail"]',
                    '[class*="jd-section"]', '[class*="job-desc"]',
                    // CutShort
                    '[class*="JobDescription"]', '[class*="job_about"]',
                    //通用
                    '[data-testid="job-description"]',
                    '[class*="detail-description"]', '[class*="description"]',
                    '[class*="detail"]', '[class*="content"]',
                    'article', 'main', '[role="main"]'
                ];
                for (const sel of descSelectors) {
                    const el = document.querySelector(sel);
                    if (el) {
                        const text = el.innerText.trim();
                        if (text.length > 100) { data.description = text.substring(0, 3000); break; }
                    }
                }

                // If no description from selectors, try getting ALL text blocks and pick the longest one
                if (!data.description || data.description.length < 80) {
                    // Strategy 1: Find largest text block on page (usually the description)
                    const allDivs = document.querySelectorAll('div, section, p');
                    let bestText = '';
                    for (const div of allDivs) {
                        // Skip tiny or navigation elements
                        if (div.children.length > 20) continue;
                        const text = div.innerText.trim();
                        if (text.length > bestText.length && text.length > 150) {
                            // Skip if it looks like a nav/header/footer
                            const lower = text.toLowerCase();
                            if (!lower.startsWith('menu') && !lower.startsWith('sign in') &&
                                !lower.startsWith('home') && text.length < 5000) {
                                bestText = text;
                            }
                        }
                    }
                    if (bestText.length > 150) {
                        data.description = bestText.substring(0, 3000);
                    }
                }

                // Strategy 2: Look for job description section markers in body text
                if (!data.description || data.description.length < 80) {
                    const body = document.body.innerText || '';
                    const markers = ['job description', 'about the role', 'about the job',
                        'what you will do', 'responsibilities', 'requirements', 'qualifications',
                        'what we are looking for', 'role description', 'key responsibilities',
                        'about the company', 'key skills', 'skills required', 'job summary',
                        'what you\'ll do', 'your role', 'role overview', 'job details',
                        'job summary', 'position summary', 'overview'];
                    const lowerBody = body.toLowerCase();
                    for (const marker of markers) {
                        const idx = lowerBody.indexOf(marker);
                        if (idx !== -1) {
                            // Start from the marker, grab up to 3000 chars
                            const snippet = body.substring(idx, idx + 3000).trim();
                            if (snippet.length > (data.description || '').length) {
                                data.description = snippet;
                            }
                            break;
                        }
                    }
                    if ((!data.description || data.description.length < 80) && body.length > 200) {
                        data.description = body.substring(0, 2500).trim();
                    }
                }

                // Get salary
                for (const sel of ['[class*="salary"]', '[data-testid="salary"]', '[class*="compensation"]']) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 1) { data.salary = el.innerText.trim(); break; }
                }

                // Get experience — try selector, then parse from text
                for (const sel of ['[class*="experience"]', '[data-testid="experience"]', '[class*="exp-required"]']) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 1) { data.experience = el.innerText.trim(); break; }
                }
                if (!data.experience) {
                    const text = (data.description || document.body.innerText || '').substring(0, 1000);
                    const expMatch = text.match(/(?:experience|exp)[\\s:.-]*(\\d+)[\\s-]*[-–]?[\\s]*(\\d+)?[\\s]*(?:years?|yrs?)/i)
                        || text.match(/(\\d+)[\\s-]*[-–]?[\\s]*(\\d+)?[\\s]*(?:years?|yrs?)[\\s]*(?:of\\s*)?(?:experience|exp)/i);
                    if (expMatch) data.experience = expMatch[0];
                    const fresherMatch = text.match(/fresher|entry.?level|0[\\s-]*[-–]?[\\s]*1[\\s]*(?:years?|yrs?)/i);
                    if (fresherMatch && !data.experience) data.experience = fresherMatch[0];
                }

                // Extract skills from description
                if (data.description) {
                    const skillPatterns = /(?:java|python|javascript|react|angular|node[\\s.]?js|sql|html|css|aws|docker|git|spring[\\s.]?boot|django|flask|fastapi|typescript|vue[\\s.]?js|mongodb|postgresql|redis|kubernetes|hibernate|microservices|rest[\\s.]?api|graphql|junit|selenium|jenkins|terraform|c[\\s+#]|c\\+\\+|ruby|go|golang|rust|scala|kotlin|swift|flutter|react[\\s.]?native|next[\\s.]?js|nuxt|svelte|tailwind|bootstrap|sass|less|webpack|vite|npm|yarn|pnpm|mysql|oracle|sql[\\s.]?server|elasticsearch|kafka|rabbitmq|celery|apache|nginx|linux|agile|scrum|jira|confluence|figma|photoshop|illustrator|power[\\s.]?bi|tableau|excel|machine[\\s.]?learning|deep[\\s.]?learning|tensorflow|pytorch|opencv|nlp|ai|ml|data[\\s.]?science|data[\\s.]?analysis|etl|airflow|spark|hadoop|hive|snowflake|redshift|bigquery|databricks|ci[\\/]?cd|devops|microsoft[\\s.]?azure|gcp|google[\\s.]?cloud)/gi;
                    const matches = data.description.match(skillPatterns);
                    if (matches) data.skills = [...new Set(matches.map(s => s.toLowerCase()))];
                }

                // Extract posting date
                const datePatterns = [
                    /\\d+\\s*(?:minute|hour|day|week|month)s?\\s*ago/i,
                    /(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\\s+\\d{1,2}[,\s]*\\d{0,4}/i,
                    /\\d{1,2}\\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*[,\s]*\\d{0,4}/i,
                    /just\\s+posted|today|yesterday/i
                ];
                const dateBody = document.body.innerText || '';
                for (const pat of datePatterns) {
                    const m = dateBody.match(pat);
                    if (m) { data.posted_text = m[0]; break; }
                }

                return data;
            }""")

                await new_page.close()
                new_page = None

                if job_data and job_data.get("title"):
                    self._log(f"Extracted job: {job_data.get('title', 'Unknown')}")
                    return job_data

            except Exception as e:
                if attempt < 2:
                    await asyncio.sleep(2 + attempt * 2)  # Increasing backoff
                    continue
                self._log(f"Job detail extraction error: {e}")
            finally:
                if new_page:
                    try:
                        await new_page.close()
                    except:
                        pass

        return {}

    async def _scroll_and_extract(self, max_scrolls: int = 3, portal: str = "") -> List[Dict]:
        """Scroll page and extract jobs at each position."""
        all_jobs = []

        # Glassdoor uses infinite scroll — more scrolls needed
        scrolls = max_scrolls + 2 if portal == "glassdoor" else max_scrolls

        for i in range(scrolls):
            # Extract from current position
            jobs = await self._extract_jobs_from_listing()
            for job in jobs:
                if not any(j.get("title") == job.get("title") and j.get("company") == job.get("company") for j in all_jobs):
                    all_jobs.append(job)

            # Random scroll amount to appear human-like
            scroll_px = random.randint(500, 1200)
            await self.browser.scroll("down", scroll_px)
            await asyncio.sleep(random.uniform(0.8, 2.0))

        return all_jobs

    async def _try_dom_pagination(self) -> bool:
        """Try to click 'Next' or page 2 via DOM selectors. Returns True if successful."""
        next_selectors = [
            "a:has-text('Next')", "a:has-text('next')", "button:has-text('Next')",
            "a[aria-label='Next']", "a[aria-label='next']",
            "a:has-text('»')", "a:has-text('>')",
            "a.pagination-next", "li.next a", "a[data-automation='pagination-next']",
            "button[aria-label='Next page']",
        ]
        for selector in next_selectors:
            try:
                el = self.browser.page.locator(selector).first
                if await el.is_visible(timeout=2000):
                    await el.click()
                    await self.browser.wait(3)
                    self._log(f"Clicked next page via DOM: {selector}")
                    return True
            except:
                continue
        return False

    async def _paginate_and_extract(self, portal: str, max_pages: int = 3) -> List[Dict]:
        """Extract jobs from current page, then paginate and extract more.
        Uses DOM for extraction, tries DOM-first for pagination, falls back to vision."""
        all_jobs = []

        for page_num in range(1, max_pages + 1):
            self._log(f"Extracting page {page_num}...")

            # Extract jobs from current page
            page_jobs = await self._scroll_and_extract(max_scrolls=3, portal=portal)
            for job in page_jobs:
                if not any(j.get("title") == job.get("title") and j.get("company") == job.get("company") for j in all_jobs):
                    all_jobs.append(job)
            self._log(f"Page {page_num}: {len(page_jobs)} jobs (total: {len(all_jobs)})")

            if page_num >= max_pages:
                break

            # Try DOM-based pagination first (fast, no API cost)
            prev_url = self.browser.page.url
            dom_success = await self._try_dom_pagination()

            if dom_success:
                # Check if URL changed or new content loaded
                new_url = self.browser.page.url
                if new_url != prev_url:
                    self._log(f"DOM pagination worked, new URL: {new_url[:80]}")
                    await self.browser.wait(2)
                    continue
                # URL didn't change — might have loaded content dynamically
                await self.browser.wait(2)
                continue

            # DOM pagination failed — try vision
            self._log("DOM pagination failed, trying vision...")
            try:
                import os
                has_mistral = os.getenv("MISTRAL_API_KEY")
                has_nvidia = os.getenv("NVIDIA_API_KEY")
                
                if not has_mistral and not has_nvidia:
                    self._log("No MISTRAL_API_KEY or NVIDIA_API_KEY, stopping pagination")
                    break
                
                from agents.vision_scraper.ui_tars_agent import UITarsAgent
                # Prefer NVIDIA for vision if Mistral isn't available
                vision_key = has_mistral or has_nvidia
                agent = UITarsAgent(self.browser, vision_key, max_steps=2)
                result = await agent.run(
                    "Look at the page. If there is a 'Next' button, 'Load More' button, or pagination links "
                    "(like page numbers 2, 3, etc.), click the Next button or page 2 link to go to the next page. "
                    "If there is no way to go to the next page, say finished()."
                )
                status = result.get("status", "unknown")
                self._log(f"Vision pagination result: {status}")

                if status in ("success", "finished"):
                    new_url = self.browser.page.url
                    if new_url != prev_url:
                        self._log(f"Vision pagination worked, new URL: {new_url[:80]}")
                        await self.browser.wait(2)
                        continue
                    else:
                        self._log("Vision tried but URL unchanged, stopping pagination")
                        break
                else:
                    self._log("Vision pagination failed, stopping")
                    break

            except Exception as e:
                self._log(f"Vision pagination error: {e}")
                break

        return all_jobs

    async def run_task(self, task: str, target_count: int = 20, keywords: str = "",
                       is_fresher: bool = False, location: str = "Hyderabad",
                       portals: List[str] = None, is_us: bool = False,
                       overall_timeout: int = 1200) -> List[Dict]:
        """Run efficient job search using Mistral for UI, DOM for data."""
        self._log(f"Starting efficient job search")
        self._log(f"Keywords: {keywords}, Location: {location}, Fresher: {is_fresher}, Target: {target_count}")
        start_time = time.time()

        self._log(f"Launching browser (headless={self.browser.headless})...")
        try:
            await asyncio.wait_for(self.browser.start(), timeout=90)
            self._log(f"Browser launched successfully")
        except asyncio.TimeoutError:
            self._log(f"ERROR: Browser launch timed out after 90s")
            await self.browser.close()
            return []
        except Exception as e:
            self._log(f"ERROR: Browser launch failed: {type(e).__name__}: {e}")
            return []
        all_jobs = []
        seen_urls = set()
        self._search_cache = {}  # {(portal, keyword, location): {"jobs": [...], "timestamp": float}}
        self._glassdoor_blocked = False  # Track if Glassdoor triggered CAPTCHA
        self._is_fresher = is_fresher  # Used by _build_search_url for portal-specific filters
        portals_to_search = portals or ["naukri", "indeed", "linkedin"]
        glassdoor_blocked = False  # Once CAPTCHA hits, skip for all remaining keywords

        # Split keywords — search each one separately to maximize coverage
        keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
        if not keyword_list:
            keyword_list = [keywords]

        # Collect more raw jobs than target since many get filtered out
        raw_target = target_count * 5
        time_up = False
        browser_dead = False

        try:
            for kw_idx, kw in enumerate(keyword_list):
                if time_up or browser_dead:
                    break

                # Delay between keyword rounds — longer if Glassdoor is in the mix
                if kw_idx > 0:
                    delay = random.uniform(10, 15) if "glassdoor" in portals_to_search and not glassdoor_blocked else random.uniform(5, 10)
                    await asyncio.sleep(delay)

                self._log(f"\n{'#'*60}")
                self._log(f"Keyword round: '{kw}' (total so far: {len(all_jobs)} raw jobs)")
                self._log(f"{'#'*60}")

                for portal in portals_to_search:
                    if time_up or browser_dead:
                        break

                    self._log(f"\n{'='*50}")
                    self._log(f"Searching: {portal} for '{kw}'")
                    self._log(f"{'='*50}")

                    # Check overall time budget
                    elapsed = time.time() - start_time
                    if elapsed > overall_timeout:
                        self._log(f"Overall time budget ({overall_timeout}s) reached at {elapsed:.0f}s, stopping")
                        time_up = True
                        break

                    # Skip Glassdoor entirely if Cloudflare blocked it
                    if portal == "glassdoor":
                        if getattr(self, '_glassdoor_blocked', False):
                            self._log(f"Glassdoor blocked by Cloudflare — skipping")
                            continue

                    try:
                        portal_jobs = await asyncio.wait_for(
                            self._search_single_portal(portal, kw, location, 50, seen_urls),
                            timeout=180,  # 3 min per portal — visiting all detail pages takes time
                        )
                        all_jobs.extend(portal_jobs)
                        self._log(f"Portal {portal} [{kw}]: found {len(portal_jobs)} jobs (total: {len(all_jobs)})")
                    except asyncio.TimeoutError:
                        self._log(f"Portal {portal} [{kw}]: timed out after 180s, moving on")
                    except Exception as e:
                        err_msg = str(e)
                        self._log(f"Portal {portal} [{kw}]: failed with {type(e).__name__}: {err_msg[:100]}")
                        # Browser crash recovery — relaunch if context/page died
                        is_closed_err = (
                            "TargetClosedError" in type(e).__name__ or
                            "closed" in err_msg.lower() or
                            "connection" in err_msg.lower()
                        )
                        if is_closed_err:
                            self._log("Browser crashed — attempting recovery...")
                            try:
                                await self.browser.close()
                            except:
                                pass
                            try:
                                self.browser = BrowserController(headless=False, proxy=self.browser.proxy)
                                await self.browser.start()
                                self._log("Browser recovered successfully")
                            except Exception as recover_err:
                                self._log(f"Browser recovery failed: {recover_err}")
                                browser_dead = True
                                break

                    # Anti-detection delay between portals (random 3-7s)
                    delay = random.uniform(3, 7)
                    await asyncio.sleep(delay)

                    # Check browser health after each portal — recover if dead
                    try:
                        if self.browser.is_browser_crashed():
                            self._log("Browser died after portal search — attempting recovery...")
                            try:
                                await self.browser.close()
                            except:
                                pass
                            try:
                                self.browser = BrowserController(headless=False, proxy=self.browser.proxy)
                                await self.browser.start()
                                self._log("Browser recovered successfully")
                            except Exception as recover_err:
                                self._log(f"Browser recovery failed: {recover_err}")
                                browser_dead = True
                                break
                    except Exception:
                        pass

                    # Close any extra tabs/popups opened by the portal
                    try:
                        await self.browser.close_extra_tabs()
                    except Exception:
                        pass

                    # Check browser still alive between portals
                    if self.browser.is_browser_crashed():
                        self._log("Browser crashed, stopping search")
                        browser_dead = True
                        break

        except Exception as e:
            self._log(f"Error: {e}")
        finally:
            await self.browser.close()

        # Log extraction health stats
        try:
            if self.browser.browser:
                health = self.browser.get_portal_health()
                if health:
                    self._log(f"Portal health: {health}")
        except:
            pass

        # Filter jobs based on experience, relevance, and location
        filtered_jobs = self._filter_jobs(all_jobs, keywords, location, is_fresher)

        self._log(f"\nSearch complete: {len(filtered_jobs)} jobs found (filtered from {len(all_jobs)})")
        return filtered_jobs

    async def _search_single_portal(self, portal: str, keywords: str, location: str,
                                     remaining: int, seen_urls: set) -> List[Dict]:
        """Search a single portal with caching, network interception, and retry."""
        import time as _time

        # Check cache first
        cache_key = (portal, keywords.lower().strip(), location.lower().strip())
        cached = self._search_cache.get(cache_key)
        if cached and (_time.time() - cached["timestamp"]) < 1800:  # 30 min cache
            self._log(f"Cache hit for {portal}/{keywords} ({len(cached['jobs'])} cached jobs)")
            return [j for j in cached["jobs"] if j.get("source_url") not in seen_urls][:remaining]

        # Check portal health — skip retries if consistently broken
        is_healthy = self.browser.is_portal_healthy(portal)
        # LinkedIn is always blocked by login wall — don't waste retries
        if portal == "linkedin" and not is_healthy:
            max_retries = 0
        else:
            max_retries = 2 if is_healthy else 0

        search_url = self._build_search_url(portal, keywords, location)
        all_portal_jobs = []

        for attempt in range(max_retries + 1):
            if attempt > 0:
                wait_time = 3 * (2 ** (attempt - 1))  # 3s, 6s
                self._log(f"Retry {attempt}/{max_retries} for {portal} (waiting {wait_time}s)...")
                await asyncio.sleep(wait_time)

            self._log(f"Navigating: {search_url}")
            self.browser.clear_intercepted()

            # Close any leftover tabs from previous search
            try:
                await self.browser.close_extra_tabs()
            except Exception:
                pass

            try:
                # CloakBrowser already patches navigator.webdriver at C++ level — no JS override needed
                await self.browser.go_to(search_url, timeout=30000)
                await self.browser.wait(2)
            except Exception as e:
                self._log(f"Navigation failed: {e}")
                continue

            # Check for Cloudflare challenge / IP block — skip this keyword (not permanently)
            try:
                page_content = await self.browser.page.content()
                page_content_lower = page_content.lower()
                captcha_signals = [
                    ("ray id:" in page_content_lower and "cloudflare" in page_content_lower),
                    "humans only" in page_content_lower,
                    "access denied" in page_content_lower,
                    "cf_chl" in page_content_lower,
                    "verify you are human" in page_content_lower,
                    "security check" in page_content_lower and "glassdoor" in portal,
                    "captcha" in page_content_lower,
                    "unusual traffic" in page_content_lower,
                ]
                if any(captcha_signals):
                    self._log(f"BLOCKED: {portal} returned anti-bot challenge for '{kw}' — skipping")
                    # Mark Glassdoor as blocked so we skip it for ALL remaining keywords
                    if portal == "glassdoor":
                        self._glassdoor_blocked = True
                    break  # Skip to next keyword/portal immediately
            except:
                pass

            # Check for "no results" page — skip portal immediately
            try:
                await self.browser.wait(1)  # Wait for JS to render
                page_text = (await self.browser.get_page_content(max_chars=5000)).lower()
                # Only trigger if the page EXPLICITLY says no results (not just "no" in some sentence)
                no_result_signals = [
                    "no result", "no-result", "no jobs found",
                    "sorry no result", "no matching jobs", "we couldn't find",
                    "we couldn't find a match", "did not match any",
                    "no openings", "your search did not match", "no vacancies",
                    "please make sure your keywords",
                ]
                # Don't trigger if page says "showing X results" or "X jobs found"
                has_positive = "showing" in page_text and "results" in page_text
                has_positive = has_positive or ("found" in page_text and "jobs" in page_text and "no" not in page_text[:page_text.find("found")])
                if not has_positive and any(signal in page_text for signal in no_result_signals):
                    self._log(f"No results page detected on {portal} for '{kw}' — skipping")
                    # Mark as zero-result but don't penalize permanently (keyword might just not exist)
                    self.browser._extraction_stats.setdefault(portal, {"attempts": 0, "jobs": 0, "zeros": 0, "last_zero": 0})
                    self.browser._extraction_stats[portal]["attempts"] += 1
                    self.browser._extraction_stats[portal]["zeros"] += 1
                    break  # Skip to next portal
            except:
                pass

            # Vision-guided navigation (popup dismissal + experience filter)
            await self._vision_navigate(portal, keywords)

            # Check for LinkedIn login wall — try to dismiss it first
            if portal == "linkedin":
                if await self._check_linkedin_blocked():
                    self._log(f"LinkedIn sign-in wall detected, attempting dismiss...")
                    await self._close_popups()
                    # Also try LinkedIn-specific dismiss
                    for sel in [
                        "button[aria-label='Dismiss']",
                        "button.authwall-join-form-modal__dismiss",
                        ".join-form-modal__dismiss",
                        "button[data-tracking-control-name='authwall_dismiss_btn']",
                        "a.authwall-join-form-modal__dismiss",
                    ]:
                        try:
                            await self.browser.page.click(sel, timeout=1000)
                            await asyncio.sleep(0.5)
                        except:
                            continue
                    await self.browser.page.keyboard.press("Escape")
                    await asyncio.sleep(1)
                    # Re-check: if job links are visible, proceed anyway
                    try:
                        link_count = await self.browser.page.evaluate(
                            "() => document.querySelectorAll('a[href*=\"/jobs/view\"], a[href*=\"/job/\"]').length"
                        )
                        if link_count >= 3:
                            self._log(f"LinkedIn: {link_count} job links visible after dismiss, extracting anyway")
                        else:
                            self._log(f"LinkedIn blocked by login wall, skipping")
                            return []
                    except:
                        self._log(f"LinkedIn blocked by login wall, skipping")
                        return []

            await self.browser.wait(2)

            # Try network interception first (fast, structured data)
            intercepted = await self.browser.get_intercepted_jobs(portal)
            if intercepted:
                self._log(f"API intercept: {len(intercepted)} jobs from {portal}")
                api_detail_visits = 0
                for job in intercepted:
                    job_url = job.get("source_url") or job.get("apply_url") or ""
                    # Build a real search URL if no link available
                    if not job_url and job.get("title"):
                        from urllib.parse import quote_plus
                        title_q = quote_plus(job.get("title", ""))
                        loc_q = quote_plus(location)
                        title_d = title_q.replace("+", "-")
                        loc_d = loc_q.replace("+", "-")
                        ko_s = len(loc_d) + 1
                        ko_e = ko_s + len(title_d)
                        _exp_naukri = "?experience=0" if getattr(self, "_is_fresher", False) else ""
                        _exp_indeed = "&explvl=entry_level" if getattr(self, "_is_fresher", False) else ""
                        portal_search_urls = {
                            "naukri": f"https://www.naukri.com/{title_d}-jobs-in-{loc_d}{_exp_naukri}",
                            "indeed": f"https://in.indeed.com/jobs?q={title_q}&l={loc_q}{_exp_indeed}",
                            "linkedin": f"https://www.linkedin.com/jobs/search/?keywords={title_q}&location={loc_q}",
                            "shine": f"https://www.shine.com/job-search/{title_d}-jobs-in-{loc_d}" + ("?experienced=0" if getattr(self, "_is_fresher", False) else ""),
                            "foundit": f"https://www.foundit.in/srp/results?query={title_q}+{loc_q}" + ("&experience=0" if getattr(self, "_is_fresher", False) else ""),
                            "glassdoor": f"https://www.glassdoor.co.in/Job/{title_d}-{loc_d}-jobs-SRCH_IL.0,{len(loc_d)}_KO{ko_s},{ko_e}.htm",
                            "timesjobs": f"https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&from=brain&txtKeywords={title_q}&txtLocation={loc_q}",
                        }
                        job_url = portal_search_urls.get(portal, "")
                        if not job_url:
                            continue  # Skip if we can't build a search URL
                        job["source_url"] = job_url
                        job["apply_url"] = job_url
                    if not job_url or job_url in seen_urls:
                        continue
                    seen_urls.add(job_url)
                    if not job.get("source"):
                        job["source"] = portal
                    # Visit detail page for intercepted jobs missing description (cap at 5 per portal)
                    has_desc = job.get("description") and len(job.get("description", "")) > 40
                    if has_desc:
                        desc_lower = job["description"].lower()
                        if "cloudflare" in desc_lower or "ray id:" in desc_lower:
                            job["description"] = ""
                            has_desc = False
                    if not has_desc and job_url and api_detail_visits < 25:
                        await asyncio.sleep(random.uniform(1.5, 3.5))
                        api_detail_visits += 1
                        detailed = await self._open_job_and_extract(job_url)
                        try:
                            await self.browser.close_extra_tabs()
                        except Exception:
                            pass
                        if detailed:
                            detail_desc = detailed.get("description", "")
                            if detail_desc and ("cloudflare" in detail_desc.lower() or "ray id:" in detail_desc.lower()):
                                detailed["description"] = ""
                            for key in ["description", "experience_required", "experience", "salary", "skills"]:
                                if not job.get(key) and detailed.get(key):
                                    job[key] = detailed[key]
                            if detailed.get("company") and job.get("company", "Unknown") == "Unknown":
                                job["company"] = detailed["company"]
                            if detailed.get("location") and job.get("location", "Not specified") == "Not specified":
                                job["location"] = detailed["location"]
                            if not job.get("posted_text") and detailed.get("posted_text"):
                                job["posted_text"] = detailed["posted_text"]
                    all_portal_jobs.append(job)

            # DOM extraction (always run — catches what API missed)
            listing_jobs = await self._paginate_and_extract(portal, max_pages=3)
            self._log(f"DOM extraction: {len(listing_jobs)} jobs from {portal}")

            dom_detail_visits = 0
            max_dom_detail_visits = 15  # Limit to prevent hanging on detail pages

            for job in listing_jobs:
                if len(all_portal_jobs) >= remaining:
                    break
                job_url = job.get("source_url") or job.get("apply_url")
                if not job_url or job_url in seen_urls:
                    continue
                seen_urls.add(job_url)
                job["source"] = portal

                # Visit detail page for EVERY job missing description
                # Experience filtering requires full descriptions from all portals
                has_desc = job.get("description") and len(job.get("description", "")) > 40

                # Detect Cloudflare/blocked error pages in descriptions
                if has_desc:
                    desc_lower = job["description"].lower()
                    if "cloudflare" in desc_lower or "ray id:" in desc_lower or "requested url:" in desc_lower:
                        job["description"] = ""
                        has_desc = False

                # Limit detail page visits to prevent timeout
                if not has_desc and job_url and dom_detail_visits < max_dom_detail_visits:
                    dom_detail_visits += 1
                    # Random delay between detail page visits to avoid anti-bot detection
                    await asyncio.sleep(random.uniform(1.5, 3.5))
                    try:
                        # Add timeout to prevent hanging on slow detail pages
                        detailed = await asyncio.wait_for(
                            self._open_job_and_extract(job_url),
                            timeout=45  # 45 second timeout per detail page
                        )
                    except asyncio.TimeoutError:
                        self._log(f"Detail page timeout for {job_url[:50]}...")
                        detailed = {}
                    # Close any extra tabs opened by the detail page
                    try:
                        await self.browser.close_extra_tabs()
                    except Exception:
                        pass
                    if detailed:
                        # Check if detail page is also a Cloudflare block
                        detail_desc = detailed.get("description", "")
                        if detail_desc and ("cloudflare" in detail_desc.lower() or "ray id:" in detail_desc.lower()):
                            detailed["description"] = ""
                        # Merge: listing data fills gaps, detail fills the rest
                        for key in ["description", "experience_required", "experience", "salary", "skills"]:
                            if not job.get(key) and detailed.get(key):
                                job[key] = detailed[key]
                        if detailed.get("company") and job.get("company", "Unknown") == "Unknown":
                            job["company"] = detailed["company"]
                        if detailed.get("location") and job.get("location", "Not specified") == "Not specified":
                            job["location"] = detailed["location"]
                        if not job.get("posted_text") and detailed.get("posted_text"):
                            job["posted_text"] = detailed["posted_text"]

                # Convert posted_text to posted_date for filtering
                if not job.get("posted_date") and job.get("posted_text"):
                    parsed = _parse_posted_date(job["posted_text"])
                    if parsed:
                        job["posted_date"] = parsed.isoformat()

                all_portal_jobs.append(job)

            if all_portal_jobs:
                break  # Got jobs, no need to retry

            # If we extracted 0 jobs from DOM and API intercept, don't retry — skip immediately
            if not all_portal_jobs:
                self._log(f"0 jobs extracted from {portal} for '{keywords}' — skipping retries")
                break

        # Clean up any leaked tabs from detail page visits
        try:
            await self.browser.close_extra_tabs()
        except Exception:
            pass

        # Cache results
        if all_portal_jobs:
            self._search_cache[cache_key] = {"jobs": all_portal_jobs, "timestamp": _time.time()}

        return all_portal_jobs

    def _filter_jobs(self, jobs: List[Dict], keywords: str, location: str, is_fresher: bool) -> List[Dict]:
        """Filter jobs based on experience, relevance, and location."""
        filtered = []
        location_lower = location.lower()

        # Tech keywords for relevance filtering (must appear in title)
        tech_keywords = ["software", "developer", "programming", "coder", "tech", "java", "python",
                        "react", "angular", "node", "backend", "frontend", "full stack", "devops", "cloud",
                        "qa", "test", "automation", "database", "sql", "api", "web",
                        "mobile", "app", "application", "iot", "embedded", "cyber", "security", "network",
                        "appian", "bpm", "sail", "consultant", "sde", "programmer",
                        "data engineer", "data platform", "machine learning", "ai engineer",
                        "project coordinator", "project manager", "scrum master", "product owner",
                        "analyst", "data", "reporting", "power bi", "tableau", "etl"]

        # Non-tech job patterns to reject
        non_tech_patterns = ["teacher", "trainer", "chemist", "dental", "nurse", "accountant", "marketing", "sales",
                           "hr specialist", "business analyst", "content writer", "graphic designer",
                           "security officer", "receptionist", "admin", "clerk", "peon", "driver",
                           "cook", "cleaner", "housekeeping", "data entry", "typing", "back office",
                           "civil engineer", "mechanical engineer", "electrical engineer", "chemical engineer",
                           "construction", "site engineer", "maintenance engineer", "production engineer",
                           "field engineer", "plant engineer", "process engineer", "design engineer",
                           "biomedical", "aeronautical", "automobile", "automotive", "mining",
                           "architect", "surveyor", "foreman", "welder", "plumber", "electrician",
                           "fitter", "technician", "helper", "labour", "labor", "supervisor",
                           "warehouse", "logistics", "delivery", "driver", "pilot",
                           "real estate", "property", "hotel", "hospitality", "retail", "restaurant",
                           "banking", "insurance", "telecaller", "bpo", "voice process", "back office",
                           "recruitment", "talent acquisition", "human resource", "payroll",
                           "purchase", "procurement", "supply chain", "inventory", "merchandiser",
                           "pharmacist", "medical", "healthcare", "nursing", "clinical",
                           "contractor", "controller", "accounts payable", "accounts receivable",
                           "genius", "business data", "data scientist", "scientist",
                           "financial analyst", "finance", "treasury", "audit", "tax",
                           "customer support", "tech support", "service desk", "helpdesk",
                           "snowflake developer", "snowflake", "sap ", "sap consultant",
                           "oracle dba", "oracle apps", "peoplesoft", "siebel",
                           "returnship"]

        # "engineer" alone matches civil/mechanical/electrical — require tech qualifier
        engineer_requires_tech = ["software", "java", "python", "react", "node", "backend", "frontend",
                                  "full stack", "devops", "cloud", "data", "qa", "test", "automation",
                                  "web", "mobile", "app", "iot", "embedded", "cyber", "network",
                                  "platform", "systems", "sre", "machine learning", "ai"]

        # Location aliases
        city_aliases = {
            "hyderabad": ["hyderabad", "secunderabad", "cyberabad", "hyd"],
            "bangalore": ["bangalore", "bengaluru", "blr"],
            "pune": ["pune", "pimpri", "hinjewadi"],
            "chennai": ["chennai", "madras"],
            "delhi": ["delhi", "new delhi", "ncr", "gurgaon", "noida"],
            "mumbai": ["mumbai", "bombay", "thane"],
        }
        target_aliases = city_aliases.get(location_lower, [location_lower])

        # Date cutoff for "recent jobs only" filtering
        cutoff = datetime.utcnow() - timedelta(days=7)

        for job in jobs:
            # Filter out jobs older than 7 days (skip if no date info — allow those through)
            posted_text = job.get("posted_text", "")
            posted_date = _parse_posted_date(posted_text)
            if posted_date and posted_date < cutoff:
                continue
            if posted_date:
                job["posted_date"] = posted_date.isoformat()

            title = (job.get("title", "") or "").lower()
            company = (job.get("company", "") or "").lower()
            desc = (job.get("description", "") or "").lower()
            job_location = (job.get("location", "") or "").lower()
            exp_text = (job.get("experience_required", "") or job.get("experience", "") or "").lower()
            combined = title + " " + company + " " + desc

            # Skip salary search entries
            if "salary search" in title or "salary search" in desc[:100]:
                continue

            # Skip verification/CAPTCHA pages extracted as "jobs"
            if "additional verification" in title or "captcha" in title or "access denied" in title:
                continue

            # Skip DataAnnotation spam (same company, same template, different titles)
            if "dataannotation" in company and "ai trainer" in title:
                continue

            # Skip Help Us Protect Glassdoor
            if "help us protect glassdoor" in title:
                continue

            # Skip non-tech jobs
            if any(pattern in title for pattern in non_tech_patterns):
                continue

            # Require at least one tech keyword in the TITLE, OR user's search keyword
            has_tech_keyword = any(kw in title for kw in tech_keywords)
            user_keyword_list = [k.strip().lower() for k in keywords.split(",") if k.strip()]
            has_user_keyword = any(kw in title or kw in combined for kw in user_keyword_list)

            # If "engineer" in title, require a tech qualifier (software engineer OK, civil engineer NOT)
            if "engineer" in title:
                has_tech_qualifier = any(q in title for q in engineer_requires_tech)
                if not has_tech_qualifier:
                    continue
            elif not has_tech_keyword and not has_user_keyword:
                continue

            # Location filtering
            if job_location and location_lower:
                if not any(alias in job_location for alias in target_aliases):
                    if job_location not in ["", "not specified", "india", "remote"]:
                        continue

            # Experience filtering for freshers
            if is_fresher:
                # Reject senior roles by title
                senior_patterns = ["senior", "sr ", "sr.", "lead", "principal", "staff", "director", "manager",
                                  "architect", "head", "chief", " ii", " iii", " iv", " v",
                                  " l2", " l3", " l4", " l5", " l6", "-ii", "-iii", "-iv",
                                  "plus yrs", "years exp"]
                if any(w in title for w in senior_patterns):
                    continue

                # Reject Arabic numeral level indicators: "Engineer 2", "SDE-3", "Level 4"
                if re.search(r'(?:engineer|developer|sde)\s*[-\s]?\s*[2-9]\b', title):
                    continue

                # Fresher-friendly indicators in title
                fresher_indicators = ["fresher", "junior", "entry level", "intern", "trainee", "graduate", "0-1", "0-2"]
                is_fresher_friendly = any(w in title for w in fresher_indicators)

                # Parse experience from the experience_required field
                if exp_text and exp_text not in ["not specified", "not mentioned", "not specified", ""]:
                    exp_match = re.search(r'(\d+)\s*[-–+]\s*(\d*)', exp_text)
                    if exp_match:
                        min_exp = int(exp_match.group(1))
                        max_exp = int(exp_match.group(2)) if exp_match.group(2) else 0
                        if min_exp >= 2:
                            continue  # Requires 2+ years, reject for freshers
                        if min_exp >= 1 and max_exp > 3:
                            continue  # "1-5 Yrs" etc. — too senior
                        # 0-1, 0-2, 0-3 are fine for freshers
                    elif any(w in exp_text for w in ["2+", "3+", "4+", "5+", "6+", "7+", "8+", "9+", "10+"]):
                        continue  # Explicitly requires multiple years

                # If title says fresher/junior but description requires 2+ years, reject anyway
                if is_fresher_friendly:
                    # Quick description check for experience requirements that contradict the title
                    exp_in_desc = re.search(r'(\d+)\+?\s*[-–]?\s*\d*\s*(?:years?|yrs?)[\w\s]*?(?:experience|exp)', desc)
                    if exp_in_desc and int(exp_in_desc.group(1)) >= 2:
                        continue
                    exp_before = re.search(r'(?:experience|exp)\s*[:\-]?\s*(\d+)\+?\s*[-–]?\s*\d*\s*(?:years?|yrs?)?', desc)
                    if exp_before and int(exp_before.group(1)) >= 2:
                        continue
                    min_exp_desc = re.search(r'(?:min(?:imum)?|at\s*least)\s*(\d+)\s*(?:years?|yrs?)', desc)
                    if min_exp_desc and int(min_exp_desc.group(1)) >= 2:
                        continue
                    filtered.append(job)
                    continue
                else:
                    # No experience info at all — check description for experience requirements
                    # Pattern: "2+ years of professional software engineering experience" or "3-5 years experience"
                    # Uses [\w\s]*? to handle words between "years" and "experience"
                    exp_in_desc = re.search(r'(\d+)\+?\s*[-–]?\s*\d*\s*(?:years?|yrs?)[\w\s]*?(?:experience|exp)', desc)
                    if exp_in_desc:
                        num = int(exp_in_desc.group(1))
                        # "2+ years" means minimum 2 years — reject for freshers
                        has_plus = "+" in exp_in_desc.group(0)[:exp_in_desc.group(0).index(exp_in_desc.group(1)) + len(exp_in_desc.group(1)) + 1]
                        if num >= 2 or (num >= 1 and has_plus):
                            continue

                    # Pattern: "Experience : 3+ yrs" or "EXPERIENCE: 3-5" (experience keyword BEFORE the number)
                    exp_before = re.search(r'(?:experience|exp)\s*[:\-]?\s*(\d+)\+?\s*[-–]?\s*\d*\s*(?:years?|yrs?)?', desc)
                    if exp_before:
                        num = int(exp_before.group(1))
                        if num >= 2 or (num >= 1 and "+" in exp_before.group(0)):
                            continue

                    # Pattern: "minimum X years" or "min X yrs" or "at least X years"
                    min_exp_desc = re.search(r'(?:min(?:imum)?|at\s*least)\s*(\d+)\s*(?:years?|yrs?)', desc)
                    if min_exp_desc and int(min_exp_desc.group(1)) >= 2:
                        continue

                    # Pattern: "3 to 5 years" or "3 to 5 yrs"
                    range_to = re.search(r'(\d+)\s+to\s+\d+\s*(?:years?|yrs?)', desc[:500])
                    if range_to and int(range_to.group(1)) >= 2:
                        continue

                    # Pattern: "3+ yrs" or "3 yrs experience" anywhere in first 500 chars of description
                    quick_exp = re.search(r'(\d+)\+?\s*(?:years?|yrs?)', desc[:500])
                    if quick_exp:
                        num = int(quick_exp.group(1))
                        if num >= 2 or (num >= 1 and "+" in quick_exp.group(0)):
                            continue

                    # No experience info AND no description — allow through (will be enriched by detail page)

            filtered.append(job)

        return filtered

    async def _close_popups(self):
        """Close common popups and modals."""
        close_selectors = [
            "button[aria-label='Dismiss']",
            "button[aria-label='Close']",
            "button[aria-label='Reject all']",
            ".modal-close",
            "button:has-text('Got it')",
            "button:has-text('Accept')",
            "button:has-text('Reject')",
            "button:has-text('Close')",
            # Glassdoor login/sign-up modal
            "button[aria-label='Close']",
            "span.SVGInline.modal_closeIcon",
            "button.e1jbct4g0",
            "[class*='modal'] button[class*='close']",
            "button:has-text('Dismiss')",
            "span[class*='closeIcon']",
        ]

        for selector in close_selectors:
            try:
                await self.browser.page.click(selector, timeout=1000)
                await asyncio.sleep(0.5)
            except:
                continue

        try:
            await self.browser.page.keyboard.press("Escape")
            await asyncio.sleep(0.5)
        except:
            pass

    async def _check_linkedin_blocked(self) -> bool:
        """Check if LinkedIn is blocking us with a login/auth wall."""
        try:
            url = self.browser.page.url
            # Check URL patterns — redirected to login page
            if any(p in url for p in ["/login", "/checkpoint", "/authwall"]):
                self._log("LinkedIn blocked: login wall detected (URL redirect)")
                return True
            # Only check for auth wall if we were REDIRECTED away from the jobs page
            # The jobs search page itself has "Sign in" in the nav bar — that's normal
            if "/jobs/" not in url and "/jobs?" not in url:
                self._log("LinkedIn blocked: redirected away from jobs page")
                return True
        except Exception as e:
            self._log(f"LinkedIn block check failed: {e}")
        return False

    async def _vision_navigate(self, portal: str, keywords: str) -> bool:
        """Navigate portal page: close popups, check listings visible.
        Experience filtering is done post-scrape by _filter_jobs()."""
        # Always try fast DOM popup closing first (~1 second)
        await self._close_popups()

        # Glassdoor: dismiss login/sign-up modal that blocks the page
        if "glassdoor" in (self.browser.page.url or "").lower():
            for sel in [
                "span.SVGInline.modal_closeIcon",
                "button[aria-label='Close']",
                "[class*='modal'] button[class*='close']",
                "span[class*='closeIcon']",
                "button.e1jbct4g0",
            ]:
                try:
                    await self.browser.page.click(sel, timeout=1500)
                    self._log("Dismissed Glassdoor login modal")
                    await asyncio.sleep(1)
                    break
                except:
                    continue
            # Also try pressing Escape
            try:
                await self.browser.page.keyboard.press("Escape")
                await asyncio.sleep(0.5)
            except:
                pass

        # Check if job listings are already visible (most portals work fine)
        try:
            has_listings = await self.browser.page.evaluate("""() => {
                const links = document.querySelectorAll('a[href]');
                let jobLinks = 0;
                for (const link of links) {
                    const href = link.href || '';
                    if (href.includes('/job') || href.includes('/viewjob') || href.includes('/job-detail') || href.includes('/job-listing')) {
                        jobLinks++;
                    }
                }
                return jobLinks;
            }""")
            self._log(f"Page has {has_listings} job links")
            if has_listings >= 3:
                return True
        except:
            pass

        # Page looks broken or no results visible — try vision model (popup close only)
        try:
            import os
            has_mistral = os.getenv("MISTRAL_API_KEY")
            has_nvidia = os.getenv("NVIDIA_API_KEY")
            
            if not has_mistral and not has_nvidia:
                self._log("No MISTRAL_API_KEY or NVIDIA_API_KEY, can't use vision fallback")
                return False

            from agents.vision_scraper.ui_tars_agent import UITarsAgent
            # Prefer NVIDIA for vision if Mistral isn't available
            vision_key = has_mistral or has_nvidia
            agent = UITarsAgent(self.browser, vision_key, max_steps=3)

            task = "If you see a popup or overlay blocking the page, close it. If job listings are visible, say finished."

            self._log(f"Using vision for {portal}...")
            result = await agent.run(task)
            status = result.get("status", "unknown")
            self._log(f"Vision result: {status} ({result.get('steps', 0)} steps)")
            return status in ("success", "finished")

        except Exception as e:
            self._log(f"Vision failed: {e}")
            return False

    def _build_search_url(self, portal: str, keywords: str, location: str) -> str:
        """Build search URL for a portal. Experience filtering is done post-scrape by _filter_jobs()."""
        from urllib.parse import quote
        kw_raw = keywords.split(",")[0].strip()
        loc_raw = location.strip()
        kw = quote(kw_raw, safe='')  # URL-encode everything including #
        loc = quote(loc_raw, safe='')
        kw_dash = kw_raw.replace(" ", "-")  # For path-based URLs, use clean dashes
        loc_dash = loc_raw.replace(" ", "-")

        if portal == "naukri":
            base = f"https://www.naukri.com/{kw_dash}-jobs-in-{loc_dash}"
            if getattr(self, "_is_fresher", False):
                base += "?experience=0"
            return base
        elif portal == "indeed":
            base = f"https://in.indeed.com/jobs?q={kw}&l={loc}"
            if getattr(self, "_is_fresher", False):
                base += "&explvl=entry_level"
            return base
        elif portal == "linkedin":
            return f"https://www.linkedin.com/jobs/search/?keywords={kw}&location={loc}"
        elif portal == "glassdoor":
            # Format: {keyword}-{location}-jobs-SRCH_IL.0,{loc_len}_KO{kw_start},{kw_end}.htm
            ko_s = len(loc_dash) + 1
            ko_e = ko_s + len(kw_dash)
            base = f"https://www.glassdoor.co.in/Job/{kw_dash}-{loc_dash}-jobs-SRCH_IL.0,{len(loc_dash)}_KO{ko_s},{ko_e}.htm"
            if getattr(self, "_is_fresher", False):
                base += "?minExperience=0&maxExperience=1"
            return base
        elif portal == "timesjobs":
            return f"https://www.timesjobs.com/candidate/job-search.html?from=submit&actualTxtKeywords={kw_dash}&searchBy=1&fjType=1&jobType=1&locationType=1&location={loc_dash}"
        elif portal == "shine":
            # Add experience filter: experienced=0 for freshers
            base = f"https://www.shine.com/job-search/{kw_dash}-jobs-in-{loc_dash}"
            if getattr(self, "_is_fresher", False):
                base += "?experienced=0"
            return base
        elif portal == "foundit":
            base = f"https://www.foundit.in/srp/results?query={kw}+{loc}"
            if getattr(self, "_is_fresher", False):
                base += "&experience=0"
            return base

        return f"https://www.naukri.com/{kw_dash}-jobs-in-{loc_dash}"
