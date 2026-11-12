"""Per-host rate limiting for Tier-2 board endpoints (plan §8: ≤1 req/sec)."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field


@dataclass
class HostRateLimiter:
    """Enforce a minimum interval between requests to the same host."""

    min_interval_seconds: float = 1.0
    _last_request: dict[str, float] = field(default_factory=dict)
    _locks: dict[str, asyncio.Lock] = field(default_factory=dict)

    def _lock_for(self, host: str) -> asyncio.Lock:
        if host not in self._locks:
            self._locks[host] = asyncio.Lock()
        return self._locks[host]

    async def wait(self, host: str) -> None:
        """Block until at least min_interval_seconds have elapsed since the last call."""
        async with self._lock_for(host):
            now = time.monotonic()
            last = self._last_request.get(host, 0.0)
            delay = self.min_interval_seconds - (now - last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last_request[host] = time.monotonic()


DEFAULT_USER_AGENT = "JobPlatform/0.1 (+https://github.com/buschmjm/job-platform; ingest@jbuschmann.com)"
