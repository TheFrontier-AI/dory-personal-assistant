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


def test_sign_up_asks_for_nothing_it_does_not_need():
    """Google or Discord proves the email: no password box, no marketing checkbox, and the only text
    field before the preferences is the organization name."""
    html, _ = page()
    assert 'type="password"' not in html and 'type="checkbox"' not in html
    assert len(re.findall(r'<input type="text"', html)) == 1  # the organization name


def test_terms_and_privacy_and_the_sign_in_link_are_on_the_first_screen():
    html, _ = page()
    first = html.split('id="step1"', 1)[1].split("</section>", 1)[0]
    assert 'data-i18n-html="terms_agree"' in first and 'data-i18n-html="have_account"' in first
    data = json.loads(
        re.search(
            r'<script type="application/json" id="i18n-data">(.*?)</script>', html, re.S
        ).group(1)
    )
    for lang in ("th", "en"):
        terms = data["terms_agree"][lang]
        assert 'href="/terms"' in terms and 'href="/privacy"' in terms
        assert 'href="/center"' in data["have_account"][lang]  # /center is the sign-in


def test_errors_are_announced_and_the_flow_has_four_labelled_steps():
    html, _ = page()
    for ident in ("login-error", "org-error", "pref-error"):
        assert re.search(rf'id="{ident}" role="alert" hidden', html), ident
    assert 'id="signing" role="status"' in html  # "Signing you in…" while the session is exchanged
    sections = re.findall(r'<section class="card" id="(\w+)"', html)
    assert sections == ["step1", "existing", "step2", "step3", "step4"]
    assert len(re.findall(r'data-step="\d"', html)) == 4


def test_the_travel_step_is_optional_labelled_and_never_asks_for_a_permission():
    html, _ = page()
    step = html.split('id="step3"', 1)[1].split("</section>", 1)[0]
    assert step.count("<select") == 2 and step.count("<label>") == 2  # both wrap their control
    for key in ("pref_airport", "pref_ccy"):  # "(optional)" is part of the label
        en = re.search(rf'"{key}": \{{[^}}]*"en": "([^"]+)"', html).group(1)
        assert "(optional)" in en, key
    assert 'id="pref-skip"' in step and 'id="pref-save"' in step
    for api in ("geolocation", "getUserMedia", "Notification.requestPermission"):
        assert api not in html  # no location, microphone or notification prompt in sign-up


def test_an_example_is_a_link_that_fills_the_chat_box_and_nothing_sends_it():
    html, _ = page()
    center = (START.parent / "center.html").read_text("utf-8")
    assert 'a.href = "/center#/chat"' in html and "a.dataset.q = q" in html
    assert 'sessionStorage.setItem("dory_chat_prefill"' in html
    take = center.split("function takePrefill() {", 1)[1].split("\n}\n", 1)[0]
    assert 'sessionStorage.getItem("dory_chat_prefill")' in take and "Date.now()" in take
    use = center.split("const pre = takePrefill();", 1)[1].split("\n", 1)[0]
    assert "w.prefill(pre)" in use and ".ask(" not in use and "send(" not in use


def test_skipping_never_waits_and_a_save_is_not_assumed():
    html, _ = page()
    skip = html.split('$("pref-skip").addEventListener', 1)[1].split("\n});", 1)[0]
    assert "await" not in skip and 'show("step4")' in skip
    save = html.split('$("pref-form").addEventListener', 1)[1].split("\n});", 1)[0]
    assert save.index("await api(") < save.index('show("step4")')  # moves on only after the answer
    assert 'pending(btn, "pref_saving")' in save and "aria-busy" in save  # one request per press
