"""Resume Parser - Extracts structured sections from original resume while preserving content.

This module preserves the original resume's identity, achievements, and format
while extracting sections for intelligent optimization.
"""
from __future__ import annotations

import re
import logging
from typing import Any

logger = logging.getLogger("resume_tailor")


def parse_resume_sections(text_content: str) -> dict[str, Any]:
    """Extract and organize resume sections while preserving original content.
    
    Key principle: NEVER modify or remove user's original content.
    We only extract and preserve sections for later comparison.
    
    Args:
        text_content: The raw text content of the user's original resume
        
    Returns:
        Dictionary containing all extracted sections in their original form
    """
    if not text_content:
        return {
            "personal_details": {},
            "education": [],
            "experience": [],
            "skills": [],
            "projects": [],
            "certifications": [],
            "internships": [],
            "achievements": [],
            "raw_text": text_content,
        }
    
    sections = {
        "personal_details": _extract_personal_details(text_content),
        "education": _extract_education(text_content),
        "experience": _extract_experience(text_content),
        "skills": _extract_skills(text_content),
        "projects": _extract_projects(text_content),
        "certifications": _extract_certifications(text_content),
        "internships": _extract_internships(text_content),
        "achievements": _extract_achievements(text_content),
        "raw_text": text_content,
    }
    
    return sections


def _extract_personal_details(text: str) -> dict[str, str]:
    """Extract personal details (name, email, phone, linkedin, etc.) preserving original text."""
    details = {}
    
    # Extract email (preserve original format)
    email_match = re.search(r'[\w\.-]+@[\w\.-]+\.\w+', text)
    if email_match:
        details["email"] = email_match.group(0)
    
    # Extract phone (various formats)
    phone_patterns = [
        r'\+?\d{1,3}[\s\-]?\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}',
        r'\d{10}',
        r'\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{4}',
    ]
    for pattern in phone_patterns:
        phone_match = re.search(pattern, text)
        if phone_match:
            details["phone"] = phone_match.group(0)
            break
    
    # Extract LinkedIn
    linkedin_match = re.search(r'linkedin\.com/in/[\w\-]+', text, re.IGNORECASE)
    if linkedin_match:
        details["linkedin"] = linkedin_match.group(0)
    
    # Extract GitHub
    github_match = re.search(r'github\.com/[\w\-]+', text, re.IGNORECASE)
    if github_match:
        details["github"] = github_match.group(0)
    
    # Try to extract name (first non-empty line that's not an email/phone)
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    for line in lines[:5]:
        if 'PROFESSIONAL' not in line.upper() and '@' not in line:
            if len(line) < 50 and not re.search(r'\d', line):
                details["name"] = line
                break
    
    return details


def _extract_education(text: str) -> list[dict[str, str]]:
    """Extract education entries preserving all original details."""
    education = []
    lines = text.split('\n')
    
    education_keywords = ['education', 'academic', 'university', 'college', 'school', 
                          'b.tech', 'bachelor', 'master', 'm.tech', 'b.e', 'm.e',
                          'b.sc', 'm.sc', 'mba', 'degree']
    
    in_education = False
    current_entry = {}
    
    placeholder_patterns = ['[insert', 'insert', 'not provided', 'available upon']
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        
        line_upper = stripped.upper().rstrip(':').strip()
        line_lower = stripped.lower().rstrip(':').strip()
        
        if line_lower in ['education', 'academic background', 'academic history', 'academic']:
            in_education = True
            continue
        elif 'education' in line_lower or 'academic' in line_lower:
            if ':' in stripped or len(stripped) < 30:
                in_education = True
                continue
        
        if in_education and any(kw in line_upper for kw in ['EXPERIENCE', 'WORK', 'SKILLS', 
                                                                  'PROJECTS', 'CERTIFICATIONS', 'ACHIEVEMENTS']):
            in_education = False
            if current_entry:
                education.append(current_entry)
                current_entry = {}
            continue
        
        if in_education:
            line_lower_check = stripped.lower()
            if any(p in line_lower_check for p in placeholder_patterns):
                continue
            has_degree_kw = any(kw in stripped.lower() for kw in education_keywords)
            if has_degree_kw or stripped.lower().rstrip(':') in ['m.s.', 'm.s', 'b.s.', 'b.s', 'ms', 'bs', 'master', 'bachelor']:
                if current_entry:
                    education.append(current_entry)
                current_entry = {"raw": stripped}
            elif current_entry:
                current_entry["raw"] = current_entry.get("raw", "") + " " + stripped
                date_match = re.search(r'(20\d{2}|19\d{2})', stripped)
                if date_match:
                    current_entry["year"] = date_match.group(0)
            elif stripped.startswith(('•', '-', '›', '·', '⁃')):
                content = stripped.lstrip('•-›·⁃ ').strip()
                if content:
                    if current_entry:
                        education.append(current_entry)
                    current_entry = {"raw": content}
    
    if current_entry:
        education.append(current_entry)
    
    return education


