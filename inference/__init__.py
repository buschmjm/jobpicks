"""LLM and embedding clients for Ollama-backed inference."""

from inference.client import InferenceClient, InferenceUnavailableError
from inference.embeddings import EmbeddingClient, embed_text, embed_texts
from inference.explanations import (
    MatchExplanation,
    explain_match,
    template_explanation,
)
from inference.extraction import (
    extract_job_fields,
    extract_resume_profile,
)
from inference.prompts import LoadedPrompt, load_prompt

__all__ = [
    "EmbeddingClient",
    "InferenceClient",
    "InferenceUnavailableError",
    "LoadedPrompt",
    "MatchExplanation",
    "embed_text",
    "embed_texts",
    "explain_match",
    "extract_job_fields",
    "extract_resume_profile",
    "load_prompt",
    "template_explanation",
]
