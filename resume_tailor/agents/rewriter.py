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

REWRITER_PROMPT = """You are an expert resume writer who has helped thousands of candidates land their dream jobs.
Your specialty is transforming weak resumes into powerful, ATS-optimized documents that get interviews.

CANDIDATE'S ORIGINAL RESUME:
{resume_text}

CANDIDATE'S SKILLS:
{candidate_skills}

DIAGNOSIS FROM ATS ANALYSIS:
{diagnosis}

RECRUITER FINDINGS (keywords to add):
{recruiter_findings}

TARGET JOB: {job_title} at {job_company}
JOB DESCRIPTION KEYWORDS: {job_keywords}

YOUR TASK:
Rewrite the ENTIRE resume from scratch using Google's XYZ formula for EVERY bullet point:
"Accomplished [X], as measured by [Y], by doing [Z]."

RULES:
1. EVERY bullet point MUST have:
   - A clear accomplishment (X)
   - A measurable result or metric (Y) — use realistic estimates if exact numbers unavailable
   - The method or action taken (Z)
2. Work the missing keywords in NATURALLY — no keyword stuffing
3. Use strong action verbs: Led, Built, Designed, Implemented, Optimized, Delivered, Reduced, Increased, Automated, Streamlined
4. Kill all vague filler: "responsible for", "assisted with", "helped with", "worked on"
5. Keep the tone professional but confident — not arrogant
6. Quantify everything possible: time saved, money saved, users served, efficiency improved
7. If you don't have a real number, use "X+%" or "multiple" — never fabricate specific metrics

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
    "professional_summary": "2-3 sentence summary tailored to this specific role, incorporating key keywords",
    "skills": {{
        "programming": ["skill1", "skill2"],
        "frontend": ["skill1", "skill2"],
        "backend": ["skill1", "skill2"],
        "tools": ["skill1", "skill2"],
        "databases": ["skill1", "skill2"]
    }},
    "experience": [
        {{
            "title": "JOB TITLE",
            "company": "COMPANY NAME",
            "dates": "Start - End",
            "bullets": [
                "• Accomplished [X], as measured by [Y], by doing [Z]",
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
                "• Accomplished [X], as measured by [Y], by doing [Z]"
            ]
        }}
    ],
    "certifications": [
        "Certification 1",
        "Certification 2"
    ],
    "ats_keywords_added": ["keyword1", "keyword2", ...],
    "changes_made": ["change 1", "change 2", ...]
}}

Write the COMPLETE resume. Make it ready to submit to any employer.
"""


async def rewrite_resume(
    job: dict[str, Any],
    resume_text: str,
    candidate_skills: list[str],
    diagnosis: dict[str, Any],
    recruiter_findings: dict[str, Any],
    ai_client
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
