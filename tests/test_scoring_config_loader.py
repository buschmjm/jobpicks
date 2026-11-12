"""Tests for scoring_config DB loader with profile-first keys."""

from __future__ import annotations

from core.models import ScoringConfig as ScoringConfigRow
from core.scoring_config_loader import scoring_config_from_db_rows


def test_scoring_config_loader_reads_min_match_score() -> None:
    rows = [
        ScoringConfigRow(key="min_match_score", value=0.35, description=""),
        ScoringConfigRow(key="min_explore_score", value=0.25, description=""),
        ScoringConfigRow(
            key="score_weights",
            value={
                "w_sem": 0.38,
                "w_skill": 0.27,
                "w_comp": 0.10,
                "w_level": 0.15,
                "w_geo": 0.05,
                "w_title": 0.05,
            },
            description="",
        ),
    ]
    config = scoring_config_from_db_rows(rows)
    assert config.min_match_score == 0.35
    assert config.min_explore_score == 0.25
    assert config.w_sem == 0.38
