"""Hybrid Extractor - JavaScript extraction with vision fallback."""
from __future__ import annotations

import time
import logging
from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

from agents.vision_scraper.models import (
    JobData,
    ExtractionMethod,
    ActionDecision,
    ActionType,
    PageState,
)

if TYPE_CHECKING:
    from agents.browser_agent.browser_controller import BrowserController
    from agents.vision_scraper.vision_agent import VisionAgent

logger = logging.getLogger(__name__)

NAUKRI_EXTRACTION_JS = """() => {
    const jobs = [];
    const seenUrls = new Set();
    const cards = document.querySelectorAll('article.jobTuple, div.job-card, section.job-card, div[class*="jobTuple"], div[class*="job-tuple"], div.srp-jobtuple-wrapper');
    cards.forEach(card => {
        const titleEl = card.querySelector('a.title, h2.title, a.job-card__title, .title, span.job-title');
        const companyEl = card.querySelector('span.comp-name, a.comp-name, div.company-name, a.subTitle, [class*="comp-name"], [class*="company-name"]');
        const locEl = card.querySelector('li.location, span.location, div.location, .location, [class*="loc"]');
        const linkEl = card.querySelector('a.title, a.jobTupleHeader, a[class*="title"]');
        const descEl = card.querySelector('span.job-desc, div.description, p.description, .job-desc');
        const expEl = card.querySelector('li.experience, span.experience, div.experience, .experience, [class*="exp"]');
        const salaryEl = card.querySelector('li.salary, span.salary, div.salary, .salary, [class*="sal"]');
        if (titleEl) {
            const title = titleEl.innerText?.trim() || '';
            const href = linkEl?.href || titleEl?.href || '';
            const jobUrl = href || '';
            let company = companyEl?.innerText?.trim() || '';
            if (!company) {
                const allSpans = card.querySelectorAll('span, a, div');
                for (const span of allSpans) {
                    const t = span.innerText?.trim() || '';
                    if (t && t.length > 2 && t.length < 60 && !t.includes('days ago') && !t.includes('Apply') && !t.toLowerCase().includes('job') && !t.toLowerCase().includes('location') && !t.toLowerCase().includes('salary') && !t.toLowerCase().includes('role') && !t.toLowerCase().includes('experience')) {
                        if (/^[A-Z][a-zA-Z\\s.&()-]+$/.test(t)) { company = t; break; }
                    }
                }
            }
            if (title && !seenUrls.has(jobUrl)) {
                seenUrls.add(jobUrl);
                jobs.push({ title, company: company || 'Unknown', location: locEl?.innerText?.trim() || '', source: 'naukri', source_url: jobUrl.startsWith('http') ? jobUrl : 'https://www.naukri.com' + jobUrl, apply_url: jobUrl.startsWith('http') ? jobUrl : 'https://www.naukri.com' + jobUrl, salary: salaryEl?.innerText?.trim() || '', description: descEl?.innerText?.trim() || '', experience_required: expEl?.innerText?.trim() || '' });
            }
        }
    });
    return jobs;
}"""

LINKEDIN_EXTRACTION_JS = """() => {
    const jobs = [];
    const seenUrls = new Set();
    const cards = document.querySelectorAll(
        'div.base-card, li.job-card-container, div.job-card-list__item, ' +
        '.job-card-container, div[data-occludable-job-id], ' +
        'li[class*="job-card"], div[class*="job-card"], ' +
        'article[class*="job"], div[class*="job-listing"], ' +
        'div.scaffold-layout__list > div, ' +
        'ul > li.scaffold-layout__list-item'
    );
    cards.forEach(card => {
        const titleEl = card.querySelector(
            'h3.base-search-card__title, h3.job-card-list__title, ' +
            '.job-card-list__title, h4, h3, ' +
            '[class*="title"], [class*="Title"], ' +
            'a[class*="job-title"], a[class*="jobTitle"]'
        );
        const companyEl = card.querySelector(
            'a.hidden-nested-link, span.job-card-container__company-name, ' +
            '.job-card-container__company-name, [class*="company"], ' +
            '[class*="Company"], [class*="employer"]'
        );
        const locEl = card.querySelector(
            'span.job-search-card__location, span.job-card-container__metadata-item, ' +
            '.job-card-container__metadata-item, [class*="location"], ' +
            '[class*="Location"], [class*="loc"]'
        );
        const linkEl = card.querySelector(
            'a.base-card__full-link, a.job-card-list__cta, ' +
            'a[class*="job-link"], a[href*="/jobs/view/"]'
        );
        if (titleEl) {
            const title = titleEl.innerText?.trim() || '';
            const href = linkEl?.href || titleEl.querySelector('a')?.href || '';
            if (title && title.length > 3 && title.length < 100 && !title.toLowerCase().includes('sign in') && !title.toLowerCase().includes('log in') && !seenUrls.has(href)) {
                seenUrls.add(href);
                jobs.push({ title, company: companyEl?.innerText?.trim() || 'Unknown', location: locEl?.innerText?.trim() || '', source: 'linkedin', source_url: href, apply_url: href, salary: '', description: '', experience_required: '' });
            }
        }
    });
    if (jobs.length === 0) {
        const jobLinks = document.querySelectorAll('a[href*="/jobs/view/"]');
        jobLinks.forEach(link => {
            const href = link.href || '';
            if (seenUrls.has(href)) return;
            const title = link.innerText?.trim() || link.getAttribute('title') || '';
            if (title && title.length > 3 && title.length < 100 && !title.toLowerCase().includes('sign in') && !title.toLowerCase().includes('log in')) {
                seenUrls.add(href);
                jobs.push({ title, company: 'Unknown', location: '', source: 'linkedin', source_url: href, apply_url: href, salary: '', description: '', experience_required: '' });
            }
        });
    }
    return jobs;
}"""

