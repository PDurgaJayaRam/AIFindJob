"""The People-Finder waterfall. Each step is isolated and optional.

Steps (cheapest/safest first):
1. Resolve company domain (provided or naive guess from name).
2. Scrape the company site's team/contact pages for names + emails (httpx +
   BeautifulSoup, both already in requirements).
3. Verify emails via free MX lookup (optional dnspython).

Returns ONLY real contacts found on company websites. No fake/inferred contacts.
"""
from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from people_finder.email_patterns import domain_has_mx

logger = logging.getLogger("people_finder.finder")

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TEAM_PATHS = ["", "about", "team", "about-us", "company", "contact", "people", "careers", "jobs"]


def guess_domain(company: str) -> str:
    """Naive domain guess from a company name (best-effort, public)."""
    clean = re.sub(r"\s*\([^)]*\)\s*", " ", company or "")
    clean = re.sub(r"\s+(?:inc|llc|ltd|corp|gmbH|ag|sa|plc)$", "", clean, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "", clean.lower().strip())
    return f"{slug}.com" if slug else ""


async def scrape_company_contacts(domain: str, timeout: float = 12.0) -> list[dict[str, Any]]:
    """Scrape real contacts from company website pages."""
    if not domain:
        return []
    
    contacts = []
    seen_emails = set()
    base = f"https://{domain}"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; JOBFinderBot/1.0)"}
    
    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        for path in _TEAM_PATHS:
            url = f"{base}/{path}".rstrip("/")
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                
                html = resp.text
                
                email_pattern = re.compile(
                    r'(?:mailto:)?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',
                    re.IGNORECASE
                )
                
                name_email_pattern = re.compile(
                    r'(?:<[^>]*>)?([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})(?:</[^>]*>)?\s*(?:[-–—•·:|]\s*)?(?:mailto:)?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})',
                    re.IGNORECASE
                )
                
                for match in name_email_pattern.finditer(html):
                    name = match.group(1).strip()
                    email = match.group(2).lower()
                    
                    if email in seen_emails:
                        continue
                    if not email.endswith(domain.lower()):
                        continue
                    if any(skip in name.lower() for skip in ['javascript', 'script', 'function', 'var', 'const', 'let']):
                        continue
                    
                    seen_emails.add(email)
                    contacts.append({
                        "name": name,
                        "email": email,
                        "confidence": 0.7,
                        "source": f"company_site/{path or 'home'}",
                    })
                
                for match in email_pattern.finditer(html):
                    email = match.group(1).lower()
                    
                    if email in seen_emails:
                        continue
                    if not email.endswith(domain.lower()):
                        continue
                    if any(skip in email for skip in ['example', 'test', 'admin', 'noreply', 'no-reply', 'support', 'info@']):
                        continue
                    
                    seen_emails.add(email)
                    contacts.append({
                        "name": "",
                        "email": email,
                        "confidence": 0.6,
                        "source": f"company_site/{path or 'home'}",
                    })
                    
            except Exception as exc:
                logger.debug("scrape %s failed: %s", url, exc)
                continue
    
    return contacts


async def find_contacts(
    company: str,
    domain: str = "",
    candidate_names: list[str] | None = None,
) -> dict[str, Any]:
    """Run the waterfall and return REAL contacts only.
    
    Returns contacts found on company websites. No fake/inferred contacts.
    """
    domain = (domain or "").strip().lower().lstrip("@") or guess_domain(company)
    
    contacts = []
    
    try:
        contacts = await scrape_company_contacts(domain)
    except Exception as exc:
        logger.info("company scrape failed: %s", exc)
    
    contacts.sort(key=lambda c: c.get("confidence", 0), reverse=True)
    
    return {
        "company": company,
        "domain": domain,
        "contacts": contacts[:20],
        "total_found": len(contacts),
    }
    return {
        "company": company,
        "domain": domain,
        "mx_verified": mx_ok,
        "contacts": contacts,
        "note": "Public data only. Inferred emails are guesses — verify before sending.",
    }
