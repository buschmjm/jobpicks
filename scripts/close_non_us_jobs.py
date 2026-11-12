#!/usr/bin/env python3
"""Close open jobs outside the US product scope."""

from __future__ import annotations

from core.database import SessionLocal
from ingest.runner import close_non_us_open_jobs


def main() -> None:
    with SessionLocal() as session:
        closed = close_non_us_open_jobs(session)
        session.commit()
    print(f"Closed {closed} non-US open jobs")


if __name__ == "__main__":
    main()
