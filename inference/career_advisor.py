"""Career advisor chat inference."""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any, Literal

from inference.client import InferenceClient, InferenceUnavailableError, get_client
from inference.config import advisor_reply_max_chars, advisor_reply_max_tokens
from inference.extraction import ExtractionError, _chat_json
from inference.prompts import LoadedPrompt, load_prompt

logger = logging.getLogger(__name__)

AdvisorSource = Literal["llm", "template"]

_STREAM_CHAT_RULES = (
    "\n\nReply in plain chat text for this turn (not JSON). "
    "Light markdown is OK: **bold**, short bullet or numbered lists, and short paragraphs. "
    "Do not wrap the answer in JSON or markdown fences. "
    "Be frank, not warm: facts and tradeoffs only — no pep talk. "
    "Primary job: realistic fit. If a posting is included, open with apply / lean apply / lean skip / skip. "
    "Read profile.career_totals.years_across_all_roles as TOTAL career length only. "
    "Read each profile.roles[].employment.tenure_years_approx for time in that job title. "
    "Never equate total career years with years in the current title. "
    "Use the full job description when the user provided one. "
    "If a research bundle is present: cite publisher+URL for every market/salary/demand claim; "
    "prefer corpus_jobs for local openings and web_snippets for pay/outlook; "
    "if research.failed or empty, say you could not verify live market data — do not invent numbers. "
    "Keep it to 2–5 short paragraphs or a short list."
)

_MD_FENCE = re.compile(r"^```(?:\w+)?[ \t]*\n([\s\S]*?)\n```[ \t]*$")
_THINK_BLOCK = re.compile(
    r"<\s*(?:think|redacted_reasoning)\b[^>]*>[\s\S]*?</\s*(?:think|redacted_reasoning)\s*>",
    re.IGNORECASE,
)
_HISTORY_TURNS = 6
_HISTORY_CHARS = 1600


def normalize_advisor_text(text: str) -> str:
    """Normalize advisor output: unwrap fences and tidy whitespace; keep light markdown."""
    cleaned = text.replace("\r\n", "\n").strip()
    cleaned = _THINK_BLOCK.sub("", cleaned).strip()
    fenced = _MD_FENCE.fullmatch(cleaned)
    if fenced:
        cleaned = fenced.group(1).strip()
    # Drop leftover fence markers if the model partially wrapped the reply.
    cleaned = cleaned.replace("```", "").strip()
    return cleaned


def slim_advisor_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    """Shrink profile JSON for chat prompts (faster prompt eval)."""
    slim = dict(snapshot)
    overview = dict(slim.get("profile_overview") or {})
    summary = overview.get("summary")
    if isinstance(summary, str) and len(summary) > 600:
        overview["summary"] = summary[:599].rstrip() + "…"
    slim["profile_overview"] = overview

    prefs = dict(slim.get("preferences") or {})
    locations = prefs.get("locations") or []
    slim_locs: list[Any] = []
    for loc in locations[:5]:
        if isinstance(loc, dict):
            name = loc.get("name") or loc.get("formatted_name")
            slim_locs.append({"name": name} if name else {"name": str(loc)[:120]})
        else:
            slim_locs.append(str(loc)[:120])
    prefs["locations"] = slim_locs
    titles = prefs.get("target_titles") or []
    if isinstance(titles, list):
        prefs["target_titles"] = titles[:12]
    slim["preferences"] = prefs

    roles = slim.get("roles")
    if isinstance(roles, list):
        trimmed_roles: list[Any] = []
        for role in roles[:6]:
            if not isinstance(role, dict):
                continue
            row = dict(role)
            highlights = row.get("highlights") or []
            if isinstance(highlights, list):
                row["highlights"] = [str(h)[:180] for h in highlights[:3]]
            trimmed_roles.append(row)
        slim["roles"] = trimmed_roles
    return slim


