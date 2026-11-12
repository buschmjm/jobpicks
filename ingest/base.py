"""SourceAdapter interface — one plugin per job provider (plan §8)."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from ingest.quota import QuotaTracker
from ingest.schema import StandardJob


@dataclass(frozen=True)
class FetchParams:
    """Common fetch parameters across adapters."""

    search_terms: tuple[str, ...] = ()
    salary_min: int | None = None
    max_days_old: int = 60
    remote_only: bool | None = None  # None = no remote filter
    page: int = 1
    results_per_page: int = 20
    latitude: float | None = None
    longitude: float | None = None
    radius_km: float | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class FetchResult:
    """Result of a single adapter fetch call."""

    jobs: list[StandardJob]
    source: str
    requests_used: int = 1
    page: int = 1
    total_available: int | None = None
    filtered_out: int = 0
    raw_pages: list[dict[str, Any]] = field(default_factory=list)


class SourceAdapter(ABC):
    """Plugin interface: each provider implements fetch() and reports quota usage."""

    source_name: str

    def __init__(
        self,
        *,
        client: httpx.AsyncClient | None = None,
        quota: QuotaTracker | None = None,
    ) -> None:
        self._client = client
        self._owns_client = client is None
        self.quota = quota

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client

    async def aclose(self) -> None:
        if self._owns_client and self._client is not None:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> SourceAdapter:
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    def _reserve_quota(self, count: int = 1) -> None:
        if self.quota is not None:
            self.quota.consume(self.source_name, count)

    def quota_remaining(self) -> int | None:
        if self.quota is None:
            return None
        return self.quota.remaining(self.source_name)

    def quota_used(self) -> int | None:
        if self.quota is None:
            return None
        return self.quota.used(self.source_name)

    @staticmethod
    def utc_now() -> datetime:
        return datetime.now(UTC)

    @abstractmethod
    async def fetch(self, params: FetchParams) -> FetchResult:
        """Pull jobs from the provider and return normalized StandardJob records."""
