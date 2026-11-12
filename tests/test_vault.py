"""Vault merge and key normalization tests."""

from __future__ import annotations

from core.apply.vault import merge_vault_into_answers, normalize_question_key, vault_map


def test_normalize_question_key_slugifies() -> None:
    assert normalize_question_key("Work Authorization?") == "work_authorization"
    assert normalize_question_key("salary-expectation") == "salary_expectation"


def test_merge_vault_preconfirms_matching_answers() -> None:
    answers = [
        {
            "key": "work_authorization",
            "question_text": "Work auth?",
            "suggested_answer": "LLM draft",
            "source": "llm",
            "status": "pending",
        }
    ]
    vault = {
        "work_authorization": {
            "question_text": "Authorized to work in the US?",
            "answer": "Yes, US citizen.",
        }
    }
    merged = merge_vault_into_answers(answers, vault, preconfirm=True)
    assert merged[0]["suggested_answer"] == "Yes, US citizen."
    assert merged[0]["source"] == "vault"
    assert merged[0]["status"] == "confirmed"
    assert merged[0]["final_answer"] == "Yes, US citizen."


def test_merge_vault_adds_extra_keys() -> None:
    merged = merge_vault_into_answers(
        [],
        {"sponsorship": {"question_text": "Visa?", "answer": "No sponsorship needed."}},
        preconfirm=True,
    )
    assert len(merged) == 1
    assert merged[0]["key"] == "sponsorship"


def test_vault_map_from_rows() -> None:
    rows = [
        {"question_key": "salary_expectation", "question_text": "Salary?", "answer": "$150k"},
    ]
    assert vault_map(rows)["salary_expectation"]["answer"] == "$150k"
