"""Domain logic: scoring, preferences, constraints (pure functions, no I/O)."""

from core.constraints import filter_hard_constraints, passes_hard_constraints
from core.preference import (
    apply_feedback,
    build_recommendations,
    compute_event_weight,
    select_explore_jobs,
)
from core.scoring import score_job, score_jobs
from core.types import (
    FeedbackAction,
    FeedbackEvent,
    HardConstraints,
    JobFeatures,
    PreferenceState,
    RejectionReason,
    ScoredJob,
    ScoringConfig,
    SessionState,
    UserProfile,
)

__all__ = [
    "FeedbackAction",
    "FeedbackEvent",
    "HardConstraints",
    "JobFeatures",
    "PreferenceState",
    "RejectionReason",
    "ScoredJob",
    "ScoringConfig",
    "SessionState",
    "UserProfile",
    "apply_feedback",
    "build_recommendations",
    "compute_event_weight",
    "filter_hard_constraints",
    "passes_hard_constraints",
    "score_job",
    "score_jobs",
    "select_explore_jobs",
]
