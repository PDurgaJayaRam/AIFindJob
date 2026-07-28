"""Per-user endpoints: store resume + target role, get ranked pool matches.

Mounted under /me. Uses the existing JWT `get_current_user` dependency from the
main app (passed in at mount time to avoid a circular import).
"""
from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Query, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from database.engine import async_session
from database.models import Resume, UserPreference, Job
from matching.scorer import rank_jobs


class ResumeIn(BaseModel):
    text_content: str = ""
    skills: list[str] = []
    experience_years: float = 0.0
    is_fresher: bool = True
    target_roles: list[str] = []
    filename: str = ""


# Thread-safe signal file for cross-event-loop notifications.
# The scraper runs in asyncio.run() (separate loop), so asyncio.Queue won't
# work. Instead we write a timestamp to a signal file; the SSE endpoint polls it.
_SIGNAL_FILE = os.path.join(os.path.dirname(__file__), "..", "data", ".matches_signal")
_last_signal: float = 0.0


def notify_matches_updated(new_jobs: int = 0):
    """Write a signal file so the SSE endpoint in the main loop picks it up."""
    try:
        os.makedirs(os.path.dirname(_SIGNAL_FILE), exist_ok=True)
        with open(_SIGNAL_FILE, "w") as f:
            f.write(json.dumps({"t": time.time(), "n": new_jobs}))
    except Exception:
        pass


