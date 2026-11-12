"""Job ingestion framework: adapters, normalization, dedupe, freshness."""

from ingest.base import FetchParams, FetchResult, SourceAdapter
from ingest.pipeline import FreshnessConfig, IngestPipeline
from ingest.quota import QuotaBudget, QuotaTracker
from ingest.schema import SalaryInfo, StandardJob

__all__ = [
    "FetchParams",
    "FetchResult",
    "FreshnessConfig",
    "IngestPipeline",
    "QuotaBudget",
    "QuotaTracker",
    "SalaryInfo",
    "SourceAdapter",
    "StandardJob",
]
