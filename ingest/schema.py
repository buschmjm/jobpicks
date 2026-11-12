"""Standard job schema — adapter output contract (plan §8, §18)."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WorkArrangement(StrEnum):
    REMOTE = "remote"
    HYBRID = "hybrid"
    ONSITE = "onsite"
    UNKNOWN = "unknown"


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    FREELANCE = "freelance"
    UNKNOWN = "unknown"


class SalaryInfo(BaseModel):
    """Normalized salary when source provides structured or parseable values."""

    model_config = ConfigDict(frozen=True)

    min_amount: float | None = None
    max_amount: float | None = None
    currency: str = "USD"
    period: str = "year"  # year | hour | month | day
    raw: str | None = None  # original string when only text is available


class StandardJob(BaseModel):
    """Normalized job record emitted by every SourceAdapter."""

    model_config = ConfigDict(frozen=True)

    # Core contract (§18)
    title: str
    company: str
    location: str
    remote: bool | None = None  # None = unknown (never infer onsite from null)
    latitude: float | None = None
    longitude: float | None = None
    employment_type: EmploymentType = EmploymentType.UNKNOWN
    salary: SalaryInfo | None = None
    date_posted: date
    description: str
    requirements: str | None = None
    source: str
    source_url: str
    collected_timestamp: datetime

    # Apply URL intelligence (Phase 4)
    apply_url: str | None = None
    ats_type: str | None = None
    ats_metadata: dict[str, Any] | None = None

    # Normalized extensions (§8 / JSearch pre-extracted fields)
    source_id: str | None = None
    country: str | None = None
    work_arrangement: WorkArrangement = WorkArrangement.UNKNOWN
    seniority_level: str | None = None
    required_experience_years: int | None = None
    required_technologies: tuple[str, ...] = Field(default_factory=tuple)
    benefits: tuple[str, ...] = Field(default_factory=tuple)
    publisher: str | None = None

    # Pipeline metadata (filled by ingest pipeline, not adapters)
    description_simhash: str | None = None
    canonical_hash: str | None = None
    raw_payload: dict[str, Any] | None = Field(default=None, repr=False)

    @field_validator("title", "company", "location", "description", "source", "source_url")
    @classmethod
    def strip_required_strings(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            msg = "Required string fields must be non-empty after stripping"
            raise ValueError(msg)
        return stripped

    @field_validator("required_technologies", "benefits", mode="before")
    @classmethod
    def coerce_str_tuple(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(str(item).strip() for item in value if str(item).strip())
