"""Inference configuration from environment variables."""

from __future__ import annotations

import os

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434/v1"
DEFAULT_LLM_CHAT_MODEL = "qwen3:4b"
DEFAULT_REQUEST_TIMEOUT_SECONDS = 300
DEFAULT_MAX_RETRIES = 2
DEFAULT_ADVISOR_REPLY_MAX_CHARS = 8000
DEFAULT_ADVISOR_REPLY_MAX_TOKENS = 2000
DEFAULT_APPLY_ASSIST_REPLY_MAX_TOKENS = 1200
DEFAULT_APPLY_ASSIST_REPLY_MAX_CHARS = 8000
DEFAULT_EMBEDDING_MODEL = "nomic-embed-text"
DEFAULT_EMBEDDING_DIMENSION = 768

# Circuit breaker defaults
DEFAULT_CIRCUIT_FAILURE_THRESHOLD = 3
DEFAULT_CIRCUIT_RECOVERY_SECONDS = 60.0


def ollama_base_url() -> str:
    return llm_base_url()


def llm_base_url() -> str:
    """OpenAI-compatible base URL (Ollama /v1 or cloud provider)."""
    explicit = os.environ.get("LLM_BASE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    return os.environ.get("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL).rstrip("/")


def llm_api_key() -> str | None:
    key = os.environ.get("LLM_API_KEY", "").strip()
    return key or None


def ollama_num_parallel() -> int:
    raw = os.environ.get("OLLAMA_NUM_PARALLEL", "1").strip()
    return max(1, int(raw))


def interactive_num_ctx() -> int:
    raw = os.environ.get("INTERACTIVE_NUM_CTX", "4096").strip()
    return int(raw)


def interactive_temperature() -> float:
    raw = os.environ.get("INTERACTIVE_TEMPERATURE", "0.3").strip()
    return float(raw)


def ollama_keep_alive() -> str:
    return os.environ.get("OLLAMA_KEEP_ALIVE", "30m").strip() or "30m"


def advisor_num_predict() -> int:
    raw = os.environ.get("ADVISOR_NUM_PREDICT", "512").strip()
    return int(raw)


def builder_num_predict() -> int:
    raw = os.environ.get("BUILDER_NUM_PREDICT", "1024").strip()
    return int(raw)


def advisor_rate_limit_per_min() -> int:
    raw = os.environ.get("ADVISOR_RATE_LIMIT_PER_MIN", "10").strip()
    return int(raw)


def builder_rate_limit_per_min() -> int:
    raw = os.environ.get("BUILDER_RATE_LIMIT_PER_MIN", "6").strip()
    return int(raw)


def advisor_fifo_busy_depth() -> int:
    raw = os.environ.get("ADVISOR_FIFO_BUSY_DEPTH", "3").strip()
    return int(raw)


def request_timeout_seconds() -> float:
    raw = os.environ.get("INFERENCE_TIMEOUT_SECONDS")
    return float(raw) if raw else DEFAULT_REQUEST_TIMEOUT_SECONDS


def max_retries() -> int:
    raw = os.environ.get("INFERENCE_MAX_RETRIES")
    return int(raw) if raw else DEFAULT_MAX_RETRIES


def embedding_model() -> str:
    return os.environ.get("EMBEDDING_MODEL", DEFAULT_EMBEDDING_MODEL)


def embedding_dimension() -> int:
    raw = os.environ.get("EMBEDDING_DIMENSION")
    return int(raw) if raw else DEFAULT_EMBEDDING_DIMENSION


def chat_model(prompt_default: str | None = None) -> str:
    """Homelab override for prompt front-matter models that are not installed."""
    override = os.environ.get("OLLAMA_CHAT_MODEL", "").strip()
    if override:
        return override
    env_model = os.environ.get("LLM_CHAT_MODEL", "").strip()
    if env_model:
        return env_model
    if prompt_default and str(prompt_default).strip():
        return str(prompt_default).strip()
    return DEFAULT_LLM_CHAT_MODEL


DEFAULT_SEARXNG_BASE_URL = "http://searxng.searxng.svc.cluster.local:8080"


def searxng_base_url() -> str:
    return os.environ.get("SEARXNG_BASE_URL", DEFAULT_SEARXNG_BASE_URL).rstrip("/")


def advisor_research_enabled() -> bool:
    raw = os.environ.get("ADVISOR_RESEARCH_ENABLED", "true").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def advisor_reply_max_chars() -> int:
    raw = os.environ.get("ADVISOR_REPLY_MAX_CHARS")
    return int(raw) if raw else DEFAULT_ADVISOR_REPLY_MAX_CHARS


def advisor_reply_max_tokens() -> int:
    raw = os.environ.get("ADVISOR_REPLY_MAX_TOKENS")
    return int(raw) if raw else DEFAULT_ADVISOR_REPLY_MAX_TOKENS


def apply_assist_reply_max_tokens() -> int:
    raw = os.environ.get("APPLY_ASSIST_REPLY_MAX_TOKENS")
    return int(raw) if raw else DEFAULT_APPLY_ASSIST_REPLY_MAX_TOKENS


def apply_assist_reply_max_chars() -> int:
    raw = os.environ.get("APPLY_ASSIST_REPLY_MAX_CHARS")
    return int(raw) if raw else DEFAULT_APPLY_ASSIST_REPLY_MAX_CHARS
