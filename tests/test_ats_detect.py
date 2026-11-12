"""Tests for ATS detection and apply URL intelligence."""

from __future__ import annotations

from core.apply.ats_detect import (
    detect_ats,
    detect_ats_type,
    enrich_standard_job_apply,
    pick_best_jsearch_apply_link,
    resolve_apply_url,
)


def test_detect_greenhouse_url() -> None:
    url = "https://boards.greenhouse.io/acme/jobs/123456"
    ats_type, metadata = detect_ats(url)
    assert ats_type == "greenhouse"
    assert metadata["board_token"] == "acme"
    assert metadata["posting_id"] == "123456"
    assert detect_ats_type(url) == "greenhouse"


def test_detect_lever_url() -> None:
    url = "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    ats_type, metadata = detect_ats(url)
    assert ats_type == "lever"
    assert metadata["site_slug"] == "acme"
    assert metadata["posting_id"] == "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def test_resolve_apply_url_prefers_explicit() -> None:
    assert (
        resolve_apply_url(
            source_url="https://example.com/listing",
            apply_url="https://boards.greenhouse.io/acme/jobs/1",
        )
        == "https://boards.greenhouse.io/acme/jobs/1"
    )
    assert resolve_apply_url(source_url="https://example.com/listing") == "https://example.com/listing"


def test_pick_best_jsearch_apply_link_prefers_greenhouse() -> None:
    link, ats_type, metadata = pick_best_jsearch_apply_link(
        apply_link="https://www.linkedin.com/jobs/view/123",
        apply_options=[
            {"apply_link": "https://www.indeed.com/viewjob?jk=abc"},
            {"apply_link": "https://boards.greenhouse.io/acme/jobs/99"},
            {"apply_link": "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        ],
    )
    assert link == "https://boards.greenhouse.io/acme/jobs/99"
    assert ats_type == "greenhouse"
    assert metadata["board_token"] == "acme"


def test_enrich_standard_job_apply_detects_from_source() -> None:
    source = "https://jobs.lever.co/acme/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    apply_url, ats_type, metadata = enrich_standard_job_apply(source_url=source)
    assert apply_url == source
    assert ats_type == "lever"
    assert metadata["site_slug"] == "acme"
