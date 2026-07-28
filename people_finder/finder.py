"""Multi-source people finder — chains free sources to find real contacts.

Waterfall (cheapest/safest first):
1. Google search — find company domain, LinkedIn page, public email listings
2. Company website scrape — /about, /team, /contact pages for emails
3. LinkedIn via Google — find employee names from cached LinkedIn results
4. Email pattern generation — guess emails from names + domain, verify via MX
5. Job description parse — extract recruiter names, apply emails, HR contacts
6. Scout social media — Instagram, TikTok, GitHub, YouTube, Twitch, Pinterest, Linktree

Returns ONLY real contacts. Inferred emails are marked as guesses.
"""
from __future__ import annotations

import asyncio
import logging
import random
import re
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from people_finder.email_patterns import domain_has_mx, infer_emails, score_email, verify_emails_for_contact

logger = logging.getLogger("people_finder.finder")


async def _discover_via_scout(
    company: str,
    domain: str = "",
    job_title: str = "",
    location: str = "",
) -> list[dict[str, Any]]:
    """Wrapper for Scout social media discovery. Returns contacts in people_finder format."""
    try:
        from people_finder.scout_integration import discover_via_social_media
        return await discover_via_social_media(
            company=company,
            domain=domain,
            job_title=job_title,
            location=location,
        )
    except Exception as exc:
        logger.warning("[Scout] Social media discovery failed: %s", exc)
        return []

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_TEAM_PATHS = ["", "about", "team", "about-us", "company", "contact", "people",
               "careers", "jobs", "contact-us", "get-in-touch", "our-team",
               "leadership", "staff", "employees"]
_DOMAIN_SUFFIXES = [".com", ".in", ".co.in", ".io", ".org", ".net", ".co", ".tech", ".ai"]

# Emails to always reject (service/error addresses, not real people)
_SKIP_EMAILS = {
    "error-lite@duckduckgo.com", "noreply@duckduckgo.com",
    "privacy@duckduckgo.com", "support@duckduckgo.com",
}

# Generic emails that are company-level, not person-level
_GENERIC_EMAILS = {
    "info@", "contact@", "hello@", "sales@", "mail@", "admin@", "support@", "noreply@",
    "hr@", "careers@", "hiring@", "recruitment@", "talent@", "jobs@", "apply@",
    "enquiry@", "enquiries@", "postmaster@", "webmaster@", "abuse@",
    "legal@", "press@", "media@", "marketing@", "partners@",
    "feedback@", "help@", "billing@", "accounts@", "finance@",
    "office@", "reception@", "general@", "team@", "staff@",
    "devnull@", "bounce@", "daemon@", "spam@", "unsubscribe@",
    # Job board pattern emails (not real people)
    "apply.now@", "apply.line@", "date.line@",
}


def _is_generic_email(email: str | None) -> bool:
    """Check if an email is a generic department mailbox, not a real person."""
    if not email:
        return False
    email_lower = email.lower()
    return any(email_lower.startswith(prefix) for prefix in _GENERIC_EMAILS)

# Words that are NOT person names (UI text, navigation, departments, locations, etc.)
_SKIP_NAME_WORDS = {
    # UI / navigation
    "javascript", "script", "function", "var", "const", "let",
    "copyright", "privacy", "terms", "cookie", "menu", "search",
    "login", "sign", "register", "toggle", "navigation",
    "apple", "user", "agreement", "password", "forgot",
    "linkedin", "sign in", "join", "home", "error", "page",
    "loading", "settings", "profile", "account", "help",
    "click", "here", "read", "more", "view", "all", "show",
    "hide", "close", "open", "next", "previous", "back",
    "apply", "now", "date", "line", "download", "upload",
    "share", "like", "follow", "subscribe", "comment",
    "post", "article", "blog", "news", "update",
    # Departments / roles (not person names)
    "careers", "career", "opportunities", "opportunity", "personnel",
    "recruitment", "recruiting", "hiring", "talent", "acquisition",
    "human", "resources", "department", "team", "company", "corporation",
    "corporate", "enterprise", "group", "organization", "system",
    "solutions", "services", "consulting", "technologies", "technology",
    "innovations", "ventures", "industries", "global", "international",
    "founder", "chief", "officer", "director", "manager", "lead",
    "head", "vice", "president", "executive", "senior", "junior",
    "engineer", "developer", "analyst", "specialist", "coordinator",
    "assistant", "associate", "intern", "trainee", "consultant",
    # Locations / geography
    "county", "city", "state", "district", "region", "province",
    "hyderabad", "bangalore", "mumbai", "chennai", "pune", "delhi",
    "india", "united", "states", "america", "london", "tokyo",
    "china", "japan", "korea", "france", "germany", "spain",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "hong", "kong", "singapore", "dubai", "abu", "dhabi",
    # Generic entities
    "unified", "national", "federal", "state", "public", "private",
    "limited", "incorporated", "associates", "partners", "group",
    "board", "council", "committee", "agency", "bureau", "office",
    "institute", "foundation", "college", "university", "school",
    "hospital", "medical", "health", "bank", "financial",
    # Content / media words
    "the", "this", "that", "with", "from", "about", "contact",
    "support", "info", "general", "specific", "related",
    "official", "music", "video", "image", "photo", "picture",
    "online", "courses", "training", "programs", "classes",
    "clinical", "case", "discussions", "cases", "studies",
    "dictionary", "wikipedia", "encyclopedia", "reference",
    "love", "hate", "best", "worst", "top", "bottom",
    "ranking", "rated", "review", "feedback", "survey",
    "brochures", "catalog", "catalogue", "portfolio",
    "also", "and", "or", "but", "not", "for", "with",
    "what", "how", "why", "when", "where", "who",
    "faq", "help", "guide", "tutorial", "instructions",
    # Product / brand names
    "oracle", "database", "support", "services", "engineering",
    "starring", "film", "movie", "show", "episode", "season",
    "actor", "actress", "cast", "character", "role",
    "store", "shop", "buy", "price", "cost", "free",
    "mode", "devices", "find", "lost", "imagine",
    # Company-specific (from bad results)
    "capgemini", "apple", "google", "microsoft", "amazon",
    "netflix", "spotify", "uber", "lyft", "airbnb",
}

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.2 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
]

_last_request_time = 0.0
_MIN_DELAY = 1.0


async def _search_domain_via_bing(company: str, client: httpx.AsyncClient) -> str:
    """Search Bing for company website as fallback when domain resolution fails."""
    try:
        _throttle()
        url = f"https://www.bing.com/search?q={quote_plus(company + ' official website')}&count=5"
        headers = {"User-Agent": _random_ua(), "Accept": "text/html",
                   "Accept-Language": "en-US,en;q=0.9"}
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code != 200:
            return ""

        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")

        skip_domains = ["google.", "facebook.", "indeed.", "glassdoor.",
                        "linkedin.", "twitter.", "youtube.", "wikipedia.",
                        "naukri.", "monster.", "shine.", "bing.", "duckduckgo."]

        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"https?://(?:www\.)?([^/]+)", href)
            if m:
                domain = m.group(1)
                if not any(sd in domain for sd in skip_domains):
                    # Verify the domain is accessible
                    try:
                        test_resp = await client.get(f"https://{domain}", timeout=5, follow_redirects=True)
                        if test_resp.status_code == 200:
                            logger.info("Found domain via Bing for %s: %s", company, domain)
                            return domain
                    except Exception:
                        continue
    except Exception as exc:
        logger.debug("Bing domain search failed for %s: %s", company, exc)
    return ""


