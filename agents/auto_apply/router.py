"""Phase 5 endpoints: trigger auto-apply for a matched job.

Mounted under /me, reusing the JWT get_current_user dependency.
Each portal is an isolated plugin with clear failure boundaries.
"""
from __future__ import annotations

import asyncio
import sys
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from database.engine import async_session
from database.models import Job, Resume, ApplicationSubmission
from agents.auto_apply.auto_apply_agent import AutoApplyAgent

# Windows fix: ensure ProactorEventLoop
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())


def build_router(get_current_user: Callable) -> APIRouter:
    router = APIRouter(prefix="/me", tags=["auto-apply"])

    async def _get_resume_data(user_id: int) -> dict:
        async with async_session() as session:
            row = await session.execute(
                select(Resume).where(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = row.scalar_one_or_none()
            if not resume:
                return {}
            parsed = resume.parsed_data or {}
            return {
                "name": parsed.get("name", ""),
                "email": parsed.get("email", ""),
                "phone": parsed.get("phone", ""),
                "skills": resume.skills or [],
                "experience_years": resume.experience_years or 0,
                "location": parsed.get("location", ""),
                "linkedin_url": parsed.get("linkedin_url", ""),
                "portfolio_url": parsed.get("portfolio_url", ""),
            }

    @router.post("/jobs/{job_id}/apply")
    async def auto_apply_job(
        job_id: int,
        user=Depends(get_current_user),
    ):
        """
        Trigger auto-apply for a specific matched job.
        Uses isolated browser session per portal.
        """
        # Load job
        async with async_session() as session:
            job_row = await session.execute(select(Job).where(Job.id == job_id))
            job = job_row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            if not job.apply_url:
                raise HTTPException(status_code=400, detail="Job has no apply URL")

        # Load resume data for form filling
        resume_data = await _get_resume_data(user.id)
        if not resume_data.get("email"):
            raise HTTPException(status_code=400, detail="No resume with contact info found")

        # Create submission record
        sub = ApplicationSubmission(
            user_id=user.id,
            job_id=job_id,
            apply_url=job.apply_url,
            portal=job.source or "unknown",
            status="in_progress",
        )
        async with async_session() as session:
            session.add(sub)
            await session.commit()
            await session.refresh(sub)

        # Run auto-apply in background (never blocking)
        try:
            from agents.browser_agent.browser_controller import BrowserController
            browser = BrowserController(headless=True)
            agent = AutoApplyAgent(browser)
            
            job_data = {
                "title": job.title,
                "company": job.company or "",
                "requirements": " ".join(job.skills_required or []),
            }
            
            result = await agent.apply_to_job(
                apply_url=job.apply_url,
                resume_data=resume_data,
                job_data=job_data,
                user_review_required=False,  # Auto-mode
            )

            # Update submission record
            async with async_session() as session:
                sub.status = "submitted" if result.get("submitted") else "needs_review"
                sub.fields_filled = result.get("fields_filled", 0)
                sub.questions_answered = result.get("questions_answered", 0)
                sub.time_elapsed_ms = result.get("time_elapsed_ms", 0)
                sub.error_message = "; ".join(result.get("errors", []))[:500]
                await session.commit()

            return {
                "submission_id": sub.id,
                "status": sub.status,
                "fields_filled": result.get("fields_filled", 0),
                "completed": result.get("success", False),
            }
        except Exception as e:
            async with async_session() as session:
                sub.status = "failed"
                sub.error_message = str(e)[:500]
                await session.commit()
            raise HTTPException(status_code=500, detail=f"Auto-apply failed: {e}")
        finally:
            await browser.close()

    @router.get("/applications")
    async def list_applications(
        user=Depends(get_current_user),
        limit: int = 50,
        offset: int = 0,
    ):
        """List user's application submissions."""
        async with async_session() as session:
            from sqlalchemy import select as sa_select
            rows = await session.execute(
                sa_select(ApplicationSubmission)
                .where(ApplicationSubmission.user_id == user.id)
                .order_by(ApplicationSubmission.created_at.desc())
                .limit(limit)
                .offset(offset)
            )
            submissions = rows.scalars().all()
            
            # Include job titles
            results = []
            for s in submissions:
                job_row = await session.execute(
                    sa_select(Job).where(Job.id == s.job_id)
                )
                job = job_row.scalar_one_or_none()
                results.append({
                    "id": s.id,
                    "job_id": s.job_id,
                    "job_title": job.title if job else "Unknown",
                    "company": job.company if job else "Unknown",
                    "portal": s.portal,
                    "status": s.status,
                    "apply_url": s.apply_url,
                    "fields_filled": s.fields_filled,
                    "time_elapsed_ms": s.time_elapsed_ms,
                    "error_message": s.error_message,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                })
            return {"count": len(results), "applications": results}

    return router