"""Social Intelligence Module - Monitors job market across platforms.

Uses free methods that work WITHOUT login or API keys:
- Twitter: Google search + Jina Reader
- Reddit: RSS feeds (no auth needed)
- LinkedIn: Jina Reader
- GitHub: Public API
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any
from dataclasses import dataclass, asdict
import requests

logger = logging.getLogger("social_intel")

JINA_HEADERS = {"Accept": "text/plain", "X-No-Cache": "true"}
REQUEST_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0"}


@dataclass
class JobPost:
    title: str
    company: str
    location: str
    url: str
    source: str
    description: str = ""
    posted_date: str = ""


def _fetch_jina(url: str, timeout: int = 15) -> str:
    try:
        r = requests.get(f"https://r.jina.ai/{url}", headers=JINA_HEADERS, timeout=timeout)
        return r.text if r.status_code == 200 else ""
    except Exception:
        return ""


def search_twitter_jobs(query: str, limit: int = 10) -> list[JobPost]:
    """Search Twitter for jobs via Google search (no login needed)."""
    posts = []
    search_query = f'site:twitter.com OR site:x.com "{query}" hiring OR #hiring OR #jobopening'
    
    try:
        content = _fetch_jina(f"https://www.google.com/search?q={search_query.replace(' ', '+')}&num={limit}")
        
        if content:
            url_pattern = re.compile(r'https?://(?:twitter\.com|x\.com)/\w+/status/\d+')
            urls = url_pattern.findall(content)
            
            for url in urls[:limit]:
                tweet_content = _fetch_jina(url)
                if tweet_content and len(tweet_content) > 50:
                    lines = [l.strip() for l in tweet_content.split('\n') if l.strip()]
                    title = _extract_job_title(' '.join(lines[:5]))
                    company = _extract_company(' '.join(lines[:10]))
                    
                    posts.append(JobPost(
                        title=title,
                        company=company,
                        location=_extract_location(' '.join(lines[:10])),
                        url=url,
                        source="twitter",
                        description=' '.join(lines[:10])[:500],
                    ))
    except Exception as e:
        logger.warning("Twitter search failed: %s", e)
    
    return posts


def search_reddit_jobs(subreddit: str = "jobs", query: str = "", limit: int = 10) -> list[JobPost]:
    """Search Reddit for jobs via RSS feeds (no login needed)."""
    posts = []
    
    try:
        search_term = query.replace(' ', '+') if query else "hiring"
        rss_url = f"https://www.reddit.com/r/{subreddit}/search.rss?q={search_term}+hiring&restrict_sr=on&sort=new&t=week&limit={limit}"
        
        r = requests.get(rss_url, headers=REQUEST_HEADERS, timeout=15)
        
        if r.status_code == 200:
            entries = _parse_rss(r.text)
            
            for entry in entries[:limit]:
                title = entry.get('title', '')
                link = entry.get('link', '')
                summary = entry.get('summary', '')
                published = entry.get('published', '')
                
                if title:
                    posts.append(JobPost(
                        title=title[:150],
                        company=_extract_company_from_text(summary),
                        location=_extract_location_from_text(summary),
                        url=link,
                        source="reddit",
                        description=summary[:500],
                        posted_date=published,
                    ))
        
        if not posts:
            alt_rss = f"https://www.reddit.com/r/{subreddit}/.rss?limit={limit}"
            r2 = requests.get(alt_rss, headers=REQUEST_HEADERS, timeout=15)
            if r2.status_code == 200:
                entries = _parse_rss(r2.text)
                for entry in entries[:limit]:
                    title = entry.get('title', '')
                    if any(kw in title.lower() for kw in ['hiring', 'job', 'position', 'opening', query.lower()]):
                        posts.append(JobPost(
                            title=title[:150],
                            company="Various",
                            location="Remote",
                            url=entry.get('link', ''),
                            source="reddit",
                            description=entry.get('summary', '')[:500],
                        ))
    except Exception as e:
        logger.warning("Reddit RSS search failed: %s", e)
    
    return posts


def _parse_rss(xml_text: str) -> list[dict]:
    """Parse RSS/Atom XML."""
    entries = []
    
    item_pattern = re.compile(r'<item>(.*?)</item>', re.DOTALL)
    entry_pattern = re.compile(r'<entry>(.*?)</entry>', re.DOTALL)
    
    items = item_pattern.findall(xml_text) + entry_pattern.findall(xml_text)
    
    for item in items:
        title_match = re.search(r'<title[^>]*>(.*?)</title>', item, re.DOTALL)
        link_match = re.search(r'<link[^>]*>(.*?)</link>', item, re.DOTALL) or re.search(r'<link[^>]*href="([^"]*)"', item)
        summary_match = re.search(r'<content[^>]*>(.*?)</content>', item, re.DOTALL) or re.search(r'<summary[^>]*>(.*?)</summary>', item, re.DOTALL)
        date_match = re.search(r'<published[^>]*>(.*?)</published>', item) or re.search(r'<updated[^>]*>(.*?)</updated>', item)
        
        title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip() if title_match else ""
        link = link_match.group(1).strip() if link_match else ""
        summary = re.sub(r'<[^>]+>', '', summary_match.group(1)).strip() if summary_match else ""
        date = date_match.group(1).strip() if date_match else ""
        
        if title:
            entries.append({"title": title, "link": link, "summary": summary, "published": date})
    
    return entries


def search_linkedin_jobs(query: str, location: str = "", limit: int = 10) -> list[JobPost]:
    """Search LinkedIn for jobs via Jina Reader."""
    posts = []
    
    search_url = f"https://www.linkedin.com/jobs/search/?keywords={query.replace(' ', '%20')}"
    if location:
        search_url += f"&location={location.replace(' ', '%20')}"
    
    content = _fetch_jina(search_url)
    
    if content and len(content) > 200:
        job_blocks = re.split(r'\n(?=(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*\s+(?:Engineer|Developer|Analyst|Manager|Intern|Specialist|Consultant|Lead|Architect)))', content)
        
        for block in job_blocks[:limit]:
            lines = [l.strip() for l in block.split('\n') if l.strip()]
            if not lines:
                continue
            
            title = lines[0][:100]
            company = lines[1] if len(lines) > 1 else "Unknown"
            
            if any(kw in title.lower() for kw in ['engineer', 'developer', 'analyst', 'manager', 'intern', 'specialist', 'consultant']):
                posts.append(JobPost(
                    title=title,
                    company=company,
                    location=location or "Not specified",
                    url=search_url,
                    source="linkedin",
                    description=block[:500],
                ))
    
    return posts


def search_github_jobs(query: str = "hiring", limit: int = 10) -> list[JobPost]:
    """Search GitHub for job-related repos (no auth needed)."""
    posts = []
    
    try:
        url = f"https://api.github.com/search/repositories?q={query.replace(' ', '+')}+jobs+hiring&sort=updated&per_page={limit}"
        r = requests.get(url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=15)
        
        if r.status_code == 200:
            for repo in r.json().get("items", [])[:limit]:
                posts.append(JobPost(
                    title=repo.get("name", "Unknown"),
                    company=repo.get("owner", {}).get("login", "Unknown"),
                    location="Remote",
                    url=repo.get("html_url", ""),
                    source="github",
                    description=repo.get("description", "")[:500],
                ))
    except Exception as e:
        logger.warning("GitHub search failed: %s", e)
    
    return posts


def get_company_insight(company_name: str) -> dict:
    """Get company tech stack from GitHub (no auth needed)."""
    tech_stack = []
    
    try:
        url = f"https://api.github.com/orgs/{company_name}/repos?per_page=10&sort=updated"
        r = requests.get(url, headers={"Accept": "application/vnd.github.v3+json"}, timeout=15)
        
        if r.status_code == 200:
            for repo in r.json():
                lang = repo.get("language")
                if lang:
                    tech_stack.append(lang)
            tech_stack = list(set(tech_stack))[:10]
    except Exception:
        pass
    
    return {
        "name": company_name,
        "tech_stack": tech_stack or ["Not determined"],
        "source": "github",
    }


def monitor_job_market(keywords: list[str], location: str = "India") -> dict[str, Any]:
    """Monitor job market across all platforms."""
    all_jobs = []
    source_stats = {}
    
    for keyword in keywords:
        for source_fn, source_name in [
            (lambda q: search_twitter_jobs(q, 5), "twitter"),
            (lambda q: search_reddit_jobs(query=q, limit=5), "reddit"),
            (lambda q: search_linkedin_jobs(q, location, 5), "linkedin"),
            (lambda q: search_github_jobs(q, 3), "github"),
        ]:
            jobs = source_fn(keyword)
            all_jobs.extend(jobs)
            source_stats[source_name] = source_stats.get(source_name, 0) + len(jobs)
    
    seen = set()
    unique = []
    for job in all_jobs:
        key = f"{job.title.lower()}|{job.company.lower()}"
        if key not in seen:
            seen.add(key)
            unique.append(job)
    
    return {
        "total_jobs": len(unique),
        "by_source": source_stats,
        "jobs": [asdict(j) for j in unique[:50]],
    }


def get_channel_status() -> dict:
    """Check which channels are available."""
    return {
        "twitter": {"configured": True, "method": "Google search + Jina Reader"},
        "reddit": {"configured": True, "method": "RSS feeds (no auth needed)"},
        "linkedin": {"configured": True, "method": "Jina Reader"},
        "github": {"configured": True, "method": "GitHub API (public)"},
    }


def _extract_job_title(text: str) -> str:
    patterns = [
        r'(?:hiring|looking for|seeking)\s+(?:a\s+)?(.+?)(?:\s+(?:to join|at|for|with|in))',
        r'((?:senior|junior|lead|staff|principal)?\s*(?:software|frontend|backend|full.?stack|data|ml|devops|qa|mobile)\s*(?:engineer|developer|scientist|analyst|architect))',
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()[:100]
    return "Position Available"


def _extract_company(text: str) -> str:
    patterns = [
        r'(?:at|@|for)\s+([A-Z][A-Za-z\s&]+?)(?:\s+(?:is|we|looking|hiring))',
        r'([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)\s+(?:is hiring|hiring)',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()[:50]
    return "Unknown"


def _extract_location(text: str) -> str:
    locations = ['remote', 'hyderabad', 'bangalore', 'mumbai', 'delhi', 'chennai', 'pune',
                 'san francisco', 'new york', 'london', 'india', 'usa', 'global']
    text_lower = text.lower()
    for loc in locations:
        if loc in text_lower:
            return loc.title()
    return "Not specified"


def _extract_company_from_text(text: str) -> str:
    return _extract_company(text)


def _extract_location_from_text(text: str) -> str:
    return _extract_location(text)
