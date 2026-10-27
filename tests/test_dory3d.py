"""The 3D Dory module (static/dory/dory3d.js): served, small, gated, pinned. Offline, no browser."""

import gzip
import re
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from meeting_scribe.config import get_settings

DORY = Path(__file__).parents[1] / "src/meeting_scribe/static/dory"
JS = (DORY / "dory3d.js").read_text("utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE", "memory")
    monkeypatch.setenv("USE_PUBSUB", "false")
    get_settings.cache_clear()
    from meeting_scribe.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_module_and_poster_are_served(client):
    r = client.get("/static/dory/dory3d.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    r = client.get("/static/dory/dory3d-poster.webp")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/webp"


def test_module_stays_under_its_size_budget():
    assert len(gzip.compress(JS.encode(), 9)) < 25 * 1024


def test_poster_is_a_transparent_square_under_90_kb():
    data = (DORY / "dory3d-poster.webp").read_bytes()
    assert len(data) < 90 * 1024
    im = Image.open(BytesIO(data))
    assert im.size == (900, 900)
    assert im.mode == "RGBA"
    assert im.getchannel("A").getextrema()[0] == 0  # the reef field shows through


def test_three_is_pinned_to_one_exact_version():
    urls = re.findall(r"https://[^'\"\s]+", JS)
    assert urls == ["https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.min.js"]
    assert re.search(r"import\(THREE_URL\)", JS), "three loads lazily, after the page"


def test_capability_gate():
    gate = JS[JS.index("function capable") : JS.index("// ---------- the model")]
    assert "saveData" in gate
    assert "deviceMemory < 4" in gate
    assert "hardwareConcurrency || 0) >= 4" in gate
    assert "WebGL2RenderingContext" in gate
    assert "getContext('webgl2'" in JS
    assert "Math.min(window.devicePixelRatio || 1, POSTER ? 2 : 1.5)" in JS


def test_motion_guards():
    assert "prefers-reduced-motion: reduce" in JS
    assert "classList.contains('motion-off')" in JS
    assert "new MutationObserver" in JS
    assert "visibilitychange" in JS
    assert "IntersectionObserver" in JS
    # boots only after load + idle, never with motion off or reduced motion
    assert "requestIdleCallback" in JS and "addEventListener('load'" in JS
    assert "!motionOff() && !reduced.matches" in JS


def test_contract_with_the_page():
    assert "getElementById('dory3d')" in JS
    assert "classList.add('is-3d')" in JS
    assert "new CustomEvent('dory3d:ready')" in JS
    assert "classList.remove('is-3d')" in JS  # any failure leaves the still image in place
    assert "forceContextLoss" in JS
    assert "alpha: true" in JS and "setClearColor(0x000000, 0)" in JS


def test_no_downloaded_assets():
    for ext in (".glb", ".gltf", ".fbx", ".obj", ".ktx2", ".png", ".jpg", ".hdr"):
        assert ext not in JS