def _random_ua() -> str:
    return random.choice(_USER_AGENTS)


def _throttle():
    """Enforce minimum delay between requests to avoid blocking."""
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed + random.uniform(0.2, 0.5))
    _last_request_time = time.monotonic()


def guess_domain(company: str) -> str:
    """Naive domain guess from a company name."""
    clean = re.sub(r"\s*\([^)]*\)\s*", " ", company or "")
    clean = re.sub(r"\s+(?:inc|llc|ltd|corp|gmbH|ag|sa|plc|consulting|technologies|solutions|services|pvt|ltd)$", "", clean, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "", clean.lower().strip())
    return f"{slug}.com" if slug else ""


async def _probe_domain(domain: str, client: httpx.AsyncClient) -> bool:
    """Check if a domain responds with HTTP 200."""
    if not domain:
        return False
    try:
        resp = await client.get(f"https://{domain}", timeout=5, follow_redirects=True)
        return resp.status_code == 200
    except Exception:
        return False


async def resolve_company_domain(company: str, client: httpx.AsyncClient) -> str:
    """Try multiple domain guesses until one responds. Free, no API needed."""
    clean = re.sub(r"\s*\([^)]*\)\s*", " ", company or "")
    clean = re.sub(
        r"\s+(?:inc|llc|ltd|corp|gmbh|ag|sa|plc|consulting|technologies|solutions|services|pvt|tech)$",
        "", clean, flags=re.IGNORECASE,
    )
    slug = re.sub(r"[^a-z0-9]+", "", clean.lower().strip())
    if not slug:
        return ""

    suffixes = [".com", ".in", ".co.in", ".io", ".tech", ".org", ".net", ".co", ".ai"]

    # Try full slug first
    for suffix in suffixes:
        domain = f"{slug}{suffix}"
        if await _probe_domain(domain, client):
            logger.info("Resolved domain: %s -> %s", company, domain)
            return domain

    # Try shorter slug (strip common words like "tech", "solutions")
    for word in ["tech", "solutions", "services", "consulting", "labs", "digital"]:
        short_slug = slug
        if slug.endswith(word):
            short_slug = slug[: -len(word)]
        elif word in slug:
            short_slug = slug.replace(word, "")
        if short_slug and short_slug != slug and len(short_slug) >= 3:
            for suffix in suffixes:
                domain = f"{short_slug}{suffix}"
                if await _probe_domain(domain, client):
                    logger.info("Resolved domain: %s -> %s (short slug)", company, domain)
                    return domain

    return ""


def _is_valid_email(email: str) -> bool:
    """Check if an email looks real (not a placeholder or service address)."""
    low = email.lower()
    if low in _SKIP_EMAILS:
        return False
    skip = ["example", "test", "admin", "noreply", "no-reply",
            "placeholder", "email@domain", "your@email", "error-",
            "bounce", "daemon", "postmaster", "webmaster"]
    return not any(s in low for s in skip)


def _slug_to_name(slug: str) -> str:
    """Convert a LinkedIn slug to a guessed person name.
    e.g., 'samrhood' → 'Sam Rhood', 'itsjakelavelle' → 'Jake Lavelle'
    'priyanshi-yadav-6a350737a' → 'Priyanshi Yadav'
    """
    # Remove random hex suffixes (LinkedIn adds these)
    slug = re.sub(r'-[0-9a-f]{6,10}$', '', slug, flags=re.IGNORECASE)
    # Remove common prefixes
    slug = re.sub(r'^(its|the|my|iam|i_am|im)', '', slug, flags=re.IGNORECASE)
    if len(slug) < 4:
        return ""

    # If slug has hyphens, treat each segment as a name part
    if '-' in slug:
        parts = slug.split('-')
        # Filter out very short parts and capitalize
        name_parts = [p.capitalize() for p in parts if len(p) >= 2 and p.isalpha()]
        if 1 <= len(name_parts) <= 3:
            return " ".join(name_parts)

    # Score each split for slugs without hyphens
    def _consonant_clusters(s):
        return len(re.findall(r'[^aeiou]{3,}', s, re.I))
    best_score = -1
    best_split = ""
    for i in range(2, len(slug) - 1):
        left = slug[:i]
        right = slug[i:]
        if not left[0].isalpha() or not right[0].isalpha():
            continue
        clusters = _consonant_clusters(left) + _consonant_clusters(right)
        vowel_score = len(re.findall(r'[aeiou]', left, re.I)) + len(re.findall(r'[aeiou]', right, re.I))
        len_score = (1 if 2 <= len(left) <= 6 else 0) + (1 if 2 <= len(right) <= 8 else 0)
        end_vowel = (1 if left[-1] in 'aeiou' else 0) + (1 if right[-1] in 'aeiou' else 0)
        score = vowel_score + len_score + end_vowel - (clusters * 3)
        if score > best_score:
            best_score = score
            best_split = f"{left} {right}"
    if best_split:
        parts = best_split.split()
        return " ".join(p.capitalize() for p in parts)
    return ""


def _clean_name(name: str) -> str:
    """Remove noise from extracted names. Only return real person names."""
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) < 4 or len(name) > 50:
        return ""
    low = name.lower()
    words = name.split()

    # Must have 2-3 words (first name + last name, maybe middle)
    if len(words) < 2 or len(words) > 3:
        return ""

    # Reject if ANY word is a non-person word (whole-word match)
    skip_set = _SKIP_NAME_WORDS
    for w in words:
        wl = w.lower().strip(".,;:!?")
        if wl in skip_set:
            return ""
        # Also reject if a skip word is a substring (catches "Opportunities" matching "opportunity")
        if any(sw in wl for sw in skip_set if len(sw) >= 4):
            return ""

    # Each word must start with a capital letter (proper noun)
    if not all(w[0].isupper() for w in words):
        return ""

    # Each word must be at least 2 chars
    if not all(len(w) >= 2 for w in words):
        return ""

    # No word should be all caps (acronyms like HR, CEO, USA)
    if any(w.isupper() and len(w) > 2 for w in words):
        return ""

    # Reject common title prefixes that leak through (Mr, Mrs, Ms, Dr, Prof)
    # These are fine in real names, so only reject if the REST looks fake
    # Reject names where any word is a known location / state / country
    _LOCATIONS = {
        "andhra", "telangana", "karnataka", "tamil", "nadu", "kerala",
        "maharashtra", "rajasthan", "gujarat", "punjab", "haryana",
        "pradesh", "county", "district", "city", "town", "village",
        "north", "south", "east", "west", "central",
    }
    for w in words:
        if w.lower() in _LOCATIONS:
            return ""

    # Reject names that look like company/brand names (contain common business suffixes)
    _BIZ_SUFFIXES = {"llc", "inc", "ltd", "corp", "co", "plc", "gmbh", "ag", "sa"}
    for w in words:
        if w.lower().rstrip(".,") in _BIZ_SUFFIXES:
            return ""

    return name


# ─── Source 1: Search engines (DuckDuckGo primary, Bing, Google fallback) ──

