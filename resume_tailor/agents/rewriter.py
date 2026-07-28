"""The Rewriter Agent - Rebuilds every bullet using Google's XYZ formula.

This agent takes the diagnosed gaps and recruiter findings, then rewrites
the entire resume using the XYZ formula:
"Accomplished [X], as measured by [Y], by doing [Z]."
"""
from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger("resume.agents.rewriter")

REWRITER_PROMPT = """You are an expert resume writer who helps candidates present their REAL experience clearly and professionally.

CANDIDATE'S ORIGINAL RESUME:
{resume_text}

CANDIDATE'S SKILLS:
{candidate_skills}

CANDIDATE'S EXPERIENCE LEVEL: {experience_level}
WHY: {experience_reasons}

DIAGNOSIS FROM ATS ANALYSIS:
{diagnosis}

RECRUITER FINDINGS (keywords to add):
{recruiter_findings}

TARGET JOB: {job_title} at {job_company}
JOB DESCRIPTION KEYWORDS: {job_keywords}

YOUR TASK:
Rewrite the resume to be ATS-optimized while preserving the candidate's ACTUAL experience.

CRITICAL RULES — VIOLATION IS UNACCEPTABLE:
1. PRESERVE THE CANDIDATE'S ACTUAL EXPERIENCE LEVEL:
   - If experience_level is "fresher": This person has NEVER held a full-time job.
     They may have done internships. They are NOT a Senior Developer, Lead, or Architect.
     DO NOT create fake job titles, fake companies, or fake employment periods.
     If their resume says "Intern at XYZ", keep it as "Intern at XYZ" — do NOT promote it.
   - If experience_level is "junior": 1-2 years max. Titles must be junior-level.
   - If experience_level is "mid": 3-5 years. Titles can be mid-level.
   - If experience_level is "senior": 5+ years. Titles can be senior.
2. USE THE CANDIDATE'S REAL EXPERIENCE from the original resume.
   - You may IMPROVE wording (better action verbs, clearer descriptions).
   - You may ADD relevant keywords from the job description NATURALLY.
   - You MUST NOT invent new job titles, companies, or employment periods.
3. NEVER FABRICATE METRICS. This is the most important rule.
   - DO NOT invent percentages (e.g., "30% increase", "25% improvement").
   - DO NOT invent numbers (e.g., "reduced errors by 40%", "saved 20 hours").
   - If the original resume has NO metrics, keep it without metrics.
   - Use factual descriptions only: what was built, what was done, what tools were used.
4. PROFESSIONAL SUMMARY must be GENERIC — do NOT mention specific company names.
   - CORRECT: "Motivated Fresher with skills in Java, SQL, and Appian"
   - WRONG: "Seeking SQL Developer role at Gravitix Tech" — NEVER include the target company name.
5. PRESERVE ALL SECTIONS from the original resume: Experience, Education, Projects, Certifications, Awards, Activities.
   - Do NOT duplicate sections (e.g., do not list projects under both "Academic Projects" and "Projects").
   - Do NOT remove sections that exist in the original.
6. Skills should be a SINGLE comma-separated line: "Technical: Java, HTML, CSS, SQL, Appian, Python"
   - Do NOT split into categories like "Programming:", "Frontend:", "Backend:".
7. Work the missing keywords in NATURALLY — no keyword stuffing
8. Use strong action verbs: Designed, Built, Implemented, Developed, Configured, Automated
9. Kill all vague filler: "responsible for", "assisted with", "helped with", "worked on"

OUTPUT FORMAT:
Return ONLY valid JSON with this structure:
{{
    "contact": {{
        "name": "...",
        "email": "...",
        "phone": "...",
        "linkedin": "...",
        "github": "..."
    }},
    "professional_summary": "2-3 sentence GENERIC summary — do NOT mention any company name",
    "skills": "Technical: skill1, skill2, skill3, ...",
    "experience": [
        {{
            "title": "JOB TITLE",
            "company": "COMPANY NAME",
            "dates": "Start - End",
            "bullets": [
                "• Description of what was done (NO fabricated metrics)",
                "• ..."
            ]
        }}
    ],
    "education": [
        {{
            "degree": "Degree Name",
            "institution": "University/College",
            "year": "20XX",
            "details": "CGPA, honors, relevant coursework"
        }}
    ],
    "projects": [
        {{
            "name": "Project Name",
            "bullets": [
                "• Description of what was built (NO fabricated metrics)"
            ]
        }}
    ],
    "certifications": [
        "Certification 1",
        "Certification 2"
    ],
    "ats_keywords_added": ["keyword1", "keyword2"],
    "changes_made": ["change 1", "change 2"]
}}

Write the COMPLETE resume with ALL sections from the original. Make it ready to submit.
"""


async def rewrite_resume(
    job: dict[str, Any],
    resume_text: str,
    candidate_skills: list[str],
    diagnosis: dict[str, Any],
    recruiter_findings: dict[str, Any],
    ai_client,
    experience_level: str = "fresher",
    experience_reasons: list[str] = None,
) -> dict[str, Any]:
    """Run the Rewriter agent.
    
    Transforms the resume using Google's XYZ formula and
    incorporates all recommended keywords naturally.
    """
    top_keywords = recruiter_findings.get("top_10_to_add", [])
    missing_keywords = [m.get("keyword", "") for m in recruiter_findings.get("missing_keywords", [])]
    all_keywords = list(set(top_keywords + missing_keywords))
    
    prompt = REWRITER_PROMPT.format(
        resume_text=resume_text[:5000] if resume_text else "No resume provided",
        candidate_skills=", ".join(candidate_skills[:30]) if candidate_skills else "Not specified",
        experience_level=experience_level,
        experience_reasons="; ".join(experience_reasons[:5]) if experience_reasons else "AI analyzed resume content",
        diagnosis=json.dumps(diagnosis, indent=2)[:2000] if diagnosis else "No diagnosis",
        recruiter_findings=json.dumps(recruiter_findings, indent=2)[:2000] if recruiter_findings else "No findings",
        job_title=job.get("title", "Unknown Role"),
        job_company=job.get("company", "Unknown Company"),
        job_keywords=", ".join(all_keywords[:20]) if all_keywords else "Not specified",
    )
    
    try:
        response = await ai_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.4,
            max_tokens=3000,
        )
        
        if response:
            response = _clean_json_response(response)
            rewritten = json.loads(response)
            logger.info("Rewriter: Generated %d experience bullets, %d keywords added",
                       sum(len(e.get("bullets", [])) for e in rewritten.get("experience", [])),
                       len(rewritten.get("ats_keywords_added", [])))
            return rewritten
    except json.JSONDecodeError as e:
        logger.warning("Rewriter returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("Rewriter failed: %s", e)
    
    return _fallback_rewrite(resume_text, candidate_skills, job)


def _clean_json_response(text: str) -> str:
    """Clean AI response to extract valid JSON."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    return text


def _fallback_rewrite(resume_text: str, candidate_skills: list[str], job: dict[str, Any]) -> dict[str, Any]:
    """Fallback when AI fails - returns original with minimal changes."""
    return {
        "contact": {},
        "professional_summary": f"Motivated {job.get('title', 'professional')} with skills in {', '.join(candidate_skills[:5])}.",
        "skills": {"technical": candidate_skills[:15]},
        "experience": [],
        "education": [],
        "projects": [],
        "certifications": [],
        "ats_keywords_added": [],
        "changes_made": ["Fallback mode - original resume preserved"],
    }
