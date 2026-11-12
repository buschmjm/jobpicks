"""Execute a research plan and assemble a citation bundle."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from inference.research.allowlist import is_fetch_allowed
from inference.research.corpus import search_corpus
from inference.research.searxng import fetch_url_text, search_web

logger = logging.getLogger(__name__)

_MAX_SEARCHES = 3
_MAX_FETCHES = 2
_SNIPPET_BUDGET = 2000


@dataclass(frozen=True)
class ResearchSource:
    title: str
    url: str
    publisher: str
    kind: str = "web"  # web | corpus | fetch


@dataclass
class ResearchBundle:
    sources: list[ResearchSource] = field(default_factory=list)
    web_snippets: list[dict[str, str]] = field(default_factory=list)
    corpus_jobs: list[dict[str, Any]] = field(default_factory=list)
    fetched_pages: list[dict[str, Any]] = field(default_factory=list)
    failed: bool = False
    detail: str = ""

    def to_prompt_dict(self) -> dict[str, Any]:
        return {
            "web_snippets": self.web_snippets,
            "corpus_jobs": self.corpus_jobs,
            "fetched_pages": [
                {
                    "url": page.get("url"),
                    "publisher": page.get("publisher"),
                    "excerpt": page.get("content"),
                }
                for page in self.fetched_pages
            ],
            "sources": [asdict(src) for src in self.sources],
            "failed": self.failed,
            "detail": self.detail,
        }

    def sources_payload(self) -> list[dict[str, str]]:
        return [
            {"title": s.title, "url": s.url, "publisher": s.publisher, "kind": s.kind}
            for s in self.sources
            if s.url or s.kind == "corpus"
        ]


def execute_research_plan(
    plan: dict[str, Any],
    *,
    session: Session | None,
    location_hint: str | None = None,
) -> ResearchBundle:
    """Run searches / corpus / fetches from a planner JSON object."""
    bundle = ResearchBundle()
    searches = [
        str(q).strip()
        for q in (plan.get("searches") or [])
        if isinstance(q, str) and str(q).strip()
    ][:_MAX_SEARCHES]
    fetches = [
        str(u).strip()
        for u in (plan.get("fetches") or [])
        if isinstance(u, str) and str(u).strip()
    ][:_MAX_FETCHES]
    corpus_query = str(plan.get("corpus_query") or "").strip()[:240]

    if not searches and not fetches and not corpus_query:
        bundle.failed = True
        bundle.detail = "Research plan was empty."
        return bundle

    snippet_chars = 0
    errors: list[str] = []

    # Parallel web searches
    if searches:
        with ThreadPoolExecutor(max_workers=min(3, len(searches))) as pool:
            futures = {pool.submit(search_web, q): q for q in searches}
            for fut in as_completed(futures):
                q = futures[fut]
                try:
                    hits = fut.result()
                except Exception as exc:
                    errors.append(f"search:{q}:{exc}")
                    continue
                for hit in hits:
                    if snippet_chars >= _SNIPPET_BUDGET:
                        break
                    content = hit.get("content") or ""
                    room = _SNIPPET_BUDGET - snippet_chars
                    clipped = content[:room]
                    snippet_chars += len(clipped)
                    row = {
                        "title": hit["title"],
                        "url": hit["url"],
                        "publisher": hit["publisher"],
                        "content": clipped,
                        "query": q,
                    }
                    bundle.web_snippets.append(row)
                    bundle.sources.append(
                        ResearchSource(
                            title=hit["title"],
                            url=hit["url"],
                            publisher=hit["publisher"],
                            kind="web",
                        )
                    )

    if corpus_query and session is not None:
        jobs = search_corpus(session, corpus_query, location_hint=location_hint, limit=8)
        bundle.corpus_jobs = jobs
        for job in jobs:
            title = f"{job.get('title')} @ {job.get('company')}"
            bundle.sources.append(
                ResearchSource(
                    title=title[:200],
                    url=str(job.get("source_url") or ""),
                    publisher="jobdeck-corpus",
                    kind="corpus",
                )
            )

    for url in fetches:
        if not is_fetch_allowed(url):
            errors.append(f"fetch_blocked:{url}")
            continue
        page = fetch_url_text(url)
        if page is None:
            errors.append(f"fetch_failed:{url}")
            continue
        bundle.fetched_pages.append(page)
        bundle.sources.append(
            ResearchSource(
                title=str(page.get("title") or page.get("publisher") or url)[:200],
                url=str(page.get("url") or url),
                publisher=str(page.get("publisher") or "web"),
                kind="fetch",
            )
        )

    # Dedupe sources by URL
    seen: set[str] = set()
    unique: list[ResearchSource] = []
    for src in bundle.sources:
        key = src.url or f"corpus:{src.title}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(src)
    bundle.sources = unique[:15]

    if not bundle.web_snippets and not bundle.corpus_jobs and not bundle.fetched_pages:
        bundle.failed = True
        bundle.detail = "; ".join(errors) if errors else "No research results."
    elif errors:
        bundle.detail = "; ".join(errors[:5])
    return bundle
