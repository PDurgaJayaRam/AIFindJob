"""Email pattern inference + free MX/SMTP verification.

Inference is pure Python. Verification uses DNS MX lookup + SMTP RCPT TO check
to verify if an email mailbox actually exists — no API key needed.
"""
from __future__ import annotations

import asyncio
import logging
import re
import smtplib
import socket
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
    """Attach a confidence score to an inferred email."""
    if mx_ok is False:
        return {"email": email, "confidence": 0.0, "status": "invalid_domain"}
    if mx_ok is True:
        return {"email": email, "confidence": 0.25, "status": "domain_ok"}
    return {"email": email, "confidence": 0.15, "status": "unverified"}


def verify_email_smtp(email: str, domain: str, timeout: float = 5.0) -> dict[str, Any]:
    """Verify if an email exists using SMTP RCPT TO check.

    Tries port 25 first, then port 587 (STARTTLS). Many ISPs block port 25.
    Free, no API key needed.
    """
    try:
        import dns.resolver
        answers = dns.resolver.resolve(domain, "MX")
        mx_host = str(answers[0].exchange).rstrip(".")
    except Exception:
        return {"email": email, "confidence": 0.1, "status": "no_mx_record"}

    # Try port 25 first, then 587
    for port in [25, 587]:
        try:
            smtp = smtplib.SMTP(mx_host, port, timeout=timeout)
            smtp.ehlo("verify.example.com")
            if port == 587:
                try:
                    smtp.starttls()
                    smtp.ehlo("verify.example.com")
                except Exception:
                    pass
            smtp.mail("verify@example.com")
            code, msg = smtp.rcpt(email)
            smtp.quit()

            if code == 250:
                return {"email": email, "confidence": 0.65, "status": "verified"}
            elif code in (550, 551, 552, 553):
                return {"email": email, "confidence": 0.0, "status": "mailbox_not_found"}
            else:
                return {"email": email, "confidence": 0.15, "status": "smtp_ambiguous"}
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPResponseException,
                socket.timeout, ConnectionRefusedError, ConnectionResetError, OSError):
            continue
        except Exception:
            continue

    return {"email": email, "confidence": 0.1, "status": "smtp_connection_failed"}


def verify_emails_for_contact(
    name: str, domain: str, max_verify: int = 3
) -> list[dict[str, Any]]:
    """Generate email candidates and verify them via SMTP.

    Returns only emails that passed verification or have high confidence.
    """
    if not name or not domain:
        return []

    candidates = infer_emails(name, domain)[:max_verify]
    results = []

    for email in candidates:
        result = verify_email_smtp(email, domain)
        results.append(result)
        # If verified, no need to check more patterns
        if result["status"] == "verified":
            break

    return results