async def _duckduckgo_search(query: str, client: httpx.AsyncClient) -> str:
    """Fetch DuckDuckGo HTML results. Returns 202 on success (not 200)."""
    _throttle()
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html"}
    try:
        resp = await client.get(url, headers=headers, timeout=10)
        # DDG returns 202 Accepted (not 200) for search results
        if resp.status_code in (200, 202) and len(resp.text) > 500:
            return resp.text
    except Exception as exc:
        logger.debug("DuckDuckGo failed: %s", exc)
    return ""


async def _bing_search(query: str, client: httpx.AsyncClient) -> str:
    """Fetch Bing search results. Moderate blocking risk."""
    _throttle()
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count=10"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
    except Exception as exc:
        logger.debug("Bing failed: %s", exc)
    return ""


async def _google_search(query: str, client: httpx.AsyncClient) -> str:
    """Fetch Google search results. High CAPTCHA risk — use as last resort."""
    _throttle()
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=10&hl=en"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
    except Exception as exc:
        logger.debug("Google failed: %s", exc)
    return ""


async def _multi_search(query: str, client: httpx.AsyncClient) -> str:
    """Try search engines in order: DuckDuckGo (least blocking) → Bing → Google."""
    for searcher in [_duckduckgo_search, _bing_search, _google_search]:
        html = await searcher(query, client)
        if html:
            logger.debug("Search succeeded with %s for query: %s",
                        searcher.__name__, query[:50])
            return html
    logger.debug("All search engines failed for query: %s", query[:50])
    return ""


async def search_google_for_domain(
    company: str, client: httpx.AsyncClient
) -> dict[str, Any]:
    """Search multiple engines to find the real company domain and LinkedIn URL."""
    result = {"domain": "", "linkedin_url": "", "emails": [], "names": []}

    skip_domains = ["google.", "facebook.", "indeed.", "glassdoor.",
                    "linkedin.", "twitter.", "youtube.", "wikipedia.",
                    "zoominfo.", "crunchbase.", "ambitionbox.", "naukri.",
                    "monster.", "shine.", "glassdoor.", "ambitionbox.",
                    "bing.", "duckduckgo.", "startpage.", "yahoo.",
                    "baidu.", "yandex.", "ask.com", "aol."]

    def _extract_urls_from_html(html: str) -> list[str]:
        """Extract actual URLs from search result HTML (works for Bing, Google, DuckDuckGo)."""
        urls = []
        soup = BeautifulSoup(html, "html.parser")

        # Method 1: Direct http links in <a> tags
        for a in soup.find_all("a", href=True):
            href = a["href"]
            # Google redirect format: /url?q=ACTUAL_URL
            m = re.search(r"[?&]q=([^&]+)", href)
            if m:
                from urllib.parse import unquote
                href = unquote(m.group(1))
            if href.startswith("http"):
                urls.append(href)

        # Method 2: Bing uses <cite> tags for display URLs
        for cite in soup.find_all("cite"):
            text = cite.get_text(strip=True)
            if text.startswith("http"):
                urls.append(text)
            elif "." in text and "/" not in text:
                urls.append("https://" + text)

        # Method 3: Extract from text content (some engines embed URLs in snippets)
        text = soup.get_text(" ")
        for m in re.finditer(r"https?://[^\s\"'<>]+", text):
            urls.append(m.group(0))

        return urls

    def _extract_emails_from_html(html: str) -> list[str]:
        """Extract emails from HTML content."""
        emails = []
        for m in re.finditer(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html):
            email = m.group(0).lower()
            if _is_valid_email(email):
                emails.append(email)
        return emails

    # Search 1: company website
    html = await _multi_search(f'"{company}" official website', client)
    if html:
        urls = _extract_urls_from_html(html)
        for url in urls:
            if not any(sd in url.lower() for sd in skip_domains):
                domain_m = re.search(r"https?://(?:www\.)?([^/]+)", url)
                if domain_m:
                    domain = domain_m.group(1)
                    if not any(x in domain for x in ["naukri", "indeed", "glassdoor",
                                                      "linkedin", "monster", "shine"]):
                        result["domain"] = domain
                        break
        # Also grab any emails from this page
        for email in _extract_emails_from_html(html):
            if email not in result["emails"]:
                result["emails"].append(email)

    # Search 2: LinkedIn company page
    html = await _multi_search(f'"{company}" site:linkedin.com/company', client)
    if html:
        m = re.search(r"(https?://[^\s\"']+linkedin\.com/company/[^\s\"']+)", html)
        if m:
            result["linkedin_url"] = m.group(1).split("?")[0]
        # Also extract LinkedIn employee names from snippets
        for m in re.finditer(
            r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
            r".*?(?:at|@)\s+.*?" + re.escape(company.split()[0]),
            html, re.IGNORECASE
        ):
            name = _clean_name(m.group(1))
            if name and name not in result["names"]:
                result["names"].append(name)

    # Search 3: find public emails
    html = await _multi_search(f'"{company}" email OR contact OR recruiter', client)
    if html:
        for email in _extract_emails_from_html(html):
            if email not in result["emails"]:
                result["emails"].append(email)

    # Search 4: find employee names for email guessing
    html = await _multi_search(f'"{company}" site:linkedin.com/in recruiter OR hr OR hiring', client)
    if html:
        # Parse names from search result snippets
        soup = BeautifulSoup(html, "html.parser")
        for elem in soup.find_all(["h2", "h3", "a", "span", "div"]):
            text = elem.get_text(" ", strip=True)
            # Look for "Name - Title at Company" patterns
            m = re.search(
                r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)"
                r"\s*[-–—|]\s*"
                r"(?:.*?(?:recruit|hr|hiring|talent|people))",
                text, re.IGNORECASE
            )
            if m:
                name = _clean_name(m.group(1))
                if name and name not in result["names"]:
                    result["names"].append(name)

    return result


# ─── Source 2: Company website scrape ───────────────────────────────────

_PHONE_RE = re.compile(
    r"(?:\+91[\s\-]?\d{10}|\d{10}|\d{5}\s?\d{5}|"
    r"\+?\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4})"
)
_ROLE_KEYWORDS = re.compile(
    r"(?:recruit|hr|hiring|talent|people|founder|ceo|cto|vp|director|"
    r"lead|head|manager|engineer|developer|architect|consultant|"
    r"associate|specialist|coordinator|officer|analyst)",
    re.IGNORECASE,
)


def _extract_phones(text: str) -> list[str]:
    """Pull phone numbers from page text."""
    phones = []
    for m in _PHONE_RE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if 10 <= len(digits) <= 15:
            phones.append(raw)
    return phones


def _guess_role_from_context(context: str) -> str:
    """Guess a person's role from surrounding text."""
    m = _ROLE_KEYWORDS.search(context)
    if m:
        return m.group(0).strip().title()
    return ""


