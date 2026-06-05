"""Core interfaces for the ingestion engine."""
from __future__ import annotations

import abc
import datetime
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class JobRecord:
    title: str
    company: str = ""
    location: str = ""
    description: str = ""
    source: str = ""
    source_url: str = ""
    apply_url: str = ""
    salary: str = ""
    remote: bool = False
    skills_required: list[str] = field(default_factory=list)
    posted_date: Optional[datetime.datetime] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def dedup_key(self) -> str:
        if self.source_url:
            return f"url:{self.source_url.strip().lower()}"
        if self.apply_url:
            return f"apply:{self.apply_url.strip().lower()}"
        return (
            f"composite:{self.title.strip().lower()}|"
            f"{self.company.strip().lower()}|{self.source.strip().lower()}"
        )

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        if self.posted_date:
            d["posted_date"] = self.posted_date.isoformat()
        return d


@dataclass
class SourceStatus:
    name: str
    last_run: Optional[str] = None
    ok: bool = True
    jobs_fetched: int = 0
    jobs_new: int = 0
    last_error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class StatusStore:
    """In-memory per-source status store (Redis-swappable later)."""

    def __init__(self) -> None:
        self._statuses: dict[str, SourceStatus] = {}

    def record(self, name: str, *, ok: bool, jobs_fetched: int = 0,
               jobs_new: int = 0, error: Optional[str] = None) -> None:
        self._statuses[name] = SourceStatus(
            name=name,
            last_run=datetime.datetime.utcnow().isoformat(),
            ok=ok,
            jobs_fetched=jobs_fetched,
            jobs_new=jobs_new,
            last_error=error,
        )

    def all(self) -> list[dict[str, Any]]:
        return [s.to_dict() for s in self._statuses.values()]


status_store = StatusStore()


class BaseIngestionSource(abc.ABC):
    name: str = "base"

    @abc.abstractmethod
    async def fetch(self) -> list[JobRecord]:
        raise NotImplementedError
