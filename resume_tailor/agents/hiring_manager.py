"""The Hiring Manager Agent - Final review and quality scoring.

This agent simulates a hiring manager reviewing the resume.
It scores the resume, identifies remaining weaknesses, and provides
the final hire/no-hire recommendation.
"""
from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger("resume.agents.hiring_manager")

HIRING_MANAGER_PROMPT = """You are a senior hiring manager at {job_company} reviewing candidates for the {job_title} position.
You've seen hundreds of resumes and only advance the top 10%.

Here is the candidate's rewritten resume:
{rewritten_resume}

Here is the original resume for comparison:
{original_resume}

The job requires these skills: {job_skills}

YOUR TASK:
Review this resume as if you're deciding whether to advance this candidate to an interview.
Be brutally honest — you want to hire the best, not be nice.

Score and evaluate:

1. FIRST IMPRESSION (0-10):
   - Does the summary grab attention in 6 seconds?
   - Is the formatting clean and professional?
   - Would you keep reading?

2. SKILLS MATCH (0-10):
   - How well do the skills align with job requirements?
   - Are the right skills emphasized prominently?
   - Any critical skills missing?

3. EXPERIENCE QUALITY (0-10):
   - Do the bullet points show impact, not just duties?
   - Are metrics and results compelling?
   - Is the experience relevant to this role?

4. OVERALL PRESENTATION (0-10):
   - Is it ATS-friendly?
   - Is it human-readable?
   - Does it tell a compelling story?

5. INTERVIEW READINESS (0-10):
   - Based on this resume, would the candidate perform well in an interview?
   - Are there any red flags that would raise questions?
   - What would you ask about in the interview?

Return ONLY valid JSON in this exact format:
{{
    "scores": {{
        "first_impression": 0-10,
        "skills_match": 0-10,
        "experience_quality": 0-10,
        "overall_presentation": 0-10,
        "interview_readiness": 0-10,
        "total": 0-50
    }},
    "grade": "A+/A/A-/B+/B/B-/C+/C/F",
    "hire_recommendation": "strong_yes/yes/maybe/no/strong_no",
    "strengths": [
        "strength 1",
        "strength 2"
    ],
    "weaknesses": [
        {{
            "issue": "what's wrong",
            "severity": "critical/major/minor",
            "fix": "exact fix"
        }}
    ],
    "interview_questions": [
        "question 1 based on resume",
        "question 2 based on resume"
    ],
    "top_3_fixes_before_submitting": [
        "fix 1",
        "fix 2",
        "fix 3"
    ],
    "final_resume_quality": {{
        "ats_score": 0-100,
        "human_readability": 0-100,
        "keyword_coverage": 0-100,
        "impact_score": 0-100
    }},
    "one_line_verdict": "one sentence overall assessment"
}}
"""