INDEED_EXTRACTION_JS = """() => {
    const jobs = [];
    const seenUrls = new Set();
    const cards = document.querySelectorAll('div.job-card-container, div.job_seen_beacon, div[data-testid="job-card"], div.jobsearch-SerpJobCard');
    cards.forEach(card => {
        const titleEl = card.querySelector('h2.jobTitle, a.job-title, span[data-testid="job-title"], h2.jobTitle a, a.jcs-JobTitle');
        const companyEl = card.querySelector('span.companyName, a.companyName, span[data-testid="company-name"], .company');
        const locEl = card.querySelector('div.companyLocation, span[data-testid="job-location"], .location, .jobLocation');
        const linkEl = card.querySelector('a.jcs-JobTitle, a.job-card-container__link, a[data-testid="job-link"], .jobtitle');
        const descEl = card.querySelector('div.job-snippet, div.job-description, span.job-snippet, .job-snippet');
        const expEl = card.querySelector('div.metadata, span.metadata, .metadata');
        if (titleEl) {
            const title = titleEl.innerText?.trim() || '';
            const href = linkEl?.href || titleEl.querySelector('a')?.href || '';
            if (title && !seenUrls.has(href)) {
                seenUrls.add(href);
                jobs.push({ title, company: companyEl?.innerText?.trim() || 'Unknown', location: locEl?.innerText?.trim() || '', source: 'indeed', source_url: href, apply_url: href, salary: '', description: descEl?.innerText?.trim() || '', experience_required: expEl?.innerText?.trim() || '' });
            }
        }
    });
    return jobs;
}"""

TIMESJOBS_EXTRACTION_JS = """() => {
    const jobs = [];
    const seenUrls = new Set();
    const cards = document.querySelectorAll(
        'li.clearfix.job-bx, div.job-bx, li[class*="job-bx"], ' +
        'div[class*="srpJob"], div[class*="job-listing"], ' +
        'ul[class*="job"] li, div.new-joblist li'
    );
    cards.forEach(card => {
        const titleEl = card.querySelector(
            'h2 a, h3 a, a[class*="job-title"], a[class*="title"], ' +
            '.joblist-comp-name + a, a[href*="job-detail"], ' +
            'a[title], h2, h3'
        );
        const companyEl = card.querySelector(
            'h3.joblist-comp-name, span.company-name, [class*="company"], ' +
            'a[class*="company"], [class*="comp-name"]'
        );
        const locEl = card.querySelector(
            'span[class*="location"], [class*="loc"], li.location, ' +
            'span.loc, [class*="Location"]'
        );
        const descEl = card.querySelector(
            'ul.list-job-dtl li, p[class*="desc"], [class*="description"], ' +
            'span.job-desc, div[class*="desc"]'
        );
        const expEl = card.querySelector(
            'span.exp, li.exp, [class*="experience"], [class*="exp"]'
        );
        const salaryEl = card.querySelector(
            'span.salary, li.salary, [class*="salary"], [class*="sal"]'
        );
        const postedEl = card.querySelector(
            'span.posted, [class*="posted"], [class*="date"], span.sim-posted'
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
                    posted_text: postedEl?.innerText?.trim() || ''
                });
            }
        }
    });
    return jobs;
}"""

