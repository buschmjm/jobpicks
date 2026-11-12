"""Load curated ATS company seeds from seeds/companies.yaml."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_COMPANIES_PATH = Path(__file__).resolve().parents[1] / "seeds" / "companies.yaml"


@dataclass(frozen=True)
class CompanySeed:
    name: str
    greenhouse: str | None = None
    lever: str | None = None


def load_company_seeds(path: Path | None = None) -> list[CompanySeed]:
    file_path = path or DEFAULT_COMPANIES_PATH
    if not file_path.is_file():
        return []
    data = yaml.safe_load(file_path.read_text()) or {}
    rows = data.get("companies") or []
    seeds: list[CompanySeed] = []
    for row in rows:
        if not isinstance(row, dict) or not row.get("name"):
            continue
        seeds.append(
            CompanySeed(
                name=str(row["name"]),
                greenhouse=row.get("greenhouse"),
                lever=row.get("lever"),
            )
        )
    return seeds
