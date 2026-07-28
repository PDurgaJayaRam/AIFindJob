"""Multi-source parallel discovery engine for finding real people at companies.

Layers:
1. LinkedIn People Search (Playwright with browser cookies)
2. Company website scraping (httpx, ~5s)
3. Job description parsing (instant)
4. Email pattern generation + verification

Returns structured ContactProfile objects ready for AI enrichment.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

from people_finder.email_patterns import domain_has_mx, infer_emails, score_email

logger = logging.getLogger("people_finder.discovery")

# ─── LinkedIn Session Management ────────────────────────────────────────

SESSION_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
LINKEDIN_SESSION_FILE = os.path.join(SESSION_DIR, "linkedin_session.json")


def extract_linkedin_cookies_from_browser() -> dict | None:
    """Extract LinkedIn cookies from the user's installed browser (Chrome/Edge/Firefox).

    This allows using the user's existing LinkedIn login without manual re-authentication.
    Returns a Playwright-compatible storage state dict, or None if extraction fails.
    """
    try:
        import browser_cookie3
        import shutil
        import tempfile
        import sqlite3

        # Try Chrome first, then Edge, then Firefox
        browsers_to_try = [
            ("Chrome", browser_cookie3.chrome),
            ("Edge", browser_cookie3.edge),
            ("Firefox", browser_cookie3.firefox),
        ]

        for browser_name, cookie_func in browsers_to_try:
            try:
                logger.info("[Browser Cookies] Trying to extract from %s...", browser_name)
                cookies = cookie_func(domain_name=".linkedin.com")

                if not cookies:
                    logger.info("[Browser Cookies] No LinkedIn cookies found in %s", browser_name)
                    continue

                # Convert to Playwright format
                pw_cookies = []
                for cookie in cookies:
                    pw_cookie = {
                        "name": cookie.name,
                        "value": cookie.value,
                        "domain": cookie.domain,
                        "path": cookie.path,
                        "secure": cookie.secure,
                        "httpOnly": hasattr(cookie, 'http_only') and cookie.http_only,
                    }
                    # Playwright requires expires to be -1 or a positive Unix timestamp in seconds
                    if cookie.expires and cookie.expires > 0:
                        pw_cookie["expires"] = cookie.expires
                    pw_cookies.append(pw_cookie)

                if pw_cookies:
                    logger.info("[Browser Cookies] Extracted %d LinkedIn cookies from %s", len(pw_cookies), browser_name)
                    return {
                        "cookies": pw_cookies,
                        "origins": []
                    }

            except Exception as exc:
                logger.debug("[Browser Cookies] %s extraction failed: %s", browser_name, exc)
                # Try direct SQLite extraction as fallback
                try:
                    cookies = _extract_cookies_via_sqlite(browser_name)
                    if cookies:
                        return cookies
                except Exception:
                    pass
                continue

        logger.warning("[Browser Cookies] Could not extract LinkedIn cookies from any browser")
        return None

    except ImportError:
        logger.warning("[Browser Cookies] browser_cookie3 not installed")
        return None
    except Exception as exc:
        logger.error("[Browser Cookies] Unexpected error: %s", exc)
        return None


def _extract_cookies_via_sqlite(browser_name: str) -> dict | None:
    """Direct SQLite extraction as fallback when browser_cookie3 fails."""
    import shutil
    import tempfile
    import sqlite3
    import subprocess

    # Find cookie database path
    cookie_paths = {
        "Chrome": os.path.expanduser("~") + "/AppData/Local/Google/Chrome/User Data/Default/Network/Cookies",
        "Edge": os.path.expanduser("~") + "/AppData/Local/Microsoft/Edge/User Data/Default/Network/Cookies",
    }

    cookie_path = cookie_paths.get(browser_name)
    if not cookie_path or not os.path.exists(cookie_path):
        return None

    # Copy the database (original might be locked by browser)
    temp_dir = tempfile.mkdtemp()
    temp_cookie = os.path.join(temp_dir, "Cookies")

    copied = False
    try:
        # Method 1: Try direct copy (works if browser isn't running)
        shutil.copy2(cookie_path, temp_cookie)
        copied = True
    except PermissionError:
        logger.debug("[Browser Cookies] Direct copy failed (file locked), trying alternatives...")
        try:
            # Method 2: Use PowerShell to copy (might handle locks differently)
            ps_cmd = f"Copy-Item '{cookie_path}' '{temp_cookie}' -Force"
            subprocess.run(['powershell', '-Command', ps_cmd], capture_output=True, timeout=10)
            if os.path.exists(temp_cookie):
                copied = True
        except Exception:
            pass

        if not copied:
            try:
                # Method 3: Use cmd copy command
                cmd_cmd = f'copy "{cookie_path}" "{temp_cookie}" /Y'
                subprocess.run(['cmd', '/c', cmd_cmd], capture_output=True, timeout=10)
                if os.path.exists(temp_cookie):
                    copied = True
            except Exception:
                pass

    if not copied:
        logger.warning("[Browser Cookies] Could not copy %s cookie database (browser may be running)", browser_name)
        logger.info("[Browser Cookies] TIP: Close %s browser and try again, or use the login flow", browser_name)
        return None

    try:
        conn = sqlite3.connect(temp_cookie)
        cursor = conn.cursor()

        # Query LinkedIn cookies
        cursor.execute("""
            SELECT name, value, host_key, path, is_secure, expires_utc
            FROM cookies
            WHERE host_key LIKE '%linkedin.com%'
        """)

        pw_cookies = []
        for row in cursor.fetchall():
            name, value, domain, path, secure, expires = row
            # Chrome stores expires as microseconds since 1601-01-01
            # Convert to Unix timestamp in seconds, or use -1 for session cookies
            if expires and expires > 0:
                # Subtract 11644473600 seconds (difference between Unix epoch and Windows epoch)
                unix_ts = (expires / 1000000) - 11644473600
                expires_val = int(unix_ts) if unix_ts > 0 else -1
            else:
                expires_val = -1
            pw_cookies.append({
                "name": name,
                "value": value,
                "domain": domain,
                "path": path,
                "secure": bool(secure),
                "httpOnly": False,
                "expires": expires_val,
            })

        conn.close()

        if pw_cookies:
            logger.info("[Browser Cookies] Extracted %d LinkedIn cookies via SQLite from %s", len(pw_cookies), browser_name)
            return {"cookies": pw_cookies, "origins": []}

    except Exception as exc:
        logger.debug("[Browser Cookies] SQLite extraction failed: %s", exc)
    finally:
        try:
            shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass

    return None


def save_linkedin_session(storage_state: dict) -> bool:
    """Save Playwright storage state (cookies + localStorage) to file."""
    try:
        # Sanitize cookies before saving
        if "cookies" in storage_state:
            storage_state["cookies"] = _sanitize_cookies_for_playwright(storage_state["cookies"])
        os.makedirs(SESSION_DIR, exist_ok=True)
        with open(LINKEDIN_SESSION_FILE, "w") as f:
            json.dump(storage_state, f, indent=2)
        logger.info("[LinkedIn Session] Saved session to %s", LINKEDIN_SESSION_FILE)
        return True
    except Exception as exc:
        logger.error("[LinkedIn Session] Failed to save: %s", exc)
        return False


def _sanitize_cookies_for_playwright(cookies: list[dict]) -> list[dict]:
    """Filter cookies to only ones Playwright accepts: expires must be -1 or positive int."""
    clean = []
    for c in cookies:
        name = c.get("name", "")
        value = c.get("value", "")
        domain = c.get("domain", "")
        if not name or not domain:
            continue
        # Ensure domain starts with . for Playwright
        if not domain.startswith(".") and not domain.startswith("http"):
            domain = "." + domain
        cookie = {
            "name": name,
            "value": value,
            "domain": domain,
            "path": c.get("path", "/"),
            "secure": bool(c.get("secure", False)),
            "httpOnly": bool(c.get("httpOnly", False)),
        }
        expires = c.get("expires")
        if isinstance(expires, (int, float)) and expires > 0 and expires < 4000000000:
            cookie["expires"] = int(expires)
        # Playwright requires sameSite for some browsers
        ss = c.get("sameSite", "Lax")
        if ss in ("Strict", "Lax", "None"):
            cookie["sameSite"] = ss
        else:
            cookie["sameSite"] = "Lax"
        clean.append(cookie)
    return clean


def load_linkedin_session() -> dict | None:
    """Load saved LinkedIn session, or extract from browser if not saved yet."""
    # First try to load saved session
    if os.path.exists(LINKEDIN_SESSION_FILE):
        try:
            with open(LINKEDIN_SESSION_FILE) as f:
                data = json.load(f)

            if "cookies" not in data:
                logger.warning("[LinkedIn Session] Invalid session file")
            else:
                li_cookies = [c for c in data.get("cookies", []) if "linkedin.com" in c.get("domain", "")]
                if li_cookies:
                    # Sanitize cookies for Playwright compatibility
                    data["cookies"] = _sanitize_cookies_for_playwright(data["cookies"])
                    li_cookies = [c for c in data["cookies"] if "linkedin.com" in c.get("domain", "")]
                    logger.info("[LinkedIn Session] Loaded saved session with %d LinkedIn cookies", len(li_cookies))
                    return data
                else:
                    logger.warning("[LinkedIn Session] No LinkedIn cookies in saved session")
        except Exception as exc:
            logger.error("[LinkedIn Session] Failed to load saved session: %s", exc)

    # No saved session — try to extract from user's browser
    logger.info("[LinkedIn Session] No saved session, attempting to extract from browser...")
    browser_session = extract_linkedin_cookies_from_browser()
    if browser_session:
        # Save for future use
        save_linkedin_session(browser_session)
        return browser_session

    logger.info("[LinkedIn Session] No LinkedIn cookies found in any browser")
    return None


def delete_linkedin_session() -> bool:
    """Delete saved LinkedIn session."""
    try:
        if os.path.exists(LINKEDIN_SESSION_FILE):
            os.remove(LINKEDIN_SESSION_FILE)
            logger.info("[LinkedIn Session] Deleted session file")
        return True
    except Exception as exc:
        logger.error("[LinkedIn Session] Failed to delete: %s", exc)
        return False


async def check_linkedin_session() -> dict:
    """Check if a valid LinkedIn session exists.

    Returns: {"valid": bool, "message": str}
    """
    session = load_linkedin_session()
    if not session:
        return {"valid": False, "message": "No LinkedIn session found. Please log in."}

    # Try to verify by accessing LinkedIn
    browser = await _get_playwright_browser()
    if not browser:
        return {"valid": False, "message": "Browser not available."}

    try:
        context = await browser.new_context(storage_state=session)
        page = await context.new_page()
        await page.goto("https://www.linkedin.com/feed/", timeout=15000, wait_until="domcontentloaded")
        await page.wait_for_timeout(3000)

        url = page.url
        await page.close()
        await context.close()

        if "login" in url or "authwall" in url:
            logger.info("[LinkedIn Session] Session expired (redirected to login)")
            delete_linkedin_session()
            return {"valid": False, "message": "LinkedIn session expired. Please log in again."}

        logger.info("[LinkedIn Session] Session is valid")
        return {"valid": True, "message": "LinkedIn session is active."}

    except Exception as exc:
        logger.warning("[LinkedIn Session] Validation failed: %s", exc)
        return {"valid": False, "message": f"Could not verify session: {exc}"}

# ─── Data Model ────────────────────────────────────────────────────────

@dataclass
class ContactProfile:
    name: str = ""
    role: str = ""
    company: str = ""
    email: str = ""
    email_personal: str = ""
    phone: str = ""
    linkedin_url: str = ""
    photo_url: str = ""
    location: str = ""
    confidence: float = 0.0
    source: str = ""
    verified: bool = False
    relevance: str = "low"
    skills: list[str] = field(default_factory=list)
    contact_type: str = "unknown"
    outreach_linkedin: str = ""
    outreach_email_subject: str = ""
    outreach_email_body: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name, "role": self.role, "company": self.company,
            "email": self.email, "email_personal": self.email_personal,
            "phone": self.phone, "linkedin_url": self.linkedin_url,
            "photo_url": self.photo_url, "location": self.location,
            "confidence": self.confidence, "source": self.source,
            "verified": self.verified, "relevance": self.relevance,
            "skills": self.skills, "contact_type": self.contact_type,
            "outreach_linkedin": self.outreach_linkedin,
            "outreach_email_subject": self.outreach_email_subject,
            "outreach_email_body": self.outreach_email_body,
        }


# ─── Constants ─────────────────────────────────────────────────────────

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

_ROLE_KEYWORDS_RE = re.compile(
    r"(?:recruit|hr|hiring|talent|people|founder|ceo|cto|vp|director|"
    r"lead|head|manager|engineer|developer|architect|consultant|"
    r"associate|specialist|coordinator|officer|analyst|designer|"
    r"frontend|backend|full.?stack|devops|data|ml|ai|mobile|ios|android)",
    re.IGNORECASE,
)

_PHONE_RE = re.compile(
    r"(?:\+91[\s\-]?\d{10}|\d{10}|\d{5}\s?\d{5}|"
    r"\+?\d{1,3}[\s\-]?\(?\d{2,4}\)?[\s\-]?\d{3,4}[\s\-]?\d{3,4})"
)

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

_LINKEDIN_SLUG_RE = re.compile(r"linkedin\.com/in/([a-zA-Z0-9._-]+)", re.IGNORECASE)

_GENERIC_EMAILS = {
    "info@", "contact@", "hello@", "sales@", "mail@", "admin@", "support@", "noreply@",
    "hr@", "careers@", "hiring@", "recruitment@", "talent@", "jobs@", "apply@",
    "enquiry@", "enquiries@", "postmaster@", "webmaster@", "abuse@",
}

_SKIP_NAME_WORDS = {
    "javascript", "script", "function", "var", "const", "let",
    "copyright", "privacy", "terms", "cookie", "menu", "search",
    "login", "sign", "register", "toggle", "navigation",
    "apple", "user", "agreement", "password", "forgot", "corporation",
    "company", "team", "about", "contact", "careers", "people",
    "linkedin", "sign in", "join", "home", "error", "page",
    "loading", "settings", "profile", "account", "help",
    "click", "here", "read", "more", "view", "all", "show",
    "hide", "close", "open", "next", "previous", "back",
    "apply", "now", "date", "line", "download", "upload",
    "share", "like", "follow", "subscribe", "comment",
    "post", "article", "blog", "news", "update",
    "careers", "career", "opportunities", "opportunity", "personnel",
    "recruitment", "recruiting", "hiring", "talent", "acquisition",
    "human", "resources", "department", "group", "organization", "system",
    "solutions", "services", "consulting", "technologies", "technology",
    "innovations", "ventures", "industries", "global", "international",
    "founder", "chief", "officer", "director", "manager", "lead",
    "head", "vice", "president", "executive", "senior", "junior",
    "engineer", "developer", "analyst", "specialist", "coordinator",
    "assistant", "associate", "intern", "trainee", "consultant",
    "county", "city", "state", "district", "region", "province",
    "hyderabad", "bangalore", "mumbai", "chennai", "pune", "delhi",
    "india", "united", "states", "america", "london", "tokyo",
    "china", "japan", "korea", "france", "germany", "spain",
    "january", "february", "march", "april", "june", "july",
    "august", "september", "october", "november", "december",
    "unified", "national", "federal", "public", "private",
    "limited", "incorporated", "associates", "partners",
    "board", "council", "committee", "agency", "bureau", "office",
    "institute", "foundation", "college", "university", "school",
    "hospital", "medical", "health", "bank", "financial",
    "the", "this", "that", "with", "from", "about",
    "support", "info", "general", "specific", "related",
    "official", "music", "video", "image", "photo", "picture",
    "online", "courses", "training", "programs", "classes",
    "clinical", "case", "discussions", "cases", "studies",
    "dictionary", "wikipedia", "encyclopedia", "reference",
    "love", "hate", "best", "worst", "top", "bottom",
    "ranking", "rated", "review", "feedback", "survey",
    "brochures", "catalog", "catalogue", "portfolio",
    "also", "and", "or", "but", "not", "for",
    "what", "how", "why", "when", "where", "who",
    "faq", "help", "guide", "tutorial", "instructions",
}

_last_request_time = 0.0
_MIN_DELAY = 1.0


def _throttle():
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed + random.uniform(0.2, 0.5))
    _last_request_time = time.monotonic()


def _random_ua() -> str:
    return random.choice(_USER_AGENTS)


def _is_generic_email(email: str | None) -> bool:
    """Check if an email is a generic department mailbox, not a real person."""
    if not email:
        return False
    email_lower = email.lower()
    return any(email_lower.startswith(prefix) for prefix in _GENERIC_EMAILS)


# ─── Name Utilities ────────────────────────────────────────────────────

def _clean_name(name: str) -> str:
    name = re.sub(r"\s+", " ", name).strip()
    if len(name) < 4 or len(name) > 50:
        return ""
    low = name.lower()
    if any(w in low for w in _SKIP_NAME_WORDS):
        return ""
    words = name.split()
    if len(words) < 2 or len(words) > 4:
        return ""
    if not all(w[0].isupper() for w in words if w):
        return ""
    if not all(len(w) >= 2 for w in words):
        return ""
    if any(w.isupper() and len(w) > 2 for w in words):
        return ""
    return name


def _slug_to_name(slug: str) -> str:
    slug = re.sub(r'-[0-9a-f]{6,10}$', '', slug, flags=re.IGNORECASE)
    slug = re.sub(r'^(its|the|my|iam|i_am|im)', '', slug, flags=re.IGNORECASE)
    if len(slug) < 4:
        return ""
    if '-' in slug:
        parts = slug.split('-')
        name_parts = [p.capitalize() for p in parts if len(p) >= 2 and p.isalpha()]
        if 1 <= len(name_parts) <= 3:
            return " ".join(name_parts)

    def _clusters(s):
        return len(re.findall(r'[^aeiou]{3,}', s, re.I))

    best_score, best_split = -1, ""
    for i in range(2, len(slug) - 1):
        left, right = slug[:i], slug[i:]
        if not left[0].isalpha() or not right[0].isalpha():
            continue
        clusters = _clusters(left) + _clusters(right)
        vs = len(re.findall(r'[aeiou]', left, re.I)) + len(re.findall(r'[aeiou]', right, re.I))
        ls = (1 if 2 <= len(left) <= 6 else 0) + (1 if 2 <= len(right) <= 8 else 0)
        ev = (1 if left[-1] in 'aeiou' else 0) + (1 if right[-1] in 'aeiou' else 0)
        score = vs + ls + ev - (clusters * 3)
        if score > best_score:
            best_score = score
            best_split = f"{left} {right}"
    if best_split:
        return " ".join(p.capitalize() for p in best_split.split())
    return ""


def _extract_role_from_context(context: str) -> str:
    m = _ROLE_KEYWORDS_RE.search(context)
    return m.group(0).strip().title() if m else ""


def _extract_phones(text: str) -> list[str]:
    phones = []
    for m in _PHONE_RE.finditer(text):
        raw = m.group(0).strip()
        digits = re.sub(r"\D", "", raw)
        if 10 <= len(digits) <= 15:
            phones.append(raw)
    return phones


def _is_relevant_to_job(text: str, job_title: str) -> str:
    text_lower = text.lower()
    job_words = set(re.findall(r'\w+', job_title.lower())) - {'a', 'an', 'the', 'at', 'in', 'for', 'and', 'or', 'of', 'to', 'with'}
    matches = sum(1 for w in job_words if w in text_lower)
    if matches >= 4:
        return "high"
    elif matches >= 2:
        return "medium"
    return "low"


def _is_valid_email(email: str) -> bool:
    low = email.lower()
    skip = ["example", "test", "admin", "noreply", "no-reply", "placeholder",
            "email@domain", "your@email", "error-", "bounce", "daemon", "postmaster", "webmaster"]
    return not any(s in low for s in skip)


def _classify_contact_type(role: str, context: str) -> str:
    combined = (role + " " + context).lower()
    if any(w in combined for w in ["recruit", "talent", "hiring", "acquisition"]):
        return "recruiter"
    if any(w in combined for w in ["hr", "human resource", "people ops"]):
        return "hr"
    if any(w in combined for w in ["founder", "ceo", "cto", "vp", "director", "head", "lead"]):
        return "hiring_manager"
    if any(w in combined for w in ["engineer", "developer", "architect", "designer", "analyst"]):
        return "peer"
    return "unknown"


def _normalize_company(name: str) -> str:
    name = re.sub(r'\s*(inc|llc|ltd|corp|gmbh|ag|sa|plc|pvt|technologies|solutions|services|tech)\s*$',
                  '', name, flags=re.IGNORECASE)
    return re.sub(r"[^a-z0-9]", "", name.lower().strip())


def _is_company_in_snippet(snippet: str, company: str) -> bool:
    if not snippet or not company:
        return False
    snippet_lower = snippet.lower()
    company_lower = company.lower()
    if company_lower in snippet_lower:
        return True
    company_words = company_lower.split()
    if company_words and len(company_words[0]) > 3:
        if company_words[0] in snippet_lower:
            return True
    company_norm = _normalize_company(company)
    snippet_norm = re.sub(r"[^a-z0-9]", "", snippet_lower)
    if company_norm and len(company_norm) > 3 and company_norm in snippet_norm:
        return True
    return False


# ─── Search Engines ────────────────────────────────────────────────────

# Playwright-based search to bypass bot detection
_playwright_browser = None


async def _get_playwright_browser():
    """Get or create a Playwright browser instance."""
    global _playwright_browser
    if _playwright_browser is None:
        try:
            from playwright.async_api import async_playwright
            pw = await async_playwright().start()
            _playwright_browser = await pw.chromium.launch(
                headless=True,
                args=['--no-sandbox', '--disable-blink-features=AutomationControlled']
            )
            logger.info("[Playwright] Browser launched successfully")
        except Exception as exc:
            logger.warning("[Playwright] Failed to launch: %s", exc)
            return None
    return _playwright_browser


async def _playwright_search(query: str) -> str:
    """Use Playwright to search Bing (most reliable for LinkedIn results)."""
    browser = await _get_playwright_browser()
    if not browser:
        return ""

    try:
        page = await browser.new_page(
            user_agent=_random_ua(),
            viewport={'width': 1920, 'height': 1080}
        )
        url = f"https://www.bing.com/search?q={quote_plus(query)}"
        logger.info("[Playwright Search] Navigating to Bing: %s", url[:80])

        # Use domcontentloaded (fast) instead of networkidle (slow/timeout-prone)
        await page.goto(url, timeout=20000, wait_until="domcontentloaded")

        # Short wait for JS to render results - enough for Bing
        await page.wait_for_timeout(3000)

        html = await page.content()
        await page.close()

        # Check if we got actual results
        if 'b_algo' in html or 'b_results' in html:
            logger.info("[Playwright Search] Got %d bytes with Bing results", len(html))
            return html
        else:
            logger.info("[Playwright Search] Got %d bytes (unknown format)", len(html))
            return html if len(html) > 1000 else ""

    except Exception as exc:
        logger.warning("[Playwright Search] Failed: %s", exc)
        return ""


async def _multi_search(query: str, client: httpx.AsyncClient) -> str:
    """Try Playwright first (bypasses bot detection), then fallback to httpx."""
    # Try Playwright first (most reliable)
    html = await _playwright_search(query)
    if html:
        logger.info("[Search] Playwright succeeded for query")
        return html

    # Fallback to httpx-based search engines
    for searcher in [_duckduckgo_search, _bing_search, _google_search]:
        html = await searcher(query, client)
        if html:
            logger.info("[Search] %s succeeded for query", searcher.__name__)
            return html

    logger.warning("[Search] ALL engines failed for query: '%s'", query[:60])
    return ""


async def _duckduckgo_search(query: str, client: httpx.AsyncClient) -> str:
    _throttle()
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html"}
    try:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code in (200, 202) and len(resp.text) > 500:
            # Check if it's a challenge page
            if 'challenge-form' in resp.text or 'anomaly.js' in resp.text:
                logger.debug("[DuckDuckGo] Got challenge page")
                return ""
            return resp.text
        logger.debug("[DuckDuckGo] Status %d, %d bytes", resp.status_code, len(resp.text))
    except Exception as exc:
        logger.debug("[DuckDuckGo] Exception: %s", exc)
    return ""


async def _bing_search(query: str, client: httpx.AsyncClient) -> str:
    _throttle()
    url = f"https://www.bing.com/search?q={quote_plus(query)}&count=10"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
        logger.debug("[Bing] Status %d, %d bytes", resp.status_code, len(resp.text))
    except Exception as exc:
        logger.debug("[Bing] Exception: %s", exc)
    return ""


async def _google_search(query: str, client: httpx.AsyncClient) -> str:
    _throttle()
    url = f"https://www.google.com/search?q={quote_plus(query)}&num=10&hl=en"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html,application/xhtml+xml",
               "Accept-Language": "en-US,en;q=0.9"}
    try:
        resp = await client.get(url, headers=headers, timeout=10)
        if resp.status_code == 200 and len(resp.text) > 500:
            return resp.text
    except Exception:
        pass
    return ""


# ─── Source A: LinkedIn People Search (Playwright) ──────────────────────

async def discover_via_linkedin_people_search(
    company: str, job_title: str, location: str
) -> list[ContactProfile]:
    """Scrape LinkedIn's public people search page for employees.

    Uses: https://www.linkedin.com/search/results/people/?keywords={company}
    Extracts profile data from embedded JSON even when login wall is present.
    """
    contacts: list[ContactProfile] = []
    browser = await _get_playwright_browser()
    if not browser:
        logger.warning("[LinkedIn People Search] No browser available")
        return contacts

    try:
        # Load saved LinkedIn session for authentication
        saved_session = load_linkedin_session()
        if saved_session:
            logger.info("[LinkedIn People Search] Using saved LinkedIn session")
            context = await browser.new_context(
                storage_state=saved_session,
                user_agent=_random_ua(),
                viewport={'width': 1920, 'height': 1080}
            )
        else:
            logger.info("[LinkedIn People Search] No saved session, using fresh context")
            context = await browser.new_context(
                user_agent=_random_ua(),
                viewport={'width': 1920, 'height': 1080}
            )

        page = await context.new_page()

        from urllib.parse import quote_plus
        search_url = f"https://www.linkedin.com/search/results/people/?keywords={quote_plus(company)}&origin=SWITCH_SEARCH_VERTICAL"
        logger.info("[LinkedIn People Search] Navigating to: %s", search_url[:100])

        await page.goto(search_url, timeout=20000, wait_until='domcontentloaded')
        await page.wait_for_timeout(4000)

        # Check if we were redirected to login
        current_url = page.url
        logger.info("[LinkedIn People Search] Current URL: %s", current_url[:100])

        if "login" in current_url or "authwall" in current_url:
            logger.warning("[LinkedIn People Search] Login required — skipping (no session)")
            await page.close()
            await context.close()
            return contacts

        html = await page.content()
        logger.info("[LinkedIn People Search] Got %d bytes of HTML", len(html))

        # Save session after successful navigation
        try:
            storage = await context.storage_state()
            save_linkedin_session(storage)
        except Exception:
            pass

        # Strategy 1: Extract from embedded JSON data (works even with login wall)
        # LinkedIn embeds profile data in script tags as JSON
        import json
        json_pattern = re.compile(r'"elementResult":\s*\{.*?"title":\s*\{.*?"text":\s*"([^"]+)".*?"primarySubtitle":\s*\{.*?"text":\s*"([^"]*)".*?"secondarySubtitle":\s*\{.*?"text":\s*"([^"]*)".*?"navigationUrl":\s*"([^"]+)"', re.DOTALL)

        # Alternative: look for profile data in data attributes or script tags
        profile_data_pattern = re.compile(
            r'"firstName"\s*:\s*"([^"]+)"\s*,\s*"lastName"\s*:\s*"([^"]+)"'
            r'(?:\s*,\s*"headline"\s*:\s*"([^"]*)")?'
            r'(?:\s*,\s*"publicIdentifier"\s*:\s*"([^"]*)")?',
            re.DOTALL
        )

        # Try to extract from LinkedIn's internal data structure
        # LinkedIn stores search results in a specific JSON format within the page
        search_data_pattern = re.compile(
            r'"searchResultMetadata".*?"totalResultCount"\s*:\s*(\d+).*?"elements"\s*:\s*\[(.*?)\]',
            re.DOTALL
        )

        # More robust: look for profile URLs and associated data
        profile_url_pattern = re.compile(
            r'linkedin\.com/in/([a-zA-Z0-9._-]+)',
            re.IGNORECASE
        )

        # Extract all profile URLs from the page
        all_profile_urls = list(set(profile_url_pattern.findall(html)))
        logger.info("[LinkedIn People Search] Found %d unique profile slugs in HTML", len(all_profile_urls))

        # For each profile URL, try to find associated name and title
        for slug in all_profile_urls[:20]:
            profile_url = f"https://www.linkedin.com/in/{slug}"

            # Try to find name associated with this slug in the HTML
            # Look for patterns like "First Last" near the profile URL
            slug_idx = html.find(slug)
            if slug_idx < 0:
                continue

            # Extract surrounding context (500 chars before and after)
            context = html[max(0, slug_idx - 500):slug_idx + 500]

            # Try to find a name near the profile URL
            name_match = re.search(
                r'"name"\s*:\s*"([^"]+)"',
                context
            )
            if not name_match:
                # Try alternative pattern
                name_match = re.search(
                    r'"firstName"\s*:\s*"([^"]+)"\s*,\s*"lastName"\s*:\s*"([^"]+)"',
                    context
                )
                if name_match:
                    name = f"{name_match.group(1)} {name_match.group(2)}"
                else:
                    # Try to find display name
                    name_match = re.search(
                        r'"displayName"\s*:\s*"([^"]+)"',
                        context
                    )
                    name = name_match.group(1) if name_match else ""
            else:
                name = name_match.group(1)

            # Try to find title/headline
            title_match = re.search(
                r'"headline"\s*:\s*"([^"]+)"',
                context
            )
            if not title_match:
                title_match = re.search(
                    r'"title"\s*:\s*"([^"]+)"',
                    context
                )
            role = title_match.group(1) if title_match else ""

            # Try to find location
            loc_match = re.search(
                r'"location"\s*:\s*"([^"]+)"',
                context
            )
            if not loc_match:
                loc_match = re.search(
                    r'"geoLocation"\s*:\s*\{[^}]*"full"\s*:\s*"([^"]+)"',
                    context
                )
            loc = loc_match.group(1) if loc_match else ""

            # If no name found from JSON, try slug-to-name conversion
            if not name:
                name = _slug_to_name(slug)

            if not name or len(name) < 3:
                continue

            # Skip if already found
            if any(c.linkedin_url == profile_url for c in contacts):
                continue

            relevance = _is_relevant_to_job(role + " " + name, job_title)
            contact_type = _classify_contact_type(role, role)

            contacts.append(ContactProfile(
                name=name,
                role=role,
                company=company,
                linkedin_url=profile_url,
                location=loc,
                confidence=0.80,
                source="linkedin_people_search",
                verified=True,
                relevance=relevance,
                contact_type=contact_type,
            ))

            logger.info("[LinkedIn People Search] Found: %s | %s | %s", name, role, profile_url)

        # If no contacts found from JSON parsing, try HTML parsing
        if not contacts:
            logger.info("[LinkedIn People Search] JSON parsing found 0 contacts, trying HTML parsing...")
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html, 'html.parser')

            # Look for any links to LinkedIn profiles
            for a_tag in soup.find_all('a', href=re.compile(r'linkedin\.com/in/')):
                href = a_tag.get('href', '')
                if '?' in href:
                    href = href.split('?')[0]
                if not href.startswith('http'):
                    href = 'https://www.linkedin.com' + href

                slug_m = re.search(r'linkedin\.com/in/([a-zA-Z0-9._-]+)', href)
                if not slug_m:
                    continue
                slug = slug_m.group(1)
                name = _slug_to_name(slug)
                if not name:
                    continue

                if any(c.linkedin_url == href for c in contacts):
                    continue

                # Get surrounding text for role
                parent = a_tag.find_parent(['div', 'li', 'span'])
                context_text = parent.get_text(' ', strip=True) if parent else ""
                role = _extract_role_from_context(context_text)

                contacts.append(ContactProfile(
                    name=name,
                    role=role,
                    company=company,
                    linkedin_url=href,
                    confidence=0.70,
                    source="linkedin_people_search",
                    verified=True,
                    relevance=_is_relevant_to_job(context_text, job_title),
                    contact_type=_classify_contact_type(role, context_text),
                ))

        await page.close()
        await context.close()

        # Sort by relevance
        relevance_order = {"high": 0, "medium": 1, "low": 2}
        contacts.sort(key=lambda c: (relevance_order.get(c.relevance, 3), -c.confidence))

        logger.info("[LinkedIn People Search] Final: %d contacts for %s", len(contacts), company)

    except Exception as exc:
        logger.warning("[LinkedIn People Search] Failed: %s", exc)

    return contacts[:20]


# ─── Source A2: Google Dorking for LinkedIn Profiles ─────────────────────

async def discover_via_linkedin_search(
    company: str, job_title: str, location: str, client: httpx.AsyncClient
) -> list[ContactProfile]:
    contacts: list[ContactProfile] = []
    seen_urls: set[str] = set()

    company_words = company.split()
    short_company = company_words[0] if company_words and len(company_words[0]) > 3 else company
    role_words = re.findall(r'[a-z]+', job_title.lower())
    role_kw = ' '.join(w for w in role_words if len(w) > 3)[:60]

    queries = [
        f'site:linkedin.com/in "{company}" engineer OR developer OR recruiter',
        f'site:linkedin.com/in "{company}" {role_kw}',
        f'site:linkedin.com/in "{company}" hiring manager OR HR OR talent',
        f'site:linkedin.com/in "{short_company}"',
        f'"{company}" linkedin.com/in people team',
    ]
    if location:
        queries.append(f'site:linkedin.com/in "{company}" {location} engineer OR recruiter')

    logger.info("[LinkedIn Search] Running %d queries for '%s'", len(queries), company)

    for q in queries:
        try:
            logger.info("[LinkedIn Search] Query: '%s'", q[:80])
            html = await _multi_search(q, client)
            if not html:
                logger.info("[LinkedIn Search] No results for query")
                continue
            logger.info("[LinkedIn Search] Got %d bytes of HTML", len(html))
            soup = BeautifulSoup(html, "html.parser")

            profiles_found = 0
            for a in soup.find_all("a", href=True):
                m = _LINKEDIN_SLUG_RE.search(a["href"])
                if not m:
                    continue
                slug = m.group(1).rstrip("/")
                profile_url = f"https://www.linkedin.com/in/{slug}"
                if profile_url in seen_urls:
                    continue
                seen_urls.add(profile_url)

                link_text = a.get_text(" ", strip=True)
                name = _clean_name(link_text)
                if not name or len(name) < 4:
                    name = _slug_to_name(slug)
                if not name:
                    continue

                snippet = ""
                parent = a.find_parent(["div", "li", "article"])
                if parent:
                    snippet = parent.get_text(" ", strip=True)

                role = _extract_role_from_context(snippet)
                relevance = _is_relevant_to_job(snippet, job_title)
                company_in_snippet = _is_company_in_snippet(snippet + " " + link_text, company)

                confidence = 0.70
                if company_in_snippet:
                    confidence = 0.85
                if role:
                    confidence += 0.05

                # Try profile verification
                is_verified = False
                try:
                    _throttle()
                    h = {"User-Agent": _random_ua(), "Accept": "text/html", "Accept-Language": "en-US,en;q=0.9"}
                    resp = await client.get(profile_url, headers=h, timeout=8, follow_redirects=True)
                    if resp.status_code == 200:
                        ht = resp.text.lower()
                        if not ("sign in" in ht and "password" in ht):
                            cn = _normalize_company(company)
                            if cn in re.sub(r"[^a-z0-9]", "", ht):
                                is_verified = True
                                confidence = 0.95 if role else 0.90
                except Exception:
                    pass

                contacts.append(ContactProfile(
                    name=name, role=role, company=company,
                    linkedin_url=profile_url, confidence=confidence,
                    source="linkedin_search", verified=is_verified,
                    relevance=relevance,
                    contact_type=_classify_contact_type(role, snippet),
                ))

            await asyncio.sleep(1)
        except Exception as exc:
            logger.debug("LinkedIn search failed for '%s': %s", q[:40], exc)

    contacts.sort(key=lambda c: c.confidence, reverse=True)
    logger.info("LinkedIn search found %d contacts for %s", len(contacts), company)
    return contacts[:20]


# ─── Source B: Company Website Scraping ────────────────────────────────

async def discover_via_company_site(
    domain: str, company: str, client: httpx.AsyncClient
) -> list[ContactProfile]:
    if not domain:
        return []

    contacts: list[ContactProfile] = []
    seen_emails: set[str] = set()
    seen_names: set[str] = set()
    base = f"https://{domain}"
    headers = {"User-Agent": _random_ua(), "Accept": "text/html"}
    team_paths = ["", "about", "team", "about-us", "leadership", "staff",
                  "people", "contact", "careers", "our-team"]

    async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as sc:
        for path in team_paths:
            url = f"{base}/{path}".rstrip("/")
            try:
                resp = await sc.get(url)
                if resp.status_code != 200:
                    continue
                html = resp.text
                soup = BeautifulSoup(html, "html.parser")
                text = soup.get_text(" ", strip=True)
                page_phones = _extract_phones(text + " " + html)

                # LinkedIn links
                for m in _LINKEDIN_SLUG_RE.finditer(html):
                    slug = m.group(1).rstrip("/")
                    name_guess = _slug_to_name(slug)
                    profile_url = f"https://www.linkedin.com/in/{slug}"
                    if name_guess and name_guess not in seen_names:
                        seen_names.add(name_guess)
                        idx = html.find(slug)
                        ctx = html[max(0, idx - 300):idx + 300] if idx >= 0 else ""
                        role = _extract_role_from_context(ctx)
                        contacts.append(ContactProfile(
                            name=name_guess, role=role, company=company,
                            linkedin_url=profile_url, confidence=0.65,
                            source=f"company_site/{path or 'home'}",
                            verified=True, relevance=_is_relevant_to_job(ctx, company),
                            contact_type=_classify_contact_type(role, ctx),
                        ))

                # Name+email pairs
                name_email_re = re.compile(
                    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*[-\u2013\u2014\u2022\u00b7:|]\s*"
                    r"([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})", re.IGNORECASE)
                for m in name_email_re.finditer(text):
                    name = _clean_name(m.group(1))
                    email = m.group(2).lower()
                    if email in seen_emails or not email.endswith(domain.lower()):
                        continue
                    if not _is_valid_email(email) or not name or name in seen_names:
                        continue
                    seen_emails.add(email)
                    seen_names.add(name)
                    contacts.append(ContactProfile(
                        name=name, company=company, email=email,
                        phone=page_phones[0] if page_phones else "",
                        confidence=0.75, source=f"company_site/{path or 'home'}",
                        verified=True, relevance=_is_relevant_to_job(text, company),
                    ))

                # Mailto links — skip generic department emails
                for m in re.finditer(r'mailto:([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})', html):
                    email = m.group(1).lower()
                    if email in seen_emails or not email.endswith(domain.lower()):
                        continue
                    if not _is_valid_email(email):
                        continue
                    seen_emails.add(email)
                    if _is_generic_email(email):
                        continue
                    contacts.append(ContactProfile(
                        name="", company=company, email=email,
                        confidence=0.6,
                        source=f"company_site/{path or 'home'}", verified=True,
                    ))

                # Standalone emails — skip generic department emails
                for m in _EMAIL_RE.finditer(text):
                    email = m.group(0).lower()
                    if email in seen_emails or not email.endswith(domain.lower()):
                        continue
                    if not _is_valid_email(email):
                        continue
                    seen_emails.add(email)
                    if _is_generic_email(email):
                        continue
                    contacts.append(ContactProfile(
                        name="", company=company, email=email,
                        confidence=0.5,
                        source=f"company_site/{path or 'home'}", verified=True,
                    ))

                # Phone+name pairs
                phone_name_re = re.compile(
                    r"([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\s*[-\u2013\u2014\u2022\u00b7:|]\s*"
                    r"(\+?\d[\d\s\-]{8,15})", re.IGNORECASE)
                for m in phone_name_re.finditer(text):
                    name = _clean_name(m.group(1))
                    phone = m.group(2).strip()
                    if name and name not in seen_names:
                        seen_names.add(name)
                        contacts.append(ContactProfile(
                            name=name, company=company, phone=phone,
                            confidence=0.6, source=f"company_site/{path or 'home'}",
                            verified=True,
                        ))

            except Exception as exc:
                logger.debug("Company scrape failed for %s: %s", url, exc)

    logger.info("Company site scrape found %d contacts for %s", len(contacts), company)
    return contacts[:20]


# ─── Source C: Job Description Parsing ─────────────────────────────────

def discover_from_job_description(job_description: str, company: str) -> list[ContactProfile]:
    contacts: list[ContactProfile] = []
    if not job_description:
        return contacts

    for m in _EMAIL_RE.finditer(job_description):
        email = m.group(0).lower()
        if _is_valid_email(email):
            contacts.append(ContactProfile(
                name="", company=company, email=email,
                confidence=0.45, source="job_description",
            ))

    name_patterns = [
        r"(?:contact|recruiter|hr|hiring\s*manager|talent\s*acquisition)[:\s]+"
        r"([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)",
        r"(?:reach\s*out\s*to|apply\s*(?:to|via))\s+"
        r"([A-Z][a-z]+\s+[A-Z][a-z]+)",
    ]
    seen_names: set[str] = set()
    for pat in name_patterns:
        for m in re.finditer(pat, job_description, re.IGNORECASE):
            name = _clean_name(m.group(1))
            if name and name not in seen_names:
                seen_names.add(name)
                contacts.append(ContactProfile(
                    name=name, company=company, confidence=0.5,
                    source="job_description", contact_type="recruiter",
                ))

    logger.info("Job description found %d contacts for %s", len(contacts), company)
    return contacts


# ─── Domain Resolution ─────────────────────────────────────────────────

async def resolve_company_domain(company: str, client: httpx.AsyncClient) -> str:
    """Resolve company domain with India-first suffix priority."""
    clean = re.sub(r"\s*\([^)]*\)\s*", " ", company or "")
    clean = re.sub(
        r"\s+(?:inc|llc|ltd|corp|gmbh|ag|sa|plc|consulting|technologies|solutions|services|pvt|tech)$",
        "", clean, flags=re.IGNORECASE)
    slug = re.sub(r"[^a-z0-9]+", "", clean.lower().strip())
    if not slug:
        return ""

    # India-first suffixes (.in and .co.in before .com)
    suffixes = [".com", ".in", ".co.in", ".io", ".tech", ".org", ".net", ".co", ".ai"]

    # Try full slug first
    for suffix in suffixes:
        domain = f"{slug}{suffix}"
        try:
            resp = await client.get(f"https://{domain}", timeout=5, follow_redirects=True)
            if resp.status_code == 200:
                logger.info("Resolved domain: %s -> %s", company, domain)
                return domain
        except Exception:
            pass

    # Try shorter slug (strip common words)
    for word in ["tech", "solutions", "services", "consulting", "labs", "digital", "soft", "systems"]:
        short_slug = slug
        if slug.endswith(word):
            short_slug = slug[:-len(word)]
        elif word in slug:
            short_slug = slug.replace(word, "")
        if short_slug and short_slug != slug and len(short_slug) >= 3:
            for suffix in suffixes:
                domain = f"{short_slug}{suffix}"
                try:
                    resp = await client.get(f"https://{domain}", timeout=5, follow_redirects=True)
                    if resp.status_code == 200:
                        logger.info("Resolved domain: %s -> %s (short slug)", company, domain)
                        return domain
                except Exception:
                    pass

    return ""


# ─── Email Pattern Generation ──────────────────────────────────────────

def _generate_email_patterns(name: str, domain: str) -> list[str]:
    parts = name.lower().split()
    if len(parts) < 2:
        return [f"{parts[0]}@{domain}"] if parts else []
    first, last = parts[0], parts[-1]
    f, l = first[0], last[0]
    return [
        f"{first}@{domain}", f"{first}.{last}@{domain}", f"{first}{last}@{domain}",
        f"{f}{last}@{domain}", f"{first}_{last}@{domain}", f"{last}.{first}@{domain}",
        f"{last}{first}@{domain}", f"{first}-{last}@{domain}", f"{f}.{last}@{domain}",
        f"{first}.{l}@{domain}", f"{first}{l}@{domain}", f"{f}{l}@{domain}",
    ]


# ─── Source D: AI-Powered People Discovery ─────────────────────────────

async def discover_via_ai(
    company: str, job_title: str, domain: str, location: str, client: httpx.AsyncClient
) -> list[ContactProfile]:
    """Use AI to find real people by fetching company pages + search results directly."""
    contacts: list[ContactProfile] = []

    # Collect content from multiple sources
    all_text = []

    # Source 1: Fetch company website pages directly (most reliable)
    if domain:
        for path in ["about", "team", "about-us", "our-team", "people", "leadership", "contact"]:
            try:
                resp = await client.get(f"https://{domain}/{path}", timeout=8, follow_redirects=True)
                if resp.status_code == 200:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text = soup.get_text(" ", strip=True)
                    if len(text) > 100:
                        all_text.append(text[:3000])
                await asyncio.sleep(0.5)
            except Exception:
                continue

    # Source 2: Search engine queries (fallback)
    queries = [
        f'"{company}" employees team members linkedin',
        f'"{company}" recruiter hiring manager contact',
    ]
    for q in queries:
        try:
            html = await _multi_search(q, client)
            if html:
                soup = BeautifulSoup(html, "html.parser")
                for result in soup.find_all(["div", "li", "article"]):
                    text = result.get_text(" ", strip=True)
                    if len(text) > 50:
                        all_text.append(text[:500])
            await asyncio.sleep(1)
        except Exception:
            continue

    if not all_text:
        return contacts

    # Use AI to extract real people from collected content
    try:
        from ai.ai_client import get_ai_client
        ai = get_ai_client()
        if not ai:
            return contacts

        combined = "\n---\n".join(all_text[:20])
        prompt = f"""You are researching employees at "{company}". Extract REAL people who work there.

