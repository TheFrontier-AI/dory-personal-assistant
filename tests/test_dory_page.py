"""The Dory homepage (`/`, "Dory Descent"): a dive through seven chapters, bilingual, honest about the
invite link, the scripted example and the photographs."""

import html as html_lib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_scribe.config import get_settings

PAGE = Path(__file__).parents[1] / "src/meeting_scribe/static/dory.html"
CHAPTERS = [
    ("sunlight", "0"),
    ("twilight", "200"),
    ("midnight", "1000"),
    ("seabed", "4000"),
    ("ascent", "200"),
    ("surface", "0"),
    ("lantern", "0"),
]


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


def _chapter(html: str, name: str) -> str:
    return html.split(f'data-chapter="{name}"', 1)[1].split("</section>", 1)[0]


def test_landing_page_is_served_without_an_invite_when_unconfigured(client):
    r = client.get("/")
    assert r.status_code == 200
    assert 'href="" data-invite' in r.text  # the page then shows "Create account" instead
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
    assert r.text.count(f'href="{url}" data-invite') == 4  # header, hero, ticket, last chapter
    # each one has a create-account fallback, plus "Not on Discord?" in the hero
    assert r.text.count('href="/start" data-invite-fallback') == 4
    assert r.text.count('href="/start"') >= 5


def test_dictionary_has_same_keys_in_both_languages():
    d, _ = _dict_and_html()
    assert d
    for key, entry in d.items():
        assert set(entry) == {"th", "en"}, key
        assert entry["th"].strip() and entry["en"].strip(), key
        assert set(re.findall(r"\{(\w+)\}", entry["th"])) == set(
            re.findall(r"\{(\w+)\}", entry["en"])
        ), key


def test_every_used_key_exists_and_markup_has_no_hardcoded_thai():
    d, html = _dict_and_html()
    used = set(re.findall(r'data-i18n(?:-html)?="(\w+)"', html))
    for attrs in re.findall(r'data-i18n-attr="([^"]+)"', html):
        used |= {p.split(":")[1] for p in attrs.split(";")}
    used |= set(re.findall(r'data-eg="(\w+)"', html))
    script = html.split('id="i18n-data"', 1)[1]
    used |= set(re.findall(r'\bt\("(\w+)"\)', script))
    assert used - set(d) == set(), used - set(d)
    markup = html.split('<script type="application/json"', 1)[0].split("</head>", 1)[1]
    assert not re.search(r"[\u0e00-\u0e3e\u0e40-\u0e7f]", markup)  # the baht sign (U+0E3F) is fine


def test_markup_carries_the_english_words_so_the_page_reads_without_script():
    """Every translated element holds its English text in the markup (search, no-JS, first paint) and it
    is the dictionary's English, so the two never drift. Keys whose English is Thai (ไทย) stay empty."""
    d, html = _dict_and_html()
    body = html.split("<body>", 1)[1].split('<script type="application/json"', 1)[0]
    found = 0
    for key, text in re.findall(r'data-i18n="(\w+)"[^>]*>([^<]*)<', body):
        en = d[key]["en"]
        if re.search(r"[฀-๿]", en):
            assert text == "", key
            continue
        assert html_lib.unescape(text) == en, key
        found += 1
    assert found > 120
    for attr, key in (
        ("alt", "hero_alt"),
        ("aria-label", "meet_aria"),
        ("aria-label", "bar_aria"),
        ("value", "org_eg"),
    ):
        m = re.search(rf'{attr}="([^"]*)"[^>]*data-i18n-attr="{attr}:{key}"', body)
        assert m and html_lib.unescape(m.group(1)) == d[key]["en"], key


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


def test_chapters_descend_in_order_with_their_depths():
    """The page is a dive: seven chapters in this order, each with its depth in metres. water.js and
    the header read these attributes."""
    _, html = _dict_and_html()
    found = re.findall(r'<section[^>]*data-chapter="(\w+)" data-depth="(\d+)"', html)
    assert found == CHAPTERS
    assert html.count("data-chapter=") == len(CHAPTERS)
    for name, _depth in CHAPTERS:
        sec = re.search(rf'<section[^>]*data-chapter="{name}"', html).group(0)
        assert 'class="ch' in sec, (
            name
        )  # .ch: a positioned field that never makes a stacking context
    # the header reads the depth: a visible figure with a hidden label, never a live region
    header = html.split('<header class="hd" id="hd">', 1)[1].split("</header>", 1)[0]
    assert (
        '<span class="sr" data-i18n="depth_label">Depth</span> <span id="depth">0 m</span>'
        in header
    )
    assert "aria-live" not in header
    assert 'toLocaleString("en-US") + " m"' in html
    for href in ('href="#features"', 'href="#plans"', 'href="/center"'):
        assert href in header, href
    assert 'id="features" data-chapter="ascent"' in html and 'id="plans"' in html


