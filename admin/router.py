"""Admin overview endpoint: live ingestion health + pool stats.

Read-only aggregation for the admin dashboard. Mounted under /admin.
Requires admin authentication.
"""
from __future__ import annotations

import asyncio
import json
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from database.engine import async_session
from database.models import Job, User
from ingestion.base import status_store

router = APIRouter(prefix="/admin", tags=["admin"])

# SSE event queue for live scraper updates
_sse_queue: asyncio.Queue = asyncio.Queue()


def broadcast_scraper_event(event_data: dict):
    """Broadcast scraper event to all connected SSE clients."""
    try:
        _sse_queue.put_nowait(json.dumps(event_data))
    except:
        pass


@router.post("/login")
async def admin_login(email: str = Form(...), password: str = Form(...)):
    """Admin login endpoint - returns JWT token for admin user."""
    import os
    import bcrypt
    from jose import jwt
    from datetime import datetime, timedelta
    from sqlalchemy import select
    
    async with async_session() as session:
        result = await session.execute(select(User).where(User.email == email))
        user = result.scalar_one_or_none()
        
        if not user or not user.is_admin:
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
        
        if not bcrypt.checkpw(password.encode(), user.hashed_password.encode()):
            raise HTTPException(status_code=401, detail="Invalid admin credentials")
    
    SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-in-production")
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24
    
    token = jwt.encode({"sub": str(user.id)}, SECRET_KEY, algorithm=ALGORITHM)
    
    return {"access_token": token, "token_type": "bearer"}


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


@router.get("/events")
async def scraper_events(request: Request):
    """Server-Sent Events endpoint for live scraper updates."""
    async def event_generator():
        while True:
            if await request.is_disconnected():
                break
            try:
                event = await asyncio.wait_for(_sse_queue.get(), timeout=30.0)
                yield f"data: {event}\n\n"
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


class TriggerBrowserPoolIn(BaseModel):
    query: str | None = None
    location: str | None = None
    experience_level: str | None = None


@router.post("/trigger/browser-pool")
async def trigger_browser_pool(payload: TriggerBrowserPoolIn | None = None):
    """Fire a one-shot browser-pool scrape. Same permissive auth as
    /admin/overview (no per-route dependency) — this matches the existing
    admin auth model per the project convention.

    Body is optional. If omitted (or all fields null), falls through to
    the env defaults in `enqueue_browser_scrape` (SCRAPE_QUERY /
    SCRAPE_LOCATION, no experience prepend).

    Returns: {enqueued: bool, task_id: str, reason?: str}
    """
    from workers.tasks_browser import enqueue_browser_scrape
    body = payload or TriggerBrowserPoolIn()
    task_id = enqueue_browser_scrape(
        query=body.query or "",
        location=body.location or "",
        experience_level=body.experience_level,
    )
    if not task_id:
        return {
            "enqueued": False,
            "task_id": "",
            "reason": "broker_unavailable",
        }
    return {"enqueued": True, "task_id": task_id}
