"""Tests for prompt loading."""

from __future__ import annotations

from pathlib import Path

import pytest
from inference.prompts import LoadedPrompt, load_prompt


def test_load_resume_parse_prompt() -> None:
    prompt = load_prompt("resume_parse")

    assert isinstance(prompt, LoadedPrompt)
    assert prompt.model == "qwen2.5:7b-instruct"
    assert prompt.version == "1.0.0"
    assert prompt.schema["type"] == "object"
    assert "Do NOT infer or extract protected attributes" in prompt.body


def test_load_all_prompts_have_required_front_matter() -> None:
    prompts_dir = Path(__file__).resolve().parents[2] / "prompts"
    for name in ("resume_parse", "job_normalize", "explain_match"):
        prompt = load_prompt(name, prompts_dir=prompts_dir)
        assert prompt.model
        assert prompt.version
        assert prompt.schema
        assert prompt.system_message


def test_missing_prompt_raises() -> None:
    with pytest.raises(FileNotFoundError):
        load_prompt("nonexistent_prompt")
