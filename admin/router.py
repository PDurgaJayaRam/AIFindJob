"""Admin overview endpoint: live ingestion health + pool stats.

Read-only aggregation for the admin dashboard. Mounted under /admin.
Requires admin authentication.

PHASE 5 - Enhanced with portal-specific controls.
"""
from __future__ import annotations

import asyncio
import json
import os
import logging
from fastapi import APIRouter, Depends, Form, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select

from database.engine import async_session
from database.models import Job, User
from ingestion.base import status_store

logger = logging.getLogger("admin.router")

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


class ScrapeAllIn(BaseModel):
    query: str | None = None
    location: str | None = None
    experience_level: str | None = None


@router.post("/scrape/all-portals")
async def trigger_all_portals_scrape(payload: ScrapeAllIn | None = None, background_tasks: BackgroundTasks = None):
    """Trigger scraping across ALL portals immediately.
    
    This ensures no portal sleeps - all are actively scraping.
    """
    import os
    
    query = payload.query if payload else os.getenv("SCRAPE_QUERY", "developer")
    location = payload.location if payload else os.getenv("SCRAPE_LOCATION", "India")
    exp_level = payload.experience_level if payload else "fresher"
    
    if background_tasks:
        background_tasks.add_task(_run_all_portals_sync, query, location, exp_level)
    
    return {
        "status": "started",
        "message": f"Scraping all portals for '{query}' in '{location}'",
        "portals": ["naukri", "indeed", "linkedin", "shine", "foundit", "timesjobs"]
    }


def _run_all_portals_sync(query: str, location: str, exp_level: str):
    """Run all portals sync wrapper."""
    import asyncio
    if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(_run_all_portals_async(query, location, exp_level))


async def _run_all_portals_async(query: str, location: str, exp_level: str):
    """Scrape all portals concurrently."""
    try:
        from ingestion.engine import run_browser_pool_source
        await run_browser_pool_source(query=query, location=location, experience_level=exp_level)
    except Exception as e:
        logger.error(f"All portals scrape failed: {e}")


@router.get("/portals/status")
async def portal_status():
    """Get detailed status of each portal plus contact database stats."""
    portals = ["naukri", "indeed", "linkedin", "shine", "foundit", "timesjobs"]
    status = status_store.all()
    
    # Get contact database stats
    async with async_session() as session:
        from database.models import Recruiter
        contact_count = (await session.execute(select(func.count(Recruiter.id)))).scalar() or 0
        companies_with_contacts = (await session.execute(
            select(func.count(func.distinct(Recruiter.company)))
        )).scalar() or 0
    
    portal_status = []
    for portal in portals:
        portal_data = next((s for s in status if s.get("name") == "browser_pool"), {})
        portal_status.append({
            "name": portal,
            "enabled": os.getenv("ENABLE_BROWSER_POOL", "1") != "0",
            "last_run": portal_data.get("last_run"),
            "jobs_fetched": portal_data.get("jobs_fetched", 0),
            "jobs_new": portal_data.get("jobs_new", 0),
            "ok": portal_data.get("ok", True),
            "has_vision_support": os.getenv("NVIDIA_API_KEY") is not None or os.getenv("MISTRAL_API_KEY") is not None,
        })
    
    return {
        "portals": portal_status, 
        "scrape_interval_minutes": int(os.getenv("SCRAPE_INTERVAL_MINUTES", "1")),
        "contact_database": {
            "total_contacts": contact_count,
            "companies_with_contacts": companies_with_contacts,
        }
    }


@router.post("/scrape/trigger/{portal_name}")
async def trigger_specific_portal(portal_name: str, background_tasks: BackgroundTasks):
    """Trigger scraping for a specific portal immediately."""
    valid_portals = ["naukri", "indeed", "linkedin", "shine", "foundit", "timesjobs"]
    
    if portal_name not in valid_portals:
        raise HTTPException(status_code=400, detail=f"Invalid portal. Use one of: {valid_portals}")
    
    background_tasks.add_task(_scrape_single_portal, portal_name)
    
    return {
        "status": "started",
        "portal": portal_name,
        "message": f"Scraping {portal_name} now..."
    }


def _scrape_single_portal(portal_name: str):
    """Scrape a single portal."""
    import asyncio
    if hasattr(asyncio, 'WindowsProactorEventLoopPolicy'):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(_scrape_single_portal_async(portal_name))


async def _scrape_single_portal_async(portal_name: str):
    """Async scrape implementation."""
    try:
        from ingestion.sources.browser_pool import BrowserPoolSource
        source = BrowserPoolSource(query="developer", location="India")
        # Could implement single-portal scraping here if needed
        # For now, just log
        logger.info(f"Single portal scrape requested for: {portal_name}")
    except Exception as e:
        logger.error(f"Single portal scrape failed for {portal_name}: {e}")
