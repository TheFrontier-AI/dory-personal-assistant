"""The Dory homepage (`/`): Dory's painted reef, then frosted sections in the deep. Bilingual, honest
about the invite link, the scripted examples and the models, with no 3D scene."""

import html as html_lib
import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from meeting_scribe.config import get_settings

PAGE = Path(__file__).parents[1] / "src/meeting_scribe/static/dory.html"
DORY = PAGE.parent / "dory"
# the header's links, in order, and the section each one lands on
NAV = ["features", "how", "teams", "trust", "pricing", "faq"]


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


def _section(html: str, sid: str) -> str:
    return re.split(rf'<section [^>]*id="{sid}"', html, maxsplit=1)[1].split("</section>", 1)[0]


def _hero(html: str) -> str:
    return html.split('<section class="hero" id="top"', 1)[1].split("</section>", 1)[0]


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
    assert r.text.count(f'href="{url}" data-invite') == 4  # header, hero, plan, last section
    # each one has a create-account fallback for a server without an invite link
    assert r.text.count('href="/start" data-invite-fallback hidden') == 4
    assert "a.hidden = !ok;" in r.text and "a.hidden = ok;" in r.text


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
    assert not re.search(r"[฀-฾เ-๿]", markup)  # the baht sign (U+0E3F) is fine


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
        ("aria-label", "cards_aria"),
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
    # one TH / EN pill in the header, plus the footer's "the other language" button
    assert html.count('data-lang="th"') == 1 and html.count('data-lang="en"') == 1
    pill = html.split('<div class="lang" role="group"', 1)[1].split("</div>", 1)[0]
    assert ">TH</button>" in pill and ">EN</button>" in pill
    assert 'id="lang-other" data-i18n="lang_other"' in html


def test_the_header_links_land_on_real_sections_with_headings():
    """Features, How it works, For Teams, Trust, Pricing, FAQ: each link scrolls to a section that
    exists, in that order, named by its own h2. Log in goes to /center."""
    d, html = _dict_and_html()
    header = html.split('<header class="hd" id="hd">', 1)[1].split("</header>", 1)[0]
    nav = header.split('<nav class="hd-nav"', 1)[1].split("</nav>", 1)[0]
    assert re.findall(r'<a href="#(\w+)"', nav) == NAV
    labels = [d[k]["en"] for k in re.findall(r'data-i18n="(nav_\w+)"', nav)]
    assert labels == ["Features", "How it works", "For Teams", "Trust", "Pricing", "FAQ"]
    order = [html.index(f'id="{sid}"') for sid in NAV]
    assert order == sorted(order), "the sections come in the header's order"
    for sid in NAV:
        sec = re.search(rf'<section class="sec {sid}" id="{sid}" aria-labelledby="(\w+-h)">', html)
        assert sec, sid
        assert f'<h2 id="{sec.group(1)}"' in _section(html, sid), sid
    assert 'href="/center" data-i18n="nav_login"' in header and d["nav_login"]["en"] == "Log in"
    assert "data-invite" in header and "data-invite-fallback" in header
    # on small screens the links fold into a menu button that says whether it is open
    assert 'class="menu-btn" aria-expanded="false" aria-controls="hd-menu"' in header
    assert 'id="hd-menu"' in header
    assert html.count("<h1") == 1 and html.count("</h1>") == 1


def test_hero_matches_the_reference_layout():
    """The painted reef behind, Dory on the right, the eyebrow and two-line headline, the invite with
    the film beside it, three checks and four frosted cards, all on the first screen."""
    d, html = _dict_and_html()
    hero = _hero(html)
    assert d["eyebrow"]["en"] == "AI coworker for teams on Discord"
    assert (d["h1a"]["en"], d["h1b"]["en"]) == ("Ask once.", "Dory remembers.")
    assert '<span class="grad-text" data-i18n="h1b">' in hero
    assert re.search(r"text-transform: uppercase", html.split(".eyebrow {", 1)[1].split("}", 1)[0])
    acts = hero.split('<div class="acts"', 1)[1].split("</div>", 1)[0]
    invite = acts.index('data-invite><svg class="i i-fill"><use href="#i-discord"/>')
    assert invite < acts.index('href="/start" data-invite-fallback') < acts.index('id="film-open"')
    assert [d[k]["en"] for k in ("chk1", "chk2", "chk3")] == [
        "Works in Thai & English",
        "Private to your team",
        "Free during launch",
    ]
    cards = hero.split('<ul class="cards"', 1)[1].split("</ul>", 1)[0]
    assert cards.count('<li class="hcard glass"') == 4 and cards.count('class="tile"') == 4
    assert [d[f"c{i}_t"]["en"] for i in range(1, 5)] == [
        "Meeting notes",
        "Receipts to ledger",
        "Task follow-up",
        "Smart documents",
    ]
    assert "data-motion-toggle" in hero  # the pause control is on the first screen


