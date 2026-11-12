"""Render jobdeck.resume.v1 documents to ATS HTML (buschmjm/resume style)."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape

from core.resume.document import included_education, included_roles, included_skill_groups

_TEMPLATE_DIR = Path(__file__).resolve().parents[2] / "templates" / "resume"


def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(str(_TEMPLATE_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )


def load_resume_css() -> str:
    path = _TEMPLATE_DIR / "resume.css"
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def render_ats_html(document: dict[str, Any]) -> str:
    header = document.get("header") or {}
    title_bits = [
        str(header.get("full_name") or "Resume"),
        str(header.get("headline") or ""),
        str(header.get("tagline") or ""),
    ]
    page_title = " | ".join(p for p in title_bits if p)
    target = document.get("target") or {}
    ctx = {
        "page_title": page_title,
        "css": load_resume_css(),
        "header": header,
        "summary_paragraphs": document.get("summary_paragraphs") or [],
        "roles": included_roles(document),
        "skill_groups": included_skill_groups(document),
        "projects": [
            p
            for p in (document.get("projects") or [])
            if isinstance(p, dict) and p.get("included", True)
        ],
        "education": included_education(document),
        "target": target if isinstance(target, dict) else {},
        "rationale": document.get("rationale") or "",
    }
    return _env().get_template("ats.html.j2").render(**ctx)


def escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)
