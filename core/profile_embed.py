"""Profile document embedding for cold-start semantic matching."""

from __future__ import annotations

import logging

from core.models import Profile

logger = logging.getLogger(__name__)


def profile_document_text(profile: Profile, *, experience_titles: list[str] | None = None) -> str:
    """Build embeddable text from profile fields (plan §9 user profile docs)."""
    parts: list[str] = []
    if profile.headline:
        parts.append(profile.headline)
    if profile.target_titles:
        parts.append("Target roles: " + ", ".join(profile.target_titles))
    if profile.skills:
        parts.append("Skills: " + ", ".join(profile.skills))
    if profile.summary:
        parts.append(profile.summary)
    if profile.free_text_wants:
        parts.append("Goals: " + profile.free_text_wants)
    if experience_titles:
        parts.append("Experience: " + ", ".join(experience_titles))
    return "\n\n".join(parts).strip()


def embed_profile_text(text: str) -> list[float] | None:
    """Return embedding vector or None when inference is unavailable."""
    if not text.strip():
        return None
    try:
        from inference.embeddings import embed_text

        return embed_text(text)
    except Exception:
        logger.warning("profile embedding unavailable", exc_info=True)
        return None


def embed_profile(
    profile: Profile,
    *,
    experience_titles: list[str] | None = None,
) -> list[float] | None:
    text = profile_document_text(profile, experience_titles=experience_titles)
    return embed_profile_text(text)
