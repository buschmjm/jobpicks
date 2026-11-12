"""Apply-form helpers (ATS detection, bulk fill matching)."""

from core.apply.bulk_fill import (
    BulkFillGap,
    BulkFillReport,
    build_fill_actions,
    normalize_label,
    resolve_field_value,
)
from core.apply.vault import (
    AUTO_VAULT_KEYS,
    merge_vault_into_answers,
    normalize_question_key,
    vault_map,
)

__all__ = [
    "AUTO_VAULT_KEYS",
    "BulkFillGap",
    "BulkFillReport",
    "build_fill_actions",
    "merge_vault_into_answers",
    "normalize_label",
    "normalize_question_key",
    "resolve_field_value",
    "vault_map",
]