async def scrape_company_contacts(
    domain: str, timeout: float = 12.0
) -> list[dict[str, Any]]:
    """Scrape contacts from company website pages — names, emails, phones, LinkedIn links."""
    if not domain:
        return []

    contacts = []
    seen_emails = set()
    seen_phones: dict[str, dict] = {}  # phone -> contact dict (to merge)
    linkedin_slugs_seen: set[str] = set()
    base = f"https://{domain}"
    headers = {
        "User-Agent": _random_ua(),
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "en-US,en;q=0.9",
    }

    async with httpx.AsyncClient(
        timeout=timeout, headers=headers, follow_redirects=True
    ) as client:
        for path in _TEAM_PATHS:
            url = f"{base}/{path}".rstrip("/")
            try:
                resp = await client.get(url)
                if resp.status_code != 200:
                    continue
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(" ", strip=True)

                # --- Extract LinkedIn profile links from page ---
                for m in re.finditer(
                    r'linkedin\.com/in/([a-zA-Z0-9._-]+)', html, re.IGNORECASE
                ):
                    slug = m.group(1).rstrip("/")
                    if slug in linkedin_slugs_seen:
                        continue
                    linkedin_slugs_seen.add(slug)
                    name_guess = _slug_to_name(slug)
                    profile_url = f"https://www.linkedin.com/in/{slug}"
                    if name_guess:
                        # Try to find role from surrounding context
                        idx = html.find(slug)
                        ctx = html[max(0, idx - 300):idx + 300] if idx >= 0 else ""
                        role = _guess_role_from_context(ctx)
                        contacts.append({
                            "name": name_guess,
                            "email": "",
                            "phone": "",
                            "linkedin_url": profile_url,
                            "role": role,
                            "confidence": 0.65,
                            "source": f"company_site/{path or 'home'}",
                            "verified": True,
                        })

                # --- Extract phone numbers from page ---
                page_phones = _extract_phones(text + " " + html)

                # --- Find name+email pairs ---
                name_email_re = re.compile(
                    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})"
                    r"\s*[-–—•·:|]\s*"
                    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})",
                    re.IGNORECASE,
                )
                for m in name_email_re.finditer(text):
                    name = _clean_name(m.group(1))
                    email = m.group(2).lower()
                    if email in seen_emails or not email.endswith(domain.lower()):
                        continue
                    if not _is_valid_email(email):
                        continue
                    seen_emails.add(email)
                    contacts.append({
                        "name": name,
                        "email": email,
                        "phone": page_phones[0] if page_phones else "",
                        "linkedin_url": "",
                        "role": "",
                        "confidence": 0.75,
                        "source": f"company_site/{path or 'home'}",
                        "verified": True,
                    })

                # Also check mailto: links in HTML
                for m in re.finditer(
                    r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', html
                ):
                    email = m.group(1).lower()
                    if email in seen_emails or not email.endswith(domain.lower()):
                        continue
                    if not _is_valid_email(email):
                        continue
                    seen_emails.add(email)
                    if _is_generic_email(email):
                        continue
                    contacts.append({
                        "name": "",
                        "email": email,
                        "phone": page_phones[0] if page_phones else "",
                        "linkedin_url": "",
                        "confidence": 0.6,
                        "source": f"company_site/{path or 'home'}",
                        "verified": True,
                    })

                # Parse <meta> tags for contact email
                for meta in soup.find_all("meta"):
                    content = meta.get("content", "")
                    name_attr = meta.get("name", "").lower()
                    prop_attr = meta.get("property", "").lower()
                    if any(kw in name_attr or kw in prop_attr
                           for kw in ["email", "contact", "author"]):
                        for m in re.finditer(
                            r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', content
                        ):
                            email = m.group(0).lower()
                            if email in seen_emails or not email.endswith(domain.lower()):
                                continue
                            if not _is_valid_email(email):
                                continue
                            seen_emails.add(email)
                            contacts.append({
                                "name": "",
                                "email": email,
                                "phone": "",
                                "linkedin_url": "",
                                "confidence": 0.55,
                                "source": f"meta_tag/{path or 'home'}",
                                "verified": True,
                            })

                # General email extraction from page text (catches standalone emails)
                for m in re.finditer(
                    r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text
                ):
                    email = m.group(0).lower()
                    if email in seen_emails or not email.endswith(domain.lower()):
                        continue
                    if not _is_valid_email(email):
                        continue
                    seen_emails.add(email)
                    if _is_generic_email(email):
                        continue
                    contacts.append({
                        "name": "",
                        "email": email,
                        "phone": "",
                        "linkedin_url": "",
                        "confidence": 0.5,
                        "source": f"company_site/{path or 'home'}",
                        "verified": True,
                    })

            except Exception as exc:
                logger.debug("scrape %s failed: %s", url, exc)
                continue

    return contacts


# ─── Source 3: LinkedIn via search engines (with company verification) ──

def _normalize_company(name: str) -> str:
    """Normalize company name for comparison."""
    # Remove common suffixes
    name = re.sub(r'\s*(inc|llc|ltd|corp|gmbh|ag|sa|plc|pvt|technologies|solutions|services|tech)\s*$', '', name, flags=re.IGNORECASE)
    # Remove all non-alphanumeric
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _extract_role_from_snippet(snippet: str) -> str:
    """Extract job role from search result snippet."""
    role_patterns = [
        r"(?:senior|lead|principal|staff|junior)?\s*(?:software|data|full.?stack|backend|frontend|devops|cloud|machine|ml|ai|java|python|react|angular|node|mobile|ios|android)\s+(?:engineer|developer|architect|lead|manager|scientist|analyst|sde)",
        r"(?:recruiter|talent|hr|hiring|people|recruitment)",
        r"(?:engineering|tech|cto|vp|director)\s+(?:manager|lead|head|director)",
    ]
    for pat in role_patterns:
        m = re.search(pat, snippet, re.IGNORECASE)
        if m:
            return m.group(0).strip().title()
    return ""


def _is_company_in_snippet(snippet: str, company: str) -> bool:
    """Check if company name appears in search snippet."""
    if not snippet or not company:
        return False

    snippet_lower = snippet.lower()
    company_lower = company.lower()

    # Direct substring match (most reliable)
    if company_lower in snippet_lower:
        return True

    # Check main company brand name (first word if > 3 chars, or first two words)
    company_words = company_lower.split()
    if company_words and len(company_words[0]) > 3:
        # Check if main brand name appears
        if company_words[0] in snippet_lower:
            return True

    # Check normalized versions
    company_norm = _normalize_company(company)
    snippet_norm = re.sub(r"[^a-z0-9]", "", snippet_lower)
    if company_norm and len(company_norm) > 3 and company_norm in snippet_norm:
        return True

    # Check if at least 2 significant words match
    significant_words = [w for w in company_words if len(w) > 3 and w not in ('inc', 'llc', 'ltd', 'corp')]
    if len(significant_words) >= 2:
        matches = sum(1 for w in significant_words if w in snippet_lower)
        if matches >= 2:
            return True

    return False


