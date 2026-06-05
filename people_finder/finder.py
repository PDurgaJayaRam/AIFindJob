"""The People-Finder waterfall. Each step is isolated and optional.

Steps (cheapest/safest first):
1. Resolve company domain (provided or naive guess from name).
2. Scrape the company site's team/contact pages for names + emails (httpx +
   BeautifulSoup, both already in requirements).
3. Infer email patterns for any names without emails.
4. Verify inferred emails via free MX lookup (optional dnspython).
5. (Optional) public social search via OSINT tools (lazy imports) — skipped if
   not installed; never breaks the flow.

Returns contacts with confidence scores. Public data only.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from people_finder.email_patterns import infer_emails, domain_has_mx, score_email

logger = logging.getLogger("people_finder.finder")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TEAM_PATHS = ["", "about", "team", "about-us", "company", "contact", "people"]


def guess_domain(company: str) -> str:
    """Naive domain guess from a company name (best-effort, public)."""
    slug = re.sub(r"[^a-z0-9]", "", (company or "").lower())
    return f"{slug}.com" if slug else ""


async def scrape_company_emails(domain: str, timeout: float = 12.0) -> list[str]:
    """Collect emails visible on common company pages. Best-effort, isolated."""
    if not domain:
        return []
    found: set[str] = set()
    base = f"https://{domain}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JOBFinderBot/1.0)"}
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for path in _TEAM_PATHS:
            url = f"{base}/{path}".rstrip("/")
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                for m in _EMAIL_RE.findall(resp.text):
                    if m.lower().endswith(domain.lower()):
                        found.add(m.lower())
            except Exception as exc:
                logger.debug("scrape %s failed: %s", url, exc)
                continue
    return sorted(found)


async def find_contacts(
    company: str,
    domain: str = "",
    candidate_names: list[str] | None = None,
) -> dict[str, Any]:
    """Run the waterfall and return contacts with confidence scores."""
    domain = (domain or "").strip().lower().lstrip("@") or guess_domain(company)
    contacts: list[dict[str, Any]] = []

    # Step 2: real emails visible on the company site (highest confidence).
    try:
        scraped = await scrape_company_emails(domain)
    except Exception as exc:
        logger.info("company scrape failed: %s", exc)
        scraped = []
    for email in scraped:
        contacts.append({
            "name": "",
            "email": email,
            "confidence": 0.8,
            "status": "published_on_site",
            "source": "company_site",
        })

    # Steps 3+4: infer + verify emails for provided names.
    mx_ok = domain_has_mx(domain) if domain else False
    for name in (candidate_names or []):
        for email in infer_emails(name, domain):
            scored = score_email(email, mx_ok)
            scored.update({"name": name, "source": "inferred"})
            contacts.append(scored)

    contacts.sort(key=lambda c: c.get("confidence", 0), reverse=True)
    return {
        "company": company,
        "domain": domain,
        "mx_verified": mx_ok,
        "contacts": contacts,
        "note": "Public data only. Inferred emails are guesses — verify before sending.",
    }
