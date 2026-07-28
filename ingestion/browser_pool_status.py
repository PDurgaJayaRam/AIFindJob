"""Browser Pool status store for per-portal tracking."""
from __future__ import annotations

import time
from typing import Dict, Any


class BrowserPoolStatus:
    """Tracks status per portal for the browser pool scraper."""

    def __init__(self):
        self._status: Dict[str, Dict[str, Any]] = {}

    def get(self, portal: str) -> Dict[str, Any]:
        """Get status for a portal, returns default if not exists."""
        return self._status.setdefault(portal, {
            "jobs_new": 0,
            "last_check": 0,
            "errors": 0,
            "last_error": None,
        })

    def set(self, portal: str, key: str, value: Any):
        """Set a specific status key for a portal."""
        if portal not in self._status:
            self._status[portal] = {}
        self._status[portal][key] = value

    def all(self) -> Dict[str, Dict[str, Any]]:
        """Get all portal statuses."""
        return self._status

    def record_success(self, portal: str, jobs_new: int = 0):
        """Record successful scrape for a portal."""
        self._status[portal] = {
            "jobs_new": jobs_new,
            "last_check": time.time(),
            "errors": 0,
            "last_error": None,
        }

    def record_error(self, portal: str, error: str = ""):
        """Record error for a portal."""
        if portal not in self._status:
            self._status[portal] = {}
        self._status[portal]["errors"] = self._status[portal].get("errors", 0) + 1
        self._status[portal]["last_error"] = error[:200]
        self._status[portal]["last_check"] = time.time()


browser_pool_status_store = BrowserPoolStatus()