"""RemoteOK ingestion source (free public JSON API, no signup)."""
from __future__ import annotations

import datetime
import logging
from typing import Any

import httpx

from ingestion.base import BaseIngestionSource, JobRecord

logger = logging.getLogger("ingestion.remoteok")

REMOTEOK_API_URL = "https://remoteok.com/api"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


class RemoteOKSource(BaseIngestionSource):
    name = "remoteok"

    def __init__(self, timeout: float = 20.0) -> None:
        self._timeout = timeout

    async def fetch(self) -> list[JobRecord]:
        async with httpx.AsyncClient(timeout=self._timeout, headers=_HEADERS) as client:
            resp = await client.get(REMOTEOK_API_URL)
            resp.raise_for_status()
            payload = resp.json()
        return self.parse(payload)

    @staticmethod
    def parse(payload: Any) -> list[JobRecord]:
        if not isinstance(payload, list):
            return []
        records: list[JobRecord] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            if "position" not in item and "id" not in item:
                continue
            position = (item.get("position") or item.get("title") or "").strip()
            if not position:
                continue
            tags = item.get("tags") or []
            if not isinstance(tags, list):
                tags = []
            posted = None
            raw_date = item.get("date")
            if isinstance(raw_date, str) and raw_date:
                try:
                    posted = datetime.datetime.fromisoformat(
                        raw_date.replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                except ValueError:
                    posted = None
            url = (item.get("url") or "").strip()
            apply_url = (item.get("apply_url") or url).strip()
            slug = item.get("slug") or ""
            raw_id = item.get("id")
            # Stable per-source id: RemoteOK's integer id is unique and
            # durable; combine with slug when present for debuggability.
            external_id = ""
            if raw_id is not None:
                external_id = f"{raw_id}" if not slug else f"{raw_id}-{slug}"
            records.append(
                JobRecord(
                    title=position,
                    company=(item.get("company") or "").strip(),
                    location=(item.get("location") or "Remote").strip(),
                    description=(item.get("description") or "").strip(),
                    source="remoteok",
                    source_url=url,
                    apply_url=apply_url,
                    salary=_format_salary(item),
                    external_id=external_id,
                    remote=True,
                    skills_required=[str(t) for t in tags],
                    posted_date=posted,
                    raw=item,
                )
            )
        return records


def _format_salary(item: dict[str, Any]) -> str:
    lo = item.get("salary_min")
    hi = item.get("salary_max")
    if lo and hi:
        return f"{lo} - {hi}"
    if lo:
        return str(lo)
    return ""
