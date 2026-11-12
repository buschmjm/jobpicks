"""Tests for seniority mapping."""

from core.seniority import seniority_to_int


def test_seniority_to_int() -> None:
    assert seniority_to_int("Senior Engineer") == 3
    assert seniority_to_int("staff") == 4
    assert seniority_to_int(None) == 2
