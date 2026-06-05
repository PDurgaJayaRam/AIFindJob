"""Outreach Agent: DRAFTS personalized messages. Never auto-sends.

Uses the async AI client when available; otherwise returns a clean template
draft. The user always reviews and sends manually (guardrail from the plan).
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("people_finder.outreach")


def template_draft(profile: dict[str, Any], job: dict[str, Any], contact_name: str = "") -> str:
    name = contact_name or "Hiring Team"
    candidate = profile.get("name") or "a motivated candidate"
    skills = ", ".join((profile.get("skills") or [])[:5]) or "relevant skills"
    title = job.get("title", "the open role")
    company = job.get("company", "your company")
    return (
        f"Hi {name},\n\n"
        f"I came across the {title} opening at {company} and wanted to reach out directly. "
        f"I'm {candidate}, with hands-on experience in {skills}. "
        f"I believe I can contribute quickly and would love a brief chance to share why.\n\n"
        f"I've attached a resume tailored to this role. Thank you for your time and consideration.\n\n"
        f"Best regards,\n{candidate}"
    )


async def draft_outreach(
    profile: dict[str, Any],
    job: dict[str, Any],
    contact_name: str = "",
    channel: str = "email",
) -> tuple[str, str]:
    """Return (draft_text, mode) where mode is 'ai' or 'template'. Never sends."""
    try:
        from ai.ai_client import get_ai_client

        limit = 280 if channel == "linkedin" else 1200
        prompt = (
            f"Write a concise, genuine {channel} outreach message (max ~{limit} chars) "
            "from a job seeker to a person at the hiring company. Personal, professional, "
            "no flattery, no spam. Mention the role and 1-2 relevant skills truthfully.\n\n"
            f"Candidate: {profile.get('name', 'Candidate')}\n"
            f"Candidate skills: {', '.join((profile.get('skills') or [])[:8])}\n"
            f"Recipient name: {contact_name or 'Hiring Manager'}\n"
            f"Job title: {job.get('title', '')}\n"
            f"Company: {job.get('company', '')}\n"
        )
        ai = get_ai_client()
        text = await ai.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,
            max_tokens=400,
        )
        if text and text.strip():
            return text.strip(), "ai"
    except Exception as exc:
        logger.info("Outreach AI unavailable, using template: %s", exc)
    return template_draft(profile, job, contact_name), "template"
