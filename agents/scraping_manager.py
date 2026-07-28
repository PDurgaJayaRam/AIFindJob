"""Continuous Scraping Manager - Efficiently handles scraping for many users.

Key insight: Instead of 100 users triggering 100 scrapes, we:
1. Queue all scrape requests centrally
2. Deduplicate by role+location signatures
3. Process one scrape per unique query
4. All waiting users get results from shared pool
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Dict, List, Set, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("scraping_manager")


class ScrapePriority(Enum):
    HIGH = "high"      # User just registered, waiting
    NORMAL = "normal"  # Regular update
    LOW = "low"        # Background maintenance


@dataclass
class ScrapeRequest:
    """A user's request for job scraping."""
    user_id: int
    roles: List[str]
    locations: List[str]
    experience_level: Optional[str]
    priority: ScrapePriority
    requested_at: float = field(default_factory=time.time)
    webhook_url: Optional[str] = None  # Optional callback for real-time updates


class ContinuousScrapingManager:
    """Manages concurrent scraping requests efficiently.
    
    Features:
    - Deduplicates requests (100 users asking for "designer" = 1 scrape)
    - Priority queuing (new users get faster results)
    - Shared results cache
    - Callback notifications
    """
    
    def __init__(self):
        self._requests: Dict[str, List[ScrapeRequest]] = {}  # signature -> requests
        self._running: Set[str] = set()  # Currently active signatures
        self._locks: Dict[str, asyncio.Lock] = {}
        self._results_cache: Dict[str, List[int]] = {}  # signature -> job_ids
        self._user_watchers: Dict[int, asyncio.Queue] = {}  # user_id -> result queue
        self._max_concurrent = 3  # Limit browsers on free VPS
        self._semaphore = asyncio.Semaphore(self._max_concurrent)
    
    def _normalize_signature(self, roles: List[str], locations: List[str], exp_level: Optional[str]) -> str:
        """Create a normalized signature for deduplication."""
        # Normalize roles - group similar roles
        normalized_roles = set()
        for role in roles:
            role_lower = role.lower().strip()
            if "graphic" in role_lower or "designer" in role_lower or "ui" in role_lower or "ux" in role_lower:
                normalized_roles.add("designer")
            elif "data" in role_lower or "analyst" in role_lower:
                normalized_roles.add("analyst")
            elif "python" in role_lower:
                normalized_roles.add("python")
            elif "java" in role_lower:
                normalized_roles.add("java")
            elif "frontend" in role_lower or "front" in role_lower:
                normalized_roles.add("frontend")
            elif "backend" in role_lower or "back" in role_lower:
                normalized_roles.add("backend")
            elif "full stack" in role_lower or "fullstack" in role_lower:
                normalized_roles.add("fullstack")
            elif "devops" in role_lower or "cloud" in role_lower:
                normalized_roles.add("devops")
            else:
                normalized_roles.add(role_lower)
        
        # Normalize locations - group to regions
        normalized_locs = set()
        for loc in locations:
            loc_lower = loc.lower().strip()
            if any(city in loc_lower for city in ["hyderabad", "bangalore", "chennai", "mumbai", "delhi", "pune", "india"]):
                normalized_locs.add("india")
            elif "remote" in loc_lower:
                normalized_locs.add("remote")
            else:
                normalized_locs.add(loc_lower)
        
        # Create signature
        role_str = sorted(normalized_roles)[0] if normalized_roles else "general"
        loc_str = sorted(normalized_locs)[0] if normalized_locs else "india"
        exp_str = (exp_level or "any").lower()
        
        return f"{role_str}@{loc_str}@{exp_str}"
    
    async def request_scrape(self, request: ScrapeRequest) -> Dict:
        """Submit a scrape request. Returns immediately with status."""
        signature = self._normalize_signature(request.roles, request.locations, request.experience_level)
        
        # Add to queue
        if signature not in self._requests:
            self._requests[signature] = []
            self._locks[signature] = asyncio.Lock()
        
        self._requests[signature].append(request)
        
        # Create watcher for this user
        self._user_watchers[request.user_id] = asyncio.Queue()
        
        # If already running, just wait for results
        if signature in self._running:
            return {
                "status": "queued",
                "signature": signature,
                "message": "Scraping already in progress - jobs will appear shortly",
                "estimated_wait_seconds": 30
            }
        
        # Otherwise trigger scrape
        asyncio.create_task(self._process_signature(signature))
        
        return {
            "status": "started",
            "signature": signature,
            "message": "Scraping started - check back in 1-2 minutes",
            "estimated_wait_seconds": 60
        }
    
    async def _process_signature(self, signature: str):
        """Process a scrape request for a signature."""
        async with self._locks[signature]:
            self._running.add(signature)
            
            try:
                # Get primary role and location for scrape
                parts = signature.split("@")
                query = parts[0]
                location = parts[1]
                exp_level = parts[2]
                
                async with self._semaphore:  # Limit concurrent browsers
                    from ingestion.engine import run_browser_pool_source
                    result = await run_browser_pool_source(
                        query=query,
                        location=location,
                        experience_level=exp_level if exp_level != "any" else None
                    )
                
                # Notify all waiting users
                for req in self._requests.get(signature, []):
                    viewer = self._user_watchers.get(req.user_id)
                    if viewer:
                        try:
                            viewer.put_nowait({"status": "complete", "signature": signature, "result": result})
                        except:
                            pass
                
                # Clear requests for this signature
                self._requests.pop(signature, None)
                
            except Exception as e:
                logger.error(f"Scraping failed for {signature}: {e}")
                for req in self._requests.get(signature, []):
                    viewer = self._user_watchers.get(req.user_id)
                    if viewer:
                        try:
                            viewer.put_nowait({"status": "error", "error": str(e)})
                        except:
                            pass
            finally:
                self._running.discard(signature)
    
    async def get_jobs_for_user(self, user_id: int, roles: List[str], locations: List[str], limit: int = 50) -> List[int]:
        """Get job IDs for a user instantly from cache or pool."""
        from database.engine import async_session
        from database.models import Job, UserPreference
        from sqlalchemy import select
        
        # Get signature
        signature = self._normalize_signature(roles, locations, None)
        
        # Check cache first
        if signature in self._results_cache:
            return self._results_cache[signature][:limit]
        
        # Query database directly
        async with async_session() as session:
            job_result = await session.execute(
                select(Job.id).where(Job.user_id.is_(None)).limit(limit)
            )
            job_ids = job_result.scalars().all()
        
        # Update cache
        self._results_cache[signature] = job_ids
        
        return job_ids[:limit]
    
    async def watch_results(self, user_id: int, timeout: float = 120.0):
        """Watch for scraping results for a user."""
        if user_id not in self._user_watchers:
            self._user_watchers[user_id] = asyncio.Queue()
        
        queue = self._user_watchers[user_id]
        try:
            result = await asyncio.wait_for(queue.get(), timeout=timeout)
            return result
        except asyncio.TimeoutError:
            return {"status": "timeout", "message": "Scraping still in progress"}


# Global singleton
_scraping_manager: Optional[ContinuousScrapingManager] = None


def get_scraping_manager() -> ContinuousScrapingManager:
    global _scraping_manager
    if _scraping_manager is None:
        _scraping_manager = ContinuousScrapingManager()
    return _scraping_manager