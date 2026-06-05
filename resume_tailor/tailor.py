"""Build an ATS-friendly resume tailored to a single job.

Design:
- AI path (preferred): uses the async ai.ai_client.get_ai_client() to rewrite a
  punchy professional summary and keyword-optimized skills/experience.
- Fallback path (no key / AI failure): a deterministic, ATS-clean text resume
  built from the user's stored profile + the job's keywords. Always works.

Keeping this async avoids blocking the FastAPI event loop (the legacy
agents/resume_generator is sync and is left untouched).
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("resume_tailor")


def _job_keywords(job: dict[str, Any], limit: int = 20) -> list[str]:
    """Extract candidate ATS keywords from a job's text + skill tags."""
    tags = job.get("skills_required") or []
    text = " ".join(str(job.get(k, "")) for k in ("title", "description"))
    # Simple token harvest: alphanumeric words of length >= 3, plus explicit tags.
    words = re.findall(r"[A-Za-z][A-Za-z0-9+.#-]{2,}", text)
    seen: list[str] = []
    for token in [*[str(t) for t in tags], *words]:
        t = token.strip()
        low = t.lower()
        if low and low not in {s.lower() for s in seen}:
            seen.append(t)
        if len(seen) >= limit:
            break
    return seen


def build_fallback_resume(profile: dict[str, Any], job: dict[str, Any]) -> str:
    """Deterministic ATS-friendly plain-text resume. No AI required."""
    name = profile.get("name") or "Candidate"
    skills = profile.get("skills") or []
    target = job.get("title", "the role")
    company = job.get("company", "the company")

    # Prioritise skills that appear in the job, then the rest.
    job_kw = {k.lower() for k in _job_keywords(job)}
    matched = [s for s in skills if s.lower() in job_kw]
    others = [s for s in skills if s.lower() not in job_kw]
    ordered_skills = matched + others

    summary = (
        f"Motivated candidate targeting the {target} position at {company}. "
        f"Hands-on with {', '.join(ordered_skills[:6]) or 'relevant technologies'}, "
        f"focused on delivering measurable results and continuous learning."
    )

    lines = [
        name,
        profile.get("email", ""),
        "",
        "PROFESSIONAL SUMMARY",
        summary,
        "",
        "TECHNICAL SKILLS",
        ", ".join(ordered_skills[:18]) or "See experience",
        "",
        "EXPERIENCE",
        (profile.get("experience_text") or "Relevant projects and internships demonstrating the skills above."),
        "",
        "EDUCATION",
        profile.get("education", "") or "As per attached transcript.",
    ]
    return "\n".join(line for line in lines if line is not None)


async def build_ai_resume(profile: dict[str, Any], job: dict[str, Any]) -> str:
    """AI-tailored resume text. Raises on failure so caller can fall back."""
    from ai.ai_client import get_ai_client

    keywords = _job_keywords(job)
    skills = profile.get("skills") or []
    prompt = (
        "Write an ATS-friendly, plain-text resume tailored to the target job. "
        "Use clear section headers (PROFESSIONAL SUMMARY, TECHNICAL SKILLS, "
        "EXPERIENCE, EDUCATION). Naturally include the job's keywords where "
        "truthful. Do not invent employers or dates. Keep it concise.\n\n"
        f"CANDIDATE NAME: {profile.get('name', 'Candidate')}\n"
        f"CANDIDATE SKILLS: {', '.join(skills[:20])}\n"
        f"EXPERIENCE NOTES: {(profile.get('experience_text') or '')[:1200]}\n"
        f"EDUCATION: {profile.get('education', '')}\n\n"
        f"TARGET JOB TITLE: {job.get('title', '')}\n"
        f"TARGET COMPANY: {job.get('company', '')}\n"
        f"JOB DESCRIPTION: {(job.get('description') or '')[:1500]}\n"
        f"ATS KEYWORDS TO COVER: {', '.join(keywords)}\n"
    )
    ai = get_ai_client()
    text = await ai.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=900,
    )
    if not text or not text.strip():
        raise RuntimeError("AI returned empty resume")
    return text.strip()


async def tailor_resume(profile: dict[str, Any], job: dict[str, Any]) -> tuple[str, str]:
    """Return (resume_text, mode) where mode is 'ai' or 'fallback'."""
    try:
        text = await build_ai_resume(profile, job)
        return text, "ai"
    except Exception as exc:
        logger.info("Resume AI path unavailable, using fallback: %s", exc)
        return build_fallback_resume(profile, job), "fallback"


def write_docx(resume_text: str, path: str) -> None:
    """Render plain resume text into a simple ATS-clean DOCX at `path`."""
    from docx import Document
    from docx.shared import Pt

    doc = Document()
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(11)

    known_headers = {
        "PROFESSIONAL SUMMARY", "TECHNICAL SKILLS", "SKILLS",
        "EXPERIENCE", "PROFESSIONAL EXPERIENCE", "EDUCATION",
    }
    for raw in resume_text.split("\n"):
        line = raw.rstrip()
        if not line:
            doc.add_paragraph("")
            continue
        if line.strip().upper() in known_headers:
            p = doc.add_paragraph()
            run = p.add_run(line.strip().upper())
            run.bold = True
            run.font.size = Pt(12)
        else:
            doc.add_paragraph(line)
    doc.save(path)
