"""LinkedIn API client wrapper using open-linkedin-api library.

This module provides a clean interface to LinkedIn's Voyager API endpoints
for fetching real employee data at companies. Falls back gracefully if
the library is not installed or credentials are missing.
"""
from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("people_finder.linkedin_api_client")

# Lazy import - only load when needed
_linkedin_api = None
_api_initialized = False


def _get_api():
    """Get or initialize the LinkedIn API client."""
    global _linkedin_api, _api_initialized

    if _api_initialized:
        return _linkedin_api

    _api_initialized = True

    try:
        from open_linkedin_api import Linkedin

        email = os.environ.get("LINKEDIN_EMAIL", "").strip()
        password = os.environ.get("LINKEDIN_PASSWORD", "").strip()

        if not email or not password:
            logger.info("[LinkedIn API] No credentials configured (LINKEDIN_EMAIL/LINKEDIN_PASSWORD)")
            return None

        logger.info("[LinkedIn API] Initializing with email: %s...", email[:3] + "***")
        _linkedin_api = Linkedin(email, password)
        logger.info("[LinkedIn API] Client initialized successfully")
        return _linkedin_api

    except ImportError:
        logger.warning("[LinkedIn API] open-linkedin-api not installed. Run: pip install open-linkedin-api")
        return None
    except Exception as exc:
        logger.error("[LinkedIn API] Failed to initialize: %s", exc)
        return None


