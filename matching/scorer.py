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


def _extract_experience_years(text: str) -> float | None:
    """Extract the minimum years of experience required from job text.

    Returns the lowest number found in patterns like "3+ years", "5 to 8 years",
    "experience: 4", etc. Returns None if no experience requirement is detected.
    """
    patterns = [
        r"(\d+)\+?\s*(?:to|-)\s*\d+\s*years?",  # "3 to 5 years"
        r"(\d+)\+?\s*years?\s*(?:of\s*)?(?:experience|exp)",  # "3+ years experience"
        r"experience:\s*(\d+)",  # "experience: 3"
        r"(\d+)\s*years?\s*(?:of\s*)?(?:relevant|professional|work)",  # "3 years relevant"
    ]
    matches = []
    for pat in patterns:
        for m in re.finditer(pat, text):
            try:
                matches.append(int(m.group(1)))
            except (ValueError, IndexError):
                pass
    return min(matches) if matches else None


def score_job(
    *,
    job_text: str,
    job_skills: Iterable[str],
    user_skills: Iterable[str],
    target_roles: Iterable[str],
    is_fresher: bool,
    user_experience_years: float = 0.0,
) -> dict[str, Any]:
    """Score one pool job against a user profile. Returns score + breakdown.

    Scoring (0-100):
      10 base (minimal — only meaningful matches score higher)
      + up to 50 for skill overlap ratio
      + up to 30 for a role keyword match (title or description)
      + up to 10 fresher bonus when the posting looks fresher-friendly
      - up to 40 penalty when job requires more experience than user has
    Capped at 100.  Irrelevant jobs land at 10-15%.
    """
    text = _norm(job_text)
    user_skills = [s for s in (user_skills or []) if s]
    job_skills = [s for s in (job_skills or []) if s]

    # Skill overlap: count user skills present in the job text or job skill tags.
    job_skill_text = text + " " + " ".join(_norm(s) for s in job_skills)
    matched = [s for s in user_skills if _word_in(s, job_skill_text)]
    missing = [s for s in job_skills if not _word_in(s, " ".join(_norm(u) for u in user_skills))]

    skill_ratio = (len(matched) / len(user_skills)) if user_skills else 0.0
    skill_component = skill_ratio * 50.0

    # Role match: check if any target role keyword appears in job title or description.
    role_match = False
    for r in (target_roles or []):
        role_norm = _norm(r)
        if not role_norm:
            continue
        if role_norm in text:
            role_match = True
            break
        role_words = role_norm.split()
        if len(role_words) >= 2 and all(_word_in(w, text) for w in role_words):
            role_match = True
            break
        for word in role_norm.split():
            if len(word) >= 4:
                if re.search(rf"\b{re.escape(word)}\w*\b", text):
                    role_match = True
                    break
        if role_match:
            break

    role_component = 30.0 if role_match else 0.0

    fresher_friendly = any(
        kw in text for kw in ("fresher", "entry level", "entry-level", "graduate", "junior", "0-1 year", "0-2 year")
    )
    fresher_component = 10.0 if (is_fresher and fresher_friendly) else 0.0

    score = 10.0 + skill_component + role_component + fresher_component

    # Experience penalty: penalize jobs that require more experience than the user has.
    senior_keywords = [
        "senior", "sr.", "lead", "principal", "staff", "architect",
        "director", "vp", "head of", "chief", "10+ years", "12+ years",
        "15+ years", "8+ years", "7+ years", "6+ years",
    ]
    is_senior = any(kw in text for kw in senior_keywords)
    required_years = _extract_experience_years(text)

    experience_penalty = 0.0
    if is_fresher:
        if is_senior:
            experience_penalty = 40.0
        elif required_years is not None and required_years > 2:
            experience_penalty = min(30.0, required_years * 5.0)

    score = max(score - experience_penalty, 0.0)

    # Relevance gate: if no skill match AND no role match, cap low.
    if not matched and not role_match:
        score = min(score, 15.0)

    score = min(round(score, 1), 100.0)

    return {
        "score": score,
        "matched_skills": matched,
        "missing_skills": missing[:10],
        "role_match": role_match,
        "fresher_friendly": fresher_friendly,
        "experience_penalty": experience_penalty > 0,
    }


def rank_jobs(jobs: list[dict[str, Any]], profile: dict[str, Any]) -> list[dict[str, Any]]:
    """Score and sort pool jobs. Sorts by score first, then by date (newest first)."""
    user_skills = profile.get("skills") or []
    target_roles = profile.get("target_roles") or []
    is_fresher = bool(profile.get("is_fresher", True))
    user_experience_years = float(profile.get("experience_years", 0.0))

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
            user_experience_years=user_experience_years,
        )
        scored.append({**job, "match": result})

    scored.sort(key=lambda j: (j["match"]["score"], j.get("created_at", "")), reverse=True)
    return scored