def _extract_experience(text: str) -> list[dict[str, str]]:
    """Extract work experience entries preserving all original details."""
    experience = []
    lines = text.split('\n')
    
    experience_keywords = ['experience', 'work', 'employment', 'job', 'position', 'role', 'professional']
    # Enhanced job title patterns to catch internships and various formats
    job_title_patterns = [
        r'(?:Senior|Junior|Lead|Principal|Staff)?\s*(?:Software|Data|Machine Learning|AI|Backend|Frontend|Full Stack|DevOps|QA|Product|Project)\s*(?:Engineer|Developer|Analyst|Scientist|Architect|Manager|Intern)',
        r'\w+\s+Developer',
        r'\w+\s+Engineer',
        r'\w+\s+(?:Manager|Lead|Intern)',
        r'(?:APPIAN|INDUSTRIAL|AUTOMATION|CONSULTANT|SOFTWARE|DATA|BACKEND|FRONTEND|FULL STACK|QA|TEST|DEVOPS)\s+Intern',  # Specific internship patterns
        r'(?:Intern|Internship)',  # Generic intern pattern as fallback
    ]
    
    in_experience = False
    current_entry = {}
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Detect experience section start (check before upper check)
        line_lower = stripped.lower()
        if any(kw in line_lower for kw in ['experience', 'employment', 'work history']):
            # Check if this is a header line
            if any(stripped.upper().startswith(h) for h in ['EXPERIENCE', 'WORK', 'PROFESSIONAL']) or \
               stripped.lower() in ['experience', 'work experience', 'employment history', 'professional experience']:
                in_experience = True
                continue
        
        # Detect section end
        if in_experience and any(kw in stripped.upper() for kw in ['EDUCATION', 'SKILLS', 
                                                                   'PROJECTS', 'CERTIFICATIONS', 'ACHIEVEMENTS', 'CERTIFICATES']):
            in_experience = False
            if current_entry:
                experience.append(current_entry)
                current_entry = {}
            continue
        
        if in_experience:
            # Check if this looks like a job title
            found_title = False
            for pattern in job_title_patterns:
                if re.search(pattern, stripped, re.IGNORECASE):
                    if current_entry:
                        experience.append(current_entry)
                    current_entry = {"title_company": stripped}
                    found_title = True
                    break
            
            if not found_title and current_entry:
                # Append bullet points or description
                if stripped.startswith(('•', '-', '›', '·', '⁃')):
                    if "bullet_points" not in current_entry:
                        current_entry["bullet_points"] = []
                    current_entry["bullet_points"].append(stripped)
                else:
                    current_entry["raw"] = current_entry.get("raw", "") + " " + stripped
    
    if current_entry:
        experience.append(current_entry)
    
    return experience


