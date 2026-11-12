#!/usr/bin/env python3
"""Quality checks for career advisor chat completeness (mocked LLM, no live inference)."""

from __future__ import annotations

import json
import sys
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from api.repositories.user_repo import UserRepository
from api.schemas import CareerMessageCreate
from api.services.career_advisor_service import iter_advisor_sse, prepare_stream
from core.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from tests.api.conftest import _restore_metadata, _sqlite_compat_metadata


@dataclass(frozen=True)
class PromptScenario:
    name: str
    prompt: str
    reply: str
    min_chars: int
    must_include: tuple[str, ...]


SCENARIOS: tuple[PromptScenario, ...] = (
    PromptScenario(
        name="short_fit_check",
        prompt="Should I apply to this SRE role?",
        reply="**Lean apply.** Your platform background matches the core requirements.",
        min_chars=40,
        must_include=("Lean apply", "platform"),
    ),
    PromptScenario(
        name="long_market_analysis",
        prompt="Give me a detailed market and fit analysis for platform roles near me.",
        reply=(
            "**Lean apply.**\n\n"
            "Market:\n"
            + "\n".join(f"- Market signal {i} with cited evidence." for i in range(1, 26))
            + "\n\nFit:\n"
            + "\n".join(f"- Fit point {i} grounded in your profile." for i in range(1, 26))
            + "\n\n"
            + ("Use this to prioritize applications this week. " * 80)
        ),
        min_chars=3500,
        must_include=("Lean apply", "Market:", "Fit:"),
    ),
    PromptScenario(
        name="job_posting_review",
        prompt="Review this posting and tell me whether to apply.",
        reply=(
            "**Skip.**\n\n"
            "Hard gaps:\n"
            + "\n".join(f"- Missing requirement {i}" for i in range(1, 16))
            + "\n\n"
            + ("The posting asks for credentials you have not documented. " * 60)
        ),
        min_chars=2500,
        must_include=("Skip", "Hard gaps"),
    ),
)


def _parse_sse(body: str) -> list[dict]:
    events: list[dict] = []
    for block in body.split("\n\n"):
        line = next((ln for ln in block.split("\n") if ln.startswith("data:")), None)
        if not line:
            continue
        events.append(json.loads(line[5:].strip()))
    return events


def _run_scenario(session: Session, scenario: PromptScenario) -> dict[str, object]:
    user = UserRepository(session).get_or_create_by_email(f"quality-{scenario.name}@example.com")
    session.commit()
    prep = prepare_stream(session, user.id, CareerMessageCreate(content=scenario.prompt))

    def fake_stream(**kwargs):
        step = 48
        for offset in range(0, len(scenario.reply), step):
            yield scenario.reply[offset : offset + step], "llm"

    @contextmanager
    def fake_factory():
        yield session

    with (
        patch("api.services.career_advisor_service.advisor_research_enabled", return_value=False),
        patch(
            "api.services.career_advisor_service.career_advisor_stream",
            side_effect=fake_stream,
        ),
        patch("api.services.career_advisor_service.build_profile_snapshot", return_value={}),
        patch("api.services.career_advisor_service.get_session_factory", return_value=fake_factory),
    ):
        events = _parse_sse("".join(iter_advisor_sse(prep)))

    errors = [event for event in events if event.get("type") == "error"]
    done = next((event for event in events if event.get("type") == "done"), None)
    token_text = "".join(event["text"] for event in events if event.get("type") == "token")
    final_content = str((done or {}).get("message", {}).get("content", ""))

    missing = [needle for needle in scenario.must_include if needle not in final_content]
    passed = (
        not errors
        and done is not None
        and len(final_content) >= scenario.min_chars
        and len(token_text) >= min(scenario.min_chars, len(scenario.reply))
        and not missing
    )
    return {
        "name": scenario.name,
        "passed": passed,
        "errors": errors,
        "token_chars": len(token_text),
        "final_chars": len(final_content),
        "min_chars": scenario.min_chars,
        "missing": missing,
    }


def main() -> int:
    _sqlite_compat_metadata()
    engine = create_engine("sqlite+pysqlite:///:memory:", future=True)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    results: list[dict[str, object]] = []
    try:
        with SessionLocal() as session:
            for scenario in SCENARIOS:
                results.append(_run_scenario(session, scenario))
    finally:
        _restore_metadata()

    print("Career advisor chat quality results")
    print("=" * 40)
    all_passed = True
    for result in results:
        status = "PASS" if result["passed"] else "FAIL"
        if not result["passed"]:
            all_passed = False
        print(
            f"{status}  {result['name']}: "
            f"tokens={result['token_chars']} final={result['final_chars']} "
            f"(min {result['min_chars']})"
        )
        if result["missing"]:
            print(f"      missing phrases: {result['missing']}")
        if result["errors"]:
            print(f"      errors: {result['errors']}")

    print("=" * 40)
    print(f"Summary: {sum(1 for r in results if r['passed'])}/{len(results)} passed")
    return 0 if all_passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
