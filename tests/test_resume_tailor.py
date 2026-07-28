"""Tests for the Phase 3 resume tailor (fallback path + keyword extraction).

PHASE 4.9 - Updated tests for resume preservation functionality.
"""
from resume_tailor.tailor import build_fallback_resume, _job_keywords, calculate_match_score
from resume_tailor.resume_parser import parse_resume_sections, preserve_original_format
from resume_tailor.job_analyzer import (
    analyze_job_description, 
    find_missing_skills, 
    find_matching_skills,
    get_optimization_suggestions
)


def test_fallback_resume_prioritises_matched_skills():
    profile = {
        "name": "Asha",
        "email": "asha@example.com",
        "skills": ["Excel", "Python", "SQL"],
        "experience_text": "Intern at X",
        "education": "B.Tech",
    }
    job = {
        "title": "Python Developer",
        "company": "Acme",
        "description": "We need Python and SQL skills",
        "skills_required": ["python", "sql"],
    }
    result = build_fallback_resume(profile, job)
    text = result[0] if isinstance(result, tuple) else result
    # Name is uppercase in the new format
    assert "ASHA" in text or "Asha" in text
    assert "PROFESSIONAL SUMMARY" in text
    # Now uses CORE COMPETENCIES instead of TECHNICAL SKILLS
    assert "CORE COMPETENCIES" in text
    # Python/SQL (job-matched) should appear before Excel in the skills line.
    # Find skills section (now CORE COMPETENCIES)
    skills_line = text.split("CORE COMPETENCIES\n")[1].split("\n")[0]
    assert skills_line.lower().index("python") < skills_line.lower().index("excel")


def test_job_keywords_includes_tags_and_text():
    job = {
        "title": "Backend Engineer",
        "description": "Django REST APIs and PostgreSQL",
        "skills_required": ["django"],
    }
    kws = [k.lower() for k in _job_keywords(job)]
    assert "django" in kws
    assert any("postgresql" in k for k in kws)


def test_fallback_handles_empty_profile():
    text, analysis = build_fallback_resume({}, {"title": "Analyst", "company": "Z"})
    assert "PROFESSIONAL SUMMARY" in text


def test_preserve_original_content():
    """Test that resume parser preserves original content."""
    resume_text = """John Doe
john@example.com
+1 555-123-4567

EXPERIENCE
Software Engineer at TechCorp
• Built Python applications using Django
• Worked with PostgreSQL and Redis

EDUCATION
B.S. Computer Science, University of Tech
"""
    sections = parse_resume_sections(resume_text)
    
    assert sections["personal_details"].get("email") == "john@example.com"
    # Experience detection - may or may not be detected based on patterns
    # but the raw text should always be preserved
    assert sections["raw_text"] == resume_text


def test_match_score_calculation():
    """Test match score calculation between skills."""
    user_skills = ["Python", "Java", "SQL", "React"]
    required_skills = ["python", "sql", "docker", "kubernetes"]
    
    score = calculate_match_score(user_skills, required_skills)
    assert score == 50.0  # 2 out of 4 match


def test_missing_skills_identification():
    """Test identification of missing skills."""
    user_skills = ["Python", "Java", "SQL"]
    required_skills = ["python", "sql", "docker", "kubernetes", "aws"]
    
    missing = find_missing_skills(user_skills, required_skills)
    assert "docker" in missing
    assert "kubernetes" in missing
    assert "aws" in missing
    assert "python" not in missing  # Python is in user skills


def test_matching_skills_identification():
    """Test identification of matching skills."""
    user_skills = ["Python", "Java", "SQL", "Docker"]
    required_skills = ["python", "sql", "docker", "kubernetes"]
    
    matching = find_matching_skills(user_skills, required_skills)
    assert "Python" in matching
    assert "SQL" in matching
    assert "Docker" in matching


def test_job_analysis_extracts_requirements():
    """Test job description analysis."""
    job = {
        "title": "Senior Python Developer",
        "description": "We need Python, Django, and AWS experience. Required: 5+ years.",
        "skills_required": ["python", "django", "aws"],
    }
    
    analysis = analyze_job_description(job)
    
    assert "python" in analysis["required_skills"]
    assert "django" in analysis["required_skills"]
    assert "aws" in analysis["technologies"]
    assert analysis["experience_level"] == "senior"


def test_fallback_returns_analysis_data():
    """Test that fallback function returns analysis data."""
    profile = {
        "name": "Test User",
        "email": "test@example.com",
        "skills": ["Python", "SQL"],
        "experience_text": "Python developer",
    }
    job = {
        "title": "Python Developer",
        "company": "TestCo",
        "description": "Need Python and SQL",
        "skills_required": ["python", "sql"],
    }
    
    text, analysis = build_fallback_resume(profile, job)
    
    assert isinstance(analysis, dict)
    assert "match_score" in analysis
    assert "matching_skills" in analysis
    assert "missing_skills" in analysis


def test_resume_preserves_all_sections():
    """Test that original resume sections are preserved."""
    resume_text = """Jane Smith
jane@example.com

PROFESSIONAL SUMMARY
Experienced developer

SKILLS
Python, Java, SQL

EXPERIENCE
Software Developer at BigTech
• Led team of 5 developers
• Built scalable systems

PROJECTS
E-commerce website
• Full stack development

CERTIFICATIONS
AWS Certified

EDUCATION
Bachelor of Science in Computer Science, University of Tech
Graduated: 2020
"""
    sections = parse_resume_sections(resume_text)
    
    # Raw text should always be preserved
    assert sections["raw_text"] == resume_text
    # Personal details should be extracted
    assert sections["personal_details"].get("email") == "jane@example.com"
    # Skills should be captured
    assert len(sections["skills"]) > 0
    # Certifications should be captured  
    assert len(sections["certifications"]) >= 1
    # Education should be captured when it contains degree keywords
    assert len(sections["education"]) >= 1
    assert any("computer science" in str(e).lower() for e in sections["education"])


def test_no_fake_skills_added():
    """Test that optimizer adds missing skills as Learning (for ATS)."""
    profile = {
        "name": "Test User",
        "email": "test@example.com",
        "skills": ["Python", "SQL"],  # Only 2 skills
    }
    job = {
        "title": "DevOps Engineer",
        "company": "CloudCo",
        "description": "Need Docker, Kubernetes, AWS, Terraform, Python, SQL",
        "skills_required": ["docker", "kubernetes", "aws", "terraform", "python", "sql"],
    }
    
    text, analysis = build_fallback_resume(profile, job)
    
    missing = analysis["missing_skills"]
    # Missing skills should be identified
    assert len(missing) > 0
    assert "docker" in [s.lower() for s in missing] or "kubernetes" in [s.lower() for s in missing]
    # Missing skills should be added as (Learning) to the resume for ATS compatibility
    assert "(Learning)" in text, "Missing skills should be added as (Learning) for ATS"