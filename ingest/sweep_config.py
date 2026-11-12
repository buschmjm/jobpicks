"""Constants for nightly board-sweep ingest (see docs/board-sweep-scoring-implementation-plan.md)."""

from __future__ import annotations

import os

NIGHTLY_MAX_DAYS_OLD = 1
USAJOBS_MAX_PAGES = 5
JSEARCH_ENABLED_ENV = "JSEARCH_ENABLED"


def jsearch_enabled() -> bool:
    return os.environ.get(JSEARCH_ENABLED_ENV, "").lower() == "true"