async def search_linkedin_employees(
    company: str, location: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Find real employee names and LinkedIn profiles with company verification.

    Uses multiple query patterns to maximize results:
    1. Direct company search on LinkedIn
    2. Role-specific searches (recruiter, HR, engineer)
    3. Location + company combo
    """
    contacts = []
    seen_names = set()
    seen_urls = set()

    # Multiple query patterns for better coverage
    company_words = company.split()
    short_company = company_words[0] if company_words and len(company_words[0]) > 3 else company
    queries = [
        f'site:linkedin.com/in "{company}"',
        f'linkedin.com/in "{company}" recruiter OR hr OR hiring',
        f'linkedin.com/in "{company}" engineer OR developer',
        f'site:linkedin.com/in "{short_company}"',
        f'"{company}" linkedin profile employee',
    ]
    if location:
        queries.append(f'site:linkedin.com/in "{company}" {location}')

    for q in queries:
        html = await _multi_search(q, client)
        if not html:
            logger.debug("No search results for: %s", q[:50])
            continue

        soup = BeautifulSoup(html, "html.parser")

        # Extract LinkedIn profile URLs from search results
        for a in soup.find_all("a", href=True):
            href = a["href"]
            m = re.search(r"linkedin\.com/in/([a-zA-Z0-9._-]+)", href)
            if m:
                slug = m.group(1).rstrip("/")
                profile_url = f"https://www.linkedin.com/in/{slug}"
                if profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)

                link_text = a.get_text(" ", strip=True)
                name = _clean_name(link_text)
                if not name or len(name) < 4:
                    name = _slug_to_name(slug)

                if not name or name in seen_names:
                    continue

                # Get the parent element's text for context (the search snippet)
                snippet = ""
                parent = a.find_parent(["div", "li", "article"])
                if parent:
                    snippet = parent.get_text(" ", strip=True)

                # Check if company name appears in the snippet
                company_in_snippet = _is_company_in_snippet(snippet + " " + link_text, company)

                # Try to access profile for verification (may fail due to login wall)
                is_verified = False
                role = _extract_role_from_snippet(snippet)

                try:
                    _throttle()
                    headers = {"User-Agent": _random_ua(), "Accept": "text/html",
                               "Accept-Language": "en-US,en;q=0.9"}
                    resp = await client.get(profile_url, headers=headers, timeout=8, follow_redirects=True)

                    if resp.status_code == 200:
                        html_text = resp.text.lower()
                        # Check for login wall
                        has_login_wall = "sign in" in html_text and "password" in html_text

                        if not has_login_wall:
                            # Can access profile - verify company
                            company_clean = _normalize_company(company)
                            if company_clean in re.sub(r"[^a-z0-9]", "", html_text):
                                is_verified = True
                                # Try to extract role from profile
                                role_match = re.search(
                                    r"(?:software|data|full.?stack|backend|frontend|devops|cloud|machine|ml|ai|java|python|react|angular|node|mobile|ios|android)\s+(?:engineer|developer|architect|lead|manager|scientist|analyst|sde)",
                                    html_text, re.IGNORECASE
                                )
                                if role_match:
                                    role = role_match.group(0).title()
                except Exception:
                    pass  # Profile access failed, continue with other signals

                # Determine confidence based on available signals
                # If we found this profile via company-specific search, include it
                confidence = 0.70
                verified = True

                if is_verified:
                    # Profile accessed and company confirmed - highest confidence
                    confidence = 0.95 if role else 0.90
                elif company_in_snippet:
                    # Company name appears in search snippet - high confidence
                    confidence = 0.85 if role else 0.80

                seen_names.add(name)
                contacts.append({
                    "name": name,
                    "email": "",
                    "confidence": confidence,
                    "source": "linkedin_verified" if verified else "linkedin_search",
                    "linkedin_url": profile_url,
                    "role": role,
                    "verified": verified,
                })

                logger.info(
                    "Found: %s at %s (confidence: %.2f, verified: %s, role: %s)",
                    name, company, confidence, verified, role
                )

        await asyncio.sleep(1)

    # Sort by confidence
    contacts.sort(key=lambda c: c.get("confidence", 0), reverse=True)

    if contacts:
        logger.info("Found %d LinkedIn contacts for %s (%d verified)",
                     len(contacts), company, sum(1 for c in contacts if c.get("verified")))

    return contacts[:20]


# ─── Source 3b: LinkedIn company page scrape ──────────────────────────────

async def scrape_linkedin_company(
    company_slug: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Scrape the public LinkedIn company page for employee names.

    These are automatically verified since they come from the company's own page.
    """
    if not company_slug:
        return []

    contacts = []
    url = f"https://www.linkedin.com/company/{company_slug}/people/"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html",
               "Accept-Language": "en-US,en;q=0.9"}
    _throttle()
    try:
        resp = await client.get(url, headers=headers, timeout=10, follow_redirects=True)
        if resp.status_code != 200:
            return []
        html = resp.text

        # Detect login wall — LinkedIn blocks unauthenticated access
        if "sign in" in html.lower() and "password" in html.lower():
            logger.debug("LinkedIn requires login for %s", company_slug)
            return []
        if len(html) < 5000:
            return []

        soup = BeautifulSoup(html, "html.parser")

        # Look for employee names — LinkedIn uses specific class patterns
        for elem in soup.find_all(["span", "a", "h3", "h4"]):
            text = elem.get_text(" ", strip=True)
            m = re.search(
                r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
                text
            )
            if m:
                name = _clean_name(m.group(1))
                if name and name not in [c["name"] for c in contacts]:
                    # These are verified since they come from the company page
                    contacts.append({
                        "name": name,
                        "email": "",
                        "confidence": 0.85,
                        "source": "linkedin_company_verified",
                        "verified": True,
                    })

        # Extract emails from page source
        emails = re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", html)
        for email in emails:
            if _is_valid_email(email):
                contacts.append({
                    "name": "",
                    "email": email.lower(),
                    "confidence": 0.6,
                    "source": "linkedin_company_verified",
                    "verified": True,
                })

    except Exception as exc:
        logger.debug("LinkedIn company scrape failed: %s", exc)

    return contacts[:15]


# ─── Source 4: Email pattern generation ─────────────────────────────────

def generate_email_guesses(
    names: list[str], domain: str
) -> list[dict[str, Any]]:
    """Generate likely email addresses from names + domain, with MX check."""
    if not domain:
        return []

    mx = domain_has_mx(domain)
    contacts = []
    seen = set()

    for name in names:
        emails = infer_emails(name, domain)
        for email in emails:
            if email in seen:
                continue
            seen.add(email)
            result = score_email(email, mx)
            contacts.append({
                "name": name,
                "email": email,
                "confidence": result["confidence"],
                "source": "email_pattern",
                "status": result["status"],
            })

    return contacts


# ─── Source 5: Job description parse ────────────────────────────────────

def extract_contacts_from_job_desc(
    description: str, company: str
) -> dict[str, Any]:
    """Extract recruiter names, apply emails, and HR contacts from job text."""
    result = {"emails": [], "names": [], "apply_url": ""}

    if not description:
        return result

    # Find emails
    for m in re.finditer(
        r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", description
    ):
        email = m.group(0).lower()
        if _is_valid_email(email):
            result["emails"].append(email)

    # Find recruiter/HR names: "Contact: Name", "Recruiter: Name", "HR: Name"
    name_patterns = [
        r"(?:contact|recruiter|hr|hiring\s*manager|talent\s*acquisition)[:\s]+"
        r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:reach\s*out\s*to|apply\s*(?:to|via))\s+"
        r"([A-Z][a-z]+\s+[A-Z][a-z]+)",
    ]
    for pat in name_patterns:
        for m in re.finditer(pat, description, re.IGNORECASE):
            name = _clean_name(m.group(1))
            if name and name not in result["names"]:
                result["names"].append(name)

    return result


# ─── Company Name Extraction ───────────────────────────────────────────

