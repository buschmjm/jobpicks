"""Per-source daily quota budgets (plan §8 — especially JSearch metering)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime


class QuotaExceededError(RuntimeError):
    """Raised when a source adapter would exceed its daily budget."""


@dataclass(frozen=True)
class QuotaBudget:
    """Daily request budget for a single source."""

    source: str
    daily_limit: int
    warn_threshold_pct: float = 0.8

    def __post_init__(self) -> None:
        if self.daily_limit <= 0:
            msg = "daily_limit must be positive"
            raise ValueError(msg)
        if not 0 < self.warn_threshold_pct <= 1:
            msg = "warn_threshold_pct must be in (0, 1]"
            raise ValueError(msg)


@dataclass
class QuotaTracker:
    """Tracks per-source daily consumption; resets at UTC midnight."""

    budgets: dict[str, QuotaBudget] = field(default_factory=dict)
    _usage: dict[str, int] = field(default_factory=dict)
    _usage_day: date = field(default_factory=lambda: datetime.now(UTC).date())

    def register(self, budget: QuotaBudget) -> None:
        self.budgets[budget.source] = budget
        self._usage.setdefault(budget.source, 0)

    def _maybe_roll_day(self) -> None:
        today = datetime.now(UTC).date()
        if today != self._usage_day:
            self._usage = {source: 0 for source in self.budgets}
            self._usage_day = today

    def remaining(self, source: str) -> int:
        self._maybe_roll_day()
        budget = self.budgets.get(source)
        if budget is None:
            return 0
        return max(0, budget.daily_limit - self._usage.get(source, 0))

    def used(self, source: str) -> int:
        self._maybe_roll_day()
        return self._usage.get(source, 0)

    def is_warning(self, source: str) -> bool:
        budget = self.budgets.get(source)
        if budget is None:
            return False
        used = self.used(source)
        return used / budget.daily_limit >= budget.warn_threshold_pct

    def consume(self, source: str, count: int = 1) -> None:
        """Reserve quota units; raises QuotaExceededError if budget exhausted."""
        if count <= 0:
            return
        self._maybe_roll_day()
        budget = self.budgets.get(source)
        if budget is None:
            msg = f"No quota budget registered for source {source!r}"
            raise KeyError(msg)
        current = self._usage.get(source, 0)
        if current + count > budget.daily_limit:
            msg = (
                f"Quota exceeded for {source}: "
                f"{current + count}/{budget.daily_limit} daily requests"
            )
            raise QuotaExceededError(msg)
        self._usage[source] = current + count

    def try_consume(self, source: str, count: int = 1) -> bool:
        try:
            self.consume(source, count)
        except QuotaExceededError:
            return False
        return True


# Default JSearch budget: ~30 terms × ~3 pages ≈ 90/day, well under 10k/mo tier.
DEFAULT_JSEARCH_DAILY = 100
DEFAULT_ADZUNA_DAILY = 500
DEFAULT_REMOTIVE_DAILY = 50
DEFAULT_GREENHOUSE_DAILY = 500
DEFAULT_LEVER_DAILY = 500
DEFAULT_USAJOBS_DAILY = 50


def default_quota_tracker() -> QuotaTracker:
    tracker = QuotaTracker()
    tracker.register(QuotaBudget(source="jsearch", daily_limit=DEFAULT_JSEARCH_DAILY))
    tracker.register(QuotaBudget(source="adzuna", daily_limit=DEFAULT_ADZUNA_DAILY))
    tracker.register(QuotaBudget(source="remotive", daily_limit=DEFAULT_REMOTIVE_DAILY))
    tracker.register(QuotaBudget(source="greenhouse", daily_limit=DEFAULT_GREENHOUSE_DAILY))
    tracker.register(QuotaBudget(source="lever", daily_limit=DEFAULT_LEVER_DAILY))
    tracker.register(QuotaBudget(source="usajobs", daily_limit=DEFAULT_USAJOBS_DAILY))
    return tracker
