"""Job source adapters."""

from ingest.adapters.adzuna import AdzunaAdapter
from ingest.adapters.greenhouse import GreenhouseAdapter
from ingest.adapters.jsearch import JSearchAdapter
from ingest.adapters.lever import LeverAdapter
from ingest.adapters.remotive import RemotiveAdapter
from ingest.adapters.usajobs import USAJobsAdapter

__all__ = [
    "AdzunaAdapter",
    "GreenhouseAdapter",
    "JSearchAdapter",
    "LeverAdapter",
    "RemotiveAdapter",
    "USAJobsAdapter",
]
