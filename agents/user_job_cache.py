"""User-specific job cache for instant matching.

This module provides collaborative job scraping:
1. Jobs are scraped ONCE and cached centrally
2. Each user gets matched against the pool instantly
3. No redundant scraping per user
4. Role-aware scraping with smart intervals
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import List, Dict, Set, Optional
from collections import defaultdict

from sqlalchemy import select
from database.engine import async_session
from database.models import Job, UserPreference, Resume

logger = logging.getLogger("user_job_cache")


class CollaborativeScraper:
    """Collaborative scraping that shares work across all users.
    
    Key advantages:
    - When User A searches "graphic designer", the jobs are cached
    - When User B searches "graphic designer", they get instant matches
    - Background scraping prioritizes under-served roles
    """
    
    def __init__(self):
        self._query_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._last_scrape: Dict[str, float] = {}
        self._jobs_per_query: Dict[str, int] = defaultdict(int)
        self._cooldown_seconds = 120  # 2 minutes per unique query
    
    def _normalize_roles(self, roles: List[str]) -> str:
        """Create canonical signature from roles - normalizes synonyms."""
        role_list = [r.lower().strip() for r in (roles or ["developer"])]
        
        # Normalize common synonyms for collaborative pooling
        normalized = []
        for r in role_list:
            if "graphic" in r or "designer" in r or "ui" in r or "ux" in r:
                normalized.append("designer")
            elif "data" in r or "analyst" in r:
                normalized.append("analyst")
            elif "python" in r:
                normalized.append("python")
            elif "java" in r:
                normalized.append("java")
            elif "frontend" in r or "front end" in r:
                normalized.append("frontend")
            elif "backend" in r or "back end" in r:
                normalized.append("backend")
            elif "full stack" in r or "fullstack" in r:
                normalized.append("fullstack")
            elif "devops" in r or "cloud" in r:
                normalized.append("devops")
            else:
                normalized.append(r)
        
        # Get top role for signature
        return sorted(normalized)[0] if normalized else "general"
    
    def _normalize_locations(self, locations: List[str]) -> str:
        """Create canonical signature from locations - normalizes to regions."""
        loc_list = [l.lower().strip() for l in (locations or ["india"])]
        
        # Normalize common cities to broader regions
        regions = set()
        for l in loc_list:
            if any(city in l for city in ["hyderabad", "bangalore", "bengaluru", "chennai", "mumbai", "pune", "noida", "gurgaon", "delhi", "kolkata"]):
                regions.add("india")
            elif "remote" in l or "anywhere" in l:
                regions.add("remote")
            elif "usa" in l or "us " in l or "america" in l:
                regions.add("usa")
            elif "uk" in l or "london" in l:
                regions.add("uk")
            else:
                regions.add(l)
        
        return sorted(regions)[0] if regions else "india"
    
    def get_query_signature(self, roles: List[str], locations: List[str]) -> str:
        """Get canonical signature for collaborative pooling."""
        roles_sig = self._normalize_roles(roles)
        locs_sig = self._normalize_locations(locations)
        return f"{roles_sig}@{locs_sig}"
    
    async def can_scrape(self, signature: str) -> bool:
        """Check cooldown for this signature."""
        last = self._last_scrape.get(signature, 0)
        return time.time() - last >= self._cooldown_seconds
    
    async def mark_scraped(self, signature: str):
        """Record scrape timestamp."""
        self._last_scrape[signature] = time.time()
    
    async def ensure_jobs_for_signature(self, signature: str, roles: List[str], locations: List[str]):
        """Background scrape for a query signature."""
        lock = self._query_locks[signature]
        async with lock:
            if not await self.can_scrape(signature):
                return
            
            # Check current job count
            async with async_session() as session:
                count = (await session.execute(
                    select(Job).where(Job.user_id.is_(None))
                )).rowcount
            
            if count > 100:  # Pool already healthy
                return
            
            await self.mark_scraped(signature)
            
            # Launch background scrape
            query = roles[0] if roles else "developer"
            location = locations[0] if locations else "india"
            
            asyncio.create_task(self._background_scrape(query, location))
    
    async def _background_scrape(self, query: str, location: str):
        """Execute background scrape."""
        try:
            from ingestion.engine import run_browser_pool_source
            result = await run_browser_pool_source(query=query, location=location)
            logger.info(f"Collaborative scrape: {query}@{location} -> {result}")
        except Exception as e:
            logger.warning(f"Collaborative scrape failed: {e}")


# Global instance
_collaborative_scraper: Optional[CollaborativeScraper] = None


def get_collaborative_scraper() -> CollaborativeScraper:
    global _collaborative_scraper
    if _collaborative_scraper is None:
        _collaborative_scraper = CollaborativeScraper()
    return _collaborative_scraper


async def match_jobs_for_user(user_id: int, limit: int = 30) -> Dict:
    """Match jobs for user with collaborative pooling."""
    scraper = get_collaborative_scraper()
    
    async with async_session() as session:
        pref_result = await session.execute(
            select(UserPreference).where(UserPreference.user_id == user_id)
        )
        preference = pref_result.scalar_one_or_none()
        
        resume_result = await session.execute(
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
            .limit(1)
        )
        resume = resume_result.scalar_one_or_none()
    
    roles = preference.desired_roles if preference else []
    locations = preference.desired_locations if preference else []
    
    # Get signature for collaborative pooling
    if preference:
        signature = scraper.get_query_signature(roles, locations)
    else:
        signature = "default@india"
    
    # Get existing jobs (instant!)
    async with async_session() as session:
        job_result = await session.execute(
            select(Job)
            .where(Job.user_id.is_(None))
            .order_by(Job.created_at.desc())
            .limit(200)
        )
        all_jobs = job_result.scalars().all()
    
    # Smart matching
    matched_jobs = []
    for job in all_jobs:
        score = 0
        job_title_lower = (job.title or "").lower()
        job_skills_lower = [s.lower() for s in (job.skills_required or [])]
        
        for role in roles:
            role_lower = role.lower()
            if role_lower in job_title_lower:
                score += 50
            if any(role_lower in skill for skill in job_skills_lower):
                score += 30
        
        if score > 0:
            matched_jobs.append({"job": job, "score": score})
    
    matched_jobs.sort(key=lambda x: x["score"], reverse=True)
    
    # Trigger background scrape if pool is low
    if len(matched_jobs) < 10:
        asyncio.create_task(scraper.ensure_jobs_for_signature(signature, roles, locations))
    
    return {
        "jobs": [m["job"] for m in matched_jobs[:limit]],
        "total_matches": len(matched_jobs),
        "background_scrape_triggered": len(matched_jobs) < 10,
    }