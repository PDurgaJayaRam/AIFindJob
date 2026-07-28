"""Phase 4 endpoints: find contacts + draft outreach. Mounted under /me.

DRAFTS ONLY. There is intentionally no send endpoint here (guardrail).
"""
from __future__ import annotations

import json
import logging
from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from database.engine import async_session
from database.models import Job, Resume, Recruiter, User
from people_finder.finder import find_contacts
from people_finder.outreach import draft_outreach

logger = logging.getLogger("people_finder.router")


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
            job_description = job.description or ""
            job_location = job.location or ""
            job_title = job.title or ""
            job_skills = job.skills_required or []

            # Get user profile for outreach drafts
            res_row = await session.execute(
                select(Resume).where(Resume.user_id == user.id)
                .order_by(Resume.created_at.desc()).limit(1)
            )
            resume = res_row.scalar_one_or_none()

        if not company:
            raise HTTPException(status_code=400, detail="Job has no company name")

        try:
            result = await find_contacts(
                company=company,
                domain=body.domain,
                candidate_names=body.candidate_names,
                job_description=job_description,
                job_location=job_location,
                job_title=job_title,
                job_skills=job_skills,
            )
        except Exception as exc:
            logger.error("find_contacts failed for %s: %s", company, exc, exc_info=True)
            raise HTTPException(
                status_code=502,
                detail=f"Contact discovery failed for {company}: {exc}",
            )

        # Persist contacts to database so they survive page reload
        contacts = result.get("contacts", [])
        if contacts:
            try:
                async with async_session() as session:
                    # Remove old contacts for this job
                    old = await session.execute(
                        select(Recruiter).where(Recruiter.job_id == job_id)
                    )
                    for r in old.scalars().all():
                        await session.delete(r)

                    # Save new contacts with all enriched fields
                    for c in contacts:
                        recruiter = Recruiter(
                            name=c.get("name", ""),
                            role=c.get("role", ""),
                            company=company,
                            linkedin_url=c.get("linkedin_url", ""),
                            email=c.get("email", ""),
                            phone=c.get("phone", ""),
                            photo_url=c.get("photo_url", ""),
                            location=c.get("location", ""),
                            relevance=c.get("relevance", "low"),
                            skills=c.get("skills", []),
                            contact_type=c.get("contact_type", "unknown"),
                            is_recruiter=c.get("contact_type") == "recruiter",
                            is_hiring_manager=c.get("contact_type") == "hiring_manager",
                            verified=c.get("verified", False),
                            outreach_linkedin=c.get("outreach_linkedin", ""),
                            outreach_email_subject=c.get("outreach_email_subject", ""),
                            outreach_email_body=c.get("outreach_email_body", ""),
                            github="",
                            source=c.get("source", ""),
                            confidence=c.get("confidence", 0),
                            job_id=job_id,
                        )
                        session.add(recruiter)
                    await session.commit()
                    logger.info("Persisted %d contacts for job %d", len(contacts), job_id)
            except Exception as exc:
                logger.warning("Failed to persist contacts: %s", exc)

        # Add verification summary
        result["verified_count"] = sum(1 for c in contacts if c.get("verified"))
        result["unverified_count"] = sum(1 for c in contacts if not c.get("verified"))

        return result

    @router.get("/jobs/{job_id}/contacts")
    async def get_saved_contacts(job_id: int, user=Depends(get_current_user)):
        """Retrieve previously found contacts for a job (from database)."""
        async with async_session() as session:
            row = await session.execute(select(Job).where(Job.id == job_id))
            job = row.scalar_one_or_none()
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            result = await session.execute(
                select(Recruiter).where(Recruiter.job_id == job_id)
                .order_by(Recruiter.confidence.desc())
            )
            recruiters = result.scalars().all()

            contacts = []
            _GENERIC_PREFIXES = ("hr@", "careers@", "hiring@", "recruitment@", "talent@", "jobs@", "info@", "contact@", "apply@")
            _GENERIC_NAMES = {"hr department", "careers team", "hiring team", "recruitment team", "talent acquisition", "jobs portal", "company"}
            for r in recruiters:
                email_lower = (r.email or "").lower()
                name_lower = (r.name or "").lower()
                # Skip generic department emails
                if any(email_lower.startswith(p) for p in _GENERIC_PREFIXES) or name_lower in _GENERIC_NAMES:
                    continue
                is_verified = r.verified or ("verified" in (r.source or "").lower())
                skills = r.skills or []
                if isinstance(skills, str):
                    try:
                        skills = json.loads(skills)
                    except Exception:
                        skills = []
                contacts.append({
                    "name": r.name or "",
                    "email": r.email or "",
                    "phone": r.phone or "",
                    "photo_url": r.photo_url or "",
                    "location": r.location or "",
                    "relevance": r.relevance or "low",
                    "skills": skills,
                    "contact_type": r.contact_type or "unknown",
                    "is_recruiter": r.is_recruiter or False,
                    "is_hiring_manager": r.is_hiring_manager or False,
                    "verified": is_verified,
                    "outreach_linkedin": r.outreach_linkedin or "",
                    "outreach_email_subject": r.outreach_email_subject or "",
                    "outreach_email_body": r.outreach_email_body or "",
                    "confidence": r.confidence or 0,
                    "source": r.source or "saved",
                    "role": r.role or "",
                    "linkedin_url": r.linkedin_url or "",
                })

            # Sort: verified first, then relevance, then confidence
            relevance_order = {"high": 0, "medium": 1, "low": 2}
            contacts.sort(key=lambda c: (
                -c["verified"],
                relevance_order.get(c["relevance"], 3),
                -c["confidence"]
            ))

            verified_count = sum(1 for c in contacts if c["verified"])

            return {
                "company": job.company or "",
                "domain": "",
                "contacts": contacts,
                "total_found": len(contacts),
                "verified_count": verified_count,
                "sources_used": list(set(c["source"] for c in contacts)),
            }

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

    @router.get("/linkedin/status")
    async def linkedin_status(user=Depends(get_current_user)):
        """Check if a valid LinkedIn session exists."""
        from people_finder.discovery import check_linkedin_session
        status = await check_linkedin_session()
        return status

    @router.post("/linkedin/login")
    async def linkedin_login(user=Depends(get_current_user)):
        """Open a VISIBLE browser for user to log into LinkedIn."""
        try:
            from playwright.async_api import async_playwright
            import os

            pw = await async_playwright().start()
            # Launch VISIBLE browser so user can log in
            browser = await pw.chromium.launch(
                headless=False,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                viewport={'width': 1920, 'height': 1080}
            )
            page = await context.new_page()
            await page.goto("https://www.linkedin.com/login", timeout=15000)

            logger.info("[LinkedIn Login] Browser opened — please log in. Waiting up to 180 seconds...")
            try:
                await page.wait_for_url("**/feed/**", timeout=180000)
                logger.info("[LinkedIn Login] Login successful!")

                storage = await context.storage_state()
                # Sanitize cookies before saving
                from people_finder.discovery import _sanitize_cookies_for_playwright, save_linkedin_session
                storage["cookies"] = _sanitize_cookies_for_playwright(storage.get("cookies", []))
                save_linkedin_session(storage)

                await page.close()
                await context.close()
                await browser.close()
                await pw.stop()

                return {"success": True, "message": "LinkedIn login successful! Session saved."}
            except Exception:
                await page.close()
                await context.close()
                await browser.close()
                await pw.stop()
                raise HTTPException(status_code=408, detail="Login timed out. Please try again.")

        except HTTPException:
            raise
        except Exception as exc:
            logger.error("[LinkedIn Login] Failed: %s", exc)
            raise HTTPException(status_code=500, detail=f"Login failed: {exc}")

    @router.post("/linkedin/logout")
    async def linkedin_logout(user=Depends(get_current_user)):
        """Clear saved LinkedIn session."""
        from people_finder.discovery import delete_linkedin_session
        delete_linkedin_session()
        return {"success": True, "message": "LinkedIn session cleared."}

    return router
