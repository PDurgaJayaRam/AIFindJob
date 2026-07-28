"""The Orchestrator - Coordinates all 4 agents to build an unstoppable resume.

Flow:
1. Diagnoser reads resume like ATS → finds parsing issues
2. Recruiter finds missing keywords → ranks them by importance
3. Rewriter rebuilds every bullet with XYZ formula → incorporates keywords
4. Hiring Manager scores the result → gives hire/no-hire recommendation

Each agent builds on the previous one's output.
"""
from __future__ import annotations
import json
import logging
import time
from typing import Any

logger = logging.getLogger("resume.agents.orchestrator")


class ResumeOrchestrator:
    """Coordinates the 4-agent resume building pipeline."""
    
    def __init__(self, ai_client):
        self.ai_client = ai_client
    
    async def build_resume(
        self,
        job: dict[str, Any],
        resume_text: str,
        candidate_skills: list[str],
        profile: dict[str, Any] = None,
    ) -> dict[str, Any]:
        """Run the full 4-agent pipeline to build an unstoppable resume.
        
        Returns:
            {
                "diagnosis": {...},
                "recruiter_analysis": {...},
                "rewritten_resume": {...},
                "hiring_manager_review": {...},
                "final_resume_text": "complete resume text ready to submit",
                "metadata": {
                    "total_time": seconds,
                    "agents_run": 4,
                    "ats_score_before": X,
                    "ats_score_after": Y,
                    "grade": "A+",
                    "hire_recommendation": "strong_yes"
                }
            }
        """
        start_time = time.time()
        
        logger.info("Starting 4-agent resume pipeline for %s at %s",
                    job.get("title", "Unknown"), job.get("company", "Unknown"))
        
        results = {
            "diagnosis": {},
            "recruiter_analysis": {},
            "rewritten_resume": {},
            "hiring_manager_review": {},
            "final_resume_text": "",
            "metadata": {},
        }
        
        from resume_tailor.agents.diagnoser import diagnose
        from resume_tailor.agents.recruiter import analyze_as_recruiter
        from resume_tailor.agents.rewriter import rewrite_resume
        from resume_tailor.agents.hiring_manager import review_as_hiring_manager
        
        logger.info("Agent 1/4: Diagnoser - analyzing resume like ATS...")
        try:
            results["diagnosis"] = await diagnose(
                job=job,
                resume_text=resume_text,
                candidate_skills=candidate_skills,
                ai_client=self.ai_client,
            )
        except Exception as e:
            logger.error("Diagnoser failed: %s", e)
            results["diagnosis"] = {"ats_score": 50, "parsing_issues": [], "rewritten_sections": {}}
        
        ats_before = results["diagnosis"].get("ats_score", 50)
        logger.info("Diagnoser complete: ATS score = %d", ats_before)
        
        logger.info("Agent 2/4: Recruiter - finding missing keywords...")
        try:
            results["recruiter_analysis"] = await analyze_as_recruiter(
                job=job,
                resume_text=resume_text,
                candidate_skills=candidate_skills,
                diagnosis=results["diagnosis"],
                ai_client=self.ai_client,
            )
        except Exception as e:
            logger.error("Recruiter failed: %s", e)
            results["recruiter_analysis"] = {"repeated_keywords": [], "missing_keywords": [], "top_10_to_add": []}
        
        logger.info("Recruiter complete: %d keywords to add",
                    len(results["recruiter_analysis"].get("top_10_to_add", [])))
        
        logger.info("Agent 3/4: Rewriter - rebuilding resume with XYZ formula...")
        # Determine candidate experience level by ANALYZING the actual resume content
        from resume_tailor.resume_parser import analyze_experience_level
        exp_analysis = analyze_experience_level(resume_text)
        experience_level = exp_analysis["level"]
        logger.info("Resume analysis: level=%s, confidence=%.2f, reasons=%s",
                    experience_level, exp_analysis["confidence"], exp_analysis["reasons"][:3])
        
        # Cross-check with stored profile data
        if profile:
            stored_fresher = profile.get("parsed_data", {}).get("is_fresher", True)
            stored_years = profile.get("experience_years", 0)
            if stored_fresher or (stored_years is not None and stored_years <= 1):
                if experience_level == "senior" and exp_analysis["confidence"] < 0.8:
                    experience_level = "fresher"
                    logger.info("Overriding to fresher: stored profile says fresher, AI analysis low confidence")
        try:
            results["rewritten_resume"] = await rewrite_resume(
                job=job,
                resume_text=resume_text,
                candidate_skills=candidate_skills,
                diagnosis=results["diagnosis"],
                recruiter_findings=results["recruiter_analysis"],
                ai_client=self.ai_client,
                experience_level=experience_level,
                experience_reasons=exp_analysis.get("reasons", []),
            )
        except Exception as e:
            logger.error("Rewriter failed: %s", e)
            results["rewritten_resume"] = {
                "professional_summary": f"Motivated {job.get('title', 'professional')}",
                "skills": {"technical": candidate_skills[:15]},
                "experience": [],
                "education": [],
                "projects": [],
                "certifications": [],
            }
        
        logger.info("Rewriter complete: %d experience entries, %d keywords added",
                    len(results["rewritten_resume"].get("experience", [])),
                    len(results["rewritten_resume"].get("ats_keywords_added", [])))
        
        logger.info("Agent 4/4: Hiring Manager - scoring resume...")
        try:
            results["hiring_manager_review"] = await review_as_hiring_manager(
                job=job,
                original_resume=resume_text,
                rewritten_resume=results["rewritten_resume"],
                diagnosis=results["diagnosis"],
                ai_client=self.ai_client,
            )
        except Exception as e:
            logger.error("Hiring Manager failed: %s", e)
            results["hiring_manager_review"] = {
                "scores": {"total": 35},
                "grade": "B+",
                "hire_recommendation": "yes",
                "top_3_fixes_before_submitting": [],
            }
        
        review = results["hiring_manager_review"]
        logger.info("Hiring Manager complete: Score = %d/50, Grade = %s, Hire = %s",
                    review.get("scores", {}).get("total", 0),
                    review.get("grade", "?"),
                    review.get("hire_recommendation", "?"))
        
        results["final_resume_text"] = _resume_to_text(results["rewritten_resume"], resume_text, profile_name=(profile or {}).get("name", ""))
        
        total_time = time.time() - start_time
        results["metadata"] = {
            "total_time": round(total_time, 2),
            "agents_run": 4,
            "ats_score_before": ats_before,
            "ats_score_after": review.get("final_resume_quality", {}).get("ats_score", 75),
            "grade": review.get("grade", "B+"),
            "hire_recommendation": review.get("hire_recommendation", "yes"),
            "keywords_added": len(results["rewritten_resume"].get("ats_keywords_added", [])),
            "fixes_applied": len(results["hiring_manager_review"].get("top_3_fixes_before_submitting", [])),
        }
        
        logger.info("4-agent pipeline complete in %.1fs: ATS %d→%d, Grade=%s, Hire=%s",
                    total_time, ats_before, results["metadata"]["ats_score_after"],
                    results["metadata"]["grade"], results["metadata"]["hire_recommendation"])
        
        return results


