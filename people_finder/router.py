"""Phase 4 endpoints: find contacts + draft outreach. Mounted under /me.

DRAFTS ONLY. There is intentionally no send endpoint here (guardrail).
"""
from __future__ import annotations

from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from database.engine import async_session
from database.models import Job, Resume
from people_finder.finder import find_contacts
from people_finder.outreach import draft_outreach


class ContactsIn(BaseModel):
    domain: str = ""
    candidate_names: list[str] = []


class DraftIn(BaseModel):
    job_id: int
    contact_name: str = ""
    channel: str = "email"  # 'email' or 'linkedin'


def build_router(get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/me", tags=["people-finder"])

    @router.post("/jobs/{job_id}/contacts")
    async def job_contacts(job_id: int, body: ContactsIn, user=Depends(get_current_user)):
        """Find public contacts at the hiring company for a pool job."""
        async with async_session() as session:
            row = await session.execute(select(Job).where(Job.id == job_id))
            job = row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            company = job.company or ""
        if not company:
            raise HTTPException(status_code=400, detail="Job has no company name")
        return await find_contacts(
            company=company, domain=body.domain, candidate_names=body.candidate_names
        )

    @router.post("/contacts/draft")
    async def contacts_draft(body: DraftIn, user=Depends(get_current_user)):
        """Draft (NOT send) a personalized outreach message for a job."""
        async with async_session() as session:
            job_row = await session.execute(select(Job).where(Job.id == body.job_id))
            job = job_row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            res_row = await session.execute(
                select(Resume).where(Resume.user_id == user.id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = res_row.scalar_one_or_none()
            parsed = (resume.parsed_data or {}) if resume else {}
            profile = {
                "name": parsed.get("name") or "Candidate",
                "skills": (resume.skills if resume else []) or [],
            }
            job_data = {"title": job.title, "company": job.company}

        draft, mode = await draft_outreach(
            profile, job_data, contact_name=body.contact_name, channel=body.channel
        )
        return {
            "draft": draft,
            "mode": mode,
            "channel": body.channel,
            "reminder": "Review and send this yourself. The platform does not auto-send.",
        }

    return router
