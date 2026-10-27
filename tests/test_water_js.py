"""The homepage water layer (static/dory/water.js): served, small, and polite about motion."""

import gzip
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_scribe.config import get_settings

JS = Path(__file__).parents[1] / "src/meeting_scribe/static/dory/water.js"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE", "memory")
    monkeypatch.setenv("USE_PUBSUB", "false")
    get_settings.cache_clear()
    from meeting_scribe.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_water_js_is_served(client):
    r = client.get("/static/dory/water.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    assert "window.doryWater" in r.text


def test_water_js_fits_the_size_budget():
    assert len(gzip.compress(JS.read_bytes(), 9)) < 9 * 1024


def test_fish_keep_clear_of_words_and_controls():
    src = JS.read_text("utf-8")
    keep = re.search(r"const KEEP = '([^']+)'", src).group(1).split()
    for name in ("h1", "h2", "p", "a", "button", "textarea", "figure", "[data-ui]"):
        assert name in keep, name
    assert ",.hd" in src  # the fixed header
    assert "r.left - 32" in src and "r.bottom + 32" in src  # 32 px margin


def test_water_js_stops_for_motion_preferences_and_hidden_tabs():
    src = JS.read_text("utf-8")
    for guard in (
        "prefers-reduced-motion",
        "motion-off",
        "MutationObserver",
        "visibilitychange",
        "document.hidden",
        "saveData",
        "getContext('webgl2'",
        "webglcontextlost",
        "deviceMemory",
        "Math.min(devicePixelRatio || 1, 1.5)",
    ):
        assert guard in src, guard


def test_water_js_is_a_quiet_classic_script():
    src = JS.read_text("utf-8")
    assert "console." not in src
    assert not re.search(r"^\s*(import|export)\b", src, re.M)


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_water_js_parses():
    subprocess.run(["node", "--check", str(JS)], check=True)
