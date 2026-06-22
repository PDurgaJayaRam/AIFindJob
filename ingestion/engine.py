"""Ingestion engine: runs all sources with per-source isolation and dedup."""
from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Iterable, List, Dict, Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from database.engine import async_session
from database.models import Job
from ingestion.base import BaseIngestionSource, JobRecord, status_store
from ingestion.sources.remoteok import RemoteOKSource

logger = logging.getLogger("ingestion.engine")


def default_sources() -> list[BaseIngestionSource]:
    """ALL portals are ALWAYS scraping - no idle portals.
    
    Sources run continuously via APScheduler every 1 minute.
    Each portal is scraped independently for comprehensive coverage.
    
    Environment:
    - ENABLE_BROWSER_POOL=1 (default) - enables browser pool
    - ENABLE_SOCIAL_INTEL=1 (default) - enables social media job monitoring
    - SCRAPE_PORTALS - which portals to run (default: all)
    """
    sources: list[BaseIngestionSource] = [RemoteOKSource()]
    if os.getenv("INGEST_INCLUDE_ARBEITNOW", "").lower() in {"1", "true", "yes"}:
        from ingestion.sources.arbeitnow import ArbeitnowSource
        sources.append(ArbeitnowSource())
    if os.getenv("ENABLE_BROWSER_POOL", "1") not in {"0", "false", "no"}:
        try:
            from ingestion.sources.browser_pool import BrowserPoolSource
            sources.append(BrowserPoolSource())
        except Exception as exc:
            logger.warning("BrowserPoolSource unavailable, skipping: %s", exc)
    if os.getenv("ENABLE_SOCIAL_INTEL", "1") not in {"0", "false", "no"}:
        try:
            from ingestion.sources.social_intel import SocialIntelSource
            sources.append(SocialIntelSource())
        except Exception as exc:
            logger.warning("SocialIntelSource unavailable, skipping: %s", exc)
    return sources


async def _existing_dedup_keys(records: Iterable[JobRecord]) -> set[str]:
    source_urls = {r.source_url for r in records if r.source_url}
    apply_urls = {r.apply_url for r in records if r.apply_url}
    id_keys: set[str] = {f"id:{r.source.strip().lower()}:{r.external_id}"
                         for r in records if r.external_id}
    existing: set[str] = set()
    async with async_session() as session:
        if id_keys:
            # Recover the (source, external_id) tuples for any id:key we'd find.
            # Build a (source, external_id) lookup from the id_keys.
            id_pairs = set()
            for k in id_keys:
                # k = "id:{source}:{external_id}"
                _, src, ext = k.split(":", 2)
                id_pairs.add((src, ext))
            for src, ext in id_pairs:
                rows = await session.execute(
                    select(Job.id).where(
                        (Job.source == src) & (Job.external_id == ext)
                    ).limit(1)
                )
                if rows.scalars().first() is not None:
                    existing.add(f"id:{src}:{ext}")
        if source_urls:
            rows = await session.execute(
                select(Job.source_url).where(Job.source_url.in_(source_urls))
            )
            existing.update(f"url:{u.strip().lower()}" for u in rows.scalars() if u)
        if apply_urls:
            rows = await session.execute(
                select(Job.apply_url).where(Job.apply_url.in_(apply_urls))
            )
            existing.update(f"apply:{u.strip().lower()}" for u in rows.scalars() if u)
        rows = await session.execute(select(Job.title, Job.company, Job.source))
        for title, company, source in rows.all():
            existing.add(
                f"composite:{(title or '').strip().lower()}|"
                f"{(company or '').strip().lower()}|{(source or '').strip().lower()}"
            )
    return existing


async def _persist(records: list[JobRecord]) -> int:
    if not records:
        return 0
    existing = await _existing_dedup_keys(records)
    seen_in_batch: set[str] = set()
    new_count = 0
    companies_to_process = set()
    
    # Blocked fake/demo source patterns
    blocked_sources = {"demo-data", "demo"}
    fake_url_patterns = ["demo.com", "fakejobs", "example.com", "placeholder"]
    
    async with async_session() as session:
        for rec in records:
            # Validate: reject fake/demo sources
            if rec.source.lower() in blocked_sources:
                continue
            # Validate: reject jobs with fake URLs
            url_lower = (rec.source_url or "").lower()
            if any(pattern in url_lower for pattern in fake_url_patterns):
                continue
            
            key = rec.dedup_key()
            if key in existing or key in seen_in_batch:
                continue
            seen_in_batch.add(key)
            job = Job(
                user_id=None,
                title=rec.title[:500],
                company=rec.company[:500],
                location=rec.location[:500],
                salary=rec.salary[:500],
                skills_required=rec.skills_required,
                description=rec.description,
                apply_url=rec.apply_url,
                source=rec.source[:100],
                source_url=rec.source_url,
                external_id=rec.external_id or None,
                remote=rec.remote,
                posted_date=rec.posted_date,
                ai_analysis={},
            )
            session.add(job)
            new_count += 1
            
            # Track company for contact finding
            if rec.company and len(rec.company) > 2:
                companies_to_process.add(rec.company)
        
        try:
            await session.commit()
        except IntegrityError as exc:
            await session.rollback()
            logger.warning("IntegrityError on commit; %d candidates lost this tick: %s",
                           new_count, exc.orig)
            return 0
    
    # AUTOMATIC CONTACT FINDING - Find 2 contacts per new company
    if companies_to_process:
        asyncio.create_task(_find_contacts_for_companies(companies_to_process))
    
    return new_count