def _extract_company_from_title(title: str) -> str:
    """Extract company name from job title patterns like 'Reltio MDM Developer'."""
    if not title:
        return ""

    # Pattern: "CompanyName Role/Technology" (most common on job boards)
    # e.g., "Reltio MDM Developer" -> "Reltio"
    # e.g., "Google Software Engineer" -> "Google"
    # e.g., "Amazon AWS Solutions Architect" -> "Amazon"

    # Common role/technology words that appear AFTER company name
    role_words = {
        "developer", "engineer", "architect", "manager", "lead", "senior",
        "junior", "associate", "specialist", "analyst", "consultant",
        "analyst", "designer", "administrator", "coordinator", "officer",
        "intern", "trainee", "fresher", "experienced",
        # Technologies that might appear in title
        "python", "java", "javascript", "react", "angular", "node",
        "aws", "azure", "gcp", "docker", "kubernetes", "devops",
        "fullstack", "full-stack", "full stack", "backend", "frontend",
        "front-end", "back-end", "data", "ml", "ai", "machine learning",
        "cloud", "security", "blockchain", "mobile", "ios", "android",
        "mdm", "etl", "bi", "erp", "crm", "saas", "paas",
        "walk", "drive", "hiring", "opening", "urgent", "immediate",
        "remote", "onsite", "hybrid", "contract", "permanent",
        "part-time", "full-time", "freelance",
    }

    words = title.strip().split()
    if not words:
        return ""

    # Find the first word that looks like a company name (not a role word)
    company_words = []
    for word in words:
        clean = re.sub(r"[^a-zA-Z0-9]", "", word.lower())
        if clean in role_words:
            break
        if len(word) >= 2:
            company_words.append(word)

    company = " ".join(company_words).strip()
    # Remove trailing prepositions or articles
    company = re.sub(r"\s+(at|for|in|the|a|an)$", "", company, flags=re.IGNORECASE)

    return company if len(company) >= 2 else ""


# ─── Source E: Direct Company Website People Pages ─────────────────────