def test_water_layer_and_the_3d_hero_follow_the_shared_contract():
    _, html = _dict_and_html()
    body = html.split("<body>", 1)[1]
    assert body.lstrip().startswith('<canvas id="water" aria-hidden="true"></canvas>')
    assert (
        "#water { position: fixed; inset: 0;" in html
        and "z-index: 1; pointer-events: none; }" in html
    )
    assert (
        ".g { position: relative; z-index: 2;" in html
    )  # content above the water, fields below it
    assert '<script src="/static/dory/water.js" defer></script>' in html
    assert '<script type="module" src="/static/dory/dory3d.js"></script>' in html
    hero = _chapter(html, "sunlight")
    box = hero.split('<div id="dory3d">', 1)[1].split("</div>", 1)[0]
    # the still is the 3D model's own poster, so the crossfade to the live model is seamless
    assert (
        'src="/static/dory/dory3d-poster.webp" width="900" height="900" fetchpriority="high"' in box
    )
    assert "loading=" not in box  # the still is the largest paint: never lazy
    assert (
        "#dory3d.is-3d canvas { opacity: 1; }" in html
        and "#dory3d.is-3d picture { opacity: 0; }" in html
    )
    assert "transition: opacity 600ms ease" in html
    assert "window.doryWater?.drop(" in html and "window.doryWater?.lantern(" in html


def test_the_living_reef_sits_under_the_water_and_the_words():
    """#reef fills the hero's first screen (the same grid cell as .hero-top) at z 0: over the field,
    under #water (z 1) and the words (z 2). Its still is a CSS background that crossfades to the live
    canvas, never preloaded, so Dory's poster stays the largest paint."""
    _, html = _dict_and_html()
    hero = _chapter(html, "sunlight")
    assert hero.split(">", 1)[1].lstrip().startswith('<div id="reef" aria-hidden="true"></div>')
    assert hero.index('id="reef"') < hero.index('class="g hero-top"')
    assert '<script type="module" src="/static/dory/reef.js"></script>' in html
    assert ".hero { display: grid; background: var(--reef); }" in html
    assert "#reef, .hero-top { grid-area: 1 / 1; }" in html
    assert "#reef { position: relative; z-index: 0;" in html
    assert "url(/static/dory/reef-poster.webp)" in html
    assert "url(/static/dory/reef-poster-800.webp)" in html
    assert (
        "#reef.is-live canvas { opacity: 1; }" in html
        and "#reef.is-live::before { opacity: 0; }" in html
    )
    assert not re.search(r"<link[^>]*preload[^>]*reef", html)  # never preloaded


def test_motion_can_always_be_paused_and_starts_off_under_reduced_motion():
    _, html = _dict_and_html()
    head = html.split("</head>", 1)[0]
    assert (
        'd.classList.add("js")' in head and 'd.classList.add("motion-off")' in head
    )  # before paint
    assert 'localStorage.getItem("dory-motion")' in head
    assert "data-motion-toggle" in _chapter(html, "sunlight")  # visible on the first screen
    assert 'MOTION_KEY = "dory-motion"' in html and "prefers-reduced-motion" in html
    # entrances hide content only with script and with motion on
    assert ".js:not(.motion-off) [data-group]:not(.in) [data-rise]" in html
    assert "translateY(24px)" in html and "calc(var(--i, 0) * 70ms)" in html
    assert "IntersectionObserver" in html and "rise.unobserve" in html


def test_the_introduction_film_waits_for_play_and_starts_fast():
    """The film has sound: it never autoplays, loads nothing before Play, and is a web-sized,
    fast-start MP4 (its index before the data, so playback starts while it downloads)."""
    _, html = _dict_and_html()
    sun = _chapter(html, "sunlight")
    video = re.search(r"<video[^>]*>", sun).group(0)
    assert "controls" in video and "playsinline" in video and 'preload="none"' in video
    assert "autoplay" not in html and "muted" not in video
    assert 'poster="/static/dory/meet-dory.webp"' in video and "aria-label:meet_aria" in video
    assert '<source src="/static/dory/meet-dory.mp4" type="video/mp4">' in sun
    assert 'data-i18n="meet_cap"' in sun  # what the film shows, in words
    assert 'id="film-link" href="#film"' in sun and '<figure id="film"' in sun
    mp4 = PAGE.parent / "dory" / "meet-dory.mp4"
    assert mp4.stat().st_size < 5 * 1024 * 1024
    with mp4.open("rb") as f:
        top = []
        while len(top) < 3:
            head = f.read(8)
            top.append(head[4:].decode("latin-1"))
            f.seek(int.from_bytes(head[:4], "big") - 8, 1)
    assert top.index("moov") < top.index("mdat") if "mdat" in top else "moov" in top