async def search_people_at_company(
    company: str,
    keyword: str = "",
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Search for people at a company using LinkedIn's Voyager API.

    Args:
        company: Company name to search for
        keyword: Additional keyword to filter (e.g., job title)
        limit: Maximum number of results

    Returns:
        List of dicts with keys: name, role, linkedin_url, location, company, source
    """
    api = _get_api()
    if not api:
        return []

    try:
        # Build search query
        query = company
        if keyword:
            query = f"{keyword} {company}"

        logger.info("[LinkedIn API] Searching people: '%s'", query)

        # Use raw API call to get search results
        # The library's search_people method has parsing issues, so we use raw API
        from urllib.parse import quote

        results = []
        start = 0
        count = min(limit, 25)  # LinkedIn limits to ~25 per page

        while len(results) < limit:
            # Build the GraphQL query
            variables = (
                f"(start:{start},"
                f"origin:GLOBAL_SEARCH_HEADER,"
                f"query:("
                f"keywords:{quote(query)},"
                f"flagshipSearchIntent:SEARCH_SRP,"
                f"queryParameters:List((key:resultType,value:List(PEOPLE))),"
                f"includeFiltersInResponse:false))"
            )
            query_id = "voyagerSearchDashClusters.b0928897b71bd00a5a7291755dcd64f0"

            res = api._fetch(f"/graphql?variables={variables}&queryId={query_id}")

            if res.status_code != 200:
                logger.warning("[LinkedIn API] Search returned status %d", res.status_code)
                break

            data = res.json()
            clusters = data.get("data", {}).get("searchDashClustersByAll", {})
            elements = clusters.get("elements", [])

            if not elements:
                break

            for cluster in elements:
                items = cluster.get("items", [])
                for item in items:
                    entity = item.get("item", {}).get("entityResult", {})
                    if not entity:
                        continue

                    name = entity.get("title", {}).get("text", "").strip()
                    if not name:
                        continue

                    jobtitle = entity.get("primarySubtitle", {}).get("text", "")
                    location = entity.get("secondarySubtitle", {}).get("text", "")

                    # Extract public identifier from entityUrn
                    # Format: urn:li:fsd_profile:(ACoAAFO5M0cBsEYe4z98ELvE7JUundg_pNhsRnE,SEARCH_SRP,DEFAULT)
                    entity_urn = entity.get("entityUrn", "")
                    public_id = ""
                    if "fsd_profile:" in entity_urn:
                        # Extract just the profile ID (first part before comma)
                        profile_part = entity_urn.split("fsd_profile:")[-1]
                        public_id = profile_part.split(",")[0].strip("()")

                    # Build LinkedIn URL
                    linkedin_url = ""
                    if public_id:
                        linkedin_url = f"https://www.linkedin.com/in/{public_id}"

                    # Determine relevance based on jobtitle
                    relevance = _assess_relevance(jobtitle, company)
                    contact_type = _classify_contact_type(jobtitle)

                    results.append({
                        "name": name,
                        "role": jobtitle,
                        "company": company,
                        "email": "",
                        "linkedin_url": linkedin_url,
                        "phone": "",
                        "photo_url": "",
                        "location": location,
                        "relevance": relevance,
                        "skills": [],
                        "contact_type": contact_type,
                        "is_recruiter": contact_type == "recruiter",
                        "is_hiring_manager": contact_type == "hiring_manager",
                        "verified": True,
                        "source": "linkedin_voyager_api",
                        "confidence": 0.90,
                    })

                    logger.info("[LinkedIn API] Found: %s | %s | %s", name, jobtitle[:50], linkedin_url)

                    if len(results) >= limit:
                        break

            # Check if there are more pages
            paging = clusters.get("paging", {})
            total = paging.get("total", 0)
            start += count

            if start >= total or len(results) >= limit:
                break

            # Rate limit - wait between pages
            import asyncio
            await asyncio.sleep(2)

        logger.info("[LinkedIn API] Found %d contacts for '%s'", len(results), company)
        return results

    except Exception as exc:
        error_msg = str(exc)
        if "CHALLENGE" in error_msg.upper():
            logger.error("[LinkedIn API] Got CHALLENGE - LinkedIn is blocking the request. Try logging in manually in browser first.")
        elif "401" in error_msg or "403" in error_msg:
            logger.error("[LinkedIn API] Auth failed (%s). Check LINKEDIN_EMAIL/LINKEDIN_PASSWORD.", error_msg[:20])
        else:
            logger.error("[LinkedIn API] Search failed: %s", exc)
        return []


async def get_profile_info(linkedin_url: str) -> dict[str, Any] | None:
    """Get detailed profile info from a LinkedIn URL.

    Args:
        linkedin_url: Full LinkedIn profile URL or public ID

    Returns:
        Dict with profile details, or None if failed
    """
    api = _get_api()
    if not api:
        return None

    try:
        # Extract public ID from URL
        public_id = linkedin_url
        if "linkedin.com/in/" in linkedin_url:
            public_id = linkedin_url.split("/in/")[-1].rstrip("/").split("?")[0]

        logger.info("[LinkedIn API] Getting profile: %s", public_id)

        profile = api.get_profile(public_id)
        if not profile:
            return None

        # Profile has firstName, lastName, headline, locationName, etc.
        first_name = profile.get("firstName", "")
        last_name = profile.get("lastName", "")
        name = f"{first_name} {last_name}".strip()
        headline = profile.get("headline", "")
        location = profile.get("locationName", "")
        industry = profile.get("industryName", "")
        summary = profile.get("summary", "")

        # Get contact info separately
        contact_info = {}
        try:
            contact_info = api.get_profile_contact_info(public_id) or {}
        except Exception:
            pass

        email = contact_info.get("email_address", "")
        phone_numbers = contact_info.get("phone_numbers", [])
        phone = phone_numbers[0] if phone_numbers else ""

        return {
            "name": name,
            "role": headline,
            "email": email,
            "phone": phone,
            "location": location,
            "industry": industry,
            "summary": summary[:500] if summary else "",
            "linkedin_url": linkedin_url,
        }

    except Exception as exc:
        logger.error("[LinkedIn API] Failed to get profile %s: %s", linkedin_url, exc)
        return None


async def get_company_employees(
    company: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Get employees of a company using LinkedIn search.

    Args:
        company: Company name
        limit: Maximum results

    Returns:
        List of employee dicts
    """
    return await search_people_at_company(company, limit=limit)


def _assess_relevance(headline: str, company: str) -> str:
    """Assess how relevant a person is for job outreach."""
    headline_lower = (headline or "").lower()

    # High relevance - directly involved in hiring
    high_keywords = ["recruiter", "talent", "hiring", "hr", "human resources",
                     "people ops", "talent acquisition", "recruitment"]
    if any(kw in headline_lower for kw in high_keywords):
        return "high"

    # Medium relevance - could be useful contacts
    medium_keywords = ["engineer", "developer", "manager", "lead", "director",
                       "head", "vp", "cto", "ceo", "founder"]
    if any(kw in headline_lower for kw in medium_keywords):
        return "medium"

    return "low"


def _classify_contact_type(headline: str) -> str:
    """Classify contact type based on headline."""
    headline_lower = (headline or "").lower()

    if any(kw in headline_lower for kw in ["recruiter", "talent", "hiring", "recruitment"]):
        return "recruiter"
    if any(kw in headline_lower for kw in ["hr", "human resources", "people ops"]):
        return "hr"
    if any(kw in headline_lower for kw in ["hiring manager", "team lead", "engineering manager"]):
        return "hiring_manager"
    if any(kw in headline_lower for kw in ["cto", "ceo", "founder", "co-founder"]):
        return "executive"
    if any(kw in headline_lower for kw in ["engineer", "developer", "software"]):
        return "engineer"

    return "unknown"
