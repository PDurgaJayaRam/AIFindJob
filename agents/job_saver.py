"""Job saver - saves jobs to DB with deduplication and ATS scoring."""
import os
import re
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from sqlalchemy import select, or_
from database.engine import async_session
from database.models import Job, JobStatus
from config.skills import SKILL_KEYWORDS


class JobSaver:
    """Saves jobs to database with dedup and ATS scoring."""

    @staticmethod
    def _sanitize(value: str) -> str:
        """Remove newlines and control chars that break JS template literals."""
        if not value:
            return value
        return value.replace('\n', ' ').replace('\r', '').strip()

    async def save_jobs(self, jobs: List[Dict], resume_text: str = "", user_id: str = None, is_fresher: bool = False, skills: List[str] = None) -> Dict:
        """Save jobs, skip duplicates, score with ATS."""
        new_count = 0
        dup_count = 0
        skipped_count = 0

        # Ensure tables exist
        from database.engine import engine
        from database.engine import Base
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Extract skills from resume for fast scoring
        resume_skills = skills or []
        if not resume_skills and resume_text:
            resume_lower = resume_text.lower()
            for skill in SKILL_KEYWORDS:
                if skill in resume_lower:
                    resume_skills.append(skill)

        async with async_session() as session:
            for job_data in jobs:
                source_url = job_data.get("source_url", "")
                apply_url = job_data.get("apply_url", "")
                title = job_data.get("title", "")
                company = job_data.get("company", "")

                # Filter non-fresher jobs for freshers
                if is_fresher:
                    exp_text = (job_data.get("experience_required", "") or "").lower()
                    title_lower = title.lower()
                    
                    # Reject senior/level titles
                    senior_patterns = ["senior", "lead", "principal", "staff", "director", "manager", "architect", "head", "chief",
                                       " ii", " iii", " iv", " v", " l2", " l3", " l4", " l5",
                                       "-ii", "-iii", "-iv"]
                    if any(w in title_lower for w in senior_patterns):
                        skipped_count += 1
                        continue
                    
                    # Reject spam / non-technical jobs
                    spam_patterns = ["data entry", "work from home mobile", "typing job", "part time data",
                                     "back office", "computer operator", "data entry operator"]
                    if any(w in title_lower for w in spam_patterns):
                        skipped_count += 1
                        continue
                    
                    # Check if title explicitly indicates fresher
                    is_fresher_title = any(w in title_lower for w in ["fresher", "entry level", "junior", "intern", "trainee", "associate", "apprentice", "0-1", "0-2", "sde-1", "sde 1"])
                    
                    # Parse experience range
                    exp_match = re.search(r'(\d+)\s*[-–+]\s*(\d*)', exp_text)
                    if exp_match:
                        min_exp = int(exp_match.group(1))
                        max_exp = int(exp_match.group(2)) if exp_match.group(2) else 0
                        # For freshers: reject any role requiring 2+ years min experience
                        # Also reject ranges where minimum is > 1 (e.g., "2-7 Yrs")
                        if min_exp >= 2:
                            skipped_count += 1
                            continue
                        if min_exp >= 1 and max_exp > 3:
                            skipped_count += 1
                            continue
                    elif any(w in exp_text for w in ["2+", "3+", "4+", "5+", "6+", "7+", "8+", "9+", "10+"]):
                        skipped_count += 1
                        continue

                    # Also check description for experience requirements (for fresher-titled jobs)
                    if is_fresher_title:
                        desc_lower = (job_data.get("description", "") or "").lower()
                        if desc_lower:
                            exp_in_desc = re.search(r'(\d+)\+?\s*[-–]?\s*\d*\s*(?:years?|yrs?)[\w\s]*?(?:experience|exp)', desc_lower)
                            if exp_in_desc and int(exp_in_desc.group(1)) >= 2:
                                skipped_count += 1
                                continue
                            exp_before = re.search(r'(?:experience|exp)\s*[:\-]?\s*(\d+)\+?\s*[-–]?\s*\d*\s*(?:years?|yrs?)?', desc_lower)
                            if exp_before and int(exp_before.group(1)) >= 2:
                                skipped_count += 1
                                continue

                # Dedup check by URL (use scalars().first() to handle pre-existing duplicates)
                exists = False
                if source_url:
                    result = await session.execute(
                        select(Job).where(Job.source_url == source_url).limit(1)
                    )
                    if result.scalars().first():
                        exists = True
                        dup_count += 1

                if not exists and apply_url:
                    result = await session.execute(
                        select(Job).where(Job.apply_url == apply_url).limit(1)
                    )
                    if result.scalars().first():
                        exists = True
                        dup_count += 1

                if not exists and title and company:
                    result = await session.execute(
                        select(Job).where(
                            Job.title == title,
                            Job.company == company,
                            Job.source == job_data.get("source", "")
                        ).limit(1)
                    )
                    if result.scalars().first():
                        exists = True
                        dup_count += 1

                if exists:
                    continue

                # Fast ATS score (no AI calls)
                ats_score = self._quick_score(job_data, resume_text, resume_skills)

                # Extract matched skills using word-boundary matching
                title_lower = title.lower()
                desc_lower = (job_data.get("description", "") or "").lower()
                combined = title_lower + " " + desc_lower
                matched_skills = []
                for s in resume_skills:
                    pattern = r'\b' + re.escape(s) + r'\b'
                    if re.search(pattern, combined, re.IGNORECASE):
                        matched_skills.append(s)

                # Detect fresher friendly
                fresher_friendly = any(w in title_lower + desc_lower for w in [
                    "fresher", "entry level", "junior", "0-1", "0-2", "graduate",
                    "intern", "trainee", "associate", "no experience"
                ])

                # Parse posted_date from posted_text or posted_date field
                posted_dt = None
                if job_data.get("posted_date"):
                    try:
                        posted_dt = datetime.fromisoformat(job_data["posted_date"])
                    except:
                        pass
                if not posted_dt and job_data.get("posted_text"):
                    from agents.browser_agent.autonomous_agent import _parse_posted_date
                    posted_dt = _parse_posted_date(job_data["posted_text"])

                job = Job(
                    user_id=user_id,
                    title=self._sanitize(title),
                    company=self._sanitize(company),
                    location=self._sanitize(job_data.get("location", "")),
                    salary=self._sanitize(job_data.get("salary", "")),
                    experience_required=self._sanitize(job_data.get("experience_required", "")),
                    skills_required=matched_skills if matched_skills else resume_skills[:5],
                    description=job_data.get("description", ""),
                    apply_url=apply_url,
                    source=job_data.get("source", ""),
                    source_url=source_url,
                    remote=job_data.get("remote", False),
                    walk_in=job_data.get("walk_in", False),
                    internship=job_data.get("internship", False),
                    fresher_friendly=fresher_friendly,
                    ats_score=ats_score,
                    match_score=ats_score,
                    status=JobStatus.NEW,
                    ai_analysis={
                        "ats_score": ats_score,
                        "matched_skills": matched_skills,
                        "scored_at": datetime.utcnow().isoformat()
                    },
                    posted_date=posted_dt,
                    created_at=datetime.utcnow()
                )
                session.add(job)
                await session.flush()  # Flush so within-batch dedup queries can see pending rows
                new_count += 1

            await session.commit()

        return {"new": new_count, "duplicates": dup_count, "skipped": skipped_count, "total_saved": new_count}

    async def get_all_jobs(self, limit: int = 100, offset: int = 0, status: str = None, days: int = None, sort_by: str = "newest") -> List[Dict]:
        """Get all saved jobs. Sort by 'newest' (created_at desc) or 'score' (ats_score desc)."""
        async with async_session() as session:
            if sort_by == "newest":
                query = select(Job).order_by(Job.created_at.desc())
            else:
                query = select(Job).order_by(Job.ats_score.desc())
            if status:
                query = query.where(Job.status == status)
            if days is not None:
                cutoff = datetime.utcnow() - timedelta(days=days)
                query = query.where(
                    (Job.posted_date >= cutoff) | (Job.posted_date.is_(None))
                )
            query = query.limit(limit).offset(offset)
            result = await session.execute(query)
            jobs = result.scalars().all()

            return [
                {
                    "id": j.id,
                    "title": self._sanitize(j.title),
                    "company": self._sanitize(j.company),
                    "location": self._sanitize(j.location),
                    "source": j.source,
                    "source_url": j.source_url,
                    "apply_url": j.apply_url,
                    "salary": j.salary,
                    "experience_required": j.experience_required,
                    "skills_required": j.skills_required,
                    "description": j.description,
                    "ats_score": j.ats_score,
                    "match_score": j.match_score,
                    "status": j.status,
                    "remote": j.remote,
                    "walk_in": j.walk_in,
                    "internship": j.internship,
                    "fresher_friendly": j.fresher_friendly,
                    "ai_analysis": j.ai_analysis,
                    "posted_date": j.posted_date.isoformat() if j.posted_date else "",
                    "created_at": j.created_at.isoformat() if j.created_at else ""
                }
                for j in jobs
            ]

    async def get_stats(self) -> Dict:
        """Get job stats."""
        async with async_session() as session:
            result = await session.execute(select(Job))
            all_jobs = result.scalars().all()

            total = len(all_jobs)
            sources = {}
            for j in all_jobs:
                sources[j.source] = sources.get(j.source, 0) + 1

            high_ats = sum(1 for j in all_jobs if (j.ats_score or 0) >= 70)
            medium_ats = sum(1 for j in all_jobs if 40 <= (j.ats_score or 0) < 70)
            low_ats = sum(1 for j in all_jobs if (j.ats_score or 0) < 40)

            return {
                "total": total,
                "by_source": sources,
                "high_ats": high_ats,
                "medium_ats": medium_ats,
                "low_ats": low_ats,
                "avg_ats": round(sum(j.ats_score or 0 for j in all_jobs) / max(total, 1), 1)
            }

    def _quick_score(self, job: Dict, resume_text: str, resume_skills: List[str] = None) -> float:
        """Fast keyword-based ATS score."""
        score = 40.0
        title_lower = (job.get("title", "") or "").lower()
        desc_lower = (job.get("description", "") or "").lower()
        combined = title_lower + " " + desc_lower

        # Use pre-analyzed skills or fallback to extracting from resume text
        skills_set = set(s.lower() for s in (resume_skills or []))
        if not skills_set and resume_text:
            resume_lower = resume_text.lower()
            for skill in SKILL_KEYWORDS:
                if skill in resume_lower:
                    skills_set.add(skill)

        # Score based on word-boundary matching
        matched = 0
        for skill in skills_set:
            pattern = r'\b' + re.escape(skill) + r'\b'
            if re.search(pattern, combined, re.IGNORECASE):
                matched += 1

        if skills_set:
            score += (matched / len(skills_set)) * 40

        # Fresher bonus for fresher jobs
        if any(w in title_lower for w in ["fresher", "junior", "entry", "intern", "trainee"]):
            score += 10

        return min(round(score, 1), 100.0)
