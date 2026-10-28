"""Static checks on the sign-up page (/start) after the taste audit of 27 Oct 2026: one brand with the
homepage and the chat (Dory's fish mark, her picture), no eyebrow / hairlines / resting shadows, and the
homepage's hand-over of the company name (`/start?org=...`)."""

import json
import re
from pathlib import Path

START = Path(__file__).parent.parent / "src" / "meeting_scribe" / "static" / "start.html"


def page() -> tuple[str, str]:
    html = START.read_text("utf-8")
    style = re.search(r"<style>(.*?)</style>", html, re.S).group(1)
    return html, style


def test_brand_is_the_fish_mark_and_the_theme_tokens():
    html, style = page()
    assert (
        '<span class="mark" aria-hidden="true">D</span>' in html
    )  # theme.css paints dory-mark.webp
    assert ".logo .mark { box-shadow: none; }" in style
    for old in ("#7A6CF0", "--indigo", "#EEF0FF", "#F7F7FF", "linear-gradient"):
        assert old not in style, old


def test_first_screen_has_no_eyebrow_hairline_or_resting_shadow():
    html, style = page()
    assert "eyebrow" not in html
    assert "border-bottom: 1px" not in style and "border-top: 1px" not in style
    assert re.search(r"\.nav \{[^}]*border: 0", style)
    assert "box-shadow: var(--shadow" not in style
    assert 'style="' not in html.split("<body>", 1)[1].split("<script", 1)[0]  # no inline one-offs


def test_dorys_picture_is_on_the_first_screen():
    html, _ = page()
    pic = re.search(r'<picture class="hero-pic">(.*?)</picture>', html, re.S).group(1)
    assert '<source srcset="/static/dory/dory.webp" type="image/webp">' in pic
    assert 'src="/static/dory/dory.jpg" width="777" height="779"' in pic  # no layout shift
    assert 'loading="lazy"' not in pic  # above the fold
    assert 'data-i18n-attr="alt:hero_alt"' in pic


def test_title_is_short_and_text_is_readable():
    html, style = page()
    d = re.search(r'"w_h": \{"th": "([^"]+)", "en": "([^"]+)"\}', html)
    assert len(d.group(2).split()) <= 5  # two lines at most at 390 px
    assert re.search(r"\.card h1 \{[^}]*font-size: clamp\(40px", style)
    assert re.search(
        r"\.card p \{[^}]*font-size: 17px;[^}]*max-width: 60ch;[^}]*var\(--color-text\)", style
    )


def test_motion_respects_reduced_motion():
    _, style = page()
    assert "@keyframes rise" in style and "@keyframes buoy" in style
    assert (
        "@media (prefers-reduced-motion: reduce) { .card > *, .hero-pic, .hero-pic img { animation: none; } }"
        in style
    )


def test_every_string_is_in_thai_and_english():
    html, _ = page()
    data = json.loads(
        re.search(
            r'<script type="application/json" id="i18n-data">(.*?)</script>', html, re.S
        ).group(1)
    )
    missing = [k for k, v in data.items() if not (v.get("th") and v.get("en"))]
    assert missing == []
    for key in re.findall(r'(?<![\w.])t\("(\w+)"[,)]', html):
        assert key in data, key  # every key the script asks for exists


def test_org_name_is_prefilled_from_the_query_trimmed_and_capped():
    html, _ = page()
    assert (
        'id="org-name" maxlength="120" required autocomplete="organization" aria-describedby="org-error"'
        in html
    )
    assert '<div class="notice error" id="org-error" role="alert" hidden></div>' in html
    js = html.split('const ORG_KEY = "dory_signup_org";', 1)[1].split("} catch", 1)[0]
    assert '.get("org") || "").trim().slice(0, $("org-name").maxLength)' in js
    assert '$("org-name").value = org || sessionStorage.getItem(ORG_KEY) || "";' in js
    assert "localStorage" not in js  # this tab only


def test_a_session_the_server_rejects_is_forgotten_and_the_sign_in_screen_stays_clean():
    """A saved `dory_session` answered 401/403/503 must not leave "Sign-in failed" on every load."""
    html, _ = page()
    catch = html.split("async function signedIn(stored = false) {", 1)[1].split("syncLang(", 1)[0]
    assert "const rejected = [401, 403, 503].includes(e.status);" in catch
    assert 'if (rejected) session("clear");' in catch
    assert "if (!(stored && rejected)) note(" in catch  # a stale saved session fails silently
    # a session that just came back from Discord sign-in still reports its failure
    assert 'token = session("get"); signedIn(!fromDiscord);' in html


def test_visitors_never_see_an_env_var_and_no_empty_button_gap():
    html, _ = page()
    d = re.search(r'"not_configured": \{"th": "([^"]+)", "en": "([^"]+)"\}', html)
    assert "HUB_GOOGLE_CLIENT_ID" not in d.group(1) + d.group(2)
    assert '$("not-configured").hidden = false; $("gsi-button").hidden = true;' in html


def test_welcome_bullet_titles_stand_apart_from_their_descriptions():
    html, style = page()
    assert re.search(r"ul\.gets b \{[^}]*display: block", style)
    for k in ("g1_d", "g2_d", "g3_d"):
        en = re.search(rf'"{k}": \{{"th": "[^"]+", "en": "([^"]+)"\}}', html).group(1)
        assert en[0].isupper(), k  # a sentence of its own, not the tail of the title
