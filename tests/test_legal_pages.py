import re
from pathlib import Path

from fastapi.testclient import TestClient

from meeting_scribe.app import app

STATIC = Path(__file__).parents[1] / "src" / "meeting_scribe" / "static"


def test_privacy_and_terms_are_public_and_filled():
    c = TestClient(app)
    for path, needle in (("/privacy", "Limited Use"), ("/terms", "Terms of Service")):
        r = c.get(path)
        assert r.status_code == 200
        assert needle in r.text
        assert "__CONTACT_EMAIL__" not in r.text


def test_legal_pages_wear_the_dory_design_and_lead_home():
    for name in ("privacy.html", "terms.html"):
        html = (STATIC / name).read_text("utf-8")
        links = re.findall(r'<link rel="stylesheet" href="([^"]+)"', html)
        assert links[0] == "/static/dory/theme.css", name  # the design system first
        assert '<link rel="icon" type="image/png" href="/static/dory/favicon.png">' in html, name
        assert '<link rel="apple-touch-icon" href="/static/dory/apple-touch-icon.png">' in html
        assert '<a class="logo" href="/"' in html and '<span class="mark"' in html, name
        assert "prefers-color-scheme" not in html, name
        assert "width: min(68ch" in html, name  # a readable measure


def test_privacy_matches_how_dory_keeps_and_processes_data():
    """CLAUDE.md "Memory retention": memory is the company's, kept forever by default, purged only
    after a retention period an admin chose, never deleted because a company stopped using Dory.
    Models run on Nebius Token Factory; data lives on Google Cloud; no Vertex AI in the project."""
    html = (STATIC / "privacy.html").read_text("utf-8")
    assert "kept for the period your organization sets" not in html
    assert "no expiry by default" in html and "admin can set a retention period" in html
    assert "Nothing is deleted when an organization stops using Dory" in html
    assert "Nebius Token Factory" in html and "Google Cloud" in html
    assert "Vertex" not in html and "Gemini" not in html
    assert "Last updated: 27 October 2026" in html