def test_hero_pictures_are_sized_preloaded_and_never_lazy():
    """The reef is the largest paint: preloaded with high priority, one source per width and a phone
    crop; Dory is the painted cut-out. Both carry their size (no layout shift) and load eagerly."""
    _, html = _dict_and_html()
    head = html.split("</head>", 1)[0]
    assert re.search(
        r'<link rel="preload" as="image" media="\(min-width: 700px\)" fetchpriority="high" '
        r'href="/static/dory/hero-reef-2400.webp"\s+imagesrcset="/static/dory/hero-reef-1280.webp 1280w, '
        r'/static/dory/hero-reef-2400.webp 2400w" imagesizes="100vw">',
        head,
    )
    assert re.search(
        r'<link rel="preload" as="image" media="\(max-width: 699px\)" fetchpriority="high" '
        r'href="/static/dory/hero-reef-phone.webp">',
        head,
    )
    hero = _hero(html)
    bg = hero.split('<picture class="hero-bg">', 1)[1].split("</picture>", 1)[0]
    assert '<source media="(max-width: 699px)" srcset="/static/dory/hero-reef-phone.webp">' in bg
    assert (
        'srcset="/static/dory/hero-reef-1280.webp 1280w, /static/dory/hero-reef-2400.webp 2400w"'
        in bg
    )
    assert 'alt=""' in bg and 'fetchpriority="high"' in bg and "loading=" not in bg
    img = re.search(r'<img src="/static/dory/dory-painted-1200.webp"[^>]+>', hero).group(0)
    assert "/static/dory/dory-painted-700.webp 700w" in img and "sizes=" in img
    assert re.search(r'width="\d+" height="\d+"', img) and "loading=" not in img
    assert 'data-i18n-attr="alt:hero_alt"' in img
    for name in (
        "dory.jpg",
        "dory.webp",
        "dory3d-poster.webp",
    ):  # the painted cut-out replaced them
        assert f"/static/dory/{name}" not in html, name


def test_no_3d_scene_and_no_water_layer():
    """The reference is painted: no three.js, no 3D Dory, no 3D reef, no WebGL water."""
    _, html = _dict_and_html()
    for gone in (
        "dory3d",
        "reef.js",
        "three@",
        "water.js",
        "doryWater",
        "<canvas",
        'type="module"',
    ):
        assert gone not in html, gone
    assert "cat-" not in html  # Dory replaced the cats long ago


def test_motion_can_always_be_paused_and_starts_off_under_reduced_motion():
    _, html = _dict_and_html()
    head = html.split("</head>", 1)[0]
    assert (
        'd.classList.add("js")' in head and 'd.classList.add("motion-off")' in head
    )  # before paint
    assert 'localStorage.getItem("dory-motion")' in head
    markup = html.split('<script type="application/json"', 1)[0]
    assert markup.count("data-motion-toggle") == 2  # in the hero and in the footer
    assert 'MOTION_KEY = "dory-motion"' in html and "prefers-reduced-motion" in html
    # Dory's float, the bubbles and the parallax all stop with motion off
    assert (
        ".motion-off .hero-dory img, .motion-off .bubbles span, .motion-off .sea-bubbles span { animation: none; }"
        in html
    )
    assert ".motion-off .hero-dory, .motion-off .hero-bg { transform: none; }" in html
    assert 'if (!motionOn || e.pointerType !== "mouse") return;' in html
    # entrances hide content only with script and with motion on
    assert ".js:not(.motion-off) [data-group]:not(.in) [data-rise]" in html
    assert (
        "translateY(24px)" in html and "IntersectionObserver" in html and "rise.unobserve" in html
    )


def test_glass_has_fallbacks_for_reduced_transparency_and_old_browsers():
    _, html = _dict_and_html()
    assert "backdrop-filter: blur(" in html and "-webkit-backdrop-filter: blur(" in html
    assert "@media (prefers-reduced-transparency: reduce)" in html
    assert (
        "@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px)))"
        in html
    )
    assert "@media (forced-colors: active)" in html


