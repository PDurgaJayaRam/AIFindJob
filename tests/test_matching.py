"""Tests for the Phase 2 lightweight pool scorer."""
from matching.scorer import score_job, rank_jobs


def test_skill_word_boundary_does_not_overmatch():
    # 'java' should not match 'javascript'
    result = score_job(
        job_text="We need a javascript developer",
        job_skills=["javascript"],
        user_skills=["java"],
        target_roles=[],
        is_fresher=False,
    )
    assert "java" not in result["matched_skills"]


def test_role_and_skill_boost_score():
    low = score_job(
        job_text="Marketing manager role",
        job_skills=[],
        user_skills=["python"],
        target_roles=["python developer"],
        is_fresher=False,
    )
    high = score_job(
        job_text="Python developer needed with python and sql",
        job_skills=["python", "sql"],
        user_skills=["python", "sql"],
        target_roles=["python developer"],
        is_fresher=False,
    )
    assert high["score"] > low["score"]
    assert high["role_match"] is True


def test_fresher_bonus_applies_only_when_relevant():
    fresher_job = score_job(
        job_text="Junior python developer, fresher friendly, entry level",
        job_skills=["python"],
        user_skills=["python"],
        target_roles=["python developer"],
        is_fresher=True,
    )
    senior_job = score_job(
        job_text="Senior python architect, 10 years experience",
        job_skills=["python"],
        user_skills=["python"],
        target_roles=["python developer"],
        is_fresher=True,
    )
    assert fresher_job["fresher_friendly"] is True
    assert senior_job["fresher_friendly"] is False
    assert fresher_job["score"] >= senior_job["score"]


def test_rank_orders_by_score_desc():
    jobs = [
        {"title": "Marketing", "description": "sales", "skills_required": []},
        {"title": "Python Developer", "description": "python sql", "skills_required": ["python", "sql"]},
    ]
    profile = {"skills": ["python", "sql"], "target_roles": ["python developer"], "is_fresher": False}
    ranked = rank_jobs(jobs, profile)
    assert ranked[0]["title"] == "Python Developer"
    assert ranked[0]["match"]["score"] >= ranked[1]["match"]["score"]
