"""Job Description Analyzer - Extracts required skills, keywords, and qualifications.

Analyzes job descriptions to identify what the target company is looking for,
enabling intelligent resume optimization without fabrication.
"""
from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger("resume_tailor")


def analyze_job_description(job: dict[str, Any]) -> dict[str, Any]:
    """Analyze a job description to extract requirements and keywords.
    
    Args:
        job: Dictionary containing job data (title, company, description, skills_required)
        
    Returns:
        Analysis containing required skills, keywords, responsibilities, and qualifications
    """
    title = job.get("title", "") or ""
    description = job.get("description", "") or ""
    skills_required = job.get("skills_required") or []
    company = job.get("company", "") or ""
    
    # Extract keywords from job description
    keywords = _extract_keywords(description)
    
    # Combine with explicit skills
    all_skills = list(set([s.lower() for s in skills_required] + keywords))
    
    # Extract responsibilities
    responsibilities = _extract_responsibilities(description)
    
    # Extract qualifications
    qualifications = _extract_qualifications(description)
    
    # Extract experience level
    experience_level = _extract_experience_level(description, title)
    
    # Extract technologies mentioned
    technologies = _extract_technologies(description + " " + title)
    
    return {
        "required_skills": all_skills,
        "keywords": keywords,
        "responsibilities": responsibilities,
        "qualifications": qualifications,
        "experience_level": experience_level,
        "technologies": technologies,
        "job_title": title,
        "company": company,
    }


def _extract_keywords(text: str) -> list[str]:
    """Extract technical keywords and skills from job description."""
    # Common technical skills and keywords to look for
    tech_terms = [
        # Tech roles
        'python', 'java', 'javascript', 'typescript', 'c++', 'c#', 'php', 'ruby', 'go', 'rust',
        'react', 'angular', 'vue', 'node.js', 'express', 'django', 'flask', 'spring', 'rails',
        'aws', 'azure', 'gcp', 'docker', 'kubernetes', 'terraform', 'jenkins', 'git',
        'sql', 'nosql', 'mongodb', 'postgresql', 'mysql', 'redis', 'elasticsearch',
        'machine learning', 'ai', 'ml', 'nlp', 'computer vision', 'deep learning',
        'api', 'rest', 'graphql', 'microservices', 'cloud', 'devops', 'ci/cd',
        'tensorflow', 'pytorch', 'scikit-learn', 'pandas', 'numpy', 'spark',
        'html', 'css', 'sass', 'less', 'bootstrap', 'tailwind',
        'agile', 'scrum', 'kanban', 'jira', 'tdd', 'bdd',
        'testing', 'jest', 'pytest', 'cypress', 'selenium',
        
        # Creative/Design roles
        'graphic design', 'ui', 'ux', 'figma', 'photoshop', 'illustrator', 'sketch',
        'adobe creative', 'indesign', 'xd', 'adobe xd', 'motion graphics', 'video editing',
        'branding', 'typography', 'color theory', 'wireframing', 'prototyping',
        'user interface', 'user experience', 'web design', 'mobile design',
        
        # Business/Analytics roles
        'excel', 'power bi', 'tableau', 'looker', 'data analysis', 'business analysis',
        'product management', 'project management', 'stakeholder management',
        'financial modeling', 'market research', 'seo', 'sem', 'digital marketing',
        
        # Other roles
        'customer support', 'sales', 'account management', 'hr', 'recruitment',
    ]
    
    text_lower = text.lower()
    found_keywords = []
    
    for term in tech_terms:
        if term in text_lower:
            found_keywords.append(term)
    
    # Also extract any capitalized phrases (often technologies)
    capitalized = re.findall(r'\b[A-Z][A-Z0-9]+\b', text)
    for cap in capitalized:
        if len(cap) > 2 and cap.lower() not in [k.lower() for k in found_keywords]:
            found_keywords.append(cap)
    
    return found_keywords


def _extract_responsibilities(text: str) -> list[str]:
    """Extract key responsibilities from job descriptions."""
    responsibilities = []
    
    # Look for "responsibilities" or "what you'll do" sections
    resp_patterns = [
        r'(?:responsibilities|duties|role|what you.*do|you will).*?:\s*\n(.*?)((?=\n[A-Z]|\n\n|\Z))',
        r'(?:-|\u2022|\u2023|\u2024|\u25A0|\u25B8|\u25CF)\s+(.*?)(?=\n|$)',
    ]
    
    lines = text.split('\n')
    in_responsibilities = False
    
    for line in lines:
        stripped = line.strip()
        
        # Detect responsibilities section
        if 'responsibilities' in stripped.lower() or 'what you' in stripped.lower() or 'you will' in stripped.lower():
            if stripped.endswith(':') or len(stripped.split()) < 5:
                in_responsibilities = True
                continue
                
        if in_responsibilities:
            if stripped.startswith(('•', '-', '›', '·', '⁃')):
                responsibilities.append(stripped.lstrip('•-›·⁃ '))
            elif any(kw in stripped.upper() for kw in ['QUALIFICATION', 'REQUIREMENT', 'SKILL', 'BENEFIT']):
                in_responsibilities = False
    
    return responsibilities[:10]  # Limit to 10