def _extract_skills(text: str) -> list[str]:
    """Extract skills from resume, preserving original format and order."""
    skills = []
    lines = text.split('\n')
    
    in_skills = False
    skill_section_keywords = ['skills', 'technical skills', 'competencies', 'technologies', 'tech stack']
    
    for line in lines:
        stripped = line.strip()
        
        line_lower = stripped.lower().rstrip(':').strip()
        if line_lower in skill_section_keywords:
            in_skills = True
            continue
        elif any(kw in line_lower for kw in skill_section_keywords):
            if ':' in stripped or len(stripped) < 30:
                in_skills = True
                continue
                
        if in_skills and any(kw in stripped.upper().rstrip(':') for kw in ['EXPERIENCE', 'WORK', 'PROJECTS', 'EDUCATION', 'CERTIFICATIONS']):
            in_skills = False
            continue
            
        if in_skills:
            if ',' in stripped:
                found_skills = [s.strip() for s in stripped.split(',') if s.strip() and len(s.strip()) > 1]
                skills.extend(found_skills)
            elif stripped.startswith(('•', '-', '›', '·', '⁃')):
                skill = stripped.lstrip('•-›·⁃ ').strip()
                if ':' in skill:
                    parts = skill.split(':')
                    category = parts[0].strip()
                    items = parts[1].strip()
                    if items:
                        for s in items.split(','):
                            s = s.strip()
                            if s:
                                skills.append(s)
                    elif category:
                        skills.append(category)
                elif skill:
                    skills.append(skill)
            elif '|' in stripped:
                found_skills = [s.strip() for s in stripped.split('|') if s.strip()]
                skills.extend(found_skills)
            elif stripped and not any(kw in stripped.upper() for kw in ['SKILLS', 'TECHNICAL', 'COMPETENCIES']):
                if len(stripped) < 50:
                    skills.append(stripped)
    
    return list(dict.fromkeys(skills))  # Remove duplicates, preserve order


def _extract_projects(text: str) -> list[dict[str, str]]:
    """Extract projects while preserving all original details."""
    projects = []
    lines = text.split('\n')
    
    in_projects = False
    current_project = {}
    
    project_headers = ['projects', 'project experience', 'personal projects', 'academic projects', 'key projects']
    
    for line in lines:
        stripped = line.strip()
        
        line_lower = stripped.lower().rstrip(':').strip()
        if line_lower in project_headers:
            in_projects = True
            continue
        elif any(kw in line_lower for kw in project_headers):
            if ':' in stripped or len(stripped) < 30:
                in_projects = True
                continue
            
        if in_projects and any(kw in stripped.upper().rstrip(':') for kw in ['EXPERIENCE', 'WORK', 'SKILLS', 
                                                                   'EDUCATION', 'CERTIFICATIONS', 'ACHIEVEMENTS']):
            in_projects = False
            if current_project:
                projects.append(current_project)
                current_project = {}
            continue
            
        if in_projects:
            if stripped.startswith(('•', '-', '›', '·', '⁃')):
                content = stripped.lstrip('•-›·⁃ ').strip()
                if content:
                    if current_project:
                        projects.append(current_project)
                    current_project = {"title": content, "description": []}
            elif current_project:
                if "description" not in current_project:
                    current_project["description"] = []
                current_project["description"].append(stripped)
            elif stripped and not any(kw in stripped.upper() for kw in ['PROJECT', 'ACADEMIC']):
                if len(stripped) > 5:
                    if current_project:
                        projects.append(current_project)
                    current_project = {"title": stripped, "description": []}
    
    if current_project:
        projects.append(current_project)
    
    return projects


def _extract_certifications(text: str) -> list[str]:
    """Extract certifications preserving original details."""
    certifications = []
    lines = text.split('\n')
    
    in_certifications = False
    certification_keywords = ['certification', 'certificate', 'licenses', 'credentials']
    
    for line in lines:
        stripped = line.strip()
        
        line_lower = stripped.lower().rstrip(':').strip()
        if line_lower in certification_keywords:
            in_certifications = True
            continue
        elif any(kw in line_lower for kw in certification_keywords):
            if ':' in stripped or len(stripped) < 30:
                in_certifications = True
                continue
                
        if in_certifications and any(kw in stripped.upper().rstrip(':') for kw in ['EXPERIENCE', 'WORK', 'SKILLS', 
                                                                          'EDUCATION', 'PROJECTS', 'ACHIEVEMENTS']):
            in_certifications = False
            continue
            
        if in_certifications:
            if stripped.startswith(('•', '-', '›', '·', '⁃')):
                cert = stripped.lstrip('•-›·⁃ ').strip()
                if cert:
                    certifications.append(cert)
            elif stripped and len(stripped) > 3:
                certifications.append(stripped)
    
    return certifications


