"""Browser-based ingestion source - uses autonomous agent for real-time scraping."""
from __future__ import annotations

import asyncio
import logging
import os
import json
from typing import Any

from ingestion.base import BaseIngestionSource, JobRecord

logger = logging.getLogger("ingestion.browser")


def _get_profile_from_db():
    """Fetch query and location from user profile in DB."""
    try:
        import sqlite3
        db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "career_agent.db")
        conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT desired_roles, desired_locations FROM user_preferences ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        if row:
            roles = json.loads(row[0]) if row[0] else []
            locations = json.loads(row[1]) if row[1] else []
            return roles[0] if roles else "", locations[0] if locations else ""
    except Exception:
        pass
    return "", ""


class BrowserSource(BaseIngestionSource):
    """Browser-based job scraper using autonomous agent with DOM extraction."""

    name = "browser"

    def __init__(self, timeout: float = 180.0, headless: bool = True) -> None:
        self._timeout = timeout
        self._headless = headless
        self._last_run_results: list[JobRecord] = []
        self._last_run_time: float = 0

    async def fetch(self) -> list[JobRecord]:
        """Run browser agent to scrape jobs from multiple portals."""
        import time
        
        try:
            from agents.browser_agent.agent import BrowserAgent
            
            query, location = _get_profile_from_db()
            if not query:
                query = os.getenv("SCRAPE_QUERY", "").strip()
            if not location:
                location = os.getenv("SCRAPE_LOCATION", "").strip()
            if not query:
                logger.warning("BrowserSource: no query from profile or env, skipping")
                return []
            location = location or "Hyderabad"

            agent = BrowserAgent(headless=self._headless)
            
            task = f"""Go to job portals and search for "{query}" jobs in "{location}".
Handle any popups, login prompts, or cookie banners by closing them.
Scroll down to load more jobs.
Extract at least 30 job listings with title, company, location, and URL.
Return when you have enough jobs or visited all portals."""
            
            portals = ["naukri", "indeed", "cutshort", "timesjobs", "shine", "foundit"]
            
            jobs = await asyncio.wait_for(
                agent.run_task(
                    task=task,
                    target_count=30,
                    keywords=query,
                    is_fresher=False,
                    location=location,
                    portals=portals,
                ),
                timeout=self._timeout
            )
            
            for log_msg in agent.get_log():
                if log_msg:
                    logger.info(log_msg)
            
            records = []
            for job in jobs:
                records.append(JobRecord(
                    title=job.get("title", "")[:500] if job.get("title") else "",
                    company=job.get("company", "")[:500] if job.get("company") else "",
                    location=job.get("location", "")[:500] if job.get("location") else "",
                    description=job.get("description", ""),
                    source=job.get("source", "")[:100] if job.get("source") else "",
                    source_url=job.get("source_url", ""),
                    apply_url=job.get("apply_url", ""),
                    salary=job.get("salary", "")[:500] if job.get("salary") else "",
                    experience_required=job.get("experience", "")[:500] if job.get("experience") else "",
                    skills_required=job.get("skills", []),
                    remote=job.get("remote", False),
                    walk_in=job.get("walk_in", False),
                    internship=job.get("internship", False),
                    posted_date=None,
                    raw=job,
                ))
            
            self._last_run_results = records
            self._last_run_time = time.time()
            
            return records
            
        except asyncio.TimeoutError:
            logger.warning("Browser scraping timed out after %s seconds", self._timeout)
            return []
        except Exception as e:
            logger.error("Browser scraping failed: %s", e)
            return []