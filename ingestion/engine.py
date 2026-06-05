"""Ingestion engine: runs all sources with per-source isolation and dedup."""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import select

from database.engine import async_session
from database.models import Job
from ingestion.base import BaseIngestionSource, JobRecord, status_store
from ingestion.sources.remoteok import RemoteOKSource
from ingestion.sources.arbeitnow import ArbeitnowSource
from ingestion.sources.adzuna import AdzunaSource

logger = logging.getLogger("ingestion.engine")


def default_sources() -> list[BaseIngestionSource]:
    """RemoteOK + Arbeitnow are free/no-key. Adzuna optional (needs env keys)."""
    return [RemoteOKSource(), ArbeitnowSource(), AdzunaSource()]


async def _existing_dedup_keys(records: Iterable[JobRecord]) -> set[str]:
    source_urls = {r.source_url for r in records if r.source_url}
    apply_urls = {r.apply_url for r in records if r.apply_url}
    existing: set[str] = set()
    async with async_session() as session:
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
    async with async_session() as session:
        for rec in records:
            key = rec.dedup_key()
            if key in existing or key in seen_in_batch:
                continue
            seen_in_batch.add(key)
            session.add(
                Job(
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
                    remote=rec.remote,
                    posted_date=rec.posted_date,
                    ai_analysis={},
                )
            )
            new_count += 1
        await session.commit()
    return new_count


async def run_source(source: BaseIngestionSource) -> dict:
    try:
        records = await source.fetch()
        new_count = await _persist(records)
        status_store.record(
            source.name, ok=True, jobs_fetched=len(records), jobs_new=new_count
        )
        logger.info("Source %s: fetched=%d new=%d", source.name, len(records), new_count)
        return {"source": source.name, "fetched": len(records), "new": new_count}
    except Exception as exc:
        status_store.record(source.name, ok=False, error=str(exc)[:500])
        logger.error("Source %s failed: %s", source.name, exc)
        return {"source": source.name, "error": str(exc)}


async def run_all_sources(sources: list[BaseIngestionSource] | None = None) -> list[dict]:
    sources = sources or default_sources()
    results = []
    for source in sources:
        results.append(await run_source(source))
    return results
