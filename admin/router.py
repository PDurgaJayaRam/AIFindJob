"""Admin overview endpoint: live ingestion health + pool stats.

Read-only aggregation for the admin dashboard. Mounted under /admin.
"""
from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import func, select

from database.engine import async_session
from database.models import Job
from ingestion.base import status_store

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/overview")
async def overview():
    """Aggregate ingestion source health and pool counts by source."""
    async with async_session() as session:
        total = (await session.execute(select(func.count(Job.id)))).scalar() or 0
        by_source_rows = await session.execute(
            select(Job.source, func.count(Job.id)).group_by(Job.source)
        )
        by_source = {src or "unknown": cnt for src, cnt in by_source_rows.all()}

    return {
        "pool": {"total_jobs": total, "by_source": by_source},
        "sources": status_store.all(),
    }
