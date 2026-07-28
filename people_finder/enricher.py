"""AI-powered contact enrichment + personalized outreach draft generation.

Uses the project's AI client (NVIDIA/OpenAI/DeepSeek) to:
1. Infer roles from search context
2. Score relevance to the target job
3. Classify contact type (recruiter / hiring manager / peer)
4. Generate personalized LinkedIn + email outreach drafts
"""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger("people_finder.enricher")

# Lazy import to avoid circular deps
_ai_client = None


def _get_ai():
    global _ai_client
    if _ai_client is None:
        try:
            from ai.ai_client import get_ai_client
            _ai_client = get_ai_client()
        except Exception as exc:
            logger.warning("AI client unavailable: %s", exc)
            _ai_client = False
    return _ai_client if _ai_client else None


async def enrich_contacts(
    contacts: list[dict[str, Any]],
    job_title: str,
    job_company: str,
    job_skills: list[str] = None,
) -> list[dict[str, Any]]:
    """Enrich contacts with AI-inferred roles, relevance scores, and contact classification.

    Falls back to heuristic classification if AI is unavailable.
    """
    if not contacts:
        return contacts

    ai = _get_ai()
    if not ai:
        logger.info("AI unavailable, using heuristic enrichment")
        return _heuristic_enrich(contacts, job_title, job_company, job_skills or [])

    try:
        # Build a compact prompt with only the fields we need
        compact = []
        for c in contacts:
            compact.append({
                "name": c.get("name", ""),
                "role": c.get("role", ""),
                "source": c.get("source", ""),
                "linkedin_url": c.get("linkedin_url", ""),
                "email": c.get("email", ""),
                "phone": c.get("phone", ""),
            })

        prompt = f"""You are analyzing contacts found at "{job_company}" for someone applying to "{job_title}".

Job skills: {', '.join((job_skills or [])[:10])}

For each contact, determine:
1. "role": their actual job title if inferable from context (keep existing if already set)
2. "relevance": "high" if their role matches the job, "medium" if related, "low" if unrelated
3. "contact_type": one of "recruiter", "hiring_manager", "hr", "peer", "unknown"
4. "skills": any skills mentioned or inferred (empty list if unknown)

Contacts:
{json.dumps(compact, indent=2)}

Return a JSON array with the same contacts, adding the new fields. Return ONLY valid JSON."""

        response = await ai.chat_completion(
            messages=[
                {"role": "system", "content": "You are a contact analyst. Return ONLY valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.3,
            max_tokens=3000,
            json_mode=True,
        )

        enriched = json.loads(response)
        if isinstance(enriched, list) and len(enriched) == len(contacts):
            for i, e in enumerate(enriched):
                contacts[i]["role"] = e.get("role") or contacts[i].get("role", "")
                contacts[i]["relevance"] = e.get("relevance", "low")
                contacts[i]["contact_type"] = e.get("contact_type", "unknown")
                contacts[i]["skills"] = e.get("skills", [])
            logger.info("AI enriched %d contacts", len(contacts))
            return contacts

    except Exception as exc:
        logger.warning("AI enrichment failed, falling back to heuristics: %s", exc)

    return _heuristic_enrich(contacts, job_title, job_company, job_skills or [])


def _heuristic_enrich(
    contacts: list[dict[str, Any]],
    job_title: str,
    job_company: str,
    job_skills: list[str],
) -> list[dict[str, Any]]:
    """Rule-based enrichment when AI is unavailable."""
    import re
    job_words = set(re.findall(r'\w+', job_title.lower())) - {'a', 'an', 'the', 'at', 'in', 'for', 'and', 'or', 'of', 'to', 'with'}

    for c in contacts:
        # Classify contact type from role/source
        role = (c.get("role") or "").lower()
        source = (c.get("source") or "").lower()
        combined = role + " " + source

        if any(w in combined for w in ["recruit", "talent", "hiring", "acquisition"]):
            c["contact_type"] = "recruiter"
        elif any(w in combined for w in ["hr", "human resource", "people ops"]):
            c["contact_type"] = "hr"
        elif any(w in combined for w in ["founder", "ceo", "cto", "vp", "director", "head", "lead"]):
            c["contact_type"] = "hiring_manager"
        elif any(w in combined for w in ["engineer", "developer", "architect", "designer", "analyst"]):
            c["contact_type"] = "peer"
        else:
            c["contact_type"] = c.get("contact_type", "unknown")

        # Score relevance
        role_lower = c.get("role", "").lower()
        matches = sum(1 for w in job_words if w in role_lower)
        if matches >= 2:
            c["relevance"] = "high"
        elif matches >= 1:
            c["relevance"] = "medium"
        else:
            c["relevance"] = c.get("relevance", "low")

        if not c.get("skills"):
            c["skills"] = []

    return contacts


async def generate_outreach_drafts(
    contacts: list[dict[str, Any]],
    job_data: dict[str, Any],
    user_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    """Generate personalized outreach messages for each contact.

    For each contact, produces:
    - outreach_linkedin: Short LinkedIn connection message (<300 chars)
    - outreach_email_subject: Email subject line
    - outreach_email_body: Full email body

    Falls back to templates if AI is unavailable.
    """
    if not contacts:
        return contacts

    ai = _get_ai()
    if not ai:
        logger.info("AI unavailable, using template outreach")
        return _template_outreach(contacts, job_data, user_profile)

    # Process in batches of 5 to avoid token limits
    batch_size = 5
    for i in range(0, len(contacts), batch_size):
        batch = contacts[i:i + batch_size]
        try:
            compact = []
            for c in batch:
                compact.append({
                    "name": c.get("name", "there"),
                    "role": c.get("role", ""),
                    "contact_type": c.get("contact_type", "unknown"),
                })

            prompt = f"""Generate personalized outreach messages for a job candidate contacting people at "{job_data.get('company', '')}".

Candidate: {user_profile.get('name', 'Candidate')}
Target role: {job_data.get('title', 'the position')}
Key skills: {', '.join((job_data.get('skills', []) or [])[:8])}

For each contact, generate:
1. "outreach_linkedin": LinkedIn connection request message (under 250 chars, personalized, professional)
2. "outreach_email_subject": Email subject line (specific to the role/company)
3. "outreach_email_body": Email body (3-5 sentences, professional, mentions specific details)

Contact types to personalize for:
- recruiter: Ask about the specific role, mention qualifications
- hiring_manager: Express interest in joining their team
- peer: Ask for advice or referral, share common ground
- hr: General inquiry about the role
- unknown: Professional networking message

Contacts:
{json.dumps(compact, indent=2)}

Return a JSON array matching the contacts. Return ONLY valid JSON."""

            response = await ai.chat_completion(
                messages=[
                    {"role": "system", "content": "You are a professional networking expert. Return ONLY valid JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=2000,
                json_mode=True,
            )

            drafts = json.loads(response)
            if isinstance(drafts, list) and len(drafts) == len(batch):
                for j, d in enumerate(drafts):
                    batch[j]["outreach_linkedin"] = d.get("outreach_linkedin", "")
                    batch[j]["outreach_email_subject"] = d.get("outreach_email_subject", "")
                    batch[j]["outreach_email_body"] = d.get("outreach_email_body", "")
                logger.info("Generated outreach drafts for batch %d-%d", i, i + len(batch))

        except Exception as exc:
            logger.warning("AI outreach generation failed for batch: %s", exc)
            _template_outreach_batch(batch, job_data, user_profile)

    # Fill any remaining contacts without drafts
    for c in contacts:
        if not c.get("outreach_linkedin"):
            _fill_single_template(c, job_data, user_profile)

    return contacts


def _template_outreach(
    contacts: list[dict[str, Any]],
    job_data: dict[str, Any],
    user_profile: dict[str, Any],
) -> list[dict[str, Any]]:
    for c in contacts:
        _fill_single_template(c, job_data, user_profile)
    return contacts


def _template_outreach_batch(
    batch: list[dict[str, Any]],
    job_data: dict[str, Any],
    user_profile: dict[str, Any],
):
    for c in batch:
        _fill_single_template(c, job_data, user_profile)


def _fill_single_template(c: dict, job_data: dict, user_profile: dict):
    name = c.get("name", "there")
    company = job_data.get("company", "your company")
    title = job_data.get("title", "the position")
    skills = (job_data.get("skills", []) or [])[:5]
    skills_str = ", ".join(skills) if skills else "relevant technologies"
    first_name = user_profile.get("name", "I").split()[0]
    contact_type = c.get("contact_type", "unknown")

    if contact_type == "recruiter":
        linkedin = f"Hi {name}, I noticed you're recruiting at {company}. I'm very interested in the {title} role and believe my background in {skills_str} would be a great fit. Would love to connect and learn more!"
        subject = f"Interest in {title} Position at {company}"
        body = f"Dear {name},\n\nI came across the {title} opening at {company} and wanted to reach out directly. With my experience in {skills_str}, I believe I could be a strong candidate for this role.\n\nI'd appreciate the opportunity to discuss how my skills align with your team's needs. Could we schedule a brief call?\n\nBest regards,\n{first_name}"
    elif contact_type == "hiring_manager":
        linkedin = f"Hi {name}, I'm impressed by the work your team is doing at {company}. I'm a {skills_str} professional looking for new opportunities and would love to learn about the {title} role on your team."
        subject = f"Exploring {title} Opportunities at {company}"
        body = f"Dear {name},\n\nI've been following {company}'s work and I'm very interested in joining your team. My background in {skills_str} aligns well with what you're building.\n\nI'd love to learn more about the {title} position and discuss how I can contribute to your team's goals.\n\nLooking forward to connecting.\n\nBest,\n{first_name}"
    elif contact_type == "peer":
        linkedin = f"Hi {name}, I see you're a fellow {skills_str} professional at {company}. I'm exploring opportunities there and would love to hear about your experience. Any advice would be greatly appreciated!"
        subject = f"Quick Question About {company}"
        body = f"Hi {name},\n\nI hope this message finds you well. I'm a {skills_str} professional exploring opportunities at {company} and noticed your work there.\n\nWould you be open to a quick chat about your experience? Any insights about the team or culture would be incredibly helpful.\n\nThanks in advance!\n{first_name}"
    else:
        linkedin = f"Hi {name}, I'm interested in opportunities at {company} and wanted to connect. I have experience in {skills_str} and would love to learn more about the {title} role."
        subject = f"Networking - {title} at {company}"
        body = f"Dear {name},\n\nI hope you're doing well. I'm reaching out because I'm very interested in the {title} position at {company}. My background in {skills_str} makes me a strong candidate.\n\nI'd welcome the chance to discuss this opportunity further.\n\nBest regards,\n{first_name}"

    c["outreach_linkedin"] = linkedin
    c["outreach_email_subject"] = subject
    c["outreach_email_body"] = body