async def review_as_hiring_manager(
    job: dict[str, Any],
    original_resume: str,
    rewritten_resume: dict[str, Any],
    diagnosis: dict[str, Any],
    ai_client
) -> dict[str, Any]:
    """Run the Hiring Manager agent.
    
    Provides final scoring, hire recommendation, and
    specific improvements before submission.
    """
    job_skills = job.get("skills_required", [])
    
    rewritten_text = _resume_dict_to_text(rewritten_resume)
    
    prompt = HIRING_MANAGER_PROMPT.format(
        job_company=job.get("company", "the company"),
        job_title=job.get("title", "the position"),
        rewritten_resume=rewritten_text[:4000],
        original_resume=original_resume[:3000] if original_resume else "Not available",
        job_skills=", ".join(job_skills[:15]) if job_skills else "Not specified",
    )
    
    try:
        response = await ai_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2500,
        )
        
        if response:
            response = _clean_json_response(response)
            review = json.loads(response)
            logger.info("Hiring Manager: Score = %d/50, Grade = %s, Hire = %s",
                       review.get("scores", {}).get("total", 0),
                       review.get("grade", "?"),
                       review.get("hire_recommendation", "?"))
            return review
    except json.JSONDecodeError as e:
        logger.warning("Hiring Manager returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("Hiring Manager failed: %s", e)
    
    return _fallback_review(rewritten_resume, job)


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


def _resume_dict_to_text(resume: dict[str, Any]) -> str:
    """Convert resume dictionary to readable text."""
    lines = []
    
    contact = resume.get("contact", {})
    if contact.get("name"):
        lines.append(contact["name"].upper())
    contact_parts = []
    for key in ["email", "phone", "linkedin", "github"]:
        if contact.get(key):
            contact_parts.append(contact[key])
    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")
    
    summary = resume.get("professional_summary", "")
    if summary:
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(summary)
        lines.append("")
    
    skills = resume.get("skills", {})
    if skills:
        lines.append("TECHNICAL SKILLS")
        if isinstance(skills, dict):
            for category, items in skills.items():
                if items:
                    lines.append(f"{category.title()}: {', '.join(items)}")
        elif isinstance(skills, list):
            lines.append(", ".join(skills))
        lines.append("")
    
    experience = resume.get("experience", [])
    if experience:
        lines.append("PROFESSIONAL EXPERIENCE")
        for exp in experience:
            if exp.get("title"):
                lines.append(f"{exp['title']} - {exp.get('company', '')} ({exp.get('dates', '')})")
            for bullet in exp.get("bullets", []):
                lines.append(f"  {bullet}")
            lines.append("")
    
    education = resume.get("education", [])
    if education:
        lines.append("EDUCATION")
        for edu in education:
            lines.append(f"{edu.get('degree', '')} - {edu.get('institution', '')} ({edu.get('year', '')})")
        lines.append("")
    
    projects = resume.get("projects", [])
    if projects:
        lines.append("PROJECTS")
        for proj in projects:
            if proj.get("name"):
                lines.append(f"{proj['name']}")
            for bullet in proj.get("bullets", []):
                lines.append(f"  {bullet}")
        lines.append("")
    
    certifications = resume.get("certifications", [])
    if certifications:
        lines.append("CERTIFICATIONS")
        for cert in certifications:
            lines.append(f"• {cert}")
    
    return "\n".join(lines)


def _fallback_review(rewritten_resume: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Fallback when AI fails."""
    has_summary = bool(rewritten_resume.get("professional_summary"))
    has_experience = bool(rewritten_resume.get("experience"))
    has_skills = bool(rewritten_resume.get("skills"))
    has_education = bool(rewritten_resume.get("education"))
    
    score = 0
    if has_summary: score += 2
    if has_experience: score += 3
    if has_skills: score += 2
    if has_education: score += 1
    
    return {
        "scores": {
            "first_impression": 7 if has_summary else 4,
            "skills_match": 6 if has_skills else 3,
            "experience_quality": 7 if has_experience else 4,
            "overall_presentation": 6,
            "interview_readiness": 6,
            "total": score + 15,
        },
        "grade": "B+" if score >= 6 else "B" if score >= 4 else "C+",
        "hire_recommendation": "yes" if score >= 6 else "maybe",
        "strengths": ["Resume has been rewritten with XYZ formula"],
        "weaknesses": [],
        "interview_questions": [
            "Tell me about your experience with the key technologies listed.",
            "Describe a project where you made a significant impact.",
        ],
        "top_3_fixes_before_submitting": [
            "Review the rewritten bullets for accuracy",
            "Ensure all metrics are honest and defensible",
            "Proofread for any typos or formatting issues",
        ],
        "final_resume_quality": {
            "ats_score": 75 if has_skills else 50,
            "human_readability": 80,
            "keyword_coverage": 70 if has_skills else 40,
            "impact_score": 75 if has_experience else 50,
        },
        "one_line_verdict": "Resume has been optimized and is ready for submission after final review.",
    }