def test_the_introduction_film_waits_for_play_and_starts_fast():
    """The hero's "See Dory at work" opens the 15-second film in a dialog. It has sound: it never autoplays and
    loads nothing before Play. Without script the link opens the MP4 itself. The MP4 is web-sized and
    fast-start (its index before the data, so playback starts while it downloads)."""
    d, html = _dict_and_html()
    hero = _hero(html)
    assert re.search(
        r'<a class="btn btn-ghost" id="film-open" href="/static/dory/meet-dory.mp4" aria-haspopup="dialog">',
        hero,
    )
    assert d["cta_film"]["en"] == "See Dory at work"
    dlg = html.split('<dialog class="film-dlg" id="film" aria-labelledby="film-h">', 1)[1].split(
        "</dialog>", 1
    )[0]
    video = re.search(r"<video[^>]*>", dlg).group(0)
    assert "controls" in video and "playsinline" in video and 'preload="none"' in video
    assert "autoplay" not in html and "muted" not in video
    # the poster is set when the dialog first opens: a video poster downloads even inside a closed dialog
    assert 'data-poster="/static/dory/meet-dory.webp"' in video and "aria-label:meet_aria" in video
    assert "intro.poster ||= intro.dataset.poster;" in html
    assert '<source src="/static/dory/meet-dory.mp4" type="video/mp4">' in dlg
    assert 'data-i18n="meet_cap"' in dlg  # what the film shows, in words
    assert "data-close" in dlg and 'data-i18n="close"' in dlg
    assert (
        "film.showModal();" in html
        and 'film.addEventListener("close", () => intro.pause());' in html
    )
    mp4 = DORY / "meet-dory.mp4"
    assert mp4.stat().st_size < 5 * 1024 * 1024
    with mp4.open("rb") as f:
        top = []
        while len(top) < 3:
            head = f.read(8)
            top.append(head[4:].decode("latin-1"))
            f.seek(int.from_bytes(head[:4], "big") - 8, 1)
    assert top.index("moov") < top.index("mdat") if "mdat" in top else "moov" in top


def test_the_live_thing_is_a_labelled_scripted_example():
    """How it works: an editable message and the task card Dory would send. Scripted rules, said so on
    the page, with the parsing in one function a model call can replace."""
    d, html = _dict_and_html()
    how = _section(html, "how")
    assert '<textarea id="msg"' in how and '<label for="msg"' in how
    assert '<div id="card" aria-live="polite"' in how and 'class="tc" data-ui' in how
    assert 'data-i18n="tw_note_b"' in how and 'data-i18n="tw_note"' in how
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
    egs = re.findall(r'data-eg="(\w+)"', how)
    assert len(egs) == 4
    assert sum(bool(re.search(r"[฀-๿]", d[k]["en"])) for k in egs) == 2
    for real in ("Peat", "Toey", "Jems"):
        assert real not in html, real
    # due words the rules understand, in English and Thai
    for word in ("tomorrow", "friday", "nov", "วันนี้", "พรุ่งนี้", "จันทร์", "อาทิตย์"):
        assert word in html.split("const DUE", 1)[1].split("\n", 1)[0], word


def test_the_follow_up_clock_uses_the_real_timings():
    d, html = _dict_and_html()
    bar = _section(html, "how").split('<ol class="bar"', 1)[1].split("</ol>", 1)[0]
    assert bar.count("<li") == 4
    assert [d[f"s{i}_d"]["en"] for i in range(1, 5)] == [
        "Seconds",
        "A day",
        "Three working days",
        "Every evening",
    ]
    assert "24 hours" in d["s2_w"]["en"] and "evening report" in d["s4_w"]["en"]


def test_for_teams_answer_hides_what_staff_cannot_read():
    d, html = _dict_and_html()
    teams = _section(html, "teams")
    assert 'class="ans" id="ans" data-ui aria-live="polite"' in teams
    assert re.search(r'name="ask-as" id="as-staff" value="staff" checked', teams)
    for role in ("owner", "manager"):
        assert f'id="as-{role}" value="{role}"' in teams
    assert 'name="ans-lang" id="al-en" value="en" checked' in teams and 'value="th"' in teams
    assert "#management" in d["ans_hidden"]["en"] and "can't read" in d["ans_hidden"]["en"]
    assert "A.x.hidden = !all;" in html
    assert "scripted" in d["sea_note"]["en"].lower()


