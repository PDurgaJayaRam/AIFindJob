"""Adzuna ingestion source (OPTIONAL, free dev tier). Inactive without keys."""
from __future__ import annotations

import datetime
import logging
import os
from typing import Any

import httpx

from ingestion.base import BaseIngestionSource, JobRecord

logger = logging.getLogger("ingestion.adzuna")


class AdzunaSource(BaseIngestionSource):
    name = "adzuna"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout
        self._app_id = os.getenv("ADZUNA_APP_ID", "")
        self._app_key = os.getenv("ADZUNA_APP_KEY", "")
        self._country = os.getenv("ADZUNA_COUNTRY", "in")
        self._query = os.getenv("ADZUNA_QUERY", "").strip()
        if not self._query:
            self._query = self._fetch_query_from_db()
        self._results = int(os.getenv("ADZUNA_RESULTS", "50"))

    @staticmethod
    def _fetch_query_from_db():
        try:
            import sqlite3, json
            db_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", "career_agent.db")
            conn = sqlite3.connect(db_path)
            row = conn.execute("SELECT desired_roles FROM user_preferences ORDER BY id DESC LIMIT 1").fetchone()
            conn.close()
            if row and row[0]:
                roles = json.loads(row[0])
                return roles[0] if roles else ""
        except Exception:
            pass
        return ""

    @property
    def is_active(self) -> bool:
        return bool(self._app_id and self._app_key)

    async def fetch(self) -> list[JobRecord]:
        if not self.is_active:
            logger.info("Adzuna inactive (ADZUNA_APP_ID/ADZUNA_APP_KEY not set)")
            return []
        url = f"https://api.adzuna.com/v1/api/jobs/{self._country}/search/1"
        params = {
            "app_id": self._app_id,
            "app_key": self._app_key,
            "results_per_page": self._results,
            "what": self._query,
            "content-type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
        return self.parse(payload)

    @staticmethod
    def parse(payload: Any) -> list[JobRecord]:
        if not isinstance(payload, dict):
            return []
        results = payload.get("results")
        if not isinstance(results, list):
            return []
        records: list[JobRecord] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            company = ""
            company_obj = item.get("company")
            if isinstance(company_obj, dict):
                company = (company_obj.get("display_name") or "").strip()
            location = ""
            loc_obj = item.get("location")
            if isinstance(loc_obj, dict):
                location = (loc_obj.get("display_name") or "").strip()
            posted = None
            created = item.get("created")
            if isinstance(created, str) and created:
                try:
                    posted = datetime.datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    posted = None
            url = (item.get("redirect_url") or "").strip()
            salary = ""
            lo, hi = item.get("salary_min"), item.get("salary_max")
            if lo and hi:
                salary = f"{int(lo)} - {int(hi)}"
            records.append(
                JobRecord(
                    title=title,
                    company=company,
                    location=location or "India",
                    description=(item.get("description") or "").strip(),
                    source="adzuna",
                    source_url=url,
                    apply_url=url,
                    salary=salary,
                    remote=False,
                    skills_required=[],
                    posted_date=posted,
                    raw=item,
                )
            )
        return records
