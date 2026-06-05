"""Tests for the Phase 3 resume tailor (fallback path + keyword extraction)."""
from resume_tailor.tailor import build_fallback_resume, _job_keywords


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
    text = build_fallback_resume(profile, job)
    assert "Asha" in text
    assert "PROFESSIONAL SUMMARY" in text
    assert "TECHNICAL SKILLS" in text
    # Python/SQL (job-matched) should appear before Excel in the skills line.
    skills_line = text.split("TECHNICAL SKILLS\n")[1].split("\n")[0]
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
    text = build_fallback_resume({}, {"title": "Analyst", "company": "Z"})
    assert "PROFESSIONAL SUMMARY" in text