def _extract_qualifications(text: str) -> list[str]:
    """Extract required qualifications from job descriptions."""
    qualifications = []
    
    lines = text.split('\n')
    in_qualifications = False
    
    for line in lines:
        stripped = line.strip()
        
        # Detect qualifications section
        if 'qualification' in stripped.lower() or 'requirements' in stripped.lower():
            if stripped.endswith(':') or len(stripped.split()) < 5:
                in_qualifications = True
                continue
                
        if in_qualifications:
            if stripped.startswith(('•', '-', '›', '·', '⁃')):
                qualifications.append(stripped.lstrip('•-›·⁃ '))
            elif any(kw in stripped.upper() for kw in ['BENEFIT', 'RESPONSIBILITY', 'ABOUT', 'COMPANY']):
                in_qualifications = False
    
    return qualifications[:10]  # Limit to 10


def _extract_experience_level(text: str, title: str) -> str:
    """Extract required experience level from job description."""
    text_lower = (text + " " + title).lower()
    
    # Check for seniority indicators
    if any(term in text_lower for term in ['senior', 'lead', 'principal', 'staff', 'architect']):
        return "senior"
    elif any(term in text_lower for term in ['junior', 'entry', 'associate', 'fresher', 'intern']):
        return "entry"
    elif any(term in text_lower for term in ['mid-level', 'mid level', 'intermediate']):
        return "mid"
    else:
        return "any"


def _extract_technologies(text: str) -> list[str]:
    """Extract specific technologies and tools mentioned."""
    tech_keywords = [
        'docker', 'kubernetes', 'jenkins', 'gitlab', 'github', 'git',
        'tensorflow', 'pytorch', 'scikit', 'pandas', 'numpy', 'scipy',
        'react', 'vue', 'angular', 'svelte', 'next.js', 'nuxt',
        'node', 'express', 'fastapi', 'flask', 'django', 'spring',
        'aws', 'azure', 'gcp', 'heroku', 'vercel',
        'mysql', 'postgresql', 'mongodb', 'redis', 'cassandra',
    ]
    
    text_lower = text.lower()
    found = []
    
    for tech in tech_keywords:
        if tech in text_lower:
            found.append(tech)
    
    return found


def calculate_match_score(user_skills: list[str], required_skills: list[str]) -> float:
    """Calculate match percentage between user skills and required skills."""
    if not required_skills:
        return 100.0
    
    user_skills_lower = {s.lower() for s in user_skills}
    matched = sum(1 for s in required_skills if s.lower() in user_skills_lower)
    
    return round((matched / len(required_skills)) * 100, 1)


def find_missing_skills(user_skills: list[str], required_skills: list[str]) -> list[str]:
    """Find skills that are required but missing from user's resume."""
    # Normalize user skills to lowercase for comparison
    user_skills_lower = {s.lower().strip() for s in user_skills if s.strip()}
    missing = []
    
    for skill in required_skills:
        skill_normalized = skill.lower().strip()
        if not skill_normalized:
            continue
        if skill_normalized not in user_skills_lower:
            missing.append(skill)
    
    return missing


def find_matching_skills(user_skills: list[str], required_skills: list[str]) -> list[str]:
    """Find skills that match between user's resume and job requirements."""
    user_skills_lower = {s.lower(): s for s in user_skills}
    matching = []
    
    for skill in required_skills:
        if skill.lower() in user_skills_lower:
            matching.append(user_skills_lower[skill.lower()])
        elif any(skill.lower() in s.lower() or s.lower() in skill.lower() for s in user_skills):
            matching.append(skill)
    
    return matching


def get_optimization_suggestions(
    original_sections: dict[str, Any], 
    job_analysis: dict[str, Any],
    missing_skills: list[str]
) -> list[str]:
    """Generate optimization suggestions while preserving original content.
    
    These are suggestions for what to ADD or MODIFY, not what to remove.
    """
    suggestions = []
    
    # Suggest improvements to existing content
    if original_sections.get("skills"):
        # Suggest reordering existing skills
        suggestions.append("Reorder skills section to prioritize job-matching skills")
    
    if original_sections.get("experience"):
        suggestions.append("Enhance experience bullet points with more impactful action verbs")
        suggestions.append("Add quantifiable achievements where possible")
    
    # Suggest adding keywords (without fabrication)
    suggestions.append("Consider adding relevant keywords to improve ATS compatibility")
    
    # Suggest highlighting relevant sections
    suggestions.append("Emphasize relevant projects and experience in your summary")
    
    # If skills are missing, suggest them without adding to resume
    if missing_skills:
        suggestions.append(f"Consider learning missing skills: {', '.join(missing_skills[:3])}")
    
    return suggestions