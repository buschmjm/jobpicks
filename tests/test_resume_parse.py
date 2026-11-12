"""Tests for resume parsing helpers."""

from __future__ import annotations

from api.resume_io import extract_pdf_text, sniff_resume_content_type
from api.resume_parse import parse_resume_with_fallback, profile_from_extracted_text, profile_from_llm
from api.schemas import FactStatus


def _pdf_with_text(text: str) -> bytes:
    """Build a tiny valid PDF whose page content is `text`."""
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET\n".encode("latin-1", "replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode())
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def test_profile_from_llm_maps_facts() -> None:
    data = {
        "full_name": {"value": "Jane Doe", "status": "confirmed"},
        "summary": {"value": "Platform engineer", "status": "inferred"},
        "seniority_level": {"value": "senior", "status": "inferred"},
        "years_experience": {"value": 8, "status": "inferred"},
        "skills": [
            {"value": "kubernetes", "status": "inferred"},
            {"value": "terraform", "status": "inferred"},
        ],
        "job_titles": [{"value": "Senior SRE", "status": "inferred"}],
        "email": {"value": "", "status": "needs_confirmation"},
        "phone": {"value": "", "status": "needs_confirmation"},
        "location": {"value": "Austin, TX", "status": "inferred"},
        "work_history": [],
        "education": [],
        "certifications": [],
    }
    profile = profile_from_llm(data)
    keys = {f.key for f in profile.facts}
    assert "title" in keys
    assert "skills" not in keys
    assert "years_experience" not in keys
    assert profile.skill_names == ["kubernetes", "terraform"]
    assert any(f.status == FactStatus.inferred for f in profile.facts)


def test_extracted_text_profile_does_not_call_llm() -> None:
    text = "Jacob Buschmann\nInfrastructure Engineer\njake@example.com\nKubernetes, Terraform"
    profile = parse_resume_with_fallback(text, filename="resume.pdf")
    assert profile.parse_failed is False
    facts = {f.key: f.value for f in profile.facts}
    assert facts["full_name"] == "Jacob Buschmann"
    assert facts["title"] == "Infrastructure Engineer"
    assert facts["email"] == "jake@example.com"
    assert "kubernetes" in profile.skill_names
    assert "terraform" in profile.skill_names
    assert "skills" not in facts
    assert "years_experience" not in facts
    assert "parsing unavailable" not in facts["summary"].lower()
    assert "jake@example.com" not in facts["summary"]


SAMPLE_RESUME = """
Jane Q. Doe
Senior Platform Engineer
Austin, TX | jane.doe@example.com | (512) 555-0100

SUMMARY
Platform engineer focused on Kubernetes platforms and CI/CD. I like small teams
and boring infrastructure.

EXPERIENCE
Staff Site Reliability Engineer
Example Corp — Austin, TX
January 2021 – Present
- Led Kubernetes and Terraform platform for 40 services

Senior DevOps Engineer
Other Co
June 2018 – December 2020
- Built GitHub Actions pipelines on AWS

SKILLS
Kubernetes, Terraform, Python, AWS, PostgreSQL, Linux, Docker

EDUCATION
B.S. Computer Science, University of Texas, 2016
"""


def test_structured_parse_fills_fields_not_whole_resume() -> None:
    profile = parse_resume_with_fallback(SAMPLE_RESUME, filename="jane.pdf")
    facts = {f.key: f.value for f in profile.facts}
    assert facts["full_name"] == "Jane Q. Doe"
    assert facts["title"] == "Staff Site Reliability Engineer"
    assert facts["email"] == "jane.doe@example.com"
    assert facts["location"] == "Austin, TX"
    assert facts["phone"] == "(512) 555-0100"
    for token in ("kubernetes", "terraform", "python", "aws", "postgresql", "linux", "docker"):
        assert token in profile.skill_names
    assert "skills" not in facts
    assert "years_experience" not in facts
    assert "EXPERIENCE" not in facts["summary"]
    assert "SKILLS" not in facts["summary"]
    assert "University of Texas" not in facts["summary"]
    assert "Platform engineer focused on Kubernetes" in facts["summary"]
    assert len(facts["summary"]) < 500
    assert "seniority_level" not in facts
    assert len(profile.experiences) == 2
    assert profile.experiences[0].title == "Staff Site Reliability Engineer"
    assert profile.experiences[0].company_name == "Example Corp"
    assert profile.experiences[0].location == "Austin, TX"
    assert profile.experiences[0].is_current is True
    assert profile.experiences[0].start_date == "2021-01"
    assert "Kubernetes" in profile.experiences[0].highlights[0]
    assert profile.experiences[1].title == "Senior DevOps Engineer"
    assert profile.experiences[1].company_name == "Other Co"
    assert profile.experiences[1].is_current is False
    assert profile.experiences[1].end_date == "2020-12"
    assert len(profile.education) == 1
    assert profile.education[0].institution == "University of Texas"
    assert profile.education[0].end_date == "2016"
    assert "Computer Science" in profile.education[0].field or profile.education[0].degree


