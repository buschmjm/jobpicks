"""Load versioned prompt files with YAML front-matter."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from inference.config import chat_model

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
FRONT_MATTER_PATTERN = re.compile(r"\A---\s*\n(.*?)\n---\s*\n(.*)\Z", re.DOTALL)


@dataclass(frozen=True)
class LoadedPrompt:
    name: str
    model: str
    version: str
    schema: dict[str, Any]
    body: str
    path: Path

    @property
    def system_message(self) -> str:
        return self.body.strip()


def load_prompt(name: str, *, prompts_dir: Path | None = None) -> LoadedPrompt:
    """Load ``prompts/{name}.md`` with YAML front-matter."""
    base = prompts_dir or PROMPTS_DIR
    path = base / f"{name}.md"
    if not path.is_file():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_PATTERN.match(raw)
    if not match:
        raise ValueError(f"Prompt {path} is missing YAML front-matter")

    meta = yaml.safe_load(match.group(1))
    if not isinstance(meta, dict):
        raise ValueError(f"Prompt {path} front-matter must be a mapping")

    for key in ("model", "version", "schema"):
        if key not in meta:
            raise ValueError(f"Prompt {path} front-matter missing required key: {key}")

    schema = meta["schema"]
    if not isinstance(schema, dict):
        raise ValueError(f"Prompt {path} schema must be a JSON Schema object")

    return LoadedPrompt(
        name=name,
        model=chat_model(str(meta["model"])),
        version=str(meta["version"]),
        schema=schema,
        body=match.group(2),
        path=path,
    )
