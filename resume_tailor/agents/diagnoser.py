"""The Diagnoser Agent - Reads resume like an ATS system.

This agent simulates how an Applicant Tracking System parses a resume.
It flags anything that breaks parsing and provides exact fixes.
"""
from __future__ import annotations
import json
import logging
from typing import Any

logger = logging.getLogger("resume.agents.diagnoser")

DIAGNOSER_PROMPT = """You are an applicant tracking system (ATS) resume parser. Here is my resume:

{resume_text}

Read it the way an ATS does — for machine-readability, not style. Then:
1. Flag anything that breaks parsing: tables, columns, text boxes, images, icons,
   headers/footers, unusual section titles, or non-standard fonts.
2. List every section an ATS might misread or drop, and why.
3. Give me the exact fix for each one, rewritten so a parser reads it cleanly.
4. Extract all keywords, skills, and qualifications you can find.
5. Score the resume from 0-100 for ATS readability.

Target role: {job_title}
Target company: {job_company}

Return ONLY valid JSON in this exact format:
{{
    "ats_score": 0-100,
    "parsing_issues": [
        {{
            "issue": "description of the problem",
            "section": "which section is affected",
            "severity": "critical/high/medium/low",
            "fix": "exact rewritten text to fix it"
        }}
    ],
    "extracted_keywords": ["keyword1", "keyword2", ...],
    "extracted_skills": ["skill1", "skill2", ...],
    "section_analysis": {{
        "contact": "status and issues",
        "summary": "status and issues",
        "experience": "status and issues",
        "education": "status and issues",
        "skills": "status and issues",
        "projects": "status and issues"
    }},
    "rewritten_sections": {{
        "contact": "clean ATS-friendly version",
        "summary": "clean ATS-friendly version",
        "experience": "clean ATS-friendly version",
        "education": "clean ATS-friendly version",
        "skills": "clean ATS-friendly version",
        "projects": "clean ATS-friendly version"
    }},
    "overall_recommendation": "one paragraph summary of what to fix"
}}
"""


async def diagnose(
    job: dict[str, Any],
    resume_text: str,
    candidate_skills: list[str],
    ai_client
) -> dict[str, Any]:
    """Run the Diagnoser agent.
    
    Simulates how an ATS parses the resume, flags issues,
    and provides clean rewritten sections.
    """
    prompt = DIAGNOSER_PROMPT.format(
        resume_text=resume_text[:5000] if resume_text else "No resume provided",
        job_title=job.get("title", "Unknown Role"),
        job_company=job.get("company", "Unknown Company"),
    )
    
    try:
        response = await ai_client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=2500,
        )
        
        if response:
            response = _clean_json_response(response)
            diagnosis = json.loads(response)
            logger.info("Diagnoser: ATS score = %d, issues = %d",
                       diagnosis.get("ats_score", 0),
                       len(diagnosis.get("parsing_issues", [])))
            return diagnosis
    except json.JSONDecodeError as e:
        logger.warning("Diagnoser returned invalid JSON: %s", e)
    except Exception as e:
        logger.error("Diagnoser failed: %s", e)
    
    return _fallback_diagnosis(resume_text, candidate_skills)


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


def _fallback_diagnosis(resume_text: str, candidate_skills: list[str]) -> dict[str, Any]:
    """Fallback when AI fails."""
    issues = []
    if not resume_text:
        issues.append({
            "issue": "No resume text provided",
            "section": "all",
            "severity": "critical",
            "fix": "Upload a resume first"
        })
    
    text_lower = (resume_text or "").lower()
    
    ats_score = 70
    if any(c in resume_text or "" for c in ["│", "┌", "┐", "└", "┘"]):
        ats_score -= 20
        issues.append({
            "issue": "Table/border characters detected",
            "section": "formatting",
            "severity": "critical",
            "fix": "Remove all table borders and use plain text"
        })
    
    sections = ["experience", "education", "skills", "projects"]
    for section in sections:
        if section not in text_lower:
            ats_score -= 10
            issues.append({
                "issue": f"Missing {section} section",
                "section": section,
                "severity": "high",
                "fix": f"Add a clear {section.upper()} section header"
            })
    
    return {
        "ats_score": max(0, ats_score),
        "parsing_issues": issues,
        "extracted_keywords": candidate_skills[:10],
        "extracted_skills": candidate_skills[:10],
        "section_analysis": {},
        "rewritten_sections": {},
        "overall_recommendation": "Review the parsing issues and apply the suggested fixes."
    }