def test_the_live_thing_is_a_labelled_scripted_example():
    """Twilight: an editable message and the task card Dory would send. Scripted rules, said so on the
    page, with the parsing in one function a model call can replace."""
    d, html = _dict_and_html()
    tw = _chapter(html, "twilight")
    assert '<textarea id="msg"' in tw and '<label for="msg"' in tw
    assert '<div id="card" aria-live="polite">' in tw and 'class="tc" data-ui' in tw
    assert 'data-i18n="tw_note_b"' in tw and 'data-i18n="tw_note"' in tw
    assert "scripted" in d["tw_note_b"]["en"].lower() and "not the live AI" in d["tw_note"]["en"]
    assert "สคริปต์" in d["tw_note_b"]["th"]
    assert html.count("function read(text)") == 1
    assert "Promise.resolve(read(msg.value))" in html  # read() may become a model call
    # the real handshake: Accept / Edit / Decline, and the owner question when nobody is named
    for k, en in (
        ("b_ok", "Accept"),
        ("b_edit", "Edit"),
        ("b_no", "Decline"),
        ("b_mine", "It's mine"),
        ("b_other", "Someone else"),
        ("b_none", "Not a task"),
    ):
        assert d[k]["en"] == en, k
    assert d["card_nodue"]["en"].endswith("three working days")
    # examples in both languages; names are made up (never the real reference meeting's people)
    egs = re.findall(r'data-eg="(\w+)"', tw)
    assert len(egs) == 4
    assert sum(bool(re.search(r"[฀-๿]", d[k]["en"])) for k in egs) == 2
    for real in ("Peat", "Toey", "Jems"):
        assert real not in html, real
    # due words the rules understand, in English and Thai
    for word in ("tomorrow", "friday", "nov", "วันนี้", "พรุ่งนี้", "จันทร์", "อาทิตย์"):
        assert word in html.split("const DUE", 1)[1].split("\n", 1)[0], word


def test_seabed_answer_hides_what_staff_cannot_read():
    d, html = _dict_and_html()
    sea = _chapter(html, "seabed")
    assert 'class="ans" id="ans" data-ui aria-live="polite"' in sea
    assert re.search(r'name="ask-as" id="as-staff" value="staff" checked', sea)
    assert 'name="ans-lang" id="al-en" value="en" checked' in sea and 'value="th"' in sea
    assert "#management" in d["ans_hidden"]["en"] and "can't read" in d["ans_hidden"]["en"]
    assert "A.x.hidden = !all;" in html
    assert "scripted" in d["sea_note"]["en"].lower()
    assert sea.count("<li>") == 5  # the days settle as strata


def test_noaa_photographs_are_credited_and_linked_to_their_records():
    d, html = _dict_and_html()
    credits = json.loads((PAGE.parent / "dory/photos/credits.json").read_text("utf-8"))
    records = {c["slug"]: c for c in credits}
    for slug, chapter, key in (
        ("noaa-midnight", "midnight", "mid"),
        ("noaa-seabed", "seabed", "sea"),
    ):
        sec = _chapter(html, chapter)
        assert f'src="/static/dory/photos/{slug}-1600.webp"' in sec
        assert f"/static/dory/photos/{slug}-800.webp 800w" in sec and 'loading="lazy"' in sec
        assert f'data-i18n-attr="alt:ph_{key}_alt"' in sec and f'data-i18n="ph_{key}_cap"' in sec
        rec = records[slug]
        assert (
            d[f"ph_{key}_alt"]["en"] == rec["alt_en"] and d[f"ph_{key}_alt"]["th"] == rec["alt_th"]
        )
        assert d[f"ph_{key}_cap"]["en"] == rec["caption_en"]
        assert rec["credit"] in d[f"ph_{key}_credit"]["en"]
        link = f'<a href="{rec["source_url"]}" data-credit="{key}"'
        assert link in sec  # under the photo
        assert link in html.split("<footer", 1)[1]  # and in the footer
    assert "public domain" in d["credits_t"]["en"].lower()