GENERIC_EXTRACTION_JS = """() => {
    const jobs = [];
    const seenUrls = new Set();
    const cards = document.querySelectorAll('div[class*="job"], article[class*="job"], div.job-card, div[class*="jobCard"], li[class*="job"]');
    cards.forEach(card => {
        const titleEl = card.querySelector('h2, h3, h4, a[class*="title"], [class*="job-title"]');
        const companyEl = card.querySelector('[class*="company"], [class*="Company"]');
        const locEl = card.querySelector('[class*="location"], [class*="Location"]');
        const linkEl = card.querySelector('a');
        if (titleEl) {
            const title = titleEl.innerText?.trim() || '';
            const href = linkEl?.href || '';
            if (title && title.length > 3 && title.length < 100 && !seenUrls.has(href)) {
                seenUrls.add(href);
                jobs.push({ title, company: companyEl?.innerText?.trim() || 'Unknown', location: locEl?.innerText?.trim() || '', source: 'web', source_url: href, apply_url: href, salary: '', description: '', experience_required: '' });
            }
        }
    });
    if (jobs.length === 0) {
        const allLinks = document.querySelectorAll('a');
        allLinks.forEach(link => {
            const text = link.innerText?.trim() || '';
            const href = link.href || '';
            if (text.length > 5 && text.length < 100 &&
                (text.toLowerCase().includes('developer') || text.toLowerCase().includes('engineer') ||
                 text.toLowerCase().includes('analyst') || text.toLowerCase().includes('manager') ||
                 text.toLowerCase().includes('intern') || text.toLowerCase().includes('associate') ||
                 text.toLowerCase().includes('consultant') || text.toLowerCase().includes('architect')) &&
                !text.toLowerCase().includes('apply') && !text.toLowerCase().includes('search') &&
                !text.toLowerCase().includes('login') && !text.toLowerCase().includes('sign') &&
                href && href.includes('http') && !seenUrls.has(href)) {
                seenUrls.add(href);
                jobs.push({ title: text, company: 'Unknown', location: '', source: 'web', source_url: href, apply_url: href, salary: '', description: '', experience_required: '' });
            }
        });
    }
    return jobs;
}"""

GLASSDOOR_EXTRACTION_JS = r"""() => {
    const jobs = [];
    const seenUrls = new Set();
    // Glassdoor uses /job-listing/ links for job cards
    const allLinks = document.querySelectorAll('a[href*="/job-listing/"], a[data-job-listing]');
    for (const link of allLinks) {
        const href = link.href || '';
        const text = link.innerText?.trim() || '';
        if (!href || seenUrls.has(href)) continue;
        if (text.length < 4 || text.length > 150) continue;
        seenUrls.add(href);
        let card = link.closest('div[class*="job"], div[class*="card"], article, li, section');
        let company = '';
        let location = 'Not specified';
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
                if (line.toLowerCase().includes('ago') || /^\d+[dhm]\+?\s*(ago)?$/.test(line)) {
                    posted_text = line;
                    break;
                }
            }
            for (const line of lines) {
                if ((line.includes(',') || /hyderabad|bangalore|mumbai|delhi|pune|chennai|remote|india/i.test(line))
                    && line !== text && line !== company && line.length < 80) {
                    location = line;
                    break;
                }
            }
            if (!company) {
                for (const line of lines) {
                    if (line !== text && line.length > 2 && line.length < 80
                        && !line.toLowerCase().includes('ago') && !line.includes(',')
                        && !/^\d+[dhm]/.test(line)) {
                        company = line;
                        break;
                    }
                }
            }
        }
        if (!company) company = 'Unknown';
        jobs.push({
            title: text,
            company: company,
            location: location,
            source: 'glassdoor',
            source_url: href,
            apply_url: href,
            salary: '',
            description: '',
            experience_required: '',
            posted_text: posted_text
        });
    }
    return jobs;
}"""

PORTAL_JS_MAP = {
    "naukri": NAUKRI_EXTRACTION_JS,
    "linkedin": LINKEDIN_EXTRACTION_JS,
    "linkedin_us": LINKEDIN_EXTRACTION_JS,
    "indeed_in": INDEED_EXTRACTION_JS,
    "indeed_us": INDEED_EXTRACTION_JS,
    "timesjobs": TIMESJOBS_EXTRACTION_JS,
    "glassdoor_in": GLASSDOOR_EXTRACTION_JS,
    "glassdoor_us": GLASSDOOR_EXTRACTION_JS,
}