def trim_advisor_history(history: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep recent turns and truncate long past messages (job pastes dominate tokens)."""
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
class AdvisorReply:
    reply: str
    source: AdvisorSource


def template_career_reply(snapshot: dict[str, Any], user_message: str) -> AdvisorReply:
    from core.career.profile_snapshot import snapshot_target_titles

    titles = snapshot_target_titles(snapshot)
    skills = snapshot.get("skills") or []
    title_hint = titles[0] if titles else "roles that match your documented experience"
    skill_hint = ", ".join(str(s) for s in skills[:3]) if skills else "skills listed on your profile"
    msg = user_message.strip().lower()
    if "apply" in msg or "job description" in msg or "fit assessment" in msg:
        body = (
            f"I cannot finish a full posting review without the model, so treat this as provisional. "
            f"Compare hard requirements in the posting against {title_hint} and {skill_hint}. "
            "If must-haves (years, stack, clearance, degree) are missing from your profile, skip. "
            "If gaps are only nice-to-haves, lean apply and lead with evidence from matching roles."
        )
    elif "title" in msg or "role" in msg:
        body = (
            f"Prioritize titles aligned with {title_hint}. "
            "Drop stretch titles that need credentials or tenure you do not have on record."
        )
    elif "gap" in msg or "qualif" in msg:
        body = (
            f"Diff postings for {title_hint} against your highlights ({skill_hint}). "
            "Close the largest recurring hard-requirement gap first; ignore cosmetic keyword gaps."
        )
    else:
        body = (
            f"Search around {title_hint} and lead applications with {skill_hint}. "
            "Skip postings whose must-haves you cannot evidence from your roles."
        )
    return AdvisorReply(reply=body, source="template")


def _chat_messages(
    *,
    snapshot: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    loaded: LoadedPrompt,
    plaintext: bool,
    research: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    profile = slim_advisor_snapshot(snapshot)
    turns = trim_advisor_history(history)
    if plaintext:
        from inference.prompt_builder import build_chat_messages

        context: dict[str, Any] = {"profile": profile}
        if research is not None:
            context["research"] = research
        return build_chat_messages(
            prompt_name="career_advisor",
            structured_context=context,
            history=turns,
            user_message=user_message,
            extra_system_suffix=_STREAM_CHAT_RULES,
        )

    system = loaded.system_message
    payload: dict[str, Any] = {
        "profile": profile,
        "history": turns,
        "message": user_message.strip(),
    }
    if research is not None:
        payload["research"] = research
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def career_advisor_reply(
    *,
    snapshot: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    max_attempts: int = 2,
    research: dict[str, Any] | None = None,
) -> AdvisorReply:
    llm = client or get_client()
    loaded = prompt or load_prompt("career_advisor")
    messages = _chat_messages(
        snapshot=snapshot,
        history=history,
        user_message=user_message,
        loaded=loaded,
        plaintext=False,
        research=research,
    )
    try:
        data = _chat_json(llm, loaded, messages[1]["content"], max_attempts=max_attempts)
        reply = normalize_advisor_text(str(data.get("reply") or ""))
        if len(reply) < 20:
            raise ExtractionError("Advisor reply too short")
        max_chars = advisor_reply_max_chars()
        return AdvisorReply(reply=reply[:max_chars], source="llm")
    except (InferenceUnavailableError, ExtractionError, ValueError) as exc:
        logger.warning("career advisor LLM unavailable, using template: %s", exc)
        return template_career_reply(snapshot, user_message)


def career_advisor_stream(
    *,
    snapshot: dict[str, Any],
    history: list[dict[str, str]],
    user_message: str,
    client: InferenceClient | None = None,
    prompt: LoadedPrompt | None = None,
    research: dict[str, Any] | None = None,
) -> Iterator[tuple[str, AdvisorSource]]:
    """Yield ``(token, source)`` pairs for a plain-text advisor reply."""
    llm = client or get_client()
    loaded = prompt or load_prompt("career_advisor")
    messages = _chat_messages(
        snapshot=snapshot,
        history=history,
        user_message=user_message,
        loaded=loaded,
        plaintext=True,
        research=research,
    )
    try:
        produced = False
        for chunk in llm.chat_completion_stream(
            model=loaded.model,
            messages=messages,
            max_tokens=advisor_reply_max_tokens(),
            feature="advisor",
        ):
            if not chunk:
                continue
            produced = True
            yield chunk, "llm"
        if not produced:
            raise InferenceUnavailableError("Empty stream")
    except InferenceUnavailableError as exc:
        logger.warning("career advisor stream unavailable, using template: %s", exc)
        yield template_career_reply(snapshot, user_message).reply, "template"