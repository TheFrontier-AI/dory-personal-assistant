"""The Dory landing page (/dory): static, bilingual, honest about the invite link."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_scribe.config import get_settings

PAGE = Path(__file__).parents[1] / "src/meeting_scribe/static/dory.html"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STORE", "memory")
    monkeypatch.setenv("USE_PUBSUB", "false")
    get_settings.cache_clear()
    from meeting_scribe.app import app

    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


def _dict_and_html():
    html = PAGE.read_text("utf-8")
    m = re.search(r'<script type="application/json" id="i18n-data">(.*?)</script>', html, re.S)
    assert m, "the dictionary must be an inline JSON block"
    return json.loads(m.group(1)), html


def test_landing_page_is_served_without_an_invite_when_unconfigured(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="" data-invite' in r.text  # the page then shows the "not configured" label
    assert "__DORY_INVITE_URL__" not in r.text


def test_landing_page_uses_the_real_invite_link(client, monkeypatch):
    monkeypatch.setenv("DORY_DISCORD_CLIENT_ID", "123456789012345678")
    get_settings.cache_clear()
    from meeting_scribe.app import DORY_PERMISSIONS

    r = client.get("/")
    url = (
        "https://discord.com/oauth2/authorize?client_id=123456789012345678"
        f"&scope=bot+applications.commands&permissions={DORY_PERMISSIONS}"
    )
    assert r.text.count(f'href="{url}" data-invite') == 3  # nav, hero and final call to action
    # the create-account fallbacks (nav, hero), "not on Discord?", plans, entry card, final CTA
    assert r.text.count('href="/start"') >= 6


def test_dictionary_has_same_keys_in_both_languages():
    d, _ = _dict_and_html()
    assert d
    for key, entry in d.items():
        assert set(entry) == {"th", "en"}, key
        assert entry["th"].strip() and entry["en"].strip(), key


def test_every_used_key_exists_and_markup_has_no_hardcoded_thai():
    d, html = _dict_and_html()
    used = set(re.findall(r'data-i18n(?:-html)?="(\w+)"', html))
    for attrs in re.findall(r'data-i18n-attr="([^"]+)"', html):
        used |= {p.split(":")[1] for p in attrs.split(";")}
    script = html.split('id="i18n-data"', 1)[1]
    used |= set(re.findall(r'\bt\("(\w+)"\)', script))
    assert used - set(d) == set(), used - set(d)
    markup = html.split('<script type="application/json"', 1)[0].split("</head>", 1)[1]
    assert not re.search(r"[฀-๿]", markup)


def test_language_is_english_by_default_and_a_saved_choice_wins():
    """Judges read English: every page opens in English; the browser language is ignored."""
    _, html = _dict_and_html()
    assert 'const LANG_KEY = "dory-language"' in html
    assert 'let lang = readLang("get") || "en";' in html
    assert "navigator.language" not in html
    start = START.read_text("utf-8")
    assert 'let lang = readLang("get") || "en";' in start and "navigator.language" not in start
    center = (PAGE.parent / "center.html").read_text("utf-8")
    assert 'let lang = "en";' in center and '<html lang="en">' in center
    assert "localStorage.setItem(LANG_KEY" in html and "catch" in html
    assert html.count('data-lang="th"') == 1 and html.count('data-lang="en"') == 1


def test_hero_is_the_deep_sea_with_a_rigged_fish_and_a_pause_control():
    """Lantern Deep: a dark hero, Dory as an inline SVG rig, motion that can always be stopped."""
    _, html = _dict_and_html()
    hero = html.split('id="hero"', 1)[1].split("</section>", 1)[0]
    assert 'data-theme="deep"' in re.search(r'<section[^>]*id="hero"[^>]*>', html).group(0)
    assert '<g class="dory-fish' in hero and 'class="df-pupil"' in hero
    # gradients live in ONE rendered (never display:none) defs svg, shared by every fish
    defs = re.search(r'<svg class="fish-defs"[^>]*>', html).group(0)
    assert 'width="0" height="0"' in defs and "display:none" not in defs
    assert html.count('id="df-iris"') == 1
    # a visible pause control (WCAG 2.2.2), remembered, and the OS setting respected
    assert "data-motion-toggle" in hero and 'MOTION_KEY = "dory-motion"' in html
    assert "prefers-reduced-motion" in html and ".motion-off" in html
    # loops sleep off-screen and in hidden tabs; reveal hides content only when JS runs
    assert "IntersectionObserver" in html and "visibilitychange" in html
    assert ".js .reveal" in html and 'classList.add("js")' in html
    assert "<video" not in html and "autoplay" not in html


def test_mascot_assets_are_served_but_not_the_page_templates(client):
    for name in ("dory.svg", "dory-mark.svg"):
        r = client.get(f"/static/dory/{name}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml"), name
    assert client.get("/static/dory/../hub.html").status_code == 404
    assert client.get("/static/hub.html").status_code == 404
    _, html = _dict_and_html()
    assert "cat-" not in html  # the fish replaced the cats


def test_sections_name_only_shipped_features():
    from dory.guild_settings import FEATURES

    for flag in ("voice_meetings", "receipts", "followups", "documents", "wiki"):
        assert flag in FEATURES
    _, html = _dict_and_html()
    assert html.count('class="card feat') == 8
    for section in ("hero", "preview", "features", "how", "roles", "trust", "plans", "start"):
        assert f'id="{section}"' in html, section
    for href in (
        "#features",
        "#how",
        "#trust",
        "#plans",
        "/hub",
        "/recorder",
        "/privacy",
        "/terms",
    ):
        assert f'href="{href}"' in html, href


def test_preview_is_example_html_in_accessible_tabs():
    """No recordings exist: the preview says it is an example, uses made-up names, and is text."""
    d, html = _dict_and_html()
    preview = html.split('id="preview"', 1)[1].split("</section>", 1)[0]
    assert preview.count('role="tab"') == 4 and preview.count('role="tabpanel"') == 4
    assert 'role="tablist"' in preview and "aria-selected" in preview
    assert "example" in d["pv_p"]["en"].lower() and "record" not in d["pv_p"]["en"].lower()
    for real in ("Peat", "Toey", "Jems"):
        assert real not in html, real
    roles = html.split('id="roles"', 1)[1].split("</section>", 1)[0]
    assert roles.count('role="tab"') == 4


def test_hero_primary_is_the_invite_with_a_create_account_fallback():
    """Add Dory to Discord leads; with no invite link the hero still has a primary: Create account."""
    _, html = _dict_and_html()
    hero = html.split('id="hero"', 1)[1].split("</section>", 1)[0]
    invite = hero.index('data-invite data-i18n="cta_add"')
    fallback = hero.index('href="/start" data-invite-fallback')
    assert invite < fallback < hero.index('href="#preview"')
    assert 'href="/start" data-i18n="not_discord_link"' in hero
    assert "a.hidden = !ok;" in html and "a.hidden = ok;" in html
    nav = html.split('id="nav"', 1)[1].split("</header>", 1)[0]
    assert 'href="/center" data-i18n="nav_login"' in nav and "data-invite" in nav


def test_landing_page_names_the_models_from_the_live_config(client, monkeypatch):
    """Trust: which AI runs Dory comes from the settings, escaped, and never carries a key."""
    from dory.config import Settings as DorySettings

    monkeypatch.setenv("DORY_NEBIUS_API_KEY", "secret-key-value")
    monkeypatch.setenv("DORY_NEMOTRON_VISION_MODEL", "<b>vision</b>")
    r = client.get("/")
    d = DorySettings.from_env()
    text_model = getattr(d, "brain_model", "") or d.nemotron_model  # either config
    assert text_model in r.text
    assert "&lt;b&gt;vision&lt;/b&gt;" in r.text and "secret-key-value" not in r.text
    assert "__DORY_MODELS__" not in r.text
    monkeypatch.setenv("DORY_NEBIUS_API_KEY", "")
    monkeypatch.setenv("DORY_GEMINI_MODEL", "gemini-test")
    assert 'id="models">gemini-test<' in client.get("/").text


def test_landing_page_routes_visitors_to_every_service():
    """The entry section points at the three services; the Discord card falls back to /hub."""
    _, html = _dict_and_html()
    entry = html.split('id="start"', 1)[1].split("</section>", 1)[0]
    assert 'href="/start"' in entry and 'href="/center"' in entry and 'href="/recorder"' in entry
    for section in ("how", "plans"):  # "Where Dory works" lives inside "How it works"
        assert f'id="{section}"' in html, section


START = PAGE.parent / "start.html"


def _start_dict_and_html():
    html = START.read_text("utf-8")
    m = re.search(r'<script type="application/json" id="i18n-data">(.*?)</script>', html, re.S)
    assert m
    return json.loads(m.group(1)), html


def test_start_page_is_served_with_placeholders_filled(client, monkeypatch):
    r = client.get("/start")
    assert r.status_code == 200 and r.headers["cache-control"] == "no-store"
    assert 'const CLIENT_ID = ""' in r.text  # unconfigured: the page shows the notice
    assert "__DORY_INVITE_URL__" not in r.text and "__HUB_GOOGLE_CLIENT_ID__" not in r.text
    monkeypatch.setenv("HUB_GOOGLE_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    monkeypatch.setenv("DORY_DISCORD_CLIENT_ID", "123456789012345678")
    get_settings.cache_clear()
    r = client.get("/start")
    assert 'const CLIENT_ID = "123-abc.apps.googleusercontent.com"' in r.text
    assert 'href="https://discord.com/oauth2/authorize?client_id=123456789012345678' in r.text


def test_start_page_dictionary_and_markup_are_bilingual():
    d, html = _start_dict_and_html()
    for key, entry in d.items():
        assert set(entry) == {"th", "en"}, key
        assert set(re.findall(r"\{(\w+)\}", entry["th"])) == set(
            re.findall(r"\{(\w+)\}", entry["en"])
        ), key
    used = set(re.findall(r'data-i18n(?:-html)?="(\w+)"', html))
    for attrs in re.findall(r'data-i18n-attr="([^"]+)"', html):
        used |= {p.split(":")[1] for p in attrs.split(";")}
    script = html.split('id="i18n-data"', 1)[1]
    used |= set(re.findall(r'\bt\("(\w+)"', script))
    used |= {"pl_trial"}  # t("pl_" + plan) at runtime; only the trial exists at launch
    used.discard("pl_")
    assert used - set(d) == set(), used - set(d)
    markup = html.split('<script type="application/json"', 1)[0].split("</head>", 1)[1]
    assert not re.search(r"[\u0e00-\u0e7f]", markup)
    assert 'const LANG_KEY = "dory-language"' in html  # same choice as the landing page


def test_start_page_uses_only_existing_center_routes():
    _, html = _start_dict_and_html()
    assert 'const API = "/api/center"' in html
    assert 'api("/me")' in html and 'api("/orgs", { method: "POST"' in html
    assert "license/request" not in html  # launch: the trial is the only plan, nothing is charged
    assert 'data-plan="trial"' in html and 'data-plan="monthly"' not in html
    assert 'href="/center"' in html


def test_start_hands_the_credential_to_center_once_per_tab():
    """Same tab, sessionStorage, read once, only while the ID token is still valid."""
    _, start = _start_dict_and_html()
    center = (PAGE.parent / "center.html").read_text("utf-8")
    assert 'sessionStorage.setItem("dory_center_handoff"' in start
    assert 'sessionStorage.getItem("dory_center_handoff")' in center
    assert 'sessionStorage.removeItem("dory_center_handoff")' in center
    assert "Number(h.exp) * 1000 > Date.now()" in center
    assert "localStorage" not in start.split("dory_center_handoff", 1)[1]  # never persisted


def test_every_page_shares_the_dory_theme(client):
    """One design system: every page links the shared stylesheet, which is served as CSS."""
    for name in ("dory.html", "start.html", "hub.html", "center.html", "index.html"):
        html = (PAGE.parent / name).read_text("utf-8")
        assert '<link rel="stylesheet" href="/static/dory/theme.css">' in html, name
        assert "prefers-color-scheme" not in html, (
            name
        )  # light theme only, same on every judge's machine
    r = client.get("/static/dory/theme.css")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/css")
    assert "--indigo:" in r.text and ".btn.primary" in r.text


def test_unconfigured_invite_is_hidden_not_labelled_with_an_env_var():
    """Visitors never see an internal variable name: the invite button hides and /start explains."""
    _, html = _dict_and_html()
    assert "a.hidden = !ok;" in html
    d, start = _start_dict_and_html()
    assert "a.hidden = !ok;" in start and '$("invite-soon").hidden = ok;' in start
    assert 'id="invite-soon" data-i18n="invite_soon"' in start
    assert "DORY_DISCORD_CLIENT_ID" not in d["invite_soon"]["en"] + d["invite_soon"]["th"]


def test_every_page_shares_one_language_key_and_syncs_it_with_the_account():
    """One choice follows the person: same localStorage key on every page, and after sign-in the
    language saved with the account wins (or the local choice is saved to the account)."""
    for name in ("dory.html", "start.html", "hub.html", "center.html", "pm.html"):
        html = (PAGE.parent / name).read_text("utf-8")
        assert 'LANG_KEY = "dory-language"' in html, name
        assert "navigator.language" not in html, name
    for name, put, sync in (
        ("start.html", 'api("/me/language", { method: "PUT"', "syncLang(me.language)"),
        ("hub.html", 'api("/api/hub/me/language", { method: "PUT"', "syncLang(me.language)"),
        ("center.html", 'api("/api/center/me/language", { method: "PUT"', "syncLang(me.language)"),
        ("pm.html", 'api("/api/center/me/language", { method: "PUT"', "syncLang(user.language)"),
    ):
        html = (PAGE.parent / name).read_text("utf-8")
        assert put in html and sync in html, name
    assert "pm_lang" not in (PAGE.parent / "pm.html").read_text("utf-8")


def test_every_signed_in_page_keeps_one_dory_session():
    """Sign in once, stay signed in: start, hub and center exchange the Google sign-in for a
    Dory session (localStorage `dory_session`), reuse it on load and clear it on sign-out."""
    for name in ("start.html", "hub.html", "center.html"):
        html = (PAGE.parent / name).read_text("utf-8")
        assert 'const SESSION_KEY = "dory_session"' in html, name
        assert 'fetch("/api/hub/session", { method: "POST"' in html, name
        assert "exchangeSession(" in html and 'session("get")' in html, name
    assert 'session("clear")' in (PAGE.parent / "hub.html").read_text("utf-8")
    assert 'session("clear")' in (PAGE.parent / "center.html").read_text("utf-8")