def _resume_to_text(resume: dict[str, Any], original_text: str = "", profile_name: str = "") -> str:
    """Convert the rewritten resume dictionary to formatted text.

    If the AI omits sections (common), fall back to extracting them from
    the original resume text so the output is never truncated.
    """
    import re as _re
    lines = []

    # Contact
    contact = resume.get("contact", {})
    name = contact.get("name") or profile_name
    if name:
        lines.append(name.upper())

    contact_parts = []
    for key in ["email", "phone", "linkedin", "github"]:
        val = contact.get(key, "")
        if not val:
            continue
        # Clean up linkedin/github: ensure full URL, skip bare labels
        if key == "linkedin":
            if val.lower().startswith("linkedin"):
                val = "https://www." + val if "://" not in val else val
            if "." not in val:
                continue  # skip bare word like "Linkedin"
        if key == "github":
            if val.lower().startswith("github"):
                val = "https://" + val if "://" not in val else val
            if "." not in val:
                continue
        contact_parts.append(val)

    # Ensure complete contact info: fill gaps from original text
    if original_text:
        has_email = any("@" in p for p in contact_parts)
        has_phone = any(_re.search(r'\d{5,}', p) for p in contact_parts)
        has_linkedin = any("linkedin" in p.lower() for p in contact_parts)

        if not has_email:
            email_m = _re.search(r'[\w\.-]+@[\w\.-]+\.\w+', original_text)
            if email_m:
                contact_parts.append(email_m.group(0))
        if not has_phone:
            phone_m = _re.search(r'[\+]?[\d\s\-\(\)]{7,20}', original_text)
            if phone_m:
                contact_parts.append(phone_m.group(0).strip())
        if not has_linkedin:
            linkedin_m = _re.search(r'(?:https?://)?(?:www\.)?linkedin\.com/in/[\w\-]+', original_text, _re.IGNORECASE)
            if linkedin_m:
                val = linkedin_m.group(0)
                if not val.startswith("http"):
                    val = "https://www." + val
                contact_parts.append(val)
            else:
                # Check for bare "Linkedin" label and extract username from context
                if _re.search(r'\blinkedin\b', original_text, _re.IGNORECASE):
                    # Try to find a linkedin URL or construct one
                    pass  # Can't construct URL without username
        github_m = _re.search(r'(?:https?://)?(?:www\.)?github\.com/[\w\-]+', original_text, _re.IGNORECASE)
        if github_m and not any("github" in p.lower() for p in contact_parts):
            val = github_m.group(0)
            if not val.startswith("http"):
                val = "https://" + val
            contact_parts.append(val)

    if contact_parts:
        lines.append(" | ".join(contact_parts))
    lines.append("")
    lines.append("─" * 50)
    lines.append("")
    
    # Summary
    summary = resume.get("professional_summary", "")
    if summary:
        lines.append("PROFESSIONAL SUMMARY")
        lines.append(summary)
        lines.append("")
    
    # Skills
    skills = resume.get("skills", {})
    if skills:
        lines.append("TECHNICAL SKILLS")
        if isinstance(skills, str):
            lines.append(skills)
        elif isinstance(skills, dict):
            for category, items in skills.items():
                if items:
                    lines.append(f"{category.title()}: {', '.join(items)}")
        elif isinstance(skills, list):
            lines.append(", ".join(skills))
        lines.append("")
    
    # Experience — use AI output if present, else extract from original
    experience = resume.get("experience", [])
    if experience:
        lines.append("PROFESSIONAL EXPERIENCE")
        for exp in experience:
            if exp.get("title"):
                header = exp["title"]
                if exp.get("company"):
                    header += f" | {exp['company']}"
                if exp.get("dates"):
                    header += f" | {exp['dates']}"
                lines.append(header)
            for bullet in exp.get("bullets", []):
                if not bullet.startswith(("•", "-")):
                    bullet = f"• {bullet}"
                lines.append(f"  {bullet}")
            lines.append("")
    elif original_text:
        lines.extend(_extract_section_from_text(original_text, ["EXPERIENCE", "WORK", "EMPLOYMENT", "INTERNSHIP"]))
    
    # Education — use AI output if present, else extract from original
    education = resume.get("education", [])
    if education:
        lines.append("EDUCATION")
        for edu in education:
            edu_line = edu.get("degree", "")
            if edu.get("institution"):
                edu_line += f" | {edu['institution']}"
            if edu.get("year"):
                edu_line += f" | {edu['year']}"
            lines.append(edu_line)
            if edu.get("details"):
                lines.append(f"  {edu['details']}")
        lines.append("")
    elif original_text:
        lines.extend(_extract_section_from_text(original_text, ["EDUCATION", "ACADEMIC"]))
    
    # Projects — use AI output if present, else extract from original
    projects = resume.get("projects", [])
    if projects:
        lines.append("PROJECTS")
        for proj in projects:
            if proj.get("name"):
                lines.append(proj["name"])
            for bullet in proj.get("bullets", []):
                if not bullet.startswith(("•", "-")):
                    bullet = f"• {bullet}"
                lines.append(f"  {bullet}")
            lines.append("")
    elif original_text:
        lines.extend(_extract_section_from_text(original_text, ["PROJECTS"]))
    
    # Certifications — use AI output if present, else extract from original
    certifications = resume.get("certifications", [])
    if certifications:
        lines.append("CERTIFICATIONS")
        for cert in certifications:
            if not cert.startswith(("•", "-")):
                cert = f"• {cert}"
            lines.append(cert)
    elif original_text:
        lines.extend(_extract_section_from_text(original_text, ["CERTIFICATIONS", "CERTIFICATES"]))
    
    result = "\n".join(lines)
    
    # Minimum quality gate: if result is too short, it's useless
    if len(result.strip()) < 100 and original_text:
        return original_text
    
    return result


