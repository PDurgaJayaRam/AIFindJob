"""Browser Pool Source - Scrapes Indian job portals (Naukri, Indeed, LinkedIn, etc.) using autonomous agent.

This is the main scraping source for the shared job pool. It runs periodically via:
1. APScheduler in the main FastAPI process (every SCRAPE_INTERVAL_MINUTES)
2. Celery beat every 2 hours for comprehensive scraping

Features:
- Fresher-aware filtering (prepends "Fresher" or "Entry Level" to query)
- Multiple portal support with isolation
- Deduplication via JobRecord.dedup_key()
- Status tracking per portal
"""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Optional

from ingestion.base import BaseIngestionSource, JobRecord

logger = logging.getLogger("ingestion.browser_pool")

# Indian tech hubs for fresher job search
INDIAN_CITIES = [
    "Hyderabad", "Bangalore", "Bengaluru", "Chennai", "Mumbai", "Delhi", 
    "Pune", "Noida", "Gurgaon", "Gurugram", "Kolkata", "Ahmedabad",
    "Jaipur", "Lucknow", "Chandigarh", "Coimbatore", "Kochi"
]

# Default tech skills to search for - EXPANDED for broader coverage
# This creates a shared pool for ALL users, minimizing redundant scraping
DEFAULT_SKILLS = [
    # Tech roles (current)
    "java", "python", "sql", "javascript", "react", "node.js", "appian", "backend", "full stack",
    "frontend", "devops", "aws", "docker", "kubernetes", "machine learning", "data science", "ai",
    "blockchain", "mobile", "android", "ios", "flutter", "qa", "testing",
    
    # Creative roles (for designers/graphics)
    "graphic designer", "ui ux", "ux designer", "ui designer", "web designer", "photoshop",
    "illustrator", "figma", "sketch", "motion graphics", "video editor", "content creator",
    
    # Other roles
    "product manager", "sales", "marketing", "hr", "business analyst", "project manager",
    "accountant", "finance", "operations", "customer support", "content writer",
    "recruitment", "talent acquisition", "recruiter", "hr generalist", "hr specialist",
    "training", "learning", "recruitment associate", "talent coordinator",
]