def build_router(get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/me", tags=["matching"])

    @router.post("/resume")
    async def save_resume(body: ResumeIn, user=Depends(get_current_user)):
        """Store/replace the user's resume + target roles used for matching."""
        async with async_session() as session:
            # Parse resume sections for optimization (PHASE 4.9)
            from resume_tailor.resume_parser import parse_resume_sections
            parsed_sections = parse_resume_sections(body.text_content or "")
            
            resume = Resume(
                user_id=user.id,
                filename=body.filename or "resume.txt",
                text_content=body.text_content,
                skills=body.skills,
                experience_years=body.experience_years,
                parsed_data={
                    "is_fresher": body.is_fresher,
                    "target_roles": body.target_roles,
                },
                parsed_sections=parsed_sections,
            )
            session.add(resume)

            # Upsert preferences (target roles drive matching).
            pref_row = await session.execute(
                select(UserPreference).where(UserPreference.user_id == user.id)
            )
            pref = pref_row.scalar_one_or_none()
            if pref is None:
                pref = UserPreference(user_id=user.id)
                session.add(pref)
            pref.desired_roles = body.target_roles
            pref.skills = body.skills

            await session.commit()
            await session.refresh(resume)
            return {"resume_id": resume.id, "skills": body.skills, "target_roles": body.target_roles}

    @router.get("/profile")
    async def get_profile(user=Depends(get_current_user)):
        """Return the latest stored resume profile used for matching."""
        async with async_session() as session:
            row = await session.execute(
                select(Resume).where(Resume.user_id == user.id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = row.scalar_one_or_none()
            if not resume:
                return {"has_resume": False, "name": user.full_name or user.email.split('@')[0]}
            parsed = resume.parsed_data or {}
            return {
                "has_resume": True,
                "name": parsed.get("name") or user.full_name or user.email.split('@')[0],
                "email": user.email,
                "skills": resume.skills or [],
                "experience_years": resume.experience_years or 0,
                "is_fresher": parsed.get("is_fresher", True),
                "target_roles": parsed.get("target_roles", []),
            }

    @router.get("/matches")
    async def get_matches(
        user=Depends(get_current_user),
        limit: int = Query(30, ge=1, le=100),
        min_score: float = Query(20.0, ge=0, le=100),
    ):
        """Rank the shared pool against the user's stored resume + target roles."""
        async with async_session() as session:
            row = await session.execute(
                select(Resume).where(Resume.user_id == user.id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = row.scalar_one_or_none()
            if not resume:
                raise HTTPException(status_code=404, detail="No resume found. POST /me/resume first.")

            parsed = resume.parsed_data or {}
            profile = {
                "skills": resume.skills or [],
                "is_fresher": parsed.get("is_fresher", True),
                "target_roles": parsed.get("target_roles", []),
                "experience_years": float(resume.experience_years or 0.0),
            }

            # Pull recent pool jobs (limit to 500 for speed; oldest jobs are least relevant)
            pool_rows = await session.execute(
                select(Job).order_by(Job.created_at.desc()).limit(500)
            )
            pool = [
                {
                    "id": j.id,
                    "title": j.title,
                    "company": j.company,
                    "location": j.location,
                    "description": j.description or "",
                    "source": j.source,
                    "source_url": j.source_url,
                    "apply_url": j.apply_url,
                    "skills_required": j.skills_required or [],
                    "created_at": j.created_at.isoformat() if j.created_at else "",
                }
                for j in pool_rows.scalars().all()
            ]

        ranked = rank_jobs(pool, profile)
        # Enforce minimum 20% so irrelevant jobs are filtered out
        effective_min = max(min_score, 20.0)
        ranked = [r for r in ranked if r["match"]["score"] >= effective_min][:limit]
        
        # If we have few matches, trigger background scrape for user's roles
        if len(ranked) < limit // 2 and profile.get("target_roles"):
            asyncio.create_task(_ensure_jobs_for_roles(profile["target_roles"]))
        
        return {"count": len(ranked), "profile": profile, "matches": ranked, "background_scrape_triggered": len(ranked) < limit // 2}

    @router.get("/matches/events")
    async def match_events(request: Request):
        """SSE stream — polls signal file and pushes event when new jobs land."""
        global _last_signal
        async def generate():
            while True:
                if await request.is_disconnected():
                    break
                try:
                    # Check signal file for new scrape events
                    if os.path.exists(_SIGNAL_FILE):
                        with open(_SIGNAL_FILE, "r") as f:
                            sig = json.loads(f.read())
                        sig_time = sig.get("t", 0)
                        if sig_time > _last_signal:
                            _last_signal = sig_time
                            yield f"data: {json.dumps({'type': 'matches_updated', 'new_jobs': sig.get('n', 0), 'timestamp': sig_time})}\n\n"
                    await asyncio.sleep(2)
                except asyncio.CancelledError:
                    break
                except Exception:
                    await asyncio.sleep(2)
        return StreamingResponse(generate(), media_type="text/event-stream")

    @router.post("/matches/scrape")
    async def trigger_scrape(user=Depends(get_current_user)):
        """Trigger an immediate scrape for the user's target roles and return once new jobs land."""
        async with async_session() as session:
            row = await session.execute(
                select(Resume).where(Resume.user_id == user.id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = row.scalar_one_or_none()
            if not resume:
                raise HTTPException(status_code=404, detail="No resume found.")

            parsed = resume.parsed_data or {}
            target_roles = parsed.get("target_roles", [])

        if not target_roles:
            return {"status": "no_roles", "message": "No target roles in profile"}

        # Run scrape in background so the endpoint returns quickly
        asyncio.create_task(_run_scrape_and_notify(target_roles))
        return {"status": "started", "roles": target_roles}

    return router


async def _run_scrape_and_notify(roles: list[str]):
    """Scrape for the given roles, then broadcast a refresh event."""
    try:
        from ingestion.engine import run_browser_pool_source
        role_lower = [r.lower() for r in roles]

        queries = set()
        for role in role_lower:
            if "graphic" in role or "design" in role:
                queries.update(["graphic designer", "ui ux designer", "creative designer"])
            elif "data" in role or "analyst" in role:
                queries.update(["data analyst", "business analyst"])
            elif "python" in role or "django" in role:
                queries.update(["python developer", "django developer"])
            elif "java" in role:
                queries.update(["java developer", "spring boot developer"])
            else:
                queries.add(role)

        total_new = 0
        for q in list(queries)[:3]:
            results = await run_browser_pool_source(query=q, location="india", experience_level="fresher")
            total_new += sum(r.get("new", 0) for r in results)

        notify_matches_updated(total_new)
    except Exception as e:
        pass


async def _ensure_jobs_for_roles(roles: list[str]):
    """Background task to ensure we have jobs for specific roles.
    
    This prevents the "wait for a decade" problem - immediately triggers
    scraping when a user's query has few matches.
    """
    try:
        role_skills = []
        role_lower = [r.lower() for r in roles]
        
        for role in role_lower:
            if "graphic" in role or "design" in role:
                role_skills.extend(["graphic designer", "ui ux", "creative"])
            elif "data" in role or "analyst" in role:
                role_skills.extend(["data analyst", "business analyst"])
            elif "python" in role or "django" in role:
                role_skills.extend(["python developer", "django"])
            elif "java" in role:
                role_skills.extend(["java developer", "spring"])
            else:
                role_skills.append(role)
        
        query = role_skills[0] if role_skills else "developer"
        
        from ingestion.engine import run_browser_pool_source
        await run_browser_pool_source(query=query, location="india", experience_level="fresher")
    except Exception as e:
        pass  # Silent fail - UI will retry on next refresh