def _extract_internships(text: str) -> list[dict[str, str]]:
    """Extract internships preserving all original details."""
    internships = []
    lines = text.split('\n')
    
    in_internships = False
    current_entry = {}
    
    for line in lines:
        stripped = line.strip()
        
        # Detect internships section
        if 'internship' in stripped.lower() and stripped.lower() in ['internships', 'internship experience']:
            in_internships = True
            continue
            
        # Detect section end
        if in_internships and any(kw in stripped.upper() for kw in ['EXPERIENCE', 'WORK', 'SKILLS', 
                                                                       'EDUCATION', 'PROJECTS', 'CERTIFICATIONS', 'ACHIEVEMENTS']):
            in_internships = False
            if current_entry:
                internships.append(current_entry)
                current_entry = {}
            continue
            
        if in_internships:
            if 'intern' in stripped.lower() or 'internship' in stripped.lower():
                if current_entry:
                    internships.append(current_entry)
                current_entry = {"title_company": stripped}
            elif current_entry:
                if stripped.startswith(('•', '-', '›', '·', '⁃')):
                    if "bullet_points" not in current_entry:
                        current_entry["bullet_points"] = []
                    current_entry["bullet_points"].append(stripped)
    
    if current_entry:
        internships.append(current_entry)
    
    return internships


def _extract_achievements(text: str) -> list[str]:
    """Extract achievements preserving original details."""
    achievements = []
    lines = text.split('\n')
    
    in_achievements = False
    achievement_keywords = ['achievement', 'awards', 'honors', 'recognition', 'accomplishment']
    
    for line in lines:
        stripped = line.strip()
        
        # Detect achievements section
        if any(kw in stripped.lower() for kw in achievement_keywords):
            if stripped.lower() in ['achievements', 'awards', 'honors', 'accomplishments']:
                in_achievements = True
                continue
                
        # Detect section end
        if in_achievements and any(kw in stripped.upper() for kw in ['EXPERIENCE', 'WORK', 'SKILLS', 
                                                                       'EDUCATION', 'PROJECTS', 'CERTIFICATIONS']):
            in_achievements = False
            continue
            
        if in_achievements:
            if stripped.startswith(('•', '-', '›', '·', '⁃')):
                ach = stripped.lstrip('•-›·⁃ ').strip()
                if ach:
                    achievements.append(ach)
            elif stripped:
                achievements.append(stripped)
    
    return achievements


def preserve_original_format(text: str) -> dict[str, Any]:
    """Analyze and preserve the original resume format for later comparison.
    
    Returns information about:
    - Section order
    - Formatting style
    - Key characteristics
    """
    lines = text.split('\n')
    
    # Detect section order
    section_order = []
    seen_sections = set()
    
    for line in lines[:50]:  # Check first 50 lines for section headers
        stripped = line.strip().upper()
        if stripped in ['PROFESSIONAL SUMMARY', 'CORE COMPETENCIES', 'TECHNICAL SKILLS',
                        'PROFESSIONAL EXPERIENCE', 'EXPERIENCE', 'WORK EXPERIENCE',
                        'EDUCATION', 'PROJECTS', 'CERTIFICATIONS', 'CERTIFICATES',
                        'ACHIEVEMENTS', 'AWARDS', 'SKILLS']:
            if stripped not in seen_sections:
                section_order.append(stripped)
                seen_sections.add(stripped)
    
    # Detect formatting style
    formatting = {
        "has_bullets": any(line.strip().startswith(('•', '-')) for line in lines),
        "has_headers": len(section_order) > 0,
        "uses_uppercase_name": any(line.strip().isupper() and len(line.strip()) < 50 and ':' not in line for line in lines[:3]),
    }
    
    return {
        "section_order": section_order,
        "formatting_style": formatting,
        "total_lines": len(lines),
        "characteristics": {
            "has_experience": any(kw in text.lower() for kw in ['experience', 'intern', 'work']),
            "has_education": any(kw in text.lower() for kw in ['education', 'university', 'college', 'b.tech', 'bachelor']),
            "has_skills": any(kw in text.lower() for kw in ['skills', 'technologies', 'tech stack']),
        }
    }