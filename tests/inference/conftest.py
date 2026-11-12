"""Shared fixtures for inference tests."""

from __future__ import annotations

import pytest
from inference.client import InferenceClient


@pytest.fixture
def inference_client() -> InferenceClient:
    client = InferenceClient(base_url="http://ollama.test/v1", retries=2, timeout=120.0)
    yield client
    client.close()
