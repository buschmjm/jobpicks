"""Tests for embedding client."""

from __future__ import annotations

import httpx
import pytest
import respx
from inference.client import InferenceClient, InferenceUnavailableError
from inference.embeddings import EmbeddingClient


def _embedding_response(dimension: int) -> dict:
    return {
        "data": [{"index": 0, "embedding": [0.01] * dimension}],
    }


@respx.mock
def test_embed_text_returns_768_dimensions() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_embedding_response(768)),
    )

    vector = EmbeddingClient(client=client, expected_dimension=768).embed("hello world")

    assert len(vector) == 768
    client.close()


@respx.mock
def test_embed_many_batch() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/embeddings").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"index": 0, "embedding": [0.1] * 768},
                    {"index": 1, "embedding": [0.2] * 768},
                ]
            },
        ),
    )

    vectors = EmbeddingClient(client=client).embed_many(["a", "b"])
    assert len(vectors) == 2
    assert len(vectors[0]) == 768
    client.close()


@respx.mock
def test_wrong_dimension_raises() -> None:
    client = InferenceClient(base_url="http://ollama.test/v1")
    respx.post("http://ollama.test/v1/embeddings").mock(
        return_value=httpx.Response(200, json=_embedding_response(512)),
    )

    with pytest.raises(InferenceUnavailableError, match="expected 768"):
        EmbeddingClient(client=client, expected_dimension=768).embed("x")
    client.close()