def test_trust_names_the_models_and_hides_the_line_without_them():
    _, html = _dict_and_html()
    trust = _section(html, "trust")
    assert trust.count('<li class="fact glass"') == 5
    assert '<code id="models">__DORY_MODELS__</code>' in trust and 'id="models-line"' in trust
    assert 'models.textContent.startsWith("__")) $("models-line").hidden = true;' in html


def test_sections_name_only_shipped_features():
    from dory.guild_settings import FEATURES

    for flag in (
        "voice_meetings",
        "receipts",
        "followups",
        "reports",
        "documents",
        "wiki",
        "briefings",
        "catchup",
        "approvals",
        "polls",
        "search",
        "company_learning",
    ):
        assert flag in FEATURES, flag
    d, html = _dict_and_html()
    feats = _section(html, "features").split('<ul class="feats"', 1)[1].split("</ul>", 1)[0]
    assert feats.count('<li class="feat glass"') == 8 and feats.count('class="tile"') == 8
    assert d["f7_t"]["en"] == "Search"
    words = json.dumps(d).lower()
    for claim in ("research", "citation", "web search", "searches the web", "testimonial"):
        assert claim not in words, claim
    for href in ("/hub", "/recorder", "/privacy", "/terms", "/center"):
        assert f'href="{href}"' in html.split("<footer", 1)[1], href


def test_pricing_is_the_one_free_launch_plan():
    d, html = _dict_and_html()
    pricing = _section(html, "pricing")
    assert pricing.count('class="plan glass"') == 1 and 'data-i18n="pl_price">Free<' in pricing
    assert [d[f"pl_{i}"]["en"] for i in range(1, 5)] == [
        "Every feature",
        "No time limit",
        "No seat limit",
        "No card, no payment",
    ]
    assert "no payment in the system" in d["pr_note"]["en"]
    assert "data-invite" in pricing and "data-invite-fallback" in pricing


def test_faq_gives_real_answers():
    """Languages, where Dory works, what she keeps and who owns it, how to start, the cost."""
    d, html = _dict_and_html()
    faq = _section(html, "faq")
    assert faq.count("<details") == 5 and faq.count("<summary>") == 5
    assert "Thai and English" in d["a1"]["en"]
    assert "Discord" in d["a2"]["en"] and "Slack and ClickUp" in d["a2"]["en"]
    assert "forever by default" in d["a3"]["en"] and "admin" in d["a3"]["en"]
    assert "@Dory" in d["a4"]["en"] and "create an account" in d["a4"]["en"]
    assert "no payment in the system" in d["a5"]["en"]


def test_sign_up_step_hands_the_organization_name_to_start():
    d, html = _dict_and_html()
    last = _section(html, "start")
    form = re.search(r'<form class="dlg" data-ui action="/start" method="get"[^>]*>', last)
    assert form, "the step works without script: a plain GET to /start?org=..."
    assert re.search(
        r'<input type="text" id="org" name="org" value="Baan Suan Coffee" required', last
    )
    assert d["org_h"]["en"] == "Name your organization" and d["org_go"]["en"] == "Continue"
    assert 'type="submit"' in last
    # the closing reef is the hero's own picture, loaded only when it is near
    assert (
        'srcset="/static/dory/hero-reef-1280.webp 1280w, /static/dory/hero-reef-2400.webp 2400w"'
        in last
    )
    assert 'loading="lazy"' in last


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


def test_painted_assets_are_served_but_not_the_page_templates(client):
    """Every picture the homepage asks for is served with its type; the templates are not."""
    _, html = _dict_and_html()
    asked = set(re.findall(r"/static/dory/([\w./-]+\.(?:webp|png|jpg|mp4))", html))
    assert {"hero-reef-2400.webp", "hero-reef-1280.webp", "hero-reef-phone.webp"} <= asked
    assert {"dory-painted-1200.webp", "dory-painted-700.webp", "meet-dory.mp4"} <= asked
    kinds = {"webp": "image/webp", "png": "image/png", "jpg": "image/jpeg", "mp4": "video/mp4"}
    for name in sorted(asked | {"dory-mark.webp"}):
        r = client.get(f"/static/dory/{name}")
        assert (
            r.status_code == 200 and r.headers["content-type"] == kinds[name.rsplit(".", 1)[1]]
        ), name
    # Safari plays video only from servers that answer byte ranges
    r = client.get("/static/dory/meet-dory.mp4", headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    assert client.get("/static/dory/../hub.html").status_code == 404
    assert client.get("/static/hub.html").status_code == 404


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
