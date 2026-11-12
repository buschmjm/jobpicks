"""Resume builder chat inference."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from inference.client import InferenceClient, InferenceUnavailableError, get_client
from inference.config import advisor_reply_max_chars, advisor_reply_max_tokens, builder_num_predict
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import LoadedPrompt, load_prompt

logger = logging.getLogger(__name__)

BuilderSource = Literal["llm", "template"]

_STREAM_CHAT_RULES = (
    "\n\nReply in plain chat text for this turn (not JSON). "
    "Light markdown is OK: short paragraphs and bullet lists. "
    "Do not wrap the answer in JSON or markdown fences. "
    "Interview for roles, dates, accomplishment bullets, education, and links. "
    "Reference the profile snapshot; do not invent employers or credentials. "
    "Adapt questions and emphasis to the active variant when provided. "
    "When you have enough data to suggest resume updates, end your reply with a line "
    "---PROPOSAL--- followed by a single JSON object (roles, education, links, summary). "
    "Otherwise omit the proposal block."
)

_MD_FENCE = re.compile(r"^```(?:\w+)?[ \t]*\n([\s\S]*?)\n```[ \t]*$", re.DOTALL)
_THINK_BLOCK = re.compile(
    r"<\s*(?:think|redacted_reasoning)\b[^>]*>[\s\S]*?</\s*(?:think|redacted_reasoning)\s*>",
    re.IGNORECASE,
)
_PROPOSAL_MARKER = re.compile(r"---PROPOSAL---\s*(\{[\s\S]*\})\s*\Z")
_HISTORY_TURNS = 8
_HISTORY_CHARS = 2000


def normalize_builder_text(text: str) -> str:
    """Normalize builder output: unwrap fences and tidy whitespace."""
    cleaned = text.replace("\r\n", "\n").strip()
    cleaned = _THINK_BLOCK.sub("", cleaned).strip()
    fenced = _MD_FENCE.fullmatch(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()
    cleaned = cleaned.replace("```", "").strip()
    return cleaned


def extract_proposal_from_reply(text: str) -> tuple[str, dict[str, Any] | None]:
    """Split chat text and optional trailing proposal JSON."""
    cleaned = normalize_builder_text(text)
    match = _PROPOSAL_MARKER.search(cleaned)
    if not match:
        return cleaned, None
    chat = cleaned[: match.start()].strip()
    try:
        proposal = json.loads(match.group(1))
    except json.JSONDecodeError:
        return cleaned, None
    if not isinstance(proposal, dict):
        return chat, None
    return chat, proposal


def slim_builder_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Shrink profile JSON for chat prompts."""
    slim = dict(snapshot)
    overview = dict(slim.get("profile_overview") or {})
    summary = overview.get("summary")
    if isinstance(summary, str) and len(summary) > 600:
        overview["summary"] = summary[:599].rstrip() + "…"
    slim["profile_overview"] = overview

    roles = slim.get("roles")
    if isinstance(roles, list):
        trimmed_roles: list[Any] = []
        for role in roles[:8]:
            if not isinstance(role, dict):
                continue
            row = dict(role)
            highlights = row.get("highlights") or []
            if isinstance(highlights, list):
                row["highlights"] = [str(h)[:180] for h in highlights[:4]]
            trimmed_roles.append(row)
        slim["roles"] = trimmed_roles
    return slim