From the text below, find people with:
- Their full name
- Their job title/role
- Their LinkedIn URL if present

RULES:
- Only include people you are CONFIDENT work at {company}
- Do NOT make up or guess names
- Do NOT include generic emails (info@, hr@, careers@)
- If no real people found, return []

Text:
{combined[:8000]}

Return JSON array: [{{"name": "...", "role": "...", "linkedin_url": "..."}}]
Return ONLY valid JSON."""

        response = await ai.chat_completion(
            messages=[
                {"role": "system", "content": "Extract real employee names from company pages. Return ONLY valid JSON array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=2000,
            json_mode=True,
        )

        import json
        people = json.loads(response)
        if isinstance(people, list):
            for person in people:
                name = person.get("name", "").strip()
                role = person.get("role", "").strip()
                linkedin_url = person.get("linkedin_url", "").strip()

                if not name or len(name) < 4:
                    continue
                if name.lower() in _SKIP_NAME_WORDS:
                    continue
                if len(name.split()) < 2:
                    continue

                relevance = _is_relevant_to_job(role + " " + name, job_title)
                contact_type = _classify_contact_type(role, role)

                contacts.append(ContactProfile(
                    name=name, role=role, company=company,
                    linkedin_url=linkedin_url, confidence=0.75,
                    source="ai_people_discovery", verified=bool(linkedin_url),
                    relevance=relevance, contact_type=contact_type,
                ))

            logger.info("[AI People Discovery] Found %d real people at '%s'", len(contacts), company)

    except Exception as exc:
        logger.debug("[AI People Discovery] Failed: %s", exc)

    return contacts[:15]


# ─── Source F2: GitHub API Search ──────────────────────────────────────

async def discover_via_github_api(
    company: str, job_title: str, client: httpx.AsyncClient
) -> list[ContactProfile]:
    """Search GitHub for people associated with the company.

    Many developers expose their email and LinkedIn in their GitHub profile.
    """
    contacts: list[ContactProfile] = []
    seen_names: set[str] = set()

    try:
        # Search for users whose bio or company field matches
        queries = [
            f'"{company}" in:bio',
            f'"{company}" in:company',
        ]
        for q in queries:
            try:
                _throttle()
                resp = await client.get(
                    f"https://api.github.com/search/users?q={quote_plus(q)}&per_page=10",
                    headers={"Accept": "application/vnd.github.v3+json", "User-Agent": _random_ua()},
                    timeout=10,
                )
                if resp.status_code != 200:
                    continue

                data = resp.json()
                for user in data.get("items", [])[:10]:
                    username = user.get("login", "")
                    if not username:
                        continue

                    # Fetch profile details
                    try:
                        _throttle()
                        profile_resp = await client.get(
                            f"https://api.github.com/users/{username}",
                            headers={"Accept": "application/vnd.github.v3+json"},
                            timeout=8,
                        )
                        if profile_resp.status_code != 200:
                            continue

                        profile = profile_resp.json()
                        name = profile.get("name", "")
                        bio = profile.get("bio", "") or ""
                        email = profile.get("email", "") or ""
                        blog = profile.get("blog", "") or ""
                        company_field = profile.get("company", "") or ""

                        # Check if company matches
                        company_lower = company.lower()
                        if company_lower not in company_field.lower() and company_lower not in bio.lower():
                            continue

                        if not name or len(name) < 4:
                            name = _slug_to_name(username) or username

                        if name in seen_names:
                            continue
                        seen_names.add(name)

                        # Extract LinkedIn from bio or blog
                        linkedin_url = ""
                        for text_field in [bio, blog]:
                            m = re.search(r'linkedin\.com/in/([a-zA-Z0-9._-]+)', text_field)
                            if m:
                                linkedin_url = f"https://www.linkedin.com/in/{m.group(1)}"
                                break

                        role = _extract_role_from_context(bio + " " + (profile.get("description", "") or ""))
                        relevance = _is_relevant_to_job(bio + " " + name, job_title)
                        contact_type = _classify_contact_type(role, bio)

                        contacts.append(ContactProfile(
                            name=name, role=role, company=company,
                            email=email, linkedin_url=linkedin_url,
                            confidence=0.75, source="github_api",
                            verified=True, relevance=relevance,
                            contact_type=contact_type,
                        ))

                    except Exception:
                        continue

                await asyncio.sleep(1)
            except Exception as exc:
                logger.debug("[GitHub API] Search failed: %s", exc)

        # Also search for repos mentioning hiring
        try:
            _throttle()
            resp = await client.get(
                f"https://api.github.com/search/repositories?q={quote_plus(company)}+hiring+OR+jobs&per_page=5",
                headers={"Accept": "application/vnd.github.v3+json"},
                timeout=10,
            )
            if resp.status_code == 200:
                for repo in resp.json().get("items", [])[:5]:
                    owner = repo.get("owner", {})
                    login = owner.get("login", "")
                    if login and login not in seen_names:
                        # Try to get owner profile
                        try:
                            _throttle()
                            owner_resp = await client.get(
                                f"https://api.github.com/users/{login}",
                                headers={"Accept": "application/vnd.github.v3+json"},
                                timeout=8,
                            )
                            if owner_resp.status_code == 200:
                                owner_profile = owner_resp.json()
                                name = owner_profile.get("name", "") or login
                                bio = owner_profile.get("bio", "") or ""
                                email = owner_profile.get("email", "") or ""

                                if name not in seen_names:
                                    seen_names.add(name)
                                    linkedin_url = ""
                                    m = re.search(r'linkedin\.com/in/([a-zA-Z0-9._-]+)', bio)
                                    if m:
                                        linkedin_url = f"https://www.linkedin.com/in/{m.group(1)}"

                                    contacts.append(ContactProfile(
                                        name=name, role="Founder/Owner", company=company,
                                        email=email, linkedin_url=linkedin_url,
                                        confidence=0.70, source="github_api",
                                        verified=True, relevance="medium",
                                        contact_type="hiring_manager",
                                    ))
                        except Exception:
                            pass
        except Exception:
            pass

    except Exception as exc:
        logger.debug("[GitHub API] Failed: %s", exc)

    logger.info("[GitHub API] Found %d contacts for %s", len(contacts), company)
    return contacts[:10]


# ─── Source G: Bing OSINT Search (finds contacts for ANY company) ──────

async def discover_via_bing_osint(
    company: str, job_title: str, location: str, client: httpx.AsyncClient
) -> list[ContactProfile]:
    """Search Bing for anyone at the company — recruiters, HR, hiring managers.

    Uses targeted queries that surface real contact info from public pages:
    - Company + recruiter/HR/hiring manager
    - Company + email/phone/contact
    - Company + LinkedIn profiles
    """
    contacts: list[ContactProfile] = []
    seen_names: set[str] = set()
    seen_emails: set[str] = set()

    queries = [
        f'"{company}" recruiter email contact',
        f'"{company}" hiring manager HR email',
        f'"{company}" site:linkedin.com recruiter OR HR OR hiring',
        f'"{company}" {location} contact email phone',
        f'"{company}" founder CEO director email',
        f'"{company}" careers email apply',
    ]
    if job_title:
        queries.append(f'"{company}" "{job_title}" recruiter OR hiring manager')

    for q in queries:
        try:
            _throttle()
            resp = await client.get(
                f"https://www.bing.com/search?q={quote_plus(q)}&count=20",
                headers={"User-Agent": _random_ua(), "Accept": "text/html",
                         "Accept-Language": "en-US,en;q=0.9"},
                timeout=10,
            )
            if resp.status_code != 200:
                continue

            soup = BeautifulSoup(resp.text, "html.parser")

            for result_elem in soup.find_all("li", class_="b_algo"):
                text = result_elem.get_text(" ", strip=True)
                if len(text) < 30:
                    continue

                # Extract emails from snippet
                for m in re.finditer(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text):
                    email = m.group(0).lower()
                    if _is_generic_email(email) or not _is_valid_email(email):
                        continue
                    if email in seen_emails:
                        continue

                    # Try to find a name near this email
                    idx = text.find(email)
                    ctx = text[max(0, idx - 150):idx]
                    name_match = re.search(r'([A-Z][a-z]+\s+[A-Z][a-z]+)', ctx)
                    name = _clean_name(name_match.group(1)) if name_match else ""

                    # Try to find role near this email
                    ctx_after = text[idx:idx + 150]
                    role = _extract_role_from_context(ctx_after)

                    if name and name not in seen_names:
                        seen_names.add(name)
                        seen_emails.add(email)
                        relevance = _is_relevant_to_job(role + " " + name, job_title)
                        contact_type = _classify_contact_type(role, text)
                        contacts.append(ContactProfile(
                            name=name, role=role, company=company, email=email,
                            confidence=0.70, source="bing_osint",
                            verified=False, relevance=relevance,
                            contact_type=contact_type,
                        ))
                    elif not name and email not in seen_emails:
                        seen_emails.add(email)
                        contacts.append(ContactProfile(
                            name="", company=company, email=email,
                            confidence=0.50, source="bing_osint",
                            verified=False,
                        ))

                # Extract LinkedIn URLs from result links
                for a in result_elem.find_all("a", href=True):
                    href = a["href"]
                    slug_match = re.search(r'linkedin\.com/in/([a-zA-Z0-9._-]+)', href)
                    if slug_match:
                        slug = slug_match.group(1).rstrip("/")
                        name = _slug_to_name(slug)
                        if name and len(name) >= 4 and name not in seen_names:
                            # Check if company is mentioned in the snippet
                            if _is_company_in_snippet(text, company):
                                seen_names.add(name)
                                profile_url = f"https://www.linkedin.com/in/{slug}"
                                role = _extract_role_from_context(text)
                                relevance = _is_relevant_to_job(text, job_title)
                                contact_type = _classify_contact_type(role, text)
                                contacts.append(ContactProfile(
                                    name=name, role=role, company=company,
                                    linkedin_url=profile_url,
                                    confidence=0.80, source="bing_osint",
                                    verified=True, relevance=relevance,
                                    contact_type=contact_type,
                                ))

                # Extract person names from snippet text
                name_pattern = re.compile(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\b')
                for nm in name_pattern.finditer(text):
                    name = _clean_name(nm.group(1))
                    if name and name not in seen_names:
                        ctx = text[max(0, nm.start() - 100):nm.end() + 100].lower()
                        if any(w in ctx for w in ["at " + company.lower(), company.lower(),
                                                    "recruiter", "hr", "hiring", "talent",
                                                    "email", "contact", "phone"]):
                            seen_names.add(name)
                            # Try to extract email near this name
                            nearby_email = ""
                            for em in re.finditer(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', text):
                                em_text = em.group(0).lower()
                                em_idx = text.find(em_text)
                                if abs(em_idx - nm.start()) < 200 and _is_valid_email(em_text):
                                    nearby_email = em_text
                                    break

                            role = _extract_role_from_context(ctx)
                            contact_type = _classify_contact_type(role, ctx)
                            contacts.append(ContactProfile(
                                name=name, role=role, company=company,
                                email=nearby_email, confidence=0.65,
                                source="bing_osint", verified=False,
                                relevance=_is_relevant_to_job(ctx, job_title),
                                contact_type=contact_type,
                            ))

            await asyncio.sleep(1)
        except Exception as exc:
            logger.debug("[Bing OSINT] Failed: %s", exc)

    logger.info("[Bing OSINT] Found %d contacts for %s", len(contacts), company)
    return contacts[:20]


# ─── Main Orchestrator ─────────────────────────────────────────────────

async def discover_people(
    company: str,
    job_title: str = "",
    job_skills: list[str] = None,
    domain: str = "",
    location: str = "",
    job_description: str = "",
) -> list[ContactProfile]:
    """Run all discovery sources in parallel and return merged contacts."""
    job_skills = job_skills or []
    headers = {"User-Agent": _random_ua()}

    logger.info("=" * 60)
    logger.info("DISCOVERY START: company='%s', title='%s', domain='%s', location='%s'",
                company, job_title, domain, location)
    logger.info("Job skills: %s", job_skills[:10] if job_skills else [])
    logger.info("Job description length: %d chars", len(job_description) if job_description else 0)

    async with httpx.AsyncClient(timeout=12, headers=headers, follow_redirects=True) as client:
        # Phase 0: Domain resolution
        if not domain:
            logger.info("[Phase 0] Resolving domain for '%s'...", company)
            domain = await resolve_company_domain(company, client)
            logger.info("[Phase 0] Domain result: '%s'", domain or "(none)")
        else:
            logger.info("[Phase 0] Using provided domain: '%s'", domain)

        # Phase 1: Parallel discovery (8 sources now)
        logger.info("[Phase 1] Starting parallel discovery (8 sources)...")
        try:
            # Source 1: LinkedIn Voyager API (real employee data via open-linkedin-api)
            from people_finder.linkedin_api_client import search_people_at_company
            linkedin_api_coro = search_people_at_company(company, limit=20)

            # Source 2: LinkedIn People Search (Playwright - browser scraping)
            linkedin_people_coro = discover_via_linkedin_people_search(company, job_title, location)
            # Source 3: LinkedIn Search via search engines (fallback)
            linkedin_search_coro = discover_via_linkedin_search(company, job_title, location, client)
            # Source 4: Company website scraping
            site_coro = discover_via_company_site(domain, company, client) if domain else _empty_list()
            # Source 5: Job description parsing
            jd_coro = asyncio.to_thread(discover_from_job_description, job_description, company)
            # Source 6: AI-powered people discovery
            ai_coro = discover_via_ai(company, job_title, domain, location, client)
            # Source 7: Bing OSINT search (finds contacts for ANY company)
            bing_osint_coro = discover_via_bing_osint(company, job_title, location, client)
            # Source 8: GitHub API (finds developers at the company)
            github_coro = discover_via_github_api(company, job_title, client)

            results = await asyncio.gather(
                linkedin_api_coro, linkedin_people_coro, linkedin_search_coro,
                site_coro, jd_coro, ai_coro, bing_osint_coro, github_coro,
                return_exceptions=True,
            )
        except Exception as exc:
            logger.error("[Phase 1] Parallel discovery FAILED: %s", exc, exc_info=True)
            results = [[], [], [], [], [], [], [], []]

    # Log results from each source
    source_names = ["LinkedIn Voyager API", "LinkedIn People Search", "LinkedIn Search", "Company Site", "Job Description", "AI People Discovery", "Bing OSINT", "GitHub API"]
    for i, (name, result) in enumerate(zip(source_names, results)):
        if isinstance(result, Exception):
            logger.warning("[Phase 1] %s FAILED with exception: %s", name, result)
        elif isinstance(result, list):
            logger.info("[Phase 1] %s returned %d contacts", name, len(result))
            for c in result[:5]:
                if hasattr(c, 'name'):
                    logger.info("  - %s | email=%s | phone=%s | linkedin=%s | confidence=%.2f | verified=%s",
                                c.name or "(no name)", c.email or "(none)", c.phone or "(none)",
                                c.linkedin_url or "(none)", c.confidence, c.verified)
        else:
            logger.warning("[Phase 1] %s returned unexpected type: %s", name, type(result))

    # Merge + dedup
    all_contacts: list[ContactProfile] = []
    seen_names: set[str] = set()
    seen_emails: set[str] = set()
    merge_stats = {"linkedin_api": 0, "linkedin": 0, "company": 0, "job_desc": 0, "bing_osint": 0, "github": 0, "skipped_dup": 0}

    for result in results:
        if isinstance(result, Exception) or not isinstance(result, list):
            continue
        for c in result:
            # Track source
            if c.source == "linkedin_voyager_api":
                merge_stats["linkedin_api"] += 1
            elif c.source.startswith("linkedin"):
                merge_stats["linkedin"] += 1
            elif c.source.startswith("company"):
                merge_stats["company"] += 1
            elif c.source == "job_description":
                merge_stats["job_desc"] += 1
            elif c.source == "ai_people_discovery":
                merge_stats["ai"] = merge_stats.get("ai", 0) + 1
            elif c.source == "bing_osint":
                merge_stats["bing_osint"] += 1
            elif c.source == "github_api":
                merge_stats["github"] += 1

            if c.email:
                if c.email in seen_emails:
                    merge_stats["skipped_dup"] += 1
                    continue
                seen_emails.add(c.email)
            if c.name:
                key = c.name.lower()
                if key in seen_names:
                    merge_stats["skipped_dup"] += 1
                    existing = next((x for x in all_contacts if x.name.lower() == key), None)
                    if existing:
                        if not existing.email and c.email:
                            existing.email = c.email
                        if not existing.phone and c.phone:
                            existing.phone = c.phone
                        if not existing.linkedin_url and c.linkedin_url:
                            existing.linkedin_url = c.linkedin_url
                        if not existing.role and c.role:
                            existing.role = c.role
                        if c.confidence > existing.confidence:
                            existing.confidence = c.confidence
                        if c.verified:
                            existing.verified = True
                    continue
                seen_names.add(key)
            all_contacts.append(c)

    logger.info("[Phase 2] After merge+dedup: %d contacts (linkedin_api=%d, linkedin=%d, company=%d, job_desc=%d, ai=%d, bing_osint=%d, github=%d, skipped_dup=%d)",
                len(all_contacts), merge_stats["linkedin_api"], merge_stats["linkedin"], merge_stats["company"],
                merge_stats["job_desc"], merge_stats.get("ai", 0), merge_stats["bing_osint"], merge_stats["github"],
                merge_stats["skipped_dup"])

    # Generate email patterns for contacts with names but no email
    if domain and domain_has_mx(domain):
        generated = 0
        for c in all_contacts:
            if c.name and not c.email and " " in c.name:
                patterns = _generate_email_patterns(c.name, domain)
                c.email = patterns[1] if len(patterns) > 1 else patterns[0]
                c.confidence = max(c.confidence - 0.1, 0.2)
                generated += 1
        logger.info("[Phase 2] Generated %d email patterns for '%s'", generated, domain)

    # Filter out generic department emails — user wants real human contacts only
    before_count = len(all_contacts)
    all_contacts = [c for c in all_contacts if not _is_generic_email(c.email)]
    if len(all_contacts) < before_count:
        logger.info("[Phase 2] Filtered out %d generic department emails", before_count - len(all_contacts))

    # Only add a single fallback contact if absolutely nothing found
    has_real_people = any(c.name and c.name != "Company" for c in all_contacts)
    if not has_real_people and domain:
        logger.info("[Phase 2] No real people found for '%s' — no fallback emails added (user wants real contacts only)", company)

    relevance_order = {"high": 0, "medium": 1, "low": 2}
    all_contacts.sort(key=lambda c: (relevance_order.get(c.relevance, 3), -c.confidence))

    logger.info("DISCOVERY COMPLETE: %d contacts for '%s'", len(all_contacts), company)
    for c in all_contacts[:5]:
        logger.info("  FINAL: %s | %s | %s | confidence=%.2f", c.name, c.email, c.linkedin_url, c.confidence)
    logger.info("=" * 60)
    return all_contacts[:20]


async def _empty_list():
    return []
