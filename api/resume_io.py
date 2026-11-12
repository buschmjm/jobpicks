"""Resume file storage and text extraction (PDF/DOCX)."""

from __future__ import annotations

import io
import logging
import os
import re
from pathlib import Path
from uuid import UUID

logger = logging.getLogger(__name__)

DEFAULT_STORAGE_DIR = Path(
    os.environ.get("RESUME_STORAGE_DIR", "/tmp/job-platform/resumes")
)


def storage_dir() -> Path:
    path = DEFAULT_STORAGE_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_resume_file(user_id: UUID, filename: str, data: bytes) -> Path:
    safe_name = re.sub(r"[^\w.\-]", "_", filename)[:120]
    dest = storage_dir() / f"{user_id}_{safe_name}"
    dest.write_bytes(data)
    return dest


def delete_resume_files_for_user(user_id: UUID) -> int:
    removed = 0
    prefix = f"{user_id}_"
    for path in storage_dir().glob(f"{prefix}*"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


_MAX_PDF_PAGES = 20
_PDF_MAGIC = b"%PDF"


def sniff_resume_content_type(content_type: str, filename: str, data: bytes) -> str:
    """Prefer file magic over the browser Content-Type (often octet-stream)."""
    if data.startswith(_PDF_MAGIC):
        return "application/pdf"
    name = filename.lower()
    if name.endswith(".pdf"):
        return "application/pdf"
    if name.endswith(".docx") or content_type == (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return content_type


def extract_pdf_text(data: bytes) -> str:
    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data), strict=False)
        if getattr(reader, "is_encrypted", False):
            try:
                if reader.decrypt("") == 0:
                    logger.warning("Encrypted PDF; cannot extract text")
                    return ""
            except Exception:
                logger.warning("Encrypted PDF; cannot extract text")
                return ""
        parts: list[str] = []
        for page in reader.pages[:_MAX_PDF_PAGES]:
            try:
                chunk = page.extract_text() or ""
            except Exception:
                logger.exception("PDF page text extraction failed")
                chunk = ""
            if chunk.strip():
                parts.append(chunk)
        text = _normalize_extracted_text("\n".join(parts))
        if len(text) >= 40:
            return text
        layout_parts: list[str] = []
        for page in reader.pages[:_MAX_PDF_PAGES]:
            try:
                layout = page.extract_text(extraction_mode="layout") or ""
            except TypeError:
                break
            except Exception:
                logger.exception("PDF layout extraction failed")
                layout = ""
            if layout.strip():
                layout_parts.append(layout)
        layout_text = _normalize_extracted_text("\n".join(layout_parts))
        return layout_text if len(layout_text) > len(text) else text
    except Exception:
        logger.exception("PDF text extraction failed")
        return ""


def _normalize_extracted_text(text: str) -> str:
    text = text.replace("\x00", " ")
    lines = [" ".join(line.split()) for line in text.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def extract_docx_text(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()


def extract_resume_text(content_type: str, data: bytes, *, filename: str = "") -> str:
    sniffed = sniff_resume_content_type(content_type, filename, data)
    if sniffed == "application/pdf":
        return extract_pdf_text(data)
    if sniffed == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _normalize_extracted_text(extract_docx_text(data))
    raise ValueError(f"Unsupported resume type: {content_type}")
