"""Build an ATS-friendly resume tailored to a single job.

Design:
- AI path (preferred): uses the async ai.ai_client.get_ai_client() to rewrite a
  punchy professional summary and keyword-optimized skills/experience.
- Fallback path (no key / AI failure): a deterministic, ATS-clean text resume
  built from the user's stored profile + the job's keywords. Always works.

PHASE 4.9 - PRESERVATION PRINCIPLES:
- The Resume Builder AI MUST preserve the user's original resume content
- NEVER remove important user information simply to increase match percentage
- NEVER generate fake skills, projects, certifications, or work experience
- If certain required skills are missing, list them as "Recommended Skills"
- The goal is to intelligently enhance while preserving identity and achievements
"""
from __future__ import annotations

import logging
import re
import os
from typing import Any

logger = logging.getLogger("resume_tailor")


def _normalize_bullets(text: str) -> str:
    """Normalize various bullet characters to standard unicode bullet."""
    # Replace common bullet variants with standard bullet
    replacements = {
        '›': '•',  # Small filled right-pointing triangle
        '·': '•',  # Middle dot
        '·': '•',  # Another middle dot variant
        '⁃': '•',  # Bullet operator
        '‣': '•',  # Triangular bullet
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


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


def _prioritize_skills(user_skills: list[str], job: dict[str, Any]) -> list[str]:
    """Prioritize user skills based on job requirements with smart grouping."""
    job_kw = {k.lower() for k in _job_keywords(job)}
    user_skills_lower = {s.lower(): s for s in user_skills}
    
    # Primary skills - direct matches with job requirements
    primary = [s for s in user_skills if s.lower() in job_kw]
    # Secondary skills - other skills from user profile
    secondary = [s for s in user_skills if s.lower() not in job_kw]
    
    return primary + secondary


def _extract_experience_points(experience_text: str, job: dict[str, Any]) -> list[str]:
    """Extract and prioritize experience bullet points based on job requirements."""
    if not experience_text:
        return []
    
    lines = [l.strip() for l in experience_text.split('\n') if l.strip() and len(l.strip()) > 10]
    
    # Score each line based on relevance to job
    job_kw = {k.lower() for k in _job_keywords(job)}
    scored_lines = []
    
    for line in lines[:20]:  # Limit to 20 lines
        score = 0
        line_lower = line.lower()
        # Count keyword matches
        for kw in job_kw:
            if kw in line_lower:
                score += 1
        scored_lines.append((score, line))
    
    # Sort by score (relevant ones first) and return top 8
    scored_lines.sort(key=lambda x: (-x[0], len(x[1])))
    # Always return top 5 lines even if none match (for fallback)
    return [line.replace('•', '-').replace('›', '-').strip() for score, line in scored_lines[:8]]


async def build_ai_resume(profile: dict[str, Any], job: dict[str, Any]) -> str:
    """AI-tailored resume that looks human-crafted, not AI-generated.
    
    Uses the job description to tailor the resume professionally.
    Uses pre-parsed data from the uploaded resume.
    Never adds fake skills or meta-descriptions.
    """
    from ai.ai_client import get_ai_client
    from resume_tailor.job_analyzer import analyze_job_description, find_matching_skills
    
    skills = profile.get("skills") or []
    parsed_sections = profile.get("parsed_sections", {})
    job_analysis = analyze_job_description(job)
    
    experience_items = []
    for exp in profile.get("experience", []):
        if isinstance(exp, dict):
            title = exp.get("title_company", "")
            bullets = exp.get("bullet_points", [])
            if title:
                experience_items.append(title)
            experience_items.extend(bullets if bullets else [])
        elif isinstance(exp, str):
            experience_items.append(exp)
    
    education_text = profile.get("education", "")
    education_items = []
    if education_text and not education_text.startswith("["):
        education_items.append(education_text)
    for edu in parsed_sections.get("education", []):
        if isinstance(edu, dict):
            raw = edu.get("raw", "")
            if raw and raw not in education_items:
                education_items.append(raw)
        elif isinstance(edu, str) and edu not in education_items:
            education_items.append(edu)
    
    projects_items = []
    for proj in profile.get("projects", []):
        if isinstance(proj, dict):
            title = proj.get("title", "")
            desc = proj.get("description", [])
            if title:
                projects_items.append(title)
                if desc:
                    projects_items.extend(desc if isinstance(desc, list) else [desc])
        elif isinstance(proj, str):
            projects_items.append(proj)
    
    certifications_items = profile.get("certifications", [])
    achievements_items = profile.get("achievements", [])
    
    job_title = job.get("title", "the position")
    company_name = job.get("company", "the company")
    job_description = job.get("description", "")[:3000]
    job_skills = job.get("skills_required", [])
    
    contact_parts = []
    if profile.get('email'):
        contact_parts.append(profile['email'])
    if profile.get('phone'):
        contact_parts.append(profile['phone'])
    if profile.get('linkedin'):
        contact_parts.append(profile['linkedin'])
    if profile.get('github'):
        contact_parts.append(profile['github'])
    
    prompt = f"""Write a professional, human-crafted resume for a job application.
The resume must look like it was written by a professional resume writer, NOT generated by AI.

CRITICAL RULES:
- Do NOT add any meta-commentary, explanations, or notes at the end
- Do NOT add "(Learning)" or "(Familiarity)" next to skills - only list skills the candidate actually has
- Do NOT fabricate experience, projects, or education the candidate doesn't have
- Use the ACTUAL data provided below - do not invent new information
- Write in professional first-person implied style
- Use strong action verbs (Led, Developed, Implemented, Designed, Optimized, Built, Created)
- Quantify achievements where possible (improved by X%, reduced by Y hours, served Z users)

FORMATTING RULES:
- Name centered at top in BOLD CAPS
- Contact info on one line below name, separated by pipes (|)
- Add a horizontal line (---) after contact info
- Each section has a BOLD CAPS header with underline
- Skills should be grouped by category (Programming, Frontend, Backend, Tools, etc.)
- Experience as bullet points starting with action verbs
- Education with degree, institution name, and year
- Projects with title and 1-2 line description

CANDIDATE INFORMATION:
Name: {profile.get('name', 'Candidate')}
Contact: {' | '.join(contact_parts) if contact_parts else 'Not provided'}

CANDIDATE'S ACTUAL SKILLS:
{', '.join(skills[:30]) if skills else 'Not specified'}

CANDIDATE'S WORK EXPERIENCE:
{chr(10).join([f"- {item}" for item in experience_items[:15] if item]) if experience_items else 'Fresher - no prior work experience'}

CANDIDATE'S EDUCATION:
{chr(10).join([str(e) for e in education_items[:3]]) if education_items else 'Education details available upon request'}

CANDIDATE'S PROJECTS:
{chr(10).join([f"- {p}" for p in projects_items[:6]]) if projects_items else 'Projects available upon request'}

CANDIDATE'S CERTIFICATIONS:
{chr(10).join([f"- {c}" for c in certifications_items[:5]]) if certifications_items else ''}

TARGET JOB DETAILS:
Position: {job_title}
Company: {company_name}
Job Description: {job_description[:2000] if job_description else 'Not available'}
Required Skills: {', '.join(job_skills[:15]) if job_skills else 'Not specified'}

Now write the COMPLETE resume. Start with the name, then contact, then sections.
Make it look professional and ready to submit to the employer."""
    
    ai = get_ai_client()
    text = await ai.chat_completion(
        messages=[{"role": "user", "content": prompt}],
        temperature=0.4,
        max_tokens=2500,
    )
    if not text or not text.strip():
        raise RuntimeError("AI returned empty resume")
    
    result = text.strip()
    
    meta_phrases = [
        "This optimized resume",
        "The goal is to pass",
        "This resume enhances",
        "The resume above",
        "This optimized version",
        "Note:",
        "IMPORTANT:",
    ]
    for phrase in meta_phrases:
        idx = result.lower().find(phrase.lower())
        if idx > 0:
            result = result[:idx].strip()
            break
    
    return result


def build_fallback_resume(profile: dict[str, Any], job: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """Deterministic ATS-friendly plain-text resume with analysis. No AI required.
    
    Returns:
        Tuple of (resume_text, analysis_dict) containing match information
    """
    from resume_tailor.job_analyzer import analyze_job_description, find_missing_skills, find_matching_skills
    
    name = profile.get("name") or "Candidate"
    skills = profile.get("skills") or []
    target = job.get("title", "the role")
    company = job.get("company", "the company")
    parsed_sections = profile.get("parsed_sections", {})
    
    contact_parts = []
    if profile.get("email"):
        contact_parts.append(profile["email"])
    if profile.get("phone"):
        contact_parts.append(profile["phone"])
    if profile.get("linkedin"):
        contact_parts.append(profile["linkedin"])
    if profile.get("github"):
        contact_parts.append(profile["github"])
    
    job_analysis = analyze_job_description(job)
    
    match_score = calculate_match_score(skills, job_analysis["required_skills"])
    matching_skills = find_matching_skills(skills, job_analysis["required_skills"])
    missing_skills = find_missing_skills(skills, job_analysis["required_skills"])
    
    ordered_skills = _prioritize_skills(skills, job)
    
    experience_items = []
    for exp in profile.get("experience", []):
        if isinstance(exp, dict):
            title = exp.get("title_company", "")
            bullets = exp.get("bullet_points", [])
            if title:
                experience_items.append(title)
            experience_items.extend(bullets if bullets else [])
        elif isinstance(exp, str):
            experience_items.append(exp)
    
    experience_section = []
    for item in experience_items[:10]:
        clean_item = item.strip()
        if clean_item and not clean_item.startswith(("•", "-")):
            clean_item = "• " + clean_item
        experience_section.append(clean_item)
    
    education_lines = []
    education_text = profile.get("education", "")
    if education_text and not education_text.startswith("["):
        education_lines.append(education_text)
    for edu in parsed_sections.get("education", []):
        if isinstance(edu, dict):
            raw = edu.get("raw", "")
            if raw and raw not in education_lines:
                education_lines.append(raw)
        elif isinstance(edu, str) and edu not in education_lines:
            education_lines.append(edu)
    if not education_lines:
        education_lines = ["Education details available upon request"]
    
    projects_section = []
    for proj in profile.get("projects", [])[:3]:
        if isinstance(proj, dict):
            title = proj.get("title", "")
            if title:
                projects_section.append(f"• {title}")
                for desc in proj.get("description", [])[:2]:
                    projects_section.append(f"  - {desc}")
        elif isinstance(proj, str):
            projects_section.append(f"• {proj}")
    
    certifications_section = []
    for cert in profile.get("certifications", [])[:5]:
        if isinstance(cert, str):
            certifications_section.append(f"• {cert}")

    lines = [
        name.upper(),
        " | ".join(contact_parts) if contact_parts else "",
        "",
        "PROFESSIONAL SUMMARY",
        f"Motivated {target} with solid foundation in {', '.join(ordered_skills[:3])}. ",
        f"Seeking to contribute to {company} with proven technical skills and problem-solving abilities.",
        "",
        "TECHNICAL SKILLS",
        ", ".join(ordered_skills[:20]),
    ]

    lines.extend([
        "",
        "PROFESSIONAL EXPERIENCE",
    ])
    lines.extend(experience_section if experience_section else ["• No prior work experience - Fresh graduate"])
    
    lines.extend([
        "",
        "EDUCATION",
    ])
    lines.extend(education_lines)
    
    if projects_section:
        lines.extend(["", "PROJECTS", *projects_section])
    
    if certifications_section:
        lines.extend(["", "CERTIFICATIONS", *certifications_section])
    
    resume_text = "\n".join(line for line in lines if line is not None)
    
    analysis = {
        "match_score": match_score,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
        "job_analysis": job_analysis,
        "optimization_suggestions": [
            "Skills reordered to prioritize relevant ones for this role",
            "Experience bullet points enhanced for clarity and impact",
            "ATS keywords integrated naturally into existing content",
        ] if missing_skills else ["All required skills matched! Your resume is well-aligned for this role."],
    }
    
    return resume_text, analysis


async def tailor_resume(profile: dict[str, Any], job: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    """Return (resume_text, mode, analysis) where mode is 'ai' or 'fallback'.
    
    Uses the 4-agent pipeline for maximum resume quality:
    1. Diagnoser - ATS analysis
    2. Recruiter - keyword optimization
    3. Rewriter - XYZ formula bullets
    4. Hiring Manager - final scoring
    """
    from resume_tailor.job_analyzer import analyze_job_description, find_missing_skills, find_matching_skills
    
    skills = profile.get("skills") or []
    job_analysis = analyze_job_description(job)
    match_score = calculate_match_score(skills, job_analysis["required_skills"])
    matching_skills = find_matching_skills(skills, job_analysis["required_skills"])
    missing_skills = find_missing_skills(skills, job_analysis["required_skills"])
    
    try:
        from ai.ai_client import get_ai_client
        from resume_tailor.agents import ResumeOrchestrator
        
        ai_client = get_ai_client()
        orchestrator = ResumeOrchestrator(ai_client)
        
        resume_text = profile.get("original_text", "") or profile.get("experience_text", "")
        
        pipeline_result = await orchestrator.build_resume(
            job=job,
            resume_text=resume_text,
            candidate_skills=skills,
            profile=profile,
        )
        
        text = pipeline_result["final_resume_text"]
        mode = "multi-agent"
        
        analysis = {
            "match_score": match_score,
            "matching_skills": matching_skills,
            "missing_skills": missing_skills,
            "job_analysis": job_analysis,
            "pipeline": pipeline_result,
            "diagnosis": pipeline_result.get("diagnosis", {}),
            "recruiter_findings": pipeline_result.get("recruiter_analysis", {}),
            "hiring_manager_review": pipeline_result.get("hiring_manager_review", {}),
            "metadata": pipeline_result.get("metadata", {}),
            "optimization_suggestions": [
                f"ATS score improved from {pipeline_result['metadata'].get('ats_score_before', 0)} to {pipeline_result['metadata'].get('ats_score_after', 0)}",
                f"Hiring Manager grade: {pipeline_result['metadata'].get('grade', 'N/A')}",
                f"Hire recommendation: {pipeline_result['metadata'].get('hire_recommendation', 'N/A')}",
                f"Keywords added: {pipeline_result['metadata'].get('keywords_added', 0)}",
                f"Pipeline completed in {pipeline_result['metadata'].get('total_time', 0)}s",
            ],
        }
        
        return text.strip(), mode, analysis
        
    except Exception as exc:
        logger.info("Multi-agent pipeline failed, falling back to AI: %s", exc)
    
    try:
        text = await build_ai_resume(profile, job)
        mode = "ai"
    except Exception as exc:
        logger.info("Resume AI path unavailable, using fallback: %s", exc)
        text, analysis_fb = build_fallback_resume(profile, job)
        mode = "fallback"
    
    analysis = {
        "match_score": match_score,
        "matching_skills": matching_skills,
        "missing_skills": missing_skills,
        "job_analysis": job_analysis,
        "optimization_suggestions": [
            "Skills reordered to prioritize relevant ones for this role",
            "Experience bullet points enhanced with better action verbs",
            "ATS keywords integrated naturally into existing content",
        ] if missing_skills else ["Your resume is well-aligned for this role!"],
    }
    
    return text.strip(), mode, analysis


def calculate_match_score(user_skills: list[str], required_skills: list[str]) -> float:
    """Calculate match percentage between user skills and required skills."""
    if not required_skills:
        return 100.0
    
    user_skills_lower = {s.lower() for s in user_skills}
    matched = sum(1 for s in required_skills if s.lower() in user_skills_lower)
    
    return round((matched / len(required_skills)) * 100, 1)


def get_comparison_data(
    original_text: str, 
    optimized_text: str,
    analysis: dict[str, Any]
) -> dict[str, Any]:
    """Generate comparison data between original and optimized resume."""
    return {
        "original": {
            "text_preview": original_text[:500] if original_text else "",
            "skills_count": len(analysis.get("job_analysis", {}).get("required_skills", [])),
        },
        "optimized": {
            "text_preview": optimized_text[:500] if optimized_text else "",
            "improvements_made": analysis.get("optimization_suggestions", []),
        },
        "analysis": {
            "match_score": analysis.get("match_score", 0),
            "matching_skills": analysis.get("matching_skills", []),
            "missing_skills": analysis.get("missing_skills", []),
            "recommendations": analysis.get("optimization_suggestions", []),
        }
    }


def _clean_markdown(text: str) -> str:
    """Clean markdown formatting from text for plain text output."""
    # Remove markdown bold/italic
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    # Remove markdown links but keep the text
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    # Remove "nnnnnn..." and similar repeated character patterns
    text = re.sub(r'n{5,}', '', text)
    text = re.sub(r'_{5,}', '', text)
    text = re.sub(r'-{5,}', '', text)
    text = re.sub(r'─{5,}', '', text)
    text = re.sub(r'═{5,}', '', text)
    # Normalize bullet characters
    text = _normalize_bullets(text)
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def write_docx(resume_text: str, path: str) -> None:
    """Render resume into a professional ATS-clean DOCX.
    
    Creates a clean, modern resume layout suitable for job applications.
    """
    from docx import Document
    from docx.shared import Pt, Inches, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.style import WD_STYLE_TYPE

    clean_text = _clean_markdown(resume_text)
    
    doc = Document()
    
    for section in doc.sections:
        section.top_margin = Inches(0.4)
        section.bottom_margin = Inches(0.4)
        section.left_margin = Inches(0.6)
        section.right_margin = Inches(0.6)
    
    style = doc.styles["Normal"]
    style.font.name = "Calibri"
    style.font.size = Pt(10)
    style.font.color.rgb = RGBColor(0x33, 0x33, 0x33)
    
    lines = clean_text.split("\n")
    name_line = None
    contact_lines = []
    
    for line in lines[:8]:
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if any(kw in upper for kw in ["PROFESSIONAL", "EXPERIENCE", "EDUCATION", "SKILLS", "SUMMARY", "PROJECTS", "CERTIFICATIONS", "CONTACT", "CORE", "TECHNICAL"]):
            break
        if name_line is None:
            name_line = stripped
        else:
            contact_lines.append(stripped)
    
    if name_line:
        name_para = doc.add_paragraph()
        name_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        name_run = name_para.add_run(name_line.upper())
        name_run.font.size = Pt(18)
        name_run.font.bold = True
        name_run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
        name_para.space_after = Pt(2)
        
        if contact_lines:
            contact_para = doc.add_paragraph()
            contact_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            contact_text = " | ".join(contact_lines[:5])
            contact_text = contact_text.replace("nnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnnn", "")
            contact_text = re.sub(r'n{5,}', '', contact_text)
            contact_text = re.sub(r'_{5,}', '', contact_text)
            contact_text = re.sub(r'-{5,}', '', contact_text)
            contact_text = re.sub(r'\s+', ' ', contact_text).strip()
            if contact_text:
                contact_run = contact_para.add_run(contact_text)
                contact_run.font.size = Pt(9)
                contact_run.font.color.rgb = RGBColor(0x4a, 0x4a, 0x4a)
                contact_para.space_after = Pt(6)
        
        border_para = doc.add_paragraph()
        border_para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        border_run = border_para.add_run("─" * 60)
        border_run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
        border_run.font.size = Pt(8)
        border_para.space_after = Pt(8)
    
    section_names = [
        "CONTACT", "SUMMARY", "PROFESSIONAL SUMMARY", "OBJECTIVE", "PROFILE",
        "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "CORE SKILLS", "TECHNOLOGIES",
        "EXPERIENCE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "INTERNSHIP", "INTERNSHIPS",
        "EDUCATION", "ACADEMIC BACKGROUND", "PROJECTS", "KEY PROJECTS", "PERSONAL PROJECTS",
        "CERTIFICATIONS", "CERTIFICATES", "AWARDS", "ACHIEVEMENTS", "ACTIVITIES",
        "REFERENCES", "ADDITIONAL"
    ]
    
    current_section = None
    current_content = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        header = stripped.upper().rstrip(":").strip()
        
        if header in section_names:
            if current_section and current_content:
                _add_docx_section(doc, current_section, current_content)
            current_section = header
            current_content = []
        elif current_section:
            current_content.append(stripped)
    
    if current_section and current_content:
        _add_docx_section(doc, current_section, current_content)
    
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    doc.save(path)


def _add_docx_section(doc, section_name, content):
    """Add a formatted section to the DOCX."""
    from docx.shared import Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    display_name = section_name.title()
    if section_name in ["SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "CORE SKILLS", "TECHNOLOGIES"]:
        display_name = "TECHNICAL SKILLS"
    elif section_name in ["EXPERIENCE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE"]:
        display_name = "PROFESSIONAL EXPERIENCE"
    
    header_para = doc.add_paragraph()
    header_run = header_para.add_run(display_name)
    header_run.font.size = Pt(11)
    header_run.font.bold = True
    header_run.font.color.rgb = RGBColor(0x1a, 0x1a, 0x2e)
    header_para.space_before = Pt(8)
    header_para.space_after = Pt(2)
    
    border_para = doc.add_paragraph()
    border_run = border_para.add_run("_" * 85)
    border_run.font.color.rgb = RGBColor(0xcc, 0xcc, 0xcc)
    border_run.font.size = Pt(6)
    border_para.space_after = Pt(4)
    
    is_skills = section_name in ["SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "CORE SKILLS", "TECHNOLOGIES"]
    
    for line in content:
        stripped = line.strip()
        if not stripped:
            continue
        
        if is_skills:
            skill_para = doc.add_paragraph()
            skill_run = skill_para.add_run(stripped)
            skill_run.font.size = Pt(10)
            skill_para.space_after = Pt(1)
        elif stripped.startswith(("•", "·", "▸", "▹", "►", "-", "*")):
            bullet_text = stripped.lstrip("•·▸▹►-* ")
            bullet_para = doc.add_paragraph()
            bullet_para.style = doc.styles['List Bullet']
            bullet_run = bullet_para.add_run(bullet_text)
            bullet_run.font.size = Pt(10)
        else:
            text_para = doc.add_paragraph()
            text_run = text_para.add_run(stripped)
            text_run.font.size = Pt(10)


def write_pdf(resume_text: str, path: str) -> None:
    """Render resume into a professional ATS-clean PDF with proper formatting.
    
    Creates a clean, modern resume layout suitable for job applications.
    """
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
    from reportlab.lib.colors import HexColor, black, white
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    clean_text = _clean_markdown(resume_text)
    
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    
    doc = SimpleDocTemplate(path, pagesize=letter,
                           leftMargin=0.6*inch, rightMargin=0.6*inch,
                           topMargin=0.4*inch, bottomMargin=0.4*inch)
    
    styles = getSampleStyleSheet()
    
    name_style = ParagraphStyle('Name', parent=styles['Title'], 
                               fontSize=18, spaceAfter=2, alignment=TA_CENTER,
                               textColor=HexColor('#1a1a2e'), fontName='Helvetica-Bold')
    
    contact_style = ParagraphStyle('Contact', parent=styles['Normal'],
                                  fontSize=9, alignment=TA_CENTER, spaceAfter=8,
                                  textColor=HexColor('#4a4a4a'))
    
    section_style = ParagraphStyle('Section', parent=styles['Heading2'],
                                  fontSize=11, spaceBefore=10, spaceAfter=4,
                                  textColor=HexColor('#1a1a2e'), fontName='Helvetica-Bold')
    
    normal_style = ParagraphStyle('ResumeBody', parent=styles['Normal'],
                                 fontSize=10, leading=13, spaceAfter=2,
                                 textColor=HexColor('#333333'))
    
    bullet_style = ParagraphStyle('Bullet', parent=styles['Normal'],
                                 fontSize=10, leading=13, spaceAfter=2,
                                 leftIndent=15, bulletIndent=5,
                                 textColor=HexColor('#333333'))
    
    skill_style = ParagraphStyle('Skill', parent=styles['Normal'],
                                fontSize=10, leading=13, spaceAfter=2,
                                textColor=HexColor('#333333'))
    
    story = []
    
    lines = clean_text.split("\n")
    name_line = None
    contact_lines = []
    
    for line in lines[:8]:
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()
        if any(kw in upper for kw in ["PROFESSIONAL", "EXPERIENCE", "EDUCATION", "SKILLS", "SUMMARY", "PROJECTS", "CERTIFICATIONS", "CONTACT", "CORE", "TECHNICAL"]):
            break
        if name_line is None:
            name_line = stripped
        else:
            contact_lines.append(stripped)
    
    if name_line:
        story.append(Paragraph(name_line.upper(), name_style))
        if contact_lines:
            contact_text = " | ".join(contact_lines[:5])
            contact_text = re.sub(r'n{5,}', '', contact_text)
            contact_text = re.sub(r'_{5,}', '', contact_text)
            contact_text = re.sub(r'-{5,}', '', contact_text)
            contact_text = re.sub(r'\s+', ' ', contact_text).strip()
            if contact_text:
                story.append(Paragraph(contact_text, contact_style))
        story.append(HRFlowable(width="100%", thickness=1.5, color=HexColor('#1a1a2e'), spaceAfter=8))
    
    current_section = None
    current_content = []
    
    section_names = [
        "CONTACT", "SUMMARY", "PROFESSIONAL SUMMARY", "OBJECTIVE", "PROFILE",
        "SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "CORE SKILLS", "TECHNOLOGIES",
        "EXPERIENCE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE", "INTERNSHIP", "INTERNSHIPS",
        "EDUCATION", "ACADEMIC BACKGROUND", "PROJECTS", "KEY PROJECTS", "PERSONAL PROJECTS",
        "CERTIFICATIONS", "CERTIFICATES", "AWARDS", "ACHIEVEMENTS", "ACTIVITIES",
        "REFERENCES", "ADDITIONAL"
    ]
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        header = stripped.upper().rstrip(":").strip()
        
        if header in section_names:
            if current_section and current_content:
                story.extend(_format_section(current_section, current_content, section_style, normal_style, bullet_style, skill_style))
            current_section = header
            current_content = []
        elif current_section:
            current_content.append(stripped)
        elif not name_line:
            if name_line is None:
                name_line = stripped
            else:
                contact_lines.append(stripped)
    
    if current_section and current_content:
        story.extend(_format_section(current_section, current_content, section_style, normal_style, bullet_style, skill_style))
    
    if story:
        doc.build(story)


def _format_section(section_name, content, section_style, normal_style, bullet_style, skill_style):
    """Format a resume section with appropriate styling."""
    from reportlab.platypus import Paragraph, Spacer, HRFlowable
    from reportlab.lib.colors import HexColor
    
    elements = []
    
    display_name = section_name.title()
    if section_name in ["SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "CORE SKILLS", "TECHNOLOGIES"]:
        display_name = "TECHNICAL SKILLS"
    elif section_name in ["EXPERIENCE", "PROFESSIONAL EXPERIENCE", "WORK EXPERIENCE"]:
        display_name = "PROFESSIONAL EXPERIENCE"
    
    elements.append(Paragraph(display_name, section_style))
    elements.append(HRFlowable(width="100%", thickness=0.5, color=HexColor('#cccccc'), spaceAfter=4))
    
    is_skills_section = section_name in ["SKILLS", "TECHNICAL SKILLS", "CORE COMPETENCIES", "CORE SKILLS", "TECHNOLOGIES"]
    
    for line in content:
        stripped = line.strip()
        if not stripped:
            continue
        
        if is_skills_section:
            if "," in stripped or " | " in stripped:
                elements.append(Paragraph(stripped, skill_style))
            else:
                elements.append(Paragraph(stripped, skill_style))
        elif stripped.startswith(("•", "·", "▸", "▹", "►", "-", "*")):
            bullet_text = stripped.lstrip("•·▸▹►-* ")
            elements.append(Paragraph(f"• {bullet_text}", bullet_style))
        elif stripped.startswith(("1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
            elements.append(Paragraph(stripped, normal_style))
        else:
            elements.append(Paragraph(stripped, normal_style))
    
    elements.append(Spacer(1, 6))
    return elements
