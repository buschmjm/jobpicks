"""Tests for US country/location classification."""

from datetime import UTC, date, datetime

from ingest.country import (
    DEFAULT_INGEST_COUNTRY,
    infer_country_from_location,
    is_us_job,
    is_us_job_record,
    resolve_job_country,
)
from ingest.schema import StandardJob


def _job(**overrides: object) -> StandardJob:
    base = dict(
        title="Engineer",
        company="Acme",
        location="San Francisco, CA",
        date_posted=date(2026, 8, 20),
        description="Build things.",
        source="greenhouse",
        source_url="https://example.com/job/1",
        collected_timestamp=datetime(2026, 8, 27, tzinfo=UTC),
    )
    base.update(overrides)
    return StandardJob(**base)  # type: ignore[arg-type]


def test_us_state_location() -> None:
    assert infer_country_from_location("Austin, TX") == DEFAULT_INGEST_COUNTRY


def test_non_us_markers() -> None:
    assert infer_country_from_location("Worldwide") == "NON_US"
    assert infer_country_from_location("London, UK") == "NON_US"
    assert infer_country_from_location("Remote - Canada") == "NON_US"


def test_us_positive_markers() -> None:
    assert infer_country_from_location("Remote - United States") == DEFAULT_INGEST_COUNTRY


def test_is_us_job_for_aggregator_without_country() -> None:
    assert is_us_job(_job(source="jsearch", country=None, location="Remote"))


def test_is_us_job_rejects_international_greenhouse() -> None:
    assert not is_us_job(_job(source="greenhouse", location="Berlin, Germany"))


def test_is_us_job_rejects_ambiguous_remote_board() -> None:
    assert not is_us_job(_job(source="greenhouse", location="Remote"))


def test_is_us_job_record_uses_stored_country() -> None:
    assert is_us_job_record(country="US", location="Remote", source="greenhouse")


def test_resolve_job_country_from_explicit_field() -> None:
    assert resolve_job_country(country="USA", location="Remote") == DEFAULT_INGEST_COUNTRY
