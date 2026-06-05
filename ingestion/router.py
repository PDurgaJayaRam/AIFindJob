"""FastAPI router for Phase 1 ingestion (mounted under /ingestion)."""
from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select

from database.engine import async_session
from database.models import Job
from ingestion.base import status_store
from ingestion.engine import run_all_sources

router = APIRouter(prefix="/ingestion", tags=["ingestion"])


@router.get("/status")
async def ingestion_status():
    return {"sources": status_store.all()}


@router.post("/run")
async def trigger_ingestion():
    results = await run_all_sources()
    return {"results": results}


@router.get("/jobs")
async def list_pool_jobs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    source: str | None = None,
):
    async with async_session() as session:
        query = select(Job).order_by(Job.created_at.desc())
        if source:
            query = query.where(Job.source == source)
        query = query.limit(limit).offset(offset)
        rows = (await session.execute(query)).scalars().all()
        return {
            "count": len(rows),
            "jobs": [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "source": j.source,
                    "source_url": j.source_url,
                    "apply_url": j.apply_url,
                    "remote": j.remote,
                    "skills_required": j.skills_required,
                    "posted_date": j.posted_date.isoformat() if j.posted_date else None,
                    "created_at": j.created_at.isoformat() if j.created_at else None,
                }
                for j in rows
            ],
        }
