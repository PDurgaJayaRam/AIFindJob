"""Lightweight, dependency-free pool scorer.

Why not reuse agents/job_matcher here?
- job_matcher loads a SentenceTransformer at import and calls the AI per job,
  which is far too heavy to run across an entire pool on every user request.
- The fast, word-boundary skill approach (mirrors the existing ATS scoring in
  job_saver) ranks the whole pool instantly with zero AI cost or model load.

The heavy job_matcher remains available for deep single-job analysis via the
existing /jobs/{id}/analyze endpoint.
"""
from __future__ import annotations

import re
from typing import Any, Iterable


def _norm(text: str) -> str:
    return (text or "").lower()


def _word_in(skill: str, text: str) -> bool:
    """Word-boundary match so 'java' does not match 'javascript'."""
    skill = skill.strip().lower()
    if not skill:
        return False
    return re.search(rf"\b{re.escape(skill)}\b", text) is not None


def score_job(
    *,
    job_text: str,
    job_skills: Iterable[str],
    user_skills: Iterable[str],
    target_roles: Iterable[str],
    is_fresher: bool,
) -> dict[str, Any]:
    """Score one pool job against a user profile. Returns score + breakdown.

    Scoring (0-100), mirroring the project's fast ATS philosophy:
      40 base
      + up to 40 for skill overlap ratio
      + up to 20 for a role keyword match
      + up to 10 fresher bonus when the posting looks fresher-friendly
    Capped at 100.
    """
    text = _norm(job_text)
    user_skills = [s for s in (user_skills or []) if s]
    job_skills = [s for s in (job_skills or []) if s]

    # Skill overlap: count user skills present in the job text or job skill tags.
    job_skill_text = text + " " + " ".join(_norm(s) for s in job_skills)
    matched = [s for s in user_skills if _word_in(s, job_skill_text)]
    missing = [s for s in job_skills if not _word_in(s, " ".join(_norm(u) for u in user_skills))]

    skill_ratio = (len(matched) / len(user_skills)) if user_skills else 0.0
    skill_component = skill_ratio * 40.0

    role_match = any(_norm(r) and _norm(r) in text for r in (target_roles or []))
    role_component = 20.0 if role_match else 0.0

    fresher_friendly = any(
        kw in text for kw in ("fresher", "entry level", "entry-level", "graduate", "junior", "0-1 year", "0-2 year")
    )
    fresher_component = 10.0 if (is_fresher and fresher_friendly) else 0.0

    score = 40.0 + skill_component + role_component + fresher_component
    score = min(round(score, 1), 100.0)

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing[:10],
        "role_match": role_match,
        "fresher_friendly": fresher_friendly,
    }


def rank_jobs(jobs: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Score and sort pool jobs. Sorts by score first, then by date (newest first)."""
    user_skills = profile.get("skills") or []
    target_roles = profile.get("target_roles") or []
    is_fresher = bool(profile.get("is_fresher", True))

    scored: list[dict[str, Any]] = []
    for job in jobs:
        job_text = " ".join(
            str(job.get(k, "")) for k in ("title", "description", "company", "location")
        )
        result = score_job(
            job_text=job_text,
            job_skills=job.get("skills_required") or [],
            user_skills=user_skills,
            target_roles=target_roles,
            is_fresher=is_fresher,
        )
        scored.append({**job, "match": result})

    scored.sort(key=lambda j: (j["match"]["score"], j.get("created_at", "")), reverse=True)
    return scored
