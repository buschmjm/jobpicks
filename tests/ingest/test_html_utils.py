"""Tests for HTML description helpers."""

from ingest.html_utils import contains_html, html_to_plain_text


def test_contains_html() -> None:
    assert contains_html("<p>Hello</p>")
    assert not contains_html("Plain text only")


def test_html_to_plain_text_preserves_blocks() -> None:
    html = "<p>First paragraph.</p><p>Second paragraph.</p><ul><li>One</li><li>Two</li></ul>"
    text = html_to_plain_text(html)
    assert "First paragraph." in text
    assert "Second paragraph." in text
    assert "One" in text
    assert "Two" in text
    assert "\n" in text


def test_html_to_plain_text_strips_tags() -> None:
    assert "Terraform" in html_to_plain_text("<p>Operate <strong>Terraform</strong> clusters.</p>")
