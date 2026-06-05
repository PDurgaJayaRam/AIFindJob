"""Tests for the Phase 4 People-Finder (inference, scoring, outreach template)."""
from people_finder.email_patterns import infer_emails, score_email
from people_finder.outreach import template_draft
from people_finder.finder import guess_domain


def test_infer_emails_patterns():
    emails = infer_emails("Priya Sharma", "acme.com")
    assert "priya.sharma@acme.com" in emails
    assert "psharma@acme.com" in emails
    assert all(e.endswith("@acme.com") for e in emails)


def test_infer_emails_empty_inputs():
    assert infer_emails("", "acme.com") == []
    assert infer_emails("Priya", "") == []


def test_score_email_confidence_levels():
    assert score_email("a@b.com", True)["confidence"] == 0.5
    assert score_email("a@b.com", None)["confidence"] == 0.3
    assert score_email("a@b.com", False)["confidence"] == 0.0
    assert score_email("a@b.com", False)["status"] == "invalid_domain"


def test_guess_domain():
    assert guess_domain("Acme Corp") == "acmecorp.com"
    assert guess_domain("") == ""


def test_template_draft_contains_key_parts():
    profile = {"name": "Asha", "skills": ["Python", "SQL"]}
    job = {"title": "Data Analyst", "company": "Acme"}
    draft = template_draft(profile, job, "Priya")
    assert "Priya" in draft
    assert "Data Analyst" in draft
    assert "Acme" in draft
    assert "Asha" in draft
