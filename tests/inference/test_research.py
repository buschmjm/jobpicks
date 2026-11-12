"""Tests for advisor research tools."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import respx
from inference.research.allowlist import is_fetch_allowed
from inference.research.planner import should_force_research
from inference.research.searxng import search_web
from inference.research.tools import ResearchBundle, execute_research_plan


def test_force_research_keywords() -> None:
    assert should_force_research("What is the salary for SREs in Austin?")
    assert should_force_research("Should I apply to this role?")
    assert should_force_research("Fit assessment for this job description")
    assert not should_force_research("Summarize the gaps only from my resume.")


def test_fetch_allowlist() -> None:
    assert is_fetch_allowed("https://www.bls.gov/ooh/computer-and-information-technology/")
    assert is_fetch_allowed("https://texas.gov/labor")
    assert is_fetch_allowed("https://www.levels.fyi/t/software-engineer")
    assert not is_fetch_allowed("http://bls.gov/ooh/")  # http blocked
    assert not is_fetch_allowed("https://evil.example.com/salary")


@respx.mock
def test_searxng_search_parses_results() -> None:
    respx.get("http://searxng.test/search").mock(
        return_value=httpx.Response(
            200,
            json={
                "results": [
                    {
                        "title": "SRE salary Austin",
                        "url": "https://www.levels.fyi/t/sre",
                        "content": "Median total comp around $180k",
                    }
                ]
            },
        )
    )
    hits = search_web("SRE salary Austin", base_url="http://searxng.test")
    assert len(hits) == 1
    assert hits[0]["publisher"] == "levels.fyi"
    assert "180k" in hits[0]["content"]


def test_execute_research_plan_assembles_bundle() -> None:
    with patch(
        "inference.research.tools.search_web",
        return_value=[
            {
                "title": "Demand for platform engineers",
                "url": "https://www.bls.gov/ooh/example",
                "content": "Employment projected to grow",
                "publisher": "bls.gov",
            }
        ],
    ):
        bundle = execute_research_plan(
            {
                "need_research": True,
                "searches": ["platform engineer outlook"],
                "fetches": [],
                "corpus_query": "",
            },
            session=None,
        )
    assert isinstance(bundle, ResearchBundle)
    assert not bundle.failed
    assert bundle.web_snippets
    assert bundle.sources[0].publisher == "bls.gov"


def test_execute_empty_plan_fails() -> None:
    bundle = execute_research_plan(
        {"need_research": True, "searches": [], "fetches": [], "corpus_query": ""},
        session=MagicMock(),
    )
    assert bundle.failed
