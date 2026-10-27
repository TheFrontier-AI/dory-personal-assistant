"""The living reef behind the hero (static/dory/reef.js): served, small, gated, pinned, and polite about
the words on top of it. Offline, no browser."""

import gzip
import re
import shutil
import subprocess
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from meeting_scribe.config import get_settings

DORY = Path(__file__).parents[1] / "src/meeting_scribe/static/dory"
JS = (DORY / "reef.js").read_text("utf-8")


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE", "memory")
    monkeypatch.setenv("USE_PUBSUB", "false")
    get_settings.cache_clear()
    from meeting_scribe.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def test_module_and_posters_are_served(client):
    r = client.get("/static/dory/reef.js")
    assert r.status_code == 200
    assert "javascript" in r.headers["content-type"]
    for name in ("reef-poster.webp", "reef-poster-800.webp"):
        r = client.get(f"/static/dory/{name}")
        assert r.status_code == 200, name
        assert r.headers["content-type"] == "image/webp"


def test_module_stays_under_its_size_budget():
    assert len(gzip.compress(JS.encode(), 9)) < 20 * 1024


@pytest.mark.parametrize(
    ("name", "width", "budget"),
    [("reef-poster.webp", 1600, 120), ("reef-poster-800.webp", 800, 60)],
)
def test_posters_are_transparent_stills_within_budget(name, width, budget):
    data = (DORY / name).read_bytes()
    assert len(data) < budget * 1024
    im = Image.open(BytesIO(data))
    assert im.width == width and im.mode == "RGBA"
    alpha = im.getchannel("A")
    assert alpha.getextrema()[0] == 0  # open water stays transparent: the hero field shows through
    top = alpha.crop((0, 0, im.width, im.height // 4))
    assert sum(top.histogram()[:8]) > 0.8 * top.width * top.height  # mostly empty above the reef


def test_three_is_pinned_to_the_same_url_as_dory3d():
    urls = re.findall(r"https://[^'\"\s]+", JS)
    assert urls == ["https://cdn.jsdelivr.net/npm/three@0.185.0/build/three.module.min.js"]
    assert re.search(r"import\(THREE_URL\)", JS), "three loads lazily, after the page"
    assert urls[0] in (DORY / "dory3d.js").read_text("utf-8")  # one download for both


def test_capability_gate_matches_dory3d():
    gate = JS[JS.index("function capable") : JS.index("// ---------- shaders")]
    assert "saveData" in gate
    assert "deviceMemory < 4" in gate
    assert "hardwareConcurrency || 0) >= 4" in gate
    assert "WebGL2RenderingContext" in gate
    assert "getContext('webgl2'" in JS
    assert "Math.min(window.devicePixelRatio || 1, POSTER ? 2 : 1.25)" in JS


def test_motion_guards_and_frame_cap():
    assert "prefers-reduced-motion: reduce" in JS
    assert "classList.contains('motion-off')" in JS
    assert "new MutationObserver" in JS
    assert "visibilitychange" in JS
    assert "IntersectionObserver" in JS
    # boots only after load + idle, never with motion off or reduced motion (until motion is turned on)
    assert "requestIdleCallback" in JS and "addEventListener('load'" in JS
    assert "!motionOff() && !reduced.matches" in JS
    assert "else if (!off) whenIdle(boot)" in JS
    assert "matchMedia('(pointer: coarse)')" in JS and "now - last < 31" in JS  # 30 fps on phones


def test_contract_with_the_page():
    assert "getElementById('reef')" in JS
    assert "classList.add('is-live')" in JS
    assert "classList.remove('is-live')" in JS  # any failure leaves the still in place
    assert "forceContextLoss" in JS and "webglcontextlost" in JS
    assert "alpha: true" in JS and "setClearColor(0x000000, 0)" in JS
    # the fog is the hero field (#0A5BAA), so nothing in the scene has an edge
    assert "const FIELD = [10 / 255, 91 / 255, 170 / 255];" in JS


def test_the_words_stay_clear():
    """The copy and the header (+48 px) are read every resize and scroll; fish steer around them and the
    shader fades anything inside them to nothing; the reef stays below the copy."""
    assert "const MARGIN = 48;" in JS
    for sel in ("querySelector('.hero-copy')", "getElementById('hd')", "getElementById('dory3d')"):
        assert sel in JS, sel
    assert "addEventListener('scroll', onScroll" in JS and "new ResizeObserver" in JS
    assert "rel(els.copy, MARGIN)" in JS and "rel(els.hd, MARGIN)" in JS
    assert "v = Math.min(v, H - c[3] - 8)" in JS  # the reef's top under the copy's bottom + 48
    # anything inside the clear areas fades to nothing
    assert "smoothstep(0.,sf,min(rd(uR[0],p),rd(uR[1],p)))" in JS
    assert "min(col,uFog)" in JS  # never brighter than the field behind the Pause button


def test_budgets_one_draw_call_per_kind():
    # every reef kind, school and the whale is one instanced mesh: one draw call each
    assert JS.count("new T.InstancedMesh(") == 1
    assert len(re.findall(r"inst\(", JS)) <= 16


def test_no_downloaded_assets():
    for ext in (".glb", ".gltf", ".fbx", ".obj", ".ktx2", ".png", ".jpg", ".hdr", "TextureLoader"):
        assert ext not in JS


@pytest.mark.skipif(not shutil.which("node"), reason="node is not installed")
def test_reef_js_parses():
    subprocess.run(["node", "--check", str(DORY / "reef.js")], check=True)
