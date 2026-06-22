"""Per-user endpoints: store resume + target role, get ranked pool matches.

Mounted under /me. Uses the existing JWT `get_current_user` dependency from the
main app (passed in at mount time to avoid a circular import).
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
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
        pool_size: int = Query(300, ge=1, le=1000),
        min_score: float = Query(0.0, ge=0, le=100),
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
            }

            # Pull a window of the shared pool (pool jobs have user_id IS NULL).
            pool_rows = await session.execute(
                select(Job).order_by(Job.created_at.desc()).limit(pool_size)
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
        ranked = [r for r in ranked if r["match"]["score"] >= min_score][:limit]
        
        # If we have few matches, trigger background scrape for user's roles
        if len(ranked) < limit // 2 and profile.get("target_roles"):
            asyncio.create_task(_ensure_jobs_for_roles(profile["target_roles"]))
        
        return {"count": len(ranked), "profile": profile, "matches": ranked, "background_scrape_triggered": len(ranked) < limit // 2}

    return router


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