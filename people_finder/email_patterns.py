"""Email pattern inference + free MX/SMTP-style verification.

Inference is pure Python. Verification uses a DNS MX lookup when `dnspython` is
available (lazy import); if not installed, verification is skipped and the
candidate is marked 'guessed' (lower confidence) rather than failing.
"""
from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("people_finder.email")


def infer_emails(full_name: str, domain: str) -> list[str]:
    """Generate likely email candidates from a name + company domain."""
    domain = (domain or "").strip().lower().lstrip("@")
    if not domain or not full_name:
        return []
    parts = [p for p in re.split(r"\s+", full_name.strip().lower()) if p.isalpha()]
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
    # De-dup preserving order.
    seen: list[str] = []
    for c in candidates:
        if c not in seen:
            seen.append(c)
    return seen


def domain_has_mx(domain: str) -> bool | None:
    """Return True/False if the domain has MX records, or None if unknown.

    Uses dnspython lazily. None means 'could not verify' (tool not installed or
    lookup failed) so the caller treats the email as guessed, not invalid.
    """
    domain = (domain or "").strip().lower().lstrip("@")
    if not domain:
        return False
    try:
        import dns.resolver  # lazy/optional
    except Exception:
        logger.info("dnspython not installed; skipping MX verification")
        return None
    try:
        answers = dns.resolver.resolve(domain, "MX")
        return len(list(answers)) > 0
    except Exception as exc:
        logger.info("MX lookup failed for %s: %s", domain, exc)
        return None


def score_email(email: str, mx_ok: bool | None) -> dict[str, Any]:
    """Attach a confidence score to an inferred email.

    - mx_ok True  -> domain accepts mail: 'guessed-verified-domain' (0.5)
    - mx_ok None  -> unverified: 'guessed' (0.3)
    - mx_ok False -> domain has no MX: 'invalid' (0.0)
    Note: MX only proves the domain can receive mail, not that the exact mailbox
    exists, so even verified-domain inferred emails stay below 'confirmed'.
    """
    if mx_ok is False:
        return {"email": email, "confidence": 0.0, "status": "invalid_domain"}
    if mx_ok is True:
        return {"email": email, "confidence": 0.5, "status": "guessed_verified_domain"}
    return {"email": email, "confidence": 0.3, "status": "guessed"}