def test_sections_name_only_shipped_features():
    from dory.guild_settings import FEATURES

    for flag in ("voice_meetings", "receipts", "followups", "documents", "wiki"):
        assert flag in FEATURES
    d, html = _dict_and_html()
    feats = _chapter(html, "ascent").split('<ul class="feats">', 1)[1].split("</ul>", 1)[0]
    assert feats.count("<li") == 8 and "icon" not in feats and "<svg" not in feats
    assert d["f7_t"]["en"] == "Search"
    words = json.dumps(d).lower()
    for claim in ("research", "citation", "web search", "searches the web"):
        assert claim not in words, claim
    for href in ("/hub", "/recorder", "/privacy", "/terms", "/center"):
        assert f'href="{href}"' in html.split("<footer", 1)[1], href


def test_hero_primary_is_the_invite_with_a_create_account_fallback():
    """Add Dory to Discord leads; with no invite link the hero still has a primary: Create account."""
    _, html = _dict_and_html()
    hero = _chapter(html, "sunlight")
    assert hero.count("<h1") == 1 and html.count("<h1") == 1
    invite = hero.index('data-invite data-i18n="cta_add"')
    fallback = hero.index('href="/start" data-invite-fallback')
    assert invite < fallback < hero.index('href="#film"')
    assert 'href="/start" data-i18n="not_discord_link"' in hero
    assert "a.hidden = !ok;" in html and "a.hidden = ok;" in html
    nav = html.split('id="hd"', 1)[1].split("</header>", 1)[0]
    assert 'href="/center" data-i18n="nav_login"' in nav and "data-invite" in nav


def test_sign_up_step_hands_the_organization_name_to_start():
    d, html = _dict_and_html()
    last = _chapter(html, "lantern")
    form = re.search(r'<form class="dlg" data-ui action="/start" method="get"[^>]*>', last)
    assert form, "the step works without script: a plain GET to /start?org=..."
    assert re.search(
        r'<input type="text" id="org" name="org" value="Baan Suan Coffee" required', last
    )
    assert d["org_h"]["en"] == "Name your organization" and d["org_go"]["en"] == "Continue"
    assert 'type="submit"' in last


def test_the_homepage_uses_two_faces_and_no_monospace():
    _, html = _dict_and_html()
    assert "Plex+Mono" not in html and "monospace" not in html and "var(--mono)" not in html
    assert (
        "family=Anuphan:wght@600;700&amp;family=IBM+Plex+Sans+Thai:wght@400;600&amp;display=swap"
        in html
    )
    # the display face is preloaded and the fallbacks are sized to it, so the swap does not shift text
    assert re.search(
        r'<link rel="preload" as="font" type="font/woff2" crossorigin href="https://fonts\.gstatic\.com/s/anuphan/',
        html,
    )
    assert html.count("size-adjust:") == 3 and "ascent-override:" in html
    assert '"Anuphan", "Anuphan Fallback"' in html


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


def test_mascot_and_photo_assets_are_served_but_not_the_page_templates(client):
    for name in (
        "dory.svg",
        "dory-mark.svg",
    ):  # the vector drawing gave way to the 3D model's renders
        assert client.get(f"/static/dory/{name}").status_code == 404, name
    for name, kind in (
        ("dory-mark.webp", "image/webp"),
        ("dory-voice.webp", "image/webp"),
        ("favicon.png", "image/png"),
        ("apple-touch-icon.png", "image/png"),
        ("dory.webp", "image/webp"),
        ("dory.jpg", "image/jpeg"),
        ("meet-dory.mp4", "video/mp4"),
        ("photos/noaa-midnight-1600.webp", "image/webp"),
        ("photos/noaa-seabed-800.webp", "image/webp"),
    ):
        r = client.get(f"/static/dory/{name}")
        assert r.status_code == 200 and r.headers["content-type"] == kind, name
    # Safari plays video only from servers that answer byte ranges
    r = client.get("/static/dory/meet-dory.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert client.get("/static/dory/../hub.html").status_code == 404
    assert client.get("/static/hub.html").status_code == 404
    _, html = _dict_and_html()
    assert "cat-" not in html  # Dory replaced the cats


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
        assert '<link rel="icon" type="image/png" href="/static/dory/favicon.png">' in html, name
        assert '<link rel="apple-touch-icon" href="/static/dory/apple-touch-icon.png">' in html, (
            name
        )
        assert 'rel="icon" type="image/svg+xml"' not in html, (
            name
        )  # an SVG icon would win in Chrome
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
