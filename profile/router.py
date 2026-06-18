"""Profile preferences router (bounded context).

Owns: GET/PUT /me/preferences, PUT /me/resume-meta.
Side-effect: PUT /me/preferences enqueues a Celery browser-pool scrape so the
fresher-aware filter in `BrowserPoolSource` picks up the new desired_roles /
desired_locations / experience_level without waiting for the 2h beat.

Kept deliberately narrow: this module does NOT touch `matching/router.py`,
`resume_tailor/`, `auto_apply/`, or outreach. The matching router stays
about /me/resume + /me/matches; this router stays about /me/preferences +
/me/resume-meta.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from database.engine import async_session
from database.models import Resume, UserPreference
from sqlalchemy import select

logger = logging.getLogger("profile.router")


# ---------- helpers ----------

def derive_level(years: float) -> str:
    """Mirror of the frontend deriveLevel(years) rule.

    0 = fresher, 1-2 = junior, 3-5 = mid, 6+ = senior.

    Duplicated in the frontend (Profile.jsx) on purpose: pulling a shared
    module across the FastAPI/React boundary is more friction than it's
    worth for a 4-line rule.
    """
    if years <= 0:
        return "fresher"
    if years <= 2:
        return "junior"
    if years <= 5:
        return "mid"
    return "senior"


def _enqueue_scrape(query: str, location: str, experience_level: Optional[str]) -> dict:
    """Fire-and-forget Celery enqueue. Never raises — the API must not 5xx
    just because the broker is down. Returns {enqueued, task_id}."""
    try:
        from workers.tasks_browser import enqueue_browser_scrape
        task_id = enqueue_browser_scrape(
            query=query,
            location=location,
            experience_level=experience_level,
        )
        if not task_id:
            return {"enqueued": False, "task_id": ""}
        return {"enqueued": True, "task_id": task_id}
    except Exception as exc:  # noqa: BLE001 - API safety net
        logger.warning("Scrape enqueue failed (broker down?): %s", exc)
        return {"enqueued": False, "task_id": ""}


# ---------- schemas ----------

class PreferencesIn(BaseModel):
    desired_roles: List[str] = Field(..., min_length=1)
    desired_locations: List[str] = Field(..., min_length=1)
    remote_ok: bool = False
    min_salary: Optional[float] = None
    experience_years: float = Field(..., ge=0, le=30)
    skills: List[str] = Field(default_factory=list)


class PreferencesOut(BaseModel):
    desired_roles: List[str]
    desired_locations: List[str]
    remote_ok: bool
    min_salary: Optional[float]
    experience_years: float
    skills: List[str]
    experience_level: str


class ResumeMetaIn(BaseModel):
    experience_years: float = Field(..., ge=0, le=30)
    skills: List[str] = Field(default_factory=list)


# ---------- factory ----------

def build_router(get_current_user):
    """Factory pattern mirrors matching/resume_tailor routers.

    `get_current_user` is the JWT dep from `api/main.py`. We accept it as a
    parameter (rather than importing it directly) to keep the test surface
    narrow and to match the pattern used by sibling modules.
    """
    router = APIRouter(prefix="/me", tags=["profile"])

    @router.get("/preferences", response_model=PreferencesOut)
    async def get_preferences(user=Depends(get_current_user)):
        async with async_session() as session:
            pref_row = (
                await session.execute(
                    select(UserPreference).where(UserPreference.user_id == user.id)
                )
            ).scalar_one_or_none()

            resume_row = (
                await session.execute(
                    select(Resume)
                    .where(Resume.user_id == user.id)
                    .order_by(Resume.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

        experience_years = float(resume_row.experience_years) if resume_row and resume_row.experience_years is not None else 0.0
        return PreferencesOut(
            desired_roles=list(pref_row.desired_roles) if pref_row and pref_row.desired_roles else [],
            desired_locations=list(pref_row.desired_locations) if pref_row and pref_row.desired_locations else [],
            remote_ok=bool(pref_row.remote_ok) if pref_row else False,
            min_salary=pref_row.min_salary if pref_row else None,
            experience_years=experience_years,
            skills=list(resume_row.skills) if resume_row and resume_row.skills else [],
            experience_level=derive_level(experience_years),
        )

    @router.put("/preferences", response_model=PreferencesOut)
    async def put_preferences(payload: PreferencesIn, user=Depends(get_current_user)):
        async with async_session() as session:
            # Upsert UserPreference
            pref_row = (
                await session.execute(
                    select(UserPreference).where(UserPreference.user_id == user.id)
                )
            ).scalar_one_or_none()

            if pref_row is None:
                pref_row = UserPreference(user_id=user.id)
                session.add(pref_row)

            pref_row.desired_roles = payload.desired_roles
            pref_row.desired_locations = payload.desired_locations
            pref_row.remote_ok = payload.remote_ok
            pref_row.min_salary = int(payload.min_salary) if payload.min_salary is not None else None

            # Upsert latest Resume.experience_years + skills
            resume_row = (
                await session.execute(
                    select(Resume)
                    .where(Resume.user_id == user.id)
                    .order_by(Resume.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if resume_row is None:
                # Create a stub. Profile-edit-only users don't have a resume yet.
                resume_row = Resume(
                    user_id=user.id,
                    filename="profile-edit.txt",
                    text_content="",
                    skills=payload.skills,
                    experience_years=payload.experience_years,
                )
                session.add(resume_row)
            else:
                resume_row.experience_years = payload.experience_years
                resume_row.skills = payload.skills

            await session.commit()
            experience_years = float(resume_row.experience_years)
            level = derive_level(experience_years)

        # Side effect: re-scrape with the new fields. Fire-and-forget.
        role = payload.desired_roles[0] if payload.desired_roles else None
        location = payload.desired_locations[0] if payload.desired_locations else None
        scrape = {"enqueued": False, "task_id": ""}
        if role and location:
            scrape = _enqueue_scrape(role, location, level)

        return PreferencesOut(
            desired_roles=payload.desired_roles,
            desired_locations=payload.desired_locations,
            remote_ok=payload.remote_ok,
            min_salary=payload.min_salary,
            experience_years=experience_years,
            skills=payload.skills,
            experience_level=level,
        )

    @router.put("/resume-meta", response_model=PreferencesOut)
    async def put_resume_meta(payload: ResumeMetaIn, user=Depends(get_current_user)):
        """Update just experience_years + skills. NO re-scrape — the user
        can refine meta without re-firing the entire browser pool."""
        async with async_session() as session:
            resume_row = (
                await session.execute(
                    select(Resume)
                    .where(Resume.user_id == user.id)
                    .order_by(Resume.created_at.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            if resume_row is None:
                resume_row = Resume(
                    user_id=user.id,
                    filename="profile-edit.txt",
                    text_content="",
                    skills=payload.skills,
                    experience_years=payload.experience_years,
                )
                session.add(resume_row)
            else:
                resume_row.experience_years = payload.experience_years
                resume_row.skills = payload.skills

            pref_row = (
                await session.execute(
                    select(UserPreference).where(UserPreference.user_id == user.id)
                )
            ).scalar_one_or_none()

            await session.commit()
            experience_years = float(resume_row.experience_years)

        return PreferencesOut(
            desired_roles=list(pref_row.desired_roles) if pref_row and pref_row.desired_roles else [],
            desired_locations=list(pref_row.desired_locations) if pref_row and pref_row.desired_locations else [],
            remote_ok=bool(pref_row.remote_ok) if pref_row else False,
            min_salary=pref_row.min_salary if pref_row else None,
            experience_years=experience_years,
            skills=list(resume_row.skills) if resume_row and resume_row.skills else [],
            experience_level=derive_level(experience_years),
        )

    return router
