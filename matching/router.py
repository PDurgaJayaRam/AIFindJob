"""Per-user endpoints: store resume + target role, get ranked pool matches.

Mounted under /me. Uses the existing JWT `get_current_user` dependency from the
main app (passed in at mount time to avoid a circular import).
"""
from __future__ import annotations

from typing import Any, Callable, Optional

from fastapi import APIRouter, Depends, Query
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
                return {"has_resume": False}
            parsed = resume.parsed_data or {}
            return {
                "has_resume": True,
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
                return {"error": "No resume found. POST /me/resume first.", "matches": []}

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
                }
                for j in pool_rows.scalars().all()
            ]

        ranked = rank_jobs(pool, profile)
        ranked = [r for r in ranked if r["match"]["score"] >= min_score][:limit]
        return {"count": len(ranked), "profile": profile, "matches": ranked}

    return router
