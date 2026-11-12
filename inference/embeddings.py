"""Embedding generation via Ollama."""

from __future__ import annotations

from inference.client import InferenceClient, InferenceUnavailableError, get_embedding_client
from inference.config import embedding_dimension, embedding_model


class EmbeddingClient:
    """768-dimensional embeddings using nomic-embed-text (configurable)."""

    def __init__(
        self,
        client: InferenceClient | None = None,
        *,
        model: str | None = None,
        expected_dimension: int | None = None,
    ) -> None:
        self._client = client or get_embedding_client()
        self.model = model or embedding_model()
        self.expected_dimension = expected_dimension or embedding_dimension()

    def embed(self, text: str) -> list[float]:
        vectors = self.embed_many([text])
        return vectors[0]

    def embed_many(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors = self._client.embeddings(model=self.model, input_text=texts)
        for index, vector in enumerate(vectors):
            if len(vector) != self.expected_dimension:
                raise InferenceUnavailableError(
                    f"Embedding {index} has dimension {len(vector)}, "
                    f"expected {self.expected_dimension}"
                )
        return vectors


def embed_text(text: str, *, client: InferenceClient | None = None) -> list[float]:
    return EmbeddingClient(client=client).embed(text)


def embed_texts(texts: list[str], *, client: InferenceClient | None = None) -> list[list[float]]:
    return EmbeddingClient(client=client).embed_many(texts)
