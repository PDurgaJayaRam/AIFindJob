"""Phase 3 endpoints: generate + download a tailored resume for a pool job.

Mounted under /me, reusing the JWT get_current_user dependency.
"""
from __future__ import annotations

import os
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select

from database.engine import async_session
from database.models import Resume, Job, CustomResume
from resume_tailor.tailor import tailor_resume, write_docx

_OUTPUT_DIR = os.path.join("data", "generated_resumes")


def build_router(get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/me", tags=["resume-tailor"])

    async def _load_profile(user_id: int) -> dict | None:
        async with async_session() as session:
            row = await session.execute(
                select(Resume).where(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = row.scalar_one_or_none()
            if not resume:
                return None
            parsed = resume.parsed_data or {}
            return {
                "name": parsed.get("name") or (resume.filename or "Candidate").rsplit(".", 1)[0],
                "email": parsed.get("email", ""),
                "skills": resume.skills or [],
                "experience_text": resume.text_content or "",
                "education": parsed.get("education", ""),
                "resume_id": resume.id,
            }

    @router.post("/jobs/{job_id}/resume")
    async def generate_resume(job_id: int, user=Depends(get_current_user)):
        """Generate an ATS resume tailored to a pool job for the current user."""
        profile = await _load_profile(user.id)
        if not profile:
            raise HTTPException(status_code=404, detail="No resume found. POST /me/resume first.")

        async with async_session() as session:
            job_row = await session.execute(select(Job).where(Job.id == job_id))
            job = job_row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            job_data = {
                "title": job.title,
                "company": job.company,
                "description": job.description or "",
                "skills_required": job.skills_required or [],
            }

        resume_text, mode = await tailor_resume(profile, job_data)

        os.makedirs(_OUTPUT_DIR, exist_ok=True)
        filename = f"resume_user{user.id}_job{job_id}.docx"
        path = os.path.join(_OUTPUT_DIR, filename)
        write_docx(resume_text, path)

        async with async_session() as session:
            cr = CustomResume(
                job_id=job_id,
                user_id=user.id,
                resume_text=resume_text,
                resume_docx_path=path,
                ats_optimized=True,
            )
            session.add(cr)
            await session.commit()
            await session.refresh(cr)

        return {
            "custom_resume_id": cr.id,
            "mode": mode,  # 'ai' or 'fallback'
            "preview": resume_text[:600],
            "download_url": f"/me/resume/{cr.id}/download",
        }

    @router.get("/resume/{custom_resume_id}/download")
    async def download_resume(custom_resume_id: int, user=Depends(get_current_user)):
        """Download a previously generated tailored resume (owner only)."""
        async with async_session() as session:
            row = await session.execute(
                select(CustomResume).where(CustomResume.id == custom_resume_id)
            )
            cr = row.scalar_one_or_none()
            if not cr or cr.user_id != user.id:
                raise HTTPException(status_code=404, detail="Resume not found")
            if not cr.resume_docx_path or not os.path.exists(cr.resume_docx_path):
                raise HTTPException(status_code=404, detail="Resume file missing on disk")
            return FileResponse(
                cr.resume_docx_path,
                media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                filename=f"tailored_resume_{cr.job_id}.docx",
            )

    return router
