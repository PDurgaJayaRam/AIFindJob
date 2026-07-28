"""Arbeitnow ingestion source (free public API, no key)."""
from __future__ import annotations

import datetime
import logging
from typing import Any

import httpx

from ingestion.base import BaseIngestionSource, JobRecord

logger = logging.getLogger("ingestion.arbeitnow")

ARBEITNOW_API_URL = "https://www.arbeitnow.com/api/job-board-api"


class ArbeitnowSource(BaseIngestionSource):
    name = "arbeitnow"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def fetch(self) -> list[JobRecord]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.get(ARBEITNOW_API_URL)
            resp.raise_for_status()
            payload = resp.json()
        return self.parse(payload)

    @staticmethod
    def parse(payload: Any) -> list[JobRecord]:
        if not isinstance(payload, dict):
            return []
        data = payload.get("data")
        if not isinstance(data, list):
            return []
        records: list[JobRecord] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            title = (item.get("title") or "").strip()
            if not title:
                continue
            tags = item.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            posted = None
            created = item.get("created_at")
            if isinstance(created, (int, float)):
                try:
                    posted = datetime.datetime.utcfromtimestamp(int(created))
                except (ValueError, OSError):
                    posted = None
            elif isinstance(created, str) and created:
                try:
                    posted = datetime.datetime.fromisoformat(
                        created.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    posted = None
            url = (item.get("url") or "").strip()
            slug = (item.get("slug") or "").strip()
            records.append(
                JobRecord(
                    title=title,
                    company=(item.get("company_name") or "").strip(),
                    location=(item.get("location") or "Remote").strip(),
                    description=(item.get("description") or "").strip(),
                    source="arbeitnow",
                    source_url=url,
                    apply_url=url,
                    salary="",
                    external_id=slug,
                    remote=bool(item.get("remote", False)),
                    skills_required=[str(t) for t in tags],
                    posted_date=posted,
                    raw=item,
                )
            )
        return records