def trim_builder_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep recent turns and truncate long past messages."""
    trimmed: list[dict[str, str]] = []
    for turn in history[-_HISTORY_TURNS:]:
        role = turn.get("role")
        content = (turn.get("content") or "").strip()
        if role not in ("user", "assistant") or not content:
            continue
        if len(content) > _HISTORY_CHARS:
            content = content[: _HISTORY_CHARS - 1].rstrip() + "…"
        trimmed.append({"role": role, "content": content})
    return trimmed


@dataclass(frozen=True)
class BuilderReply:
    reply: str
    source: BuilderSource
    proposal: dict[str, Any] | None = None


def template_resume_builder_reply(
    snapshot: dict[str, Any],
    user_message: str,
    *,
    variant: dict[str, Any] | None = None,
) -> BuilderReply:
    from core.career.profile_snapshot import snapshot_target_titles

    titles = snapshot_target_titles(snapshot)
    title_hint = titles[0] if titles else "your target role"
    emphasis = (variant or {}).get("emphasis") or ""
    msg = user_message.strip().lower()
    focus = f"emphasis on {emphasis[:120]}" if emphasis else f"alignment with {title_hint}"

    if "bullet" in msg or "accomplish" in msg or "highlight" in msg:
        body = (
            f"For {focus}, list 2–3 bullets per role with metrics (%, $, users, latency). "
            "Include tech stack and scope. I can propose resume updates once you share specifics."
        )
    elif "education" in msg or "degree" in msg:
        body = (
            "Share institution, degree, field, and graduation year (or expected). "
            "I'll add education to your resume proposal when confirmed."
        )
    elif "date" in msg or "when" in msg or "year" in msg:
        body = (
            "Confirm start and end dates for each role (month/year). "
            "Mark current roles as present. Dates are required before I propose updates."
        )
    else:
        body = (
            f"Let's build resume content with {focus}. "
            "Walk me through your most recent role: title, employer, dates, and 2–3 accomplishment bullets."
        )
    return BuilderReply(reply=body, source="template")


def _chat_messages(
    *,
    snapshot: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    loaded: LoadedPrompt,
    plaintext: bool,
    variant: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    system = loaded.system_message
    profile = slim_builder_snapshot(snapshot)
    turns = trim_builder_history(history)
    variant_payload = variant or {"name": "Default", "emphasis": ""}

    if plaintext:
        from inference.prompt_builder import build_chat_messages

        context: dict[str, Any] = {
            "profile": profile,
            "variant": variant_payload,
        }
        return build_chat_messages(
            prompt_name="resume_builder_chat",
            structured_context=context,
            history=turns,
            user_message=user_message,
            extra_system_suffix=_STREAM_CHAT_RULES,
        )

    payload: dict[str, Any] = {
        "profile": profile,
        "variant": variant_payload,
        "history": turns,
        "message": user_message.strip(),
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def resume_builder_sync(
    *,
    snapshot: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    max_attempts: int = 2,
    variant: dict[str, Any] | None = None,
) -> BuilderReply:
    llm = client or get_client()
    loaded = prompt or load_prompt("resume_builder_chat")
    messages = _chat_messages(
        snapshot=snapshot,
        history=history,
        user_message=user_message,
        loaded=loaded,
        plaintext=False,
        variant=variant,
    )
    try:
        data = _chat_json(llm, loaded, messages[1]["content"], max_attempts=max_attempts)
        reply = normalize_builder_text(str(data.get("reply") or ""))
        if len(reply) < 10:
            raise ExtractionError("Builder reply too short")
        proposal = data.get("proposal")
        if proposal is not None and not isinstance(proposal, dict):
            proposal = None
        max_chars = advisor_reply_max_chars()
        return BuilderReply(
            reply=reply[:max_chars],
            source="llm",
            proposal=proposal,
        )
    except (InferenceUnavailableError, ExtractionError, ValueError) as exc:
        logger.warning("resume builder LLM unavailable, using template: %s", exc)
        return template_resume_builder_reply(snapshot, user_message, variant=variant)


def resume_builder_stream(
    *,
    snapshot: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    variant: dict[str, Any] | None = None,
) -> Iterator[tuple[str, BuilderSource]]:
    """Yield ``(token, source)`` pairs for a plain-text builder reply."""
    llm = client or get_client()
    loaded = prompt or load_prompt("resume_builder_chat")
    messages = _chat_messages(
        snapshot=snapshot,
        history=history,
        user_message=user_message,
        loaded=loaded,
        plaintext=True,
        variant=variant,
    )
    try:
        produced = False
        for chunk in llm.chat_completion_stream(
            model=loaded.model,
            messages=messages,
            max_tokens=advisor_reply_max_tokens(),
            feature="builder",
            num_predict=builder_num_predict(),
        ):
            if not chunk:
                continue
            produced = True
            yield chunk, "llm"
        if not produced:
            raise InferenceUnavailableError("Empty stream")
    except InferenceUnavailableError as exc:
        logger.warning("resume builder stream unavailable, using template: %s", exc)
        yield template_resume_builder_reply(
            snapshot, user_message, variant=variant
        ).reply, "template"