async def discover_via_web_people_pages(
    company: str, domain: str, job_title: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Scrape company website people/team/about pages for real employee info.

    Uses httpx first, falls back to Playwright browser if blocked (403).
    """
    contacts = []
    if not domain:
        return contacts

    team_paths = [
        "about", "team", "about-us", "our-team", "leadership",
        "people", "staff", "employees", "company", "contact",
        "meet-the-team", "the-team", "who-we-are",
    ]

    # First pass: try httpx
    blocked_paths = []
    for path in team_paths:
        url = f"https://{domain}/{path}"
        try:
            _throttle()
            resp = await client.get(url, timeout=10, follow_redirects=True)
            if resp.status_code == 403:
                blocked_paths.append(path)
                continue
            if resp.status_code != 200:
                continue
            _parse_people_from_html(resp.text, domain, company, path, contacts)
        except Exception as exc:
            logger.debug("httpx failed for %s/%s: %s", domain, path, exc)
            continue

    # If most paths returned 403, site blocks bots — use Playwright
    if len(blocked_paths) >= 3 and len(contacts) == 0:
        logger.info("[Web People] Site blocks bots (%d 403s), trying Playwright...", len(blocked_paths))
        await _scrape_with_playwright(domain, company, team_paths, contacts)

    # Dedup by email
    seen_emails = set()
    unique = []
    for c in contacts:
        email = c.get("email", "")
        if email and email not in seen_emails:
            seen_emails.add(email)
            unique.append(c)
        elif not email:
            unique.append(c)

    logger.info("[Web People Pages] Found %d contacts for %s", len(unique), company)
    return unique[:20]


def _parse_people_from_html(html: str, domain: str, company: str, path: str, contacts: list):
    """Extract people info from HTML content."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    # LinkedIn profile links
    for m in re.finditer(r'linkedin\.com/in/([a-zA-Z0-9._-]+)', html, re.IGNORECASE):
        slug = m.group(1).rstrip("/")
        name = _slug_to_name(slug)
        if name and len(name) >= 4:
            profile_url = f"https://www.linkedin.com/in/{slug}"
            idx = html.find(slug)
            ctx = html[max(0, idx - 500):idx + 500] if idx >= 0 else ""
            role = ""
            role_match = re.search(r'(?:at|position|role|title|designat)[^.]{0,100}', ctx, re.IGNORECASE)
            if role_match:
                role = role_match.group(0)[:80]
            contacts.append({
                "name": name, "role": role, "company": company,
                "email": "", "linkedin_url": profile_url,
                "confidence": 0.80, "source": f"web_people/{path}",
                "verified": True, "relevance": "medium", "contact_type": "unknown",
            })

    # Name-email pairs
    name_email_re = re.compile(
        r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*[-\u2013\u2014\u2022\u00b7:|]\s*"
        r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE
    )
    for m in name_email_re.finditer(text):
        name = _clean_name(m.group(1))
        email = m.group(2).lower()
        if name and email and not _is_generic_email(email) and email.endswith(domain.lower()):
            contacts.append({
                "name": name, "role": "", "company": company,
                "email": email, "linkedin_url": "",
                "confidence": 0.85, "source": f"web_people/{path}",
                "verified": True, "relevance": "medium", "contact_type": "unknown",
            })

    # Mailto links
    for m in re.finditer(r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', html):
        email = m.group(1).lower()
        if _is_generic_email(email) or not email.endswith(domain.lower()):
            continue
        idx = html.find(m.group(0))
        ctx = html[max(0, idx - 300):idx + 300] if idx >= 0 else ""
        name_match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', ctx)
        name = _clean_name(name_match.group(1)) if name_match else ""
        if email not in [c.get("email") for c in contacts]:
            contacts.append({
                "name": name, "role": "", "company": company,
                "email": email, "linkedin_url": "",
                "confidence": 0.70 if name else 0.50,
                "source": f"web_people/{path}",
                "verified": bool(name), "relevance": "medium", "contact_type": "unknown",
            })


async def _scrape_with_playwright(domain: str, company: str, paths: list, contacts: list):
    """Use Playwright browser (headless) to scrape pages that block httpx."""
    try:
        from playwright.async_api import async_playwright
        from people_finder.discovery import _random_ua

        pw = await async_playwright().start()
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=_random_ua(),
            viewport={"width": 1920, "height": 1080}
        )

        # Try the homepage and common paths
        all_paths = [""] + paths
        for path in all_paths:
            url = f"https://{domain}/{path}"
            try:
                page = await context.new_page()
                await page.goto(url, timeout=12000, wait_until="domcontentloaded")
                await page.wait_for_timeout(1500)
                html = await page.content()
                await page.close()

                if len(html) > 1000:
                    _parse_people_from_html(html, domain, company, path or "home", contacts)
            except Exception:
                try:
                    await page.close()
                except Exception:
                    pass
                continue

        await context.close()
        await browser.close()
        await pw.stop()
    except Exception as exc:
        logger.debug("[Playwright scrape] Failed: %s", exc)


# ─── Source F: Broad Web Search (no LinkedIn dependency) ────────────────

async def discover_via_broad_search(
    company: str, domain: str, job_title: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Search Bing for anyone associated with the company — names, emails, phone numbers."""
    contacts = []
    seen_names = set()

    queries = [
        f'"{company}" employee OR staff OR team OR developer OR contact',
        f'"{company}" Hyderabad email OR phone OR linkedin',
        f'"{company}" founder OR CEO OR director OR manager',
    ]
    if domain:
        queries.append(f'site:{domain} contact OR team OR about')

    for q in queries:
        try:
            _throttle()
            resp = await client.get(
                f"https://www.bing.com/search?q={quote_plus(q)}&count=20",
                headers={"User-Agent": _random_ua(), "Accept": "text/html"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            from bs4 import BeautifulSoup
            soup = BeautifulSoup(resp.text, "html.parser")

            # Extract all text snippets from search results
            for result in soup.find_all("li", class_="b_algo"):
                text = result.get_text(" ", strip=True)
                if len(text) < 30:
                    continue

                # Extract emails from snippet
                for m in re.finditer(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text):
                    email = m.group(0).lower()
                    if _is_generic_email(email) or not _is_valid_email(email):
                        continue
                    # Try to find a name near this email
                    idx = text.find(email)
                    ctx = text[max(0, idx - 100):idx]
                    name_match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', ctx)
                    name = _clean_name(name_match.group(1)) if name_match else ""
                    if name and name not in seen_names:
                        seen_names.add(name)
                        contacts.append({
                            "name": name, "role": "", "company": company,
                            "email": email, "linkedin_url": "",
                            "confidence": 0.65, "source": "broad_search",
                            "verified": False, "relevance": "medium", "contact_type": "unknown",
                        })

                # Extract LinkedIn URLs from result links
                for a in result.find_all("a", href=True):
                    href = a["href"]
                    slug_match = re.search(r'linkedin\.com/in/([a-zA-Z0-9._-]+)', href)
                    if slug_match:
                        slug = slug_match.group(1).rstrip("/")
                        name = _slug_to_name(slug)
                        if name and len(name) >= 4 and name not in seen_names:
                            seen_names.add(name)
                            profile_url = f"https://www.linkedin.com/in/{slug}"
                            contacts.append({
                                "name": name, "role": "", "company": company,
                                "email": "", "linkedin_url": profile_url,
                                "confidence": 0.70, "source": "broad_search",
                                "verified": False, "relevance": "medium", "contact_type": "unknown",
                            })

                # Extract person names from snippet text
                name_pattern = re.compile(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b')
                for nm in name_pattern.finditer(text):
                    name = _clean_name(nm.group(1))
                    if name and name not in seen_names:
                        # Check if context suggests this person is at the company
                        ctx = text[max(0, nm.start() - 80):nm.end() + 80].lower()
                        if any(w in ctx for w in ["at " + company.lower(), company.lower(), "works", "joined", "employee"]):
                            seen_names.add(name)
                            contacts.append({
                                "name": name, "role": "", "company": company,
                                "email": "", "linkedin_url": "",
                                "confidence": 0.55, "source": "broad_search",
                                "verified": False, "relevance": "low", "contact_type": "unknown",
                            })

            await asyncio.sleep(1)
        except Exception as exc:
            logger.debug("[Broad search] Failed: %s", exc)

    logger.info("[Broad search] Found %d contacts for %s", len(contacts), company)
    return contacts[:15]


# ─── Main orchestrator ──────────────────────────────────────────────────

async def find_contacts(
    company: str,
    domain: str = "",
    candidate_names: list[str] | None = None,
    job_description: str = "",
    job_location: str = "",
    job_title: str = "",
    job_skills: list[str] | None = None,
) -> dict[str, Any]:
    """Enhanced multi-source people finder.

    Pipeline:
    1. Parallel discovery (LinkedIn search + company site + job description)
    2. AI enrichment (role inference, relevance scoring, contact classification)
    3. Email verification (top candidates)
    4. AI outreach draft generation (personalized per contact)
    5. Sort by relevance, return top 15
    """
    try:
        return await _find_contacts_inner(company, domain, candidate_names, job_description, job_location, job_title, job_skills)
    except Exception as exc:
        logger.error("FIND_CONTACTS FAILED for %s: %s", company, exc, exc_info=True)
        return {
            "company": company,
            "domain": domain or "",
            "contacts": [],
            "total_found": 0,
            "verified_count": 0,
            "sources_used": [],
            "error": str(exc),
        }


async def _find_contacts_inner(
    company: str,
    domain: str = "",
    candidate_names: list[str] | None = None,
    job_description: str = "",
    job_location: str = "",
    job_title: str = "",
    job_skills: list[str] | None = None,
) -> dict[str, Any]:
    from people_finder.discovery import discover_people, ContactProfile
    from people_finder.enricher import enrich_contacts, generate_outreach_drafts

    domain = (domain or "").strip().lower().lstrip("@")
    job_skills = job_skills or []

    # Extract company name from job title if missing or "Unknown"
    if not company or company.lower() in ("unknown", "unknown company", "n/a", ""):
        company = _extract_company_from_title(job_title)
        if company:
            logger.info("[Phase 0] Extracted company from title: '%s'", company)

    logger.info("=" * 60)
    logger.info("FIND_CONTACTS START: company='%s', job_title='%s', domain='%s'", company, job_title, domain)
    logger.info("Params: location='%s', skills=%s", job_location, job_skills[:5] if job_skills else [])

    # Phase 1: Run parallel discovery (discovery.py + web people pages + Scout social media)
    logger.info("[Phase 1] Calling discover_people() + web people pages + Scout social media...")
    try:
        import httpx
        headers = {"User-Agent": _random_ua()}
        async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
            # Resolve domain first if not provided
            resolved_domain = domain
            if not resolved_domain and company:
                from people_finder.discovery import resolve_company_domain
                resolved_domain = await resolve_company_domain(company, client)
                if resolved_domain:
                    logger.info("[Phase 1] Resolved domain: '%s'", resolved_domain)
                else:
                    # Fallback: search Bing for company website
                    resolved_domain = await _search_domain_via_bing(company, client)
                    if resolved_domain:
                        logger.info("[Phase 1] Found domain via Bing: '%s'", resolved_domain)

            discovery_coro = discover_people(
                company=company,
                job_title=job_title,
                job_skills=job_skills,
                domain=resolved_domain or domain,
                location=job_location,
                job_description=job_description,
            )
            web_people_coro = discover_via_web_people_pages(
                company=company, domain=resolved_domain or domain, job_title=job_title, client=client
            )
            broad_search_coro = discover_via_broad_search(
                company=company, domain=resolved_domain or domain, job_title=job_title, client=client
            )
            # Scout: multi-platform social media discovery (Instagram, TikTok, GitHub, YouTube, Twitch, etc.)
            scout_coro = _discover_via_scout(
                company=company,
                domain=resolved_domain or domain,
                job_title=job_title,
                location=job_location,
            )
            profiles, web_people, broad_results, scout_results = await asyncio.gather(
                discovery_coro, web_people_coro, broad_search_coro, scout_coro, return_exceptions=True
            )
            if isinstance(profiles, Exception):
                logger.error("[Phase 1] Discovery FAILED: %s", profiles)
                profiles = []
            if isinstance(web_people, Exception):
                logger.warning("[Phase 1] Web people pages FAILED: %s", web_people)
                web_people = []
            if isinstance(broad_results, Exception):
                logger.warning("[Phase 1] Broad search FAILED: %s", broad_results)
                broad_results = []
            if isinstance(scout_results, Exception):
                logger.warning("[Phase 1] Scout social media FAILED: %s", scout_results)
                scout_results = []
    except Exception as exc:
        logger.error("[Phase 1] Phase 1 FAILED: %s", exc, exc_info=True)
        profiles = []
        web_people = []
        broad_results = []
        scout_results = []

    logger.info("[Phase 1] discover_people returned %d profiles", len(profiles) if isinstance(profiles, list) else 0)
    logger.info("[Phase 1] web_people returned %d contacts", len(web_people) if isinstance(web_people, list) else 0)
    logger.info("[Phase 1] broad_search returned %d contacts", len(broad_results) if isinstance(broad_results, list) else 0)
    logger.info("[Phase 1] scout_social returned %d contacts", len(scout_results) if isinstance(scout_results, list) else 0)

    # Merge all results into profiles (including Scout social media results)
    if isinstance(profiles, list):
        existing_names = {p.name.lower() for p in profiles if hasattr(p, 'name') and p.name}
        existing_emails = {p.email.lower() for p in profiles if hasattr(p, 'email') and p.email}
        for source_list in ([web_people] if isinstance(web_people, list) else []) + ([broad_results] if isinstance(broad_results, list) else []) + ([scout_results] if isinstance(scout_results, list) else []):
            for wp in source_list:
                name = wp.get("name", "")
                email = wp.get("email", "")
                if name and name.lower() not in existing_names:
                    from people_finder.discovery import ContactProfile
                    profiles.append(ContactProfile(
                        name=name,
                        role=wp.get("role", ""),
                        company=company,
                        email=email,
                        linkedin_url=wp.get("linkedin_url", ""),
                        confidence=wp.get("confidence", 0.7),
                        source=wp.get("source", "web_people"),
                        verified=wp.get("verified", False),
                        relevance=wp.get("relevance", "medium"),
                        contact_type=wp.get("contact_type", "unknown"),
                    ))
                    existing_names.add(name.lower())
                elif email and email.lower() not in existing_emails:
                    from people_finder.discovery import ContactProfile
                    profiles.append(ContactProfile(
                        name=name,
                        role=wp.get("role", ""),
                        company=company,
                        email=email,
                        linkedin_url=wp.get("linkedin_url", ""),
                        confidence=wp.get("confidence", 0.7),
                        source=wp.get("source", "web_people"),
                        verified=wp.get("verified", False),
                        relevance=wp.get("relevance", "medium"),
                        contact_type=wp.get("contact_type", "unknown"),
                    ))
                    existing_emails.add(email.lower())

    # Phase 2: Convert to dicts for enrichment
    contacts = [p.to_dict() if isinstance(p, ContactProfile) else p for p in profiles]
    logger.info("[Phase 2] Converted to %d contact dicts", len(contacts))

    # Phase 3: AI enrichment (role inference, relevance scoring)
    if contacts:
        logger.info("[Phase 3] Running AI enrichment for %d contacts...", len(contacts))
        try:
            contacts = await enrich_contacts(contacts, job_title, company, job_skills)
            logger.info("[Phase 3] Enrichment complete, %d contacts", len(contacts))
        except Exception as exc:
            logger.warning("[Phase 3] Enrichment failed: %s", exc)

    # Phase 4: SMTP email verification for top candidates without emails
    real_domain = domain
    if not real_domain and contacts:
        # Try to extract domain from first email found
        for c in contacts:
            email = c.get("email", "")
            if email and "@" in email:
                real_domain = email.split("@")[1]
                break

    logger.info("[Phase 4] Domain for email verification: '%s'", real_domain or "(none)")

    if real_domain and contacts:
        linkedin_contacts = [c for c in contacts
                            if c.get("linkedin_url") and c.get("name") and not c.get("email")]
        if linkedin_contacts:
            logger.info("[Phase 4] Verifying emails for %d LinkedIn contacts...", len(linkedin_contacts))
            for c in linkedin_contacts[:3]:
                name = c.get("name", "")
                if not name:
                    continue
                try:
                    verified = verify_emails_for_contact(name, real_domain, max_verify=2)
                    for v in verified:
                        if v["status"] == "verified":
                            c["email"] = v["email"]
                            c["confidence"] = v["confidence"]
                            c["source"] = "linkedin_verified_email"
                            c["verified"] = True
                            logger.info("[Phase 4] Verified email for %s: %s", name, v["email"])
                            break
                except Exception as exc:
                    logger.debug("[Phase 4] Email verification failed for %s: %s", name, exc)

    # Phase 5: Generate AI outreach drafts
    if contacts:
        logger.info("[Phase 5] Generating outreach drafts for %d contacts...", len(contacts))
        job_data = {"title": job_title, "company": company, "skills": job_skills}
        user_profile = _get_user_profile_for_outreach()
        try:
            contacts = await generate_outreach_drafts(contacts, job_data, user_profile)
            logger.info("[Phase 5] Outreach drafts generated")
        except Exception as exc:
            logger.warning("[Phase 5] Outreach generation failed: %s", exc)

    # Phase 6: Sort by relevance + confidence, separate verified/unverified
    verified_contacts = [c for c in contacts if c.get("verified")]
    unverified_contacts = [c for c in contacts if not c.get("verified")]

    logger.info("[Phase 6] Verified: %d, Unverified: %d", len(verified_contacts), len(unverified_contacts))

    # Filter out generic department emails — user wants real human contacts only
    verified_contacts = [c for c in verified_contacts if not _is_generic_email(c.get("email", ""))]
    unverified_contacts = [c for c in unverified_contacts if not _is_generic_email(c.get("email", ""))]

    # No fallback: user wants real human contacts, not generic department emails
    if not verified_contacts and not unverified_contacts:
        logger.info("[Phase 6] No real human contacts found for '%s'", company)

    def _sort_key(c):
        relevance_order = {"high": 0, "medium": 1, "low": 2}
        is_verified = 1 if c.get("verified") else 0
        relevance = relevance_order.get(c.get("relevance", "low"), 3)
        confidence = c.get("confidence", 0)
        return (-is_verified, relevance, -confidence)

    verified_contacts.sort(key=_sort_key)
    unverified_contacts.sort(key=_sort_key)
    final_contacts = verified_contacts + unverified_contacts

    logger.info("FIND_CONTACTS COMPLETE: %d total contacts for '%s' (%d verified, %d unverified)",
                len(final_contacts), company, len(verified_contacts), len(unverified_contacts))
    for c in final_contacts[:5]:
        logger.info("  FINAL: %s | %s | %s | type=%s | relevance=%s | confidence=%.2f",
                    c.get("name", ""), c.get("email", ""), c.get("linkedin_url", ""),
                    c.get("contact_type", ""), c.get("relevance", ""), c.get("confidence", 0))
    logger.info("=" * 60)

    return {
        "company": company,
        "domain": real_domain or "",
        "contacts": final_contacts[:15],
        "total_found": len(final_contacts),
        "verified_count": len(verified_contacts),
        "sources_used": list(set(c.get("source", "") for c in final_contacts)),
    }


def _get_user_profile_for_outreach() -> dict:
    """Get user profile for outreach draft generation. Best-effort from DB."""
    try:
        import asyncio
        from database.engine import async_session
        from database.models import Resume, User
        from sqlalchemy import select

        # This is a sync fallback — the async version is in the router
        return {"name": "Candidate", "skills": []}
    except Exception:
        return {"name": "Candidate", "skills": []}