class HybridExtractor:
    """Extracts job data using JavaScript with vision fallback."""

    def __init__(
        self,
        browser: BrowserController,
        vision_agent: Optional[VisionAgent] = None,
        max_jobs: int = 100,
        max_scroll_attempts: int = 5,
    ):
        self.browser = browser
        self.vision_agent = vision_agent
        self.max_jobs = max_jobs
        self.max_scroll_attempts = max_scroll_attempts

    def _dict_to_job_data(self, data: Dict[str, Any], source: str, method: ExtractionMethod) -> JobData:
        """Convert raw dict to validated JobData."""
        return JobData(
            title=data.get("title", "").strip(),
            company=data.get("company", "Unknown").strip(),
            location=data.get("location", "").strip(),
            description=data.get("description"),
            source=source,
            source_url=data.get("source_url", ""),
            apply_url=data.get("apply_url"),
            salary=data.get("salary"),
            job_type=data.get("job_type"),
            experience_required=data.get("experience_required"),
            skills=data.get("skills"),
            posted_date=data.get("posted_date"),
            extraction_method=method,
        )

    async def extract_with_javascript(self, portal_name: str) -> List[JobData]:
        """Extract jobs using JavaScript injection."""
        js_script = PORTAL_JS_MAP.get(portal_name, GENERIC_EXTRACTION_JS)
        try:
            raw_jobs = await self.browser.page.evaluate(js_script)
            jobs = []
            for data in raw_jobs:
                try:
                    job = self._dict_to_job_data(data, portal_name, ExtractionMethod.JAVASCRIPT)
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Invalid job data skipped: {e}")
            logger.info(f"JavaScript extraction found {len(jobs)} jobs from {portal_name}")
            return jobs
        except Exception as e:
            logger.error(f"JavaScript extraction failed for {portal_name}: {e}")
            return []

    async def extract_with_vision(self, portal_name: str) -> List[JobData]:
        """Extract jobs using vision analysis as fallback."""
        if not self.vision_agent:
            return []
        
        screenshot = await self.browser.take_screenshot()
        if isinstance(screenshot, str) and screenshot.startswith("screenshot_error"):
            return []
        
        prompt = f"""
Analyze this job search results page from {portal_name}. Extract all visible job listings.
Return a JSON array of jobs with these fields:
[
  {{
    "title": "Job title",
    "company": "Company name",
    "location": "Location",
    "source_url": "URL to job posting",
    "salary": "Salary if visible",
    "description": "Brief description if visible"
  }}
]
Only return valid JSON array. If no jobs visible, return [].
"""
        try:
            response = self.vision_agent.ai_client.vision_complete(
                image=__import__('base64').b64decode(screenshot),
                prompt=prompt,
            )
            parsed = response.get("parsed", [])
            if not isinstance(parsed, list):
                return []
            
            jobs = []
            for data in parsed:
                try:
                    job = self._dict_to_job_data(data, portal_name, ExtractionMethod.VISION)
                    jobs.append(job)
                except Exception as e:
                    logger.warning(f"Vision extraction invalid data: {e}")
            logger.info(f"Vision extraction found {len(jobs)} jobs from {portal_name}")
            return jobs
        except Exception as e:
            logger.error(f"Vision extraction failed for {portal_name}: {e}")
            return []

    async def scroll_and_extract(self, portal_name: str) -> List[JobData]:
        """Scroll page incrementally and extract jobs, tracking duplicates."""
        all_jobs = []
        seen_urls = set()
        
        for attempt in range(self.max_scroll_attempts):
            if len(all_jobs) >= self.max_jobs:
                break
            
            jobs = await self.extract_with_javascript(portal_name)
            
            if len(jobs) == 0 and attempt == 0:
                jobs = await self.extract_with_vision(portal_name)
            
            new_jobs = []
            for job in jobs:
                if job.source_url not in seen_urls and len(all_jobs) < self.max_jobs:
                    seen_urls.add(job.source_url)
                    new_jobs.append(job)
                    all_jobs.append(job)
            
            if len(new_jobs) == 0 and attempt > 0:
                logger.info(f"No new jobs found after scroll attempt {attempt}")
                break
            
            if attempt < self.max_scroll_attempts - 1:
                await self.browser.scroll("down", 800)
                await self.browser.wait(2)
        
        logger.info(f"Scroll extraction complete: {len(all_jobs)} unique jobs from {portal_name}")
        return all_jobs

    async def extract_jobs(self, portal_name: str, max_jobs: Optional[int] = None) -> List[JobData]:
        """Main extraction method: JavaScript first, vision fallback, with scrolling."""
        limit = max_jobs or self.max_jobs
        old_max = self.max_jobs
        self.max_jobs = limit
        
        try:
            jobs = await self.scroll_and_extract(portal_name)
            return jobs[:limit]
        finally:
            self.max_jobs = old_max