class BrowserPoolSource(BaseIngestionSource):
    """Scrapes multiple Indian job portals using autonomous browser agent."""

    name = "browser_pool"

    def __init__(
        self, 
        query: Optional[str] = None,
        location: Optional[str] = None,
        experience_level: Optional[str] = None,
        headless: bool = True,
    ) -> None:
        self._query = query
        self._location = location
        self._experience_level = experience_level
        self._headless = headless

    @property
    def query(self) -> str:
        """Get query from profile or env. Falls back to DB lookup if nothing provided."""
        base_query = self._query
        if not base_query:
            base_query = os.getenv("SCRAPE_QUERY", "").strip()
        if not base_query:
            # Try to fetch from user profile in DB
            base_query = self._fetch_query_from_db()
        if not base_query:
            logger.warning("No query available from profile, env, or DB — skipping scrape")
            return ""
        if self._experience_level in ("fresher", "junior"):
            base_query = f"fresher,entry level,{base_query}"
        return base_query

    @staticmethod
    def _fetch_query_from_db() -> str:
        """Synchronous DB lookup for query (uses most recently updated profile)."""
        try:
            import sqlite3, json
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "career_agent.db")
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT desired_roles FROM user_preferences ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row and row[0]:
                roles = json.loads(row[0])
                if roles:
                    return roles[0]
        except Exception:
            pass
        return ""

    @property
    def location(self) -> str:
        """Get location from profile or env."""
        loc = self._location
        if not loc:
            loc = os.getenv("SCRAPE_LOCATION", "").strip()
        if not loc:
            loc = self._fetch_location_from_db()
        return loc or "Hyderabad"

    @staticmethod
    def _fetch_location_from_db() -> str:
        """Synchronous DB lookup for location (uses most recently updated profile)."""
        try:
            import sqlite3, json
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "career_agent.db")
            conn = sqlite3.connect(db_path)
            row = conn.execute(
                "SELECT desired_locations FROM user_preferences ORDER BY id DESC LIMIT 1"
            ).fetchone()
            conn.close()
            if row and row[0]:
                locations = json.loads(row[0])
                if locations:
                    return locations[0]
        except Exception:
            pass
        return ""

    async def fetch(self) -> list[JobRecord]:
        """Run browser agent to scrape jobs from multiple portals."""
        try:
            from agents.browser_agent.autonomous_agent import AutonomousAgent
            
            portal_list = os.getenv("SCRAPE_PORTALS", "naukri,indeed,linkedin,shine,foundit,timesjobs")
            portals = [p.strip() for p in portal_list.split(",") if p.strip()]
            
            # Check for vision-capable AI (Mistral OR NVIDIA)
            has_mistral = os.getenv("MISTRAL_API_KEY") is not None
            has_nvidia = os.getenv("NVIDIA_API_KEY") is not None
            
            # Filter out LinkedIn if no vision-capable AI (it requires AI navigation)
            if not has_mistral and not has_nvidia:
                portals = [p for p in portals if p != "linkedin"]
                logger.warning("MISTRAL_API_KEY and NVIDIA_API_KEY not set, skipping LinkedIn scraping")
            elif not has_mistral and has_nvidia:
                logger.info("Using NVIDIA for vision navigation (LinkedIn supported)")

            agent = AutonomousAgent(headless=self._headless)
            
            is_fresher = self._experience_level in ("fresher", "junior", None)
            
            jobs = await agent.run_task(
                task=f"Find {self.query} jobs in {self.location}. Focus on fresher-friendly positions.",
                target_count=50,
                keywords=self.query,
                location=self.location,
                is_fresher=is_fresher,
                portals=portals,
                overall_timeout=600,  # 10 minutes max (need time for all 6 portals)
            )

            records = []
            for job in jobs:
                if not job.get("title"):
                    continue
                # Extract skills from description if not already populated
                skills = job.get("skills_required") or job.get("skills") or []
                if not skills and job.get("description"):
                    # Extract skills from description using simple keyword matching
                    skill_patterns = ["python", "java", "sql", "javascript", "react", "node.js", "angular",
                                      "aws", "docker", "git", "spring", "django", "flask", "c++", "c#",
                                      "html", "css", "mongodb", "postgresql", "mysql", "machine learning",
                                      "ai", "data science", "devops", "backend", "frontend"]
                    desc_lower = (job.get("description") or "").lower()
                    skills = [s for s in skill_patterns if s in desc_lower]

                records.append(
                    JobRecord(
                        title=job.get("title", "")[:500],
                        company=job.get("company", "Unknown")[:500],
                        location=job.get("location", self.location)[:500],
                        description=job.get("description", "")[:2000],
                        source=job.get("source", "")[:100],
                        source_url=job.get("source_url", ""),
                        apply_url=job.get("apply_url", "") or job.get("source_url", ""),
                        salary=job.get("salary", "")[:500],
                        experience_required=job.get("experience_required", job.get("experience", ""))[:500],
                        skills_required=[str(s) for s in skills],
                        remote=job.get("remote", False),
                        walk_in=job.get("walk_in", False),
                        internship=job.get("internship", False),
                        posted_date=None,
                        external_id=job.get("id", "") or job.get("job_id", ""),
                        raw=job,
                    )
                )
            
            logger.info(f"BrowserPoolSource: collected {len(records)} jobs")
            return records

        except Exception as exc:
            logger.error("BrowserPoolSource fetch failed: %s", exc)
            return []

    def _build_search_url(self, portal: str, query: str, location: str) -> str:
        """Build portal-specific search URL."""
        from urllib.parse import quote_plus
        
        q = quote_plus(query.replace(",", " "))
        l = quote_plus(location)
        
        urls = {
            "naukri": f"https://www.naukri.com/{q}-jobs-in-{l}-hyderabad",
            "indeed": f"https://in.indeed.com/jobs?q={q}&l={l}",
            "linkedin": f"https://www.linkedin.com/jobs/search?keywords={q}&location={l}",
            "shine": f"https://www.shine.com/job-search/{q}-jobs-in-{l}",
            "foundit": f"https://www.foundit.in/srp/results?query={q}+{l}",
            "timesjobs": f"https://www.timesjobs.com/candidate/job-search.html?searchType=personalizedSearch&txtKeywords={q}&txtLocation={l}",
        }
        return urls.get(portal, "")

    def _is_portal_healthy(self, portal: str) -> bool:
        """Check if portal should be scraped based on recent success rate."""
        # For now, always return True - could implement backoff logic later
        return True