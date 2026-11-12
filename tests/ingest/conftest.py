"""Shared fixtures for ingest tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


def load_fixture(name: str) -> dict:
    path = FIXTURES_DIR / name
    return json.loads(path.read_text())


@pytest.fixture
def adzuna_payload() -> dict:
    return load_fixture("adzuna_search_response.json")


@pytest.fixture
def jsearch_payload() -> dict:
    return load_fixture("jsearch_search_response.json")


@pytest.fixture
def remotive_payload() -> dict:
    return load_fixture("remotive_search_response.json")


@pytest.fixture
def greenhouse_payload() -> dict:
    return load_fixture("greenhouse_jobs.json")


@pytest.fixture
def lever_payload() -> list:
    return load_fixture("lever_postings.json")


@pytest.fixture
def usajobs_payload() -> dict:
    return load_fixture("usajobs_search.json")