def test_inline_skills_header() -> None:
    text = """
Alex Rivera
Software Engineer
alex@example.com
Skills: Go, Kubernetes, Terraform
"""
    profile = parse_resume_with_fallback(text, filename="alex.pdf")
    assert "kubernetes" in profile.skill_names
    assert "terraform" in profile.skill_names
    assert "go" in profile.skill_names



def test_empty_text_marks_parse_failed() -> None:
    profile = profile_from_extracted_text("   ", filename="empty.pdf")
    assert profile.parse_failed is True


def test_extract_pdf_text_from_simple_pdf() -> None:
    pdf = _pdf_with_text("Jacob Buschmann jake@example.com")
    text = extract_pdf_text(pdf)
    assert "Jacob Buschmann" in text
    assert "jake@example.com" in text


def test_sniff_pdf_magic_over_octet_stream() -> None:
    pdf = _pdf_with_text("hello")
    sniffed = sniff_resume_content_type("application/octet-stream", "file.bin", pdf)
    assert sniffed == "application/pdf"


def test_experience_title_at_company_and_paragraph_body() -> None:
    text = """
EXPERIENCE
Senior Platform Engineer at Acme Technologies Inc.
January 2020 – Present
Built and operated a multi-cluster Kubernetes platform supporting 40 production services.
Reduced deployment time by 60% through standardized GitOps workflows.

Staff Engineer | Globex Corporation
2017 - 2019
• Migrated legacy monolith to microservices on AWS
• Mentored a team of four engineers
"""
    profile = parse_resume_with_fallback(text, filename="resume.pdf")
    assert len(profile.experiences) == 2
    assert profile.experiences[0].company_name == "Acme Technologies Inc."
    assert profile.experiences[0].title == "Senior Platform Engineer"
    assert len(profile.experiences[0].highlights) == 2
    assert "Kubernetes platform" in profile.experiences[0].highlights[0]
    assert "GitOps" in profile.experiences[0].highlights[1]
    assert profile.experiences[1].company_name == "Globex Corporation"
    assert len(profile.experiences[1].highlights) == 2
    assert "microservices" in profile.experiences[1].highlights[0]


def test_experience_company_first_and_inline_dates() -> None:
    text = """
EXPERIENCE
Amazon Web Services — Senior Solutions Architect | Seattle, WA | 2018 – 2021
Designed large-scale migration programs for enterprise customers moving to AWS.

Meta Platforms, LLC
Software Engineer
Menlo Park, CA
March 2015 to June 2018
Owned feed ranking infrastructure and on-call for tier-1 services.
"""
    profile = parse_resume_with_fallback(text, filename="resume.pdf")
    assert len(profile.experiences) == 2
    assert profile.experiences[0].company_name == "Amazon Web Services"
    assert profile.experiences[0].title == "Senior Solutions Architect"
    assert profile.experiences[0].location == "Seattle, WA"
    assert profile.experiences[0].end_date == "2021"
    assert "migration programs" in profile.experiences[0].highlights[0]
    assert profile.experiences[1].company_name == "Meta Platforms, LLC"
    assert profile.experiences[1].title == "Software Engineer"
    assert profile.experiences[1].location == "Menlo Park, CA"
    assert "feed ranking" in profile.experiences[1].highlights[0]


def test_experience_unicode_bullets_and_wrapped_lines() -> None:
    text = """
EXPERIENCE
DevOps Engineer
Initech Corp.
Jan 2022 – Present
• Automated CI/CD pipelines across 12 repositories
and reduced build times by 45% using caching and parallel jobs.
• Implemented observability stack with Prometheus and Grafana.
"""
    profile = parse_resume_with_fallback(text, filename="resume.pdf")
    assert profile.experiences[0].company_name == "Initech Corp."
    assert len(profile.experiences[0].highlights) == 2
    assert "45%" in profile.experiences[0].highlights[0]
    assert "Prometheus" in profile.experiences[0].highlights[1]


def test_glued_accomplishments_split_on_action_sentences() -> None:
    from api.resume_sections import normalize_highlights, split_accomplishment_text

    glued = (
        "Built and operated a multi-cluster Kubernetes platform supporting 40 production services. "
        "Reduced deployment time by 60% through standardized GitOps workflows. "
        "Improved infrastructure visibility by deploying Grafana dashboards."
    )
    parts = split_accomplishment_text(glued)
    assert len(parts) == 3
    assert parts[0].startswith("Built")
    assert parts[1].startswith("Reduced")
    assert parts[2].startswith("Improved")

    # Existing bad imports that stored one blob should expand on normalize/save.
    assert len(normalize_highlights([glued])) == 3

    text = f"""
EXPERIENCE
Infrastructure Engineer
Patron Points Inc, Woodbury, MN
October 2025 to Present
{glued}
"""
    profile = parse_resume_with_fallback(text, filename="glued.pdf")
    assert len(profile.experiences) == 1
    assert len(profile.experiences[0].highlights) >= 3