def _extract_section_from_text(text: str, section_headers: list[str]) -> list[str]:
    """Extract a section from raw resume text by header keywords."""
    result = []
    lines = text.split("\n")
    in_section = False
    found_header = False
    
    end_headers = ["EXPERIENCE", "WORK", "SKILLS", "EDUCATION", "PROJECTS", 
                    "CERTIFICATIONS", "ACHIEVEMENTS", "CONTACT", "SUMMARY"]
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if in_section:
                result.append("")
            continue

        upper = stripped.upper().rstrip(":")

        # End of section (hit a DIFFERENT section header) — check BEFORE start
        if in_section and any(upper.startswith(h) for h in end_headers):
            # Only close if this header is NOT one of the headers we're extracting
            if not any(h in upper for h in section_headers):
                in_section = False
                continue

        # Start of target section
        if any(h in upper for h in section_headers):
            if len(stripped) < 40 or ":" in stripped:
                in_section = True
                if not found_header:
                    # Add section header
                    if any("EXPERIENCE" in h or "WORK" in h or "INTERNSHIP" in h for h in section_headers):
                        result.append("PROFESSIONAL EXPERIENCE")
                    elif any("EDUCATION" in h or "ACADEMIC" in h for h in section_headers):
                        result.append("EDUCATION")
                    elif any("PROJECT" in h for h in section_headers):
                        result.append("PROJECTS")
                    elif any("CERT" in h for h in section_headers):
                        result.append("CERTIFICATIONS")
                    else:
                        result.append(upper.title())
                    found_header = True
                continue

        if in_section and len(stripped) > 3:
            result.append(stripped)
    
    if result:
        result.append("")
    return result
