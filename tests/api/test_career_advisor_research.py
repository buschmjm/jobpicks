"""SSE research status events for career advisor stream."""

from __future__ import annotations

import json
from contextlib import contextmanager
from unittest.mock import patch

from api.main import app
from api.repositories.user_repo import UserRepository
from api.schemas import CareerMessageCreate
from api.services.career_advisor_service import prepare_stream
from fastapi.testclient import TestClient
from inference.research.tools import ResearchBundle, ResearchSource
from sqlalchemy.orm import Session

from tests.api.test_career_advisor_long_response import _SyncThread


def _parse_sse(body: str) -> list[dict]:
    events = []
    for block in body.split("\n\n"):
        line = next((ln for ln in block.split("\n") if ln.startswith("data:")), None)
        if not line:
            continue
        events.append(json.loads(line[5:].strip()))
    return events


def test_iter_advisor_sse_emits_research_then_tokens(db_session: Session) -> None:
    user = UserRepository(db_session).get_or_create_by_email("advisor-sse@example.com")
    db_session.commit()
    prep = prepare_stream(
        db_session,
        user.id,
        CareerMessageCreate(content="What is the salary market for SREs in Austin?"),
    )

    bundle = ResearchBundle(
        sources=[
            ResearchSource(
                title="SRE pay",
                url="https://www.levels.fyi/t/sre",
                publisher="levels.fyi",
                kind="web",
            )
        ],
        web_snippets=[
            {
                "title": "SRE pay",
                "url": "https://www.levels.fyi/t/sre",
                "publisher": "levels.fyi",
                "content": "Median around 180k",
            }
        ],
    )

    def fake_stream(**kwargs):
        assert kwargs.get("research") is not None
        yield "Lean apply. ", "llm"
        yield "Cited levels.fyi for local pay bands in Austin market research.", "llm"

    @contextmanager
    def fake_factory():
        yield db_session

    with (
        patch("api.services.career_advisor_service.threading.Thread", _SyncThread),
        patch("api.services.career_advisor_service.advisor_research_enabled", return_value=True),
        patch(
            "api.services.career_advisor_service.plan_research",
            return_value={
                "need_research": True,
                "searches": ["SRE salary Austin"],
                "fetches": [],
                "corpus_query": "SRE Austin",
            },
        ),
        patch(
            "api.services.career_advisor_service.execute_research_plan",
            return_value=bundle,
        ),
        patch(
            "api.services.career_advisor_service.career_advisor_stream",
            side_effect=fake_stream,
        ),
        patch("api.services.career_advisor_service.build_profile_snapshot", return_value={}),
        patch("api.services.career_advisor_service.get_session_factory", return_value=fake_factory),
    ):
        from api.services.career_advisor_service import iter_advisor_sse

        events = _parse_sse("".join(iter_advisor_sse(prep)))

    types = [e["type"] for e in events]
    assert types[0] == "user"
    assert "status" in types
    assert "sources" in types
    assert "token" in types
    assert types[-1] == "done"
    sources_event = next(e for e in events if e["type"] == "sources")
    assert sources_event["items"][0]["publisher"] == "levels.fyi"
    done = events[-1]
    assert done["message"]["sources"][0]["url"].startswith("https://www.levels.fyi")


def test_career_stream_requires_auth() -> None:
    client = TestClient(app)
    assert client.post("/api/career/messages/stream", json={"content": "hi"}).status_code == 401
