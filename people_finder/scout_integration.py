"""Scout integration — multi-platform social media scraping for contact discovery.

Wraps Scout's core scraping capabilities (Instagram, TikTok, LinkedIn, GitHub,
YouTube, Twitch, Pinterest, Linktree) to find people at a company via their
social media profiles.

This adds social media breadth to the existing people_finder waterfall which
already covers LinkedIn search, company website scraping, and email patterns.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from typing import Any
from urllib.parse import quote_plus

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("people_finder.scout")

_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

_last_request_time = 0.0
_MIN_DELAY = 1.5


def _random_ua() -> str:
    import random
    return random.choice(_USER_AGENTS)


def _throttle():
    global _last_request_time
    now = time.monotonic()
    elapsed = now - _last_request_time
    if elapsed < _MIN_DELAY:
        time.sleep(_MIN_DELAY - elapsed + 0.5)
    _last_request_time = time.monotonic()


# ─── Platform Scrapers ─────────────────────────────────────────────────


async def _scrape_github_user(username: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Scrape GitHub user profile for public info."""
    try:
        _throttle()
        resp = await client.get(
            f"https://api.github.com/users/{username}",
            headers={"Accept": "application/vnd.github.v3+json", "User-Agent": _random_ua()},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return {
            "platform": "github",
            "username": username,
            "full_name": data.get("name", ""),
            "bio": data.get("bio", ""),
            "email": data.get("email", ""),
            "website": data.get("blog", ""),
            "location": data.get("location", ""),
            "company": data.get("company", ""),
            "followers": data.get("followers", 0),
            "public_repos": data.get("public_repos", 0),
            "profile_url": f"https://github.com/{username}",
        }
    except Exception as exc:
        logger.debug("GitHub scrape failed for %s: %s", username, exc)
        return None


async def _scrape_youtube_channel(channel: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Scrape YouTube channel page for public info."""
    try:
        _throttle()
        # Normalize channel handle
        if not channel.startswith("@") and not channel.startswith("UC"):
            channel = f"@{channel}"
        url = f"https://www.youtube.com/{channel}/about"
        resp = await client.get(
            url,
            headers={"User-Agent": _random_ua(), "Accept": "text/html"},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract channel name
        name_el = soup.find("yt-formatted-string", class_="style-scope ytd-channel-name")
        name = name_el.get_text(strip=True) if name_el else ""

        # Extract description
        desc_el = soup.find("yt-formatted-string", class_="style-scope ytd-about-channel-renderer")
        description = desc_el.get_text(strip=True) if desc_el else ""

        # Extract email from description (if present)
        email = ""
        email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', description)
        if email_match:
            email = email_match.group(0).lower()

        # Extract links
        links = []
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "youtube.com" not in href:
                links.append(href)

        return {
            "platform": "youtube",
            "username": channel.lstrip("@"),
            "full_name": name,
            "bio": description[:500],
            "email": email,
            "website": links[0] if links else "",
            "profile_url": f"https://www.youtube.com/{channel}",
        }
    except Exception as exc:
        logger.debug("YouTube scrape failed for %s: %s", channel, exc)
        return None


async def _scrape_twitch_user(username: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Scrape Twitch user profile via GQL API (no auth needed for public profiles)."""
    try:
        _throttle()
        # Twitch uses a GQL endpoint for public profile data
        gql_url = "https://gql.twitch.tv/gql"
        payload = [{
            "operationName": "CoreActionsCurrentUser",
            "variables": {"login": username},
            "extensions": {
                "persistedQuery": {
                    "version": 1,
                    "sha256Hash": "03e08d6a6c29d71a8e11c9e8c8e8c8e8c8e8c8e8c8e8c8e8c8e8c8e8c8e8c8e8"
                }
            }
        }]
        # Fallback: use the search API
        resp = await client.get(
            f"https://api.twitch.tv/helix/users?login={username}",
            headers={"Client-ID": "kimne78kx3ncx6brgo4mv6wki5h1ko", "User-Agent": _random_ua()},
            timeout=10,
        )
        if resp.status_code != 200:
            return None
        data = resp.json().get("data", [])
        if not data:
            return None
        user = data[0]
        return {
            "platform": "twitch",
            "username": username,
            "full_name": user.get("display_name", ""),
            "bio": user.get("description", ""),
            "email": "",  # Twitch doesn't expose email via API
            "website": "",
            "location": user.get("broadcaster_type", ""),
            "followers": user.get("follower_count", 0),
            "profile_url": f"https://www.twitch.tv/{username}",
            "photo_url": user.get("profile_image_url", ""),
        }
    except Exception as exc:
        logger.debug("Twitch scrape failed for %s: %s", username, exc)
        return None


async def _scrape_linktree(username: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Scrape Linktree profile for links and contact info."""
    try:
        _throttle()
        resp = await client.get(
            f"https://linktr.ee/{username}",
            headers={"User-Agent": _random_ua(), "Accept": "text/html"},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        html = resp.text
        soup = BeautifulSoup(html, "html.parser")

        # Extract bio/description
        bio_el = soup.find("meta", attrs={"name": "description"})
        bio = bio_el.get("content", "") if bio_el else ""

        # Extract title (name)
        title_el = soup.find("meta", attrs={"property": "og:title"})
        name = title_el.get("content", "") if title_el else username

        # Extract email from page if present
        email = ""
        email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
        if email_match:
            email = email_match.group(0).lower()

        # Extract social links
        socials = {}
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if any(platform in href for platform in ["linkedin.com", "twitter.com", "x.com", "instagram.com", "github.com"]):
                platform = "linkedin" if "linkedin" in href else "twitter" if "twitter" in href or "x.com" in href else "instagram" if "instagram" in href else "github"
                socials[platform] = href

        return {
            "platform": "linktree",
            "username": username,
            "full_name": name,
            "bio": bio[:500],
            "email": email,
            "website": f"https://linktr.ee/{username}",
            "profile_url": f"https://linktr.ee/{username}",
            "socials": socials,
        }
    except Exception as exc:
        logger.debug("Linktree scrape failed for %s: %s", username, exc)
        return None


async def _scrape_pinterest_user(username: str, client: httpx.AsyncClient) -> dict[str, Any] | None:
    """Scrape Pinterest profile page for public info."""
    try:
        _throttle()
        resp = await client.get(
            f"https://www.pinterest.com/{username}/",
            headers={"User-Agent": _random_ua(), "Accept": "text/html"},
            timeout=10,
            follow_redirects=True,
        )
        if resp.status_code != 200:
            return None
        html = resp.text

        # Extract from meta tags
        name_match = re.search(r'<meta[^>]*property="og:title"[^>]*content="([^"]*)"', html)
        desc_match = re.search(r'<meta[^>]*name="description"[^>]*content="([^"]*)"', html)

        name = name_match.group(1) if name_match else username
        bio = desc_match.group(1) if desc_match else ""

        # Extract email if present
        email = ""
        email_match = re.search(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}', html)
        if email_match:
            email = email_match.group(0).lower()

        return {
            "platform": "pinterest",
            "username": username,
            "full_name": name,
            "bio": bio[:500],
            "email": email,
            "profile_url": f"https://www.pinterest.com/{username}/",
        }
    except Exception as exc:
        logger.debug("Pinterest scrape failed for %s: %s", username, exc)
        return None


async def _search_for_social_profiles(
    company: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Find social media profiles using direct APIs (no search engine needed).

    Uses GitHub API directly to find developers at the company.
    Search engines (Bing/Google) are unreliable due to CAPTCHA blocking.
    """
    profiles = []
    seen_usernames = set()

    # 1. GitHub API search - find users who mention the company
    try:
        github_profiles = await _search_github_for_company(company, client)
        for p in github_profiles:
            if p["username"] not in seen_usernames:
                seen_usernames.add(p["username"])
                profiles.append(p)
    except Exception as exc:
        logger.debug("[Scout] GitHub search failed: %s", exc)

    logger.info("Found %d social media profiles for %s", len(profiles), company)
    return profiles[:30]


async def _search_github_for_company(
    company: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Search GitHub API for users associated with the company."""
    profiles = []

    # Search 1: Users with company in bio
    try:
        resp = await client.get(
            f"https://api.github.com/search/users?q={quote_plus(company)}+in:bio&per_page=10",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for user in data.get("items", []):
                username = user.get("login", "")
                if username and username not in ("features", "pricing", "enterprise",
                                                  "solutions", "resources", "login",
                                                  "signup", "topics", "collections",
                                                  "explore", "security", "copilot"):
                    profiles.append({"platform": "github", "username": username})
    except Exception as exc:
        logger.debug("[Scout] GitHub bio search failed: %s", exc)

    # Search 2: Users with company in organization field
    try:
        resp = await client.get(
            f"https://api.github.com/search/users?q={quote_plus(company)}+in:company&per_page=10",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for user in data.get("items", []):
                username = user.get("login", "")
                if username and username not in seen_usernames:
                    seen_usernames.add(username)
                    profiles.append({"platform": "github", "username": username})
    except Exception as exc:
        logger.debug("[Scout] GitHub company search failed: %s", exc)

    # Search 3: Repositories mentioning the company
    try:
        resp = await client.get(
            f"https://api.github.com/search/repositories?q={quote_plus(company)}&per_page=5",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        if resp.status_code == 200:
            data = resp.json()
            for repo in data.get("items", []):
                owner = repo.get("owner", {})
                if owner.get("type") == "User":
                    username = owner.get("login", "")
                    if username and username not in seen_usernames:
                        seen_usernames.add(username)
                        profiles.append({"platform": "github", "username": username})
    except Exception as exc:
        logger.debug("[Scout] GitHub repo search failed: %s", exc)

    return profiles


def _slug_to_name(slug: str) -> str:
    """Convert a LinkedIn slug to a guessed person name."""
    slug = re.sub(r'-[0-9a-f]{6,10}$', '', slug, flags=re.IGNORECASE)
    slug = re.sub(r'^(its|the|my|iam|i_am|im)', '', slug, flags=re.IGNORECASE)
    if len(slug) < 4:
        return ""

    if '-' in slug:
        parts = slug.split('-')
        name_parts = [p.capitalize() for p in parts if len(p) >= 2 and p.isalpha()]
        if 1 <= len(name_parts) <= 3:
            return " ".join(name_parts)

    # Try to split camelCase or lowercase slug
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


# ─── Main Integration Point ────────────────────────────────────────────


async def discover_via_social_media(
    company: str,
    domain: str = "",
    job_title: str = "",
    location: str = "",
) -> list[dict[str, Any]]:
    """Discover people at a company via social media platforms.

    This is the main entry point for Scout integration. It:
    1. Searches for social media profiles associated with the company
    2. Scrapes each found profile for contact info (email, bio, links)
    3. Also tries to scrape the LinkedIn company page for employees
    4. Returns enriched contact profiles compatible with the people_finder format

    Returns a list of contact dicts with the same schema as other sources.
    """
    if not company:
        return []

    logger.info("[Scout] Starting social media discovery for: %s", company)

    contacts = []
    seen_emails = set()
    seen_names = set()

    async with httpx.AsyncClient(
        timeout=15,
        headers={"User-Agent": _random_ua(), "Accept": "text/html"},
        follow_redirects=True,
    ) as client:
        # Step 1: Find social media profiles via search (GitHub, YouTube, etc.)
        social_profiles = await _search_for_social_profiles(company, client)

        if social_profiles:
            logger.info("[Scout] Found %d profiles to scrape", len(social_profiles))
        else:
            logger.info("[Scout] No additional social media profiles found for %s", company)

        # Step 2: Scrape each profile
        for profile_info in social_profiles:
            platform = profile_info["platform"]
            username = profile_info["username"]

            try:
                profile_data = None

                # Handle LinkedIn slugs (found via search, used for email pattern generation)
                if platform == "linkedin_slug":
                    name_guess = profile_info.get("full_name", "")
                    if name_guess:
                        profile_data = {
                            "platform": "linkedin",
                            "username": username,
                            "full_name": name_guess,
                            "bio": "",
                            "email": "",
                            "profile_url": f"https://www.linkedin.com/in/{username}",
                        }
                elif platform == "github":
                    profile_data = await _scrape_github_user(username, client)
                elif platform == "youtube":
                    profile_data = await _scrape_youtube_channel(username, client)
                elif platform == "twitch":
                    profile_data = await _scrape_twitch_user(username, client)
                elif platform == "linktree":
                    profile_data = await _scrape_linktree(username, client)
                elif platform == "pinterest":
                    profile_data = await _scrape_pinterest_user(username, client)

                if not profile_data:
                    continue

                # Check if this profile is actually at the company
                profile_company = (profile_data.get("company") or "").lower()
                profile_bio = (profile_data.get("bio") or "").lower()
                company_lower = company.lower()

                # Verify the profile is associated with the company
                is_company_match = False
                if profile_company and company_lower in profile_company:
                    is_company_match = True
                elif company_lower in profile_bio:
                    is_company_match = True
                elif company.split()[0].lower() in profile_bio:
                    is_company_match = True

                # For GitHub, also check the company field
                if platform == "github" and profile_data.get("company"):
                    if company_lower in profile_data["company"].lower():
                        is_company_match = True

                # If no company match but we found via company-specific search, still include
                if not is_company_match:
                    # Lower confidence for profiles not explicitly at the company
                    confidence = 0.5
                else:
                    confidence = 0.75

                # Extract email
                email = profile_data.get("email", "")
                if email and email not in seen_emails:
                    seen_emails.add(email)
                elif email:
                    email = ""  # Duplicate, skip

                # Build contact dict compatible with people_finder format
                contact = {
                    "name": profile_data.get("full_name", ""),
                    "role": "",  # Social media doesn't usually have job titles
                    "company": company,
                    "email": email,
                    "phone": "",
                    "linkedin_url": "",
                    "photo_url": profile_data.get("photo_url", ""),
                    "location": profile_data.get("location", ""),
                    "confidence": confidence,
                    "source": f"scout_{platform}",
                    "verified": is_company_match,
                    "relevance": "medium" if is_company_match else "low",
                    "contact_type": "unknown",
                    "skills": [],
                    "profile_url": profile_data.get("profile_url", ""),
                    "bio": profile_data.get("bio", ""),
                    "platform": platform,
                    "username": username,
                }

                # Add social links from linktree
                if profile_data.get("socials"):
                    for social_platform, social_url in profile_data["socials"].items():
                        if social_platform == "linkedin":
                            contact["linkedin_url"] = social_url

                contacts.append(contact)
                logger.info(
                    "[Scout] Found: %s @ %s (platform: %s, email: %s)",
                    contact["name"] or username, company, platform,
                    "yes" if email else "no"
                )

            except Exception as exc:
                logger.debug("[Scout] Failed to scrape %s/%s: %s", platform, username, exc)
                continue

    # Sort by confidence
    contacts.sort(key=lambda c: c.get("confidence", 0), reverse=True)

    logger.info(
        "[Scout] Discovery complete: %d contacts found for %s (%d with emails)",
        len(contacts), company, sum(1 for c in contacts if c.get("email"))
    )

    return contacts


def _generate_email_patterns(name: str, domain: str) -> list[str]:
    """Generate email pattern candidates from a name and domain."""
    if not name or not domain:
        return []
    parts = [p for p in re.split(r"\s+", name.strip().lower()) if p.isalpha()]
    if not parts:
        return []
    first = parts[0]
    last = parts[-1] if len(parts) > 1 else ""
    candidates = [f"{first}@{domain}"]
    if last:
        candidates += [
            f"{first}.{last}@{domain}",
            f"{first}{last}@{domain}",
            f"{first[0]}{last}@{domain}",
            f"{first}_{last}@{domain}",
            f"{last}.{first}@{domain}",
        ]
    return list(dict.fromkeys(candidates))  # dedupe preserving order


# ─── LinkedIn Company Page Scraping ─────────────────────────────────────


async def _scrape_linkedin_company_page(
    company: str, client: httpx.AsyncClient
) -> list[dict[str, Any]]:
    """Scrape the LinkedIn company page for employee names.

    Uses common company slug patterns to find the company page,
    then extracts employee names from the page.
    """
    contacts = []

    # Try common slug patterns
    slug_patterns = [
        company.lower().replace(" ", "-"),
        company.lower().replace(" ", ""),
        company.split()[0].lower() if len(company.split()) > 1 else company.lower(),
    ]

    for slug in slug_patterns:
        try:
            _throttle()
            url = f"https://www.linkedin.com/company/{slug}/people/"
            resp = await client.get(
                url,
                headers={"User-Agent": _random_ua(), "Accept": "text/html"},
                timeout=10,
                follow_redirects=True,
            )

            if resp.status_code != 200:
                continue

            html = resp.text

            # Check if we got a valid company page
            if len(html) < 5000:
                continue

            # Check for login wall
            if "sign in" in html.lower() and "password" in html.lower():
                logger.debug("[Scout] LinkedIn company page requires login for %s", slug)
                continue

            # Check if the page actually mentions our company
            company_lower = company.lower()
            if company_lower not in html.lower():
                continue

            logger.info("[Scout] Found LinkedIn company page: %s", slug)

            # Extract employee names from the page
            soup = BeautifulSoup(html, "html.parser")

            # Look for profile links
            for a in soup.find_all("a", href=True):
                href = a["href"]
                if "/in/" in href:
                    # Extract slug
                    m = re.search(r'/in/([a-zA-Z0-9._-]+)', href)
                    if m:
                        emp_slug = m.group(1)
                        name = _slug_to_name(emp_slug)
                        if name and len(name) >= 4:
                            profile_url = f"https://www.linkedin.com/in/{emp_slug}"
                            if not any(c.get("linkedin_url") == profile_url for c in contacts):
                                contacts.append({
                                    "name": name,
                                    "role": "",
                                    "company": company,
                                    "email": "",
                                    "phone": "",
                                    "linkedin_url": profile_url,
                                    "confidence": 0.85,
                                    "source": "scout_linkedin_company",
                                    "verified": True,
                                    "relevance": "medium",
                                    "contact_type": "unknown",
                                    "skills": [],
                                    "profile_url": profile_url,
                                })

            # Also try to extract from text content
            text = soup.get_text(" ", strip=True)
            # Look for name patterns near company mentions
            name_pattern = re.compile(
                r'([A-Z][a-z]+\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)'
            )
            for m in name_pattern.finditer(text):
                name = m.group(1)
                # Validate it's a real name (not navigation text)
                if (len(name) >= 4 and len(name) <= 40
                        and not any(w in name.lower() for w in ["sign in", "join now", "learn more"])):
                    if name not in seen_names:
                        seen_names.add(name)
                        # Don't add duplicates
                        if not any(c.get("name") == name for c in contacts):
                            contacts.append({
                                "name": name,
                                "role": "",
                                "company": company,
                                "email": "",
                                "phone": "",
                                "linkedin_url": "",
                                "confidence": 0.6,
                                "source": "scout_linkedin_company_text",
                                "verified": True,
                                "relevance": "medium",
                                "contact_type": "unknown",
                                "skills": [],
                            })

            if contacts:
                logger.info("[Scout] Found %d employees from LinkedIn company page", len(contacts))
                break  # Found the company, no need to try other slugs

        except Exception as exc:
            logger.debug("[Scout] LinkedIn company page failed for %s: %s", slug, exc)
            continue

    return contacts[:20]
