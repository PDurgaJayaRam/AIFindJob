"""The Recruiter Agent - Finds missing keywords and ranks them by importance.

This agent simulates how a senior recruiter reads a resume.
It pulls keywords from job descriptions, finds gaps, and ranks what to add.
"""
from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger("resume.agents.recruiter")

RECRUITER_PROMPT = """You are a senior recruiter hiring for this role: {job_title} at {job_company}.

Here are the job descriptions for this role:
{job_descriptions}

And here is my resume:
{resume_text}

Do three things:
1. Pull the keywords and skills that show up across these job descriptions — especially
   the ones that repeat across multiple postings.
2. Tell me which are missing or weak in my resume. Be specific about what's absent.
3. Give me the top 15 to add, ranked by how often they appeared and how much they
   matter for this role.
4. For each keyword, tell me:
   - Where in my resume it should appear
   - How to phrase it naturally (not keyword stuffing)
   - Whether I can honestly back it up or would need to learn it
5. Also analyze:
   - The tone and language used in the job postings
   - What the company values most
   - How to position my experience to match their priorities

Only list skills I can honestly back up — flag any I'd need to actually learn.

Return ONLY valid JSON in this exact format:
{{
    "repeated_keywords": [
        {{
            "keyword": "the keyword/skill",
            "frequency": "how many postings mention it",
            "importance": "critical/important/nice-to-have",
            "in_resume": true/false,
            "recommendation": "how to add it or where to emphasize it"
        }}
    ],
    "missing_keywords": [
        {{
            "keyword": "missing keyword",
            "importance": "critical/important/nice-to-have",
            "can_honestly_claim": true/false,
            "suggested_addition": "exact text to add to resume",
            "section": "where to add it"
        }}
    ],
    "positioning_analysis": {{
        "company_values": ["what they value most"],
        "tone_match": "how well resume tone matches company culture",
        "priority_skills": ["skills to emphasize most prominently"]
    }},
    "top_10_to_add": ["keyword1", "keyword2", ...],
    "rewritten_summary": "optimized professional summary with keywords woven in",
    "rewritten_skills_section": "reorganized skills section prioritized by relevance"
}}
"""


async def analyze_as_recruiter(
    job: dict[str, Any],
    resume_text: str,
    candidate_skills: list[str],
    diagnosis: dict[str, Any],
    ai_client
) -> dict[str, Any]:
    """Run the Recruiter agent.
    
    Finds missing keywords, ranks them, and provides
    specific recommendations for each.
    """
    job_skills = job.get("skills_required", [])
    job_descriptions = f"""Job Title: {job.get('title', 'Unknown')}
Company: {job.get('company', 'Unknown')}
Description: {job.get('description', 'Not available')[:3000]}
Required Skills: {', '.join(job_skills[:20]) if job_skills else 'Not specified'}
"""
    
    prompt = RECRUITER_PROMPT.format(
        job_title=job.get("title", "Unknown Role"),
        job_company=job.get("company", "Unknown Company"),
        job_descriptions=job_descriptions,
        resume_text=resume_text[:4000] if resume_text else "No resume provided",
    )
    
    try:
        response = await ai_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2500,
        )
        
        if response:
            response = _clean_json_response(response)
            analysis = json.loads(response)
            logger.info("Recruiter: Found %d repeated keywords, %d missing",
                       len(analysis.get("repeated_keywords", [])),
                       len(analysis.get("missing_keywords", [])))
            return analysis
    except json.JSONDecodeError as e:
        logger.warning("Recruiter returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("Recruiter failed: %s", e)
    
    return _fallback_recruiter(job, candidate_skills)


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


def _fallback_recruiter(job: dict[str, Any], candidate_skills: list[str]) -> dict[str, Any]:
    """Fallback when AI fails."""
    job_skills = job.get("skills_required") or []
    candidate_set = set(s.lower() for s in candidate_skills)
    
    repeated = []
    for skill in job_skills[:15]:
        repeated.append({
            "keyword": skill,
            "frequency": "mentioned in job posting",
            "importance": "critical" if skill.lower() in [s.lower() for s in job_skills[:5]] else "important",
            "in_resume": skill.lower() in candidate_set,
            "recommendation": f"Add '{skill}' to skills section and experience" if skill.lower() not in candidate_set else f"Emphasize '{skill}' more prominently"
        })
    
    missing = [
        {
            "keyword": s,
            "importance": "critical",
            "can_honestly_claim": s.lower() in candidate_set,
            "suggested_addition": f"• {s}",
            "section": "skills"
        }
        for s in job_skills[:10] if s.lower() not in candidate_set
    ]
    
    return {
        "repeated_keywords": repeated,
        "missing_keywords": missing,
        "positioning_analysis": {
            "company_values": [],
            "tone_match": "neutral",
            "priority_skills": job_skills[:5],
        },
        "top_10_to_add": [s for s in job_skills[:10] if s.lower() not in candidate_set],
        "rewritten_summary": "",
        "rewritten_skills_section": "",
    }
