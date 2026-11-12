"""Advisor FAQ pre-router — template answers with zero LLM calls (A5)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class FaqAnswer:
    reply: str
    topic: str


_FAQ_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (
        re.compile(
            r"\b(how|why).{0,40}(match|score|scoring|rank)\b",
            re.I,
        ),
        "match_score",
        (
            "Match scores are computed deterministically when your queue is built — "
            "semantic fit, skills overlap, seniority, compensation, location, and title "
            "alignment. Open a job card and expand **Why this match** for the breakdown "
            "on that posting. Scores improve as you swipe and tell us what you want."
        ),
    ),
    (
        re.compile(r"\b(delete|remove|erase).{0,30}(data|account|profile)\b", re.I),
        "data_deletion",
        (
            "You can delete your account and data from **Settings → Privacy**. "
            "That permanently removes your profile, queue, messages, and saved answers. "
            "It cannot be undone."
        ),
    ),
    (
        re.compile(r"\b(privacy|gdpr|ccpa|data policy)\b", re.I),
        "privacy",
        (
            "JobDeck stores your profile, swipe feedback, and chat history to personalize "
            "matches. We do not sell your data. See the Privacy page linked from Settings "
            "for retention and deletion details."
        ),
    ),
    (
        re.compile(r"\b(how many|limit|quota).{0,30}(swipe|card|deck)\b", re.I),
        "deck_limits",
        (
            "Your daily deck size depends on your plan. Free accounts receive a smaller "
            "daily batch; Pro accounts receive more. The counter resets on the nightly "
            "queue top-up schedule (US Central)."
        ),
    ),
]


def try_faq_answer(user_message: str) -> FaqAnswer | None:
    text = user_message.strip()
    if not text:
        return None
    for pattern, topic, reply in _FAQ_PATTERNS:
        if pattern.search(text):
            return FaqAnswer(reply=reply, topic=topic)
    return None