async def _find_contacts_for_companies(companies: set[str]):
    """Automatically find contacts for companies with new jobs.
    
    Finds 2 people per company: HR + Technical Lead
    Saves to Recruiter table for future outreach.
    """
    try:
        # Import from the correct location - people_finder package
        from people_finder.finder import find_contacts
        from database.models import Recruiter
        
        for company_name in list(companies)[:10]:  # Limit to 10 companies per cycle
            # Find contacts using the public data waterfall
            result = await find_contacts(
                company=company_name,
                domain="",
                candidate_names=["HR", "Hiring Manager", "Recruiter", "Tech Lead"]
            )
            
            async with async_session() as session:
                for contact in result.get("contacts", [])[:2]:  # Limit to 2 contacts per company
                    # Check if contact already exists
                    existing = await session.execute(
                        select(Recruiter).where(
                            (Recruiter.company == company_name) & 
                            (Recruiter.name == contact.get("name", ""))
                        )
                    )
                    if existing.scalar_one_or_none():
                        continue
                    
                    # Save new recruiter contact
                    recruiter = Recruiter(
                        name=contact.get("name", ""),
                        role=contact.get("role", ""),
                        company=company_name,
                        linkedin_url=contact.get("linkedin_url", ""),
                        email=contact.get("email", ""),
                        source="auto-scrape",
                        confidence=contact.get("confidence", 0.5),
                    )
                    session.add(recruiter)
                
                await session.commit()
                
    except Exception as e:
        logger.warning(f"Auto contact finding failed: {e}")


async def run_source(source: BaseIngestionSource) -> dict:
    try:
        records = await source.fetch()
        new_count = await _persist(records)
        status_store.record(
            source.name, ok=True, jobs_fetched=len(records), jobs_new=new_count
        )
        # Broadcast to SSE clients
        try:
            from admin.router import broadcast_scraper_event
            broadcast_scraper_event({
                "type": "source_complete",
                "source": source.name,
                "jobs_fetched": len(records),
                "jobs_new": new_count,
                "timestamp": time.time()
            })
        except ImportError:
            pass
        logger.info("Source %s: fetched=%d new=%d", source.name, len(records), new_count)
        return {"source": source.name, "fetched": len(records), "new": new_count}
    except Exception as exc:
        status_store.record(source.name, ok=False, error=str(exc)[:500])
        try:
            from admin.router import broadcast_scraper_event
            broadcast_scraper_event({
                "type": "source_error",
                "source": source.name,
                "error": str(exc)[:200],
                "timestamp": time.time()
            })
        except ImportError:
            pass
        logger.error("Source %s failed: %s", source.name, exc)
        return {"source": source.name, "error": str(exc)}


async def run_all_sources(sources: list[BaseIngestionSource] | None = None) -> list[dict]:
    sources = sources or default_sources()
    results = []
    for source in sources:
        results.append(await run_source(source))
    return results


async def run_browser_pool_source(
    query=None,
    location=None,
    experience_level=None,
) -> list[dict]:
    """Run only the browser-pool source and persist its jobs. Updates
    per-portal browser_pool_status_store.jobs_new after persist so the
    admin aggregator can surface fresh counts.

    Used by `workers.tasks_browser.run_browser_scrape_task` (Celery beat
    every 2 hours), by the /admin/trigger/browser-pool "Run now" button,
    and by `profile.router.put_preferences` when a user saves their
    preferences.

    Args:
        query: Role keyword (e.g. "Data Analyst"). None → env default.
        location: City (e.g. "Hyderabad"). None → env default.
        experience_level: "fresher" | "junior" | "mid" | "senior" | None.
            None or "mid"/"senior" → no query prepend. "fresher"/"junior"
            → BrowserPoolSource prepends to the query for fresher-aware
            filtering. Per-portal URL-param mapping is deferred.
    """
    from ingestion.browser_pool_status import browser_pool_status_store
    from ingestion.sources.browser_pool import BrowserPoolSource

    source = BrowserPoolSource(
        query=query,
        location=location,
        experience_level=experience_level,
    )
    try:
        records = await source.fetch()
    except Exception as exc:
        logger.exception("Browser pool fetch failed: %s", exc)
        return [{"source": source.name, "error": str(exc)[:500]}]
    new_count = await _persist(records)
    # Update per-portal jobs_new by attributing evenly across portals that ran.
    portals_in_batch = {r.source for r in records}
    if portals_in_batch and new_count and len(portals_in_batch):
        per_portal = max(1, new_count // len(portals_in_batch))
        for p in portals_in_batch:
            s = browser_pool_status_store.get(p)
            if s:
                s["jobs_new"] = per_portal
    status_store.record(source.name, ok=True, jobs_fetched=len(records), jobs_new=new_count)
    logger.info("Browser pool: fetched=%d new=%d", len(records), new_count)
    return [{"source": source.name, "fetched": len(records), "new": new_count}]
