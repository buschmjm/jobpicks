"""Rate limiter tests."""

from __future__ import annotations

import pytest
from api.rate_limit import RateLimiter, check_magic_link_rate_limit
from fastapi import HTTPException


def test_rate_limiter_blocks_after_max() -> None:
    limiter = RateLimiter(max_requests=2, window_seconds=60)
    assert limiter.allow("a") is True
    assert limiter.allow("a") is True
    assert limiter.allow("a") is False


def test_magic_link_rate_limit_by_email() -> None:
    from api.rate_limit import _magic_link_by_email, record_magic_link_request

    email = "limit-test@example.com"
    _magic_link_by_email._windows.clear()
    for _ in range(3):
        check_magic_link_rate_limit(email=email, client_ip=None)
        record_magic_link_request(email=email, client_ip=None)
    with pytest.raises(HTTPException) as exc:
        check_magic_link_rate_limit(email=email, client_ip=None)
    assert exc.value.status_code == 429
