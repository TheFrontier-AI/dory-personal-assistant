"""Static checks on the Command Center page (single self-contained HTML file)."""

import re
import shutil
import subprocess
from pathlib import Path

import pytest

PAGE = Path(__file__).parent.parent / "src" / "meeting_scribe" / "static" / "center.html"
ALLOWED = {"accounts.google.com", "fonts.googleapis.com", "fonts.gstatic.com"}


def html() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_file_exists_and_nonempty():
    assert PAGE.is_file() and len(html()) > 10_000


def test_no_external_hosts_except_allowed():
    src = html()
    for m in re.finditer(r"""(?:src|href)=["'](https?://[^"']+)["']""", src):
        host = re.match(r"https?://([^/:]+)", m.group(1)).group(1)
        # outbound hrefs only appear in mock sample data / JS, never as page resources
        assert host in ALLOWED, host
    for m in re.finditer(r"<script[^>]+src=[\"']([^\"']+)", src):
        assert re.match(r"https://accounts\.google\.com/", m.group(1)), m.group(1)
    assert "cdn." not in src and "unpkg" not in src and "jsdelivr" not in src


def test_placeholders_present():
    src = html()
    assert "__HUB_GOOGLE_CLIENT_ID__" in src and "__INVITE_URL__" in src


def test_mock_mode_guarded_by_query_param():
    src = html()
    assert 'get("mock") === "1"' in src
    assert "if (MOCK)" in src
    assert "localStorage.setItem(LANG_KEY" in src  # one key shared by every Dory page
    assert not re.search(r"localStorage[^;\n]*token", src, re.I)


def test_served_by_fastapi_static_read():
    # The page is plain text; make sure it parses as a single document with one script block
    src = html()
    assert src.count("<script>") == 1 and src.rstrip().endswith("</html>")


def test_google_calendar_identity_and_attach_endpoints_referenced():
    src = html()
    for needle in (
        '"/google/calendar"',
        '"/connect"',
        '"/identities"',
        '"/identities/" + p + "/code"',
        '"/workspaces/" + p + "/attach-code"',
    ):
        assert needle in src, needle
    assert "window.location = r.auth_url" in src
    assert 'get("calendar")' in src and "history.replaceState" in src


def test_new_i18n_keys_in_both_languages():
    src = html()
    th, en = src.split("\nen: {", 1)
    for key in re.findall(r"\b((?:gc|la|ab)_[a-z]+):", src):
        assert f"{key}:" in th and f"{key}:" in en, key


def between(start: str, end: str) -> str:
    src = html()
    i = src.index(start) + len(start)
    return src[i : src.index(end, i)]


def test_monitor_nav_view_and_placeholder():
    s = html()
    assert '["monitor", "n_monitor"' in s and "VIEWS.monitor = async" in s and "__MONITOR__" in s


def test_monitor_keys_in_both_languages():
    src = html()
    th, en = src.split("\nen: {", 1)
    keys = set(re.findall(r"\b(mon_[a-z0-9_]+):", src))
    assert keys, "no mon_* keys"
    for k in keys:
        assert f"{k}:" in th and f"{k}:" in en, k


def test_monitor_css_is_accessible():
    css = between("/* monitor:css */", "/* monitor:css:end */")
    assert "--faint" not in css and "min-height: 24px" in css
    assert re.search(r"prefers-reduced-motion[^}]*\.mon-flash", html())


def test_monitor_live_region_and_dialog():
    s = html()
    assert 'id: "mon-live"' in s and '"aria-live": "polite"' in s and 'role: "dialog"' in s


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_inline_script_parses(tmp_path):
    # the one inline script is large: a duplicate declaration or a syntax error must fail here,
    # not in a browser
    src = html()
    code = src.split("<script>", 1)[1].split("</script>", 1)[0]
    probe = tmp_path / "center.js"
    probe.write_text(code, encoding="utf-8")
    run = subprocess.run(["node", "--check", str(probe)], capture_output=True, text=True)
    assert run.returncode == 0, run.stderr


def monitor_view() -> str:
    return between("/* ---------- Monitor: a calm live view", "\nVIEWS.settings = async")


def test_monitor_hidden_tab_polls_only_for_armed_notifications():
    view = monitor_view()
    # R10: sched() and poll() ask monPollDelay (hidden + armed -> every MON_HEAL_MS, hidden alone -> stop)
    assert view.count("monPollDelay(") >= 2
    assert 'Notification.permission === "granted" && monNotifyOptIn()' in view


def test_monitor_new_pill_is_inside_the_frozen_zone():
    view = monitor_view()
    for ev in ("pointerenter", "pointerleave", "focusin", "focusout"):
        assert (
            f'zone.addEventListener("{ev}"' in view and f'list.addEventListener("{ev}"' not in view
        )
    assert re.search(r"const zone = el\([^;]*newPill[^;]*list", view)


def test_monitor_row_name_has_no_ticking_time_and_no_repeated_kind():
    view = monitor_view()
    assert '"aria-label": rowName(x)' in view and "monTitleRest(" in view


def test_route_focuses_content_on_a_new_page_or_when_focus_was_inside():
    # a new page takes focus; so does a re-render while focus was in the page (Retry, Save, Delete),
    # which would otherwise drop focus to <body>. A re-render from outside (language, company) does not.
    s = html()
    body = between("function route() {", "\nconst stale = ")
    assert "const moved = cur !== id;" in body
    inside = body.index("const inside = c.contains(document.activeElement);")
    assert inside < body.index("c.replaceChildren(")  # read before the old page is removed
    assert "if (moved || inside) c.focus({ preventScroll: true });" in body
    assert "if (moved) c.focus(" not in s


# dory.monitor.Step.state
STEP_STATES = ("pending", "running", "done", "failed", "cancelled", "skipped")


def test_monitor_every_step_state_has_a_label_and_an_icon():
    s = html()
    th, en = s.split("\nen: {", 1)
    icons = re.search(r"const MON_ICON = \{([^}]*)\}", s).group(1)
    for st in STEP_STATES:
        assert re.search(rf"\b{st}: \"[^\"]+\"", icons), st
        if st != "pending":  # a step that has not started reads "Waiting" (mon_s_waiting)
            assert f"mon_s_{st}:" in th and f"mon_s_{st}:" in en, st
    css = between("/* monitor:css */", "/* monitor:css:end */")
    assert ".mon-ic.skipped" in css


def test_every_feature_flag_has_a_thai_label():
    from dory.guild_settings import FEATURES

    body = re.search(r"const FEAT_TH = \{(.*?)\};", html()).group(1)
    labels = dict(re.findall(r'(\w+): "([^"]+)"', body))
    missing = [f for f in FEATURES if not re.search(r"[฀-๿]", labels.get(f, ""))]
    assert not missing, missing


# ---------- chat (Lantern Deep): the panel and the #/chat page share one widget ----------
CHAT_KEYS = [
    "n_chat",
    "dory_name",
    "you",
    "chat_hi",
    "chat_intro",
    "chat_trust",
    "chat_try",
    "sug_docs",
    "sug_meet",
    "sug_people",
    "thinking_s",
    "thinking_sr",
    "still_working",
    "long_wait",
    "stop_wait",
    "stopped",
    "ask_again",
    "chat_err",
    "copy_q",
    "copy_fail",
    "offline_p",
    "send_hint",
    "drop_files",
    "search_hist",
    "jump_day",
    "yesterday",
    "no_match",
    "files_sent",
    "history",
]


def chat_widget() -> str:
    return between("function chatWidget(hist, prefix, opts = {}) {", "\nconst chatData = ")


def test_chat_is_a_page_and_still_the_panel():
    s = html()
    assert '["chat", "n_chat", "chat"]' in s and "VIEWS.chat = async" in s
    assert "the chat is the panel now" not in s  # #/chat no longer bounces to the overview
    assert '$("fab").hidden = id === "chat"' in s  # one composer at a time
    assert 'if (cur !== "chat") route();' in s  # an answer never rebuilds the page under the reader


def test_chat_strings_exist_in_both_languages():
    th, en = html().split("\nen: {", 1)
    for k in CHAT_KEYS:
        assert f"{k}:" in th and f"{k}:" in en, k


def test_chat_states_are_announced_once_and_stop_waiting_is_honest():
    w = chat_widget()
    assert '"aria-relevant": "additions"' in w and 'role: "status"' in w
    assert (
        '"msg bot wait", "aria-hidden": "true"' in w
    )  # the counter is visual; the status region speaks
    assert "AbortController" in w and "busy.abort()" in w and 'ev.key === "Escape" && busy' in w
    assert (
        "Dory may still finish" in html()
    )  # the browser stops waiting; the server may still answer
    assert (
        'class: "msg cnote"' in w and ".msg.cnote" in html()
    )  # never the docs page's sticky .note
    assert "!ev.isComposing && !coarse" in w  # Thai IME and touch keyboards never send by accident


def test_voice_call_is_the_painted_reef_scene():
    """The voice call (owner's reference, 27 Oct 2026): the painted reef fills the panel, the painted Dory stands on a CSS
    ring of light, a frosted speech bubble carries the state in words and a waveform; 2.5D, no WebGL in the app."""
    s = html()
    assert (
        "FISH_SVG" not in s and "dory-defs" not in s and "dory-mark.svg" not in s
    )  # no vector rig
    assert (
        "dory-voice.webp" not in s and "dory3d" not in s and "three@" not in s
    )  # no sprite, no WebGL
    assert 'url("/static/dory/voice-reef.webp") center / cover' in s
    assert 'src="/static/dory/dory-painted-700.webp"' in s and "dory-painted-1200.webp 1200w" in s
    css = between("/* live call:", "/* company profile:")
    assert ".call .ring {" in css and "radial-gradient" in css  # light, not a drawn rock
    assert (
        "max(var(--lvl), var(--mouth))" in css
    )  # the waveform follows the mic or Dory, whichever is louder
    assert "prefers-reduced-transparency" in css and "-webkit-backdrop-filter" in css
    assert re.search(
        r"prefers-reduced-motion[^}]*\.call \.fish[^}]*\.call \.wave i", s
    )  # bob and wave stop
    view = between("const build = () => {", "\n  // Expand:")
    assert (
        'class: "speech", role: "status", "aria-live": "polite"' in view
    )  # the state is announced in words
    assert '"data-theme": "deep"' in view and 'role: "region"' in view
    assert "page ? null :" in view  # the #/chat page keeps itself: its call has no Close


def test_speaker_is_a_real_toggle_and_expand_restores_with_escape():
    s = html()
    th, en = s.split("\nen: {", 1)
    assert (
        "S.out.gain.value = S.spkOff ? 0 : 1" in s
    )  # Dory's voice on this device; the call goes on
    assert (
        "onclick: () => setSpeaker(S.spkOff)" in s
        and 'v.spkB.setAttribute("aria-pressed", String(S.spkOff))' in s
    )
    assert ".call.max { position: fixed;" in s
    assert 'const big = document.querySelector(".call.max"); if (big) { big.unmax(); return; }' in s
    for k in (
        "live_spk",
        "live_spk_off",
        "live_spk_mute",
        "live_spk_unmute",
        "live_conv",
        "live_expand",
        "live_restore",
    ):
        assert f"{k}:" in th and f"{k}:" in en, k


def test_top_bar_search_asks_dory_and_the_bell_needs_the_monitor():
    s = html()
    th, en = s.split("\nen: {", 1)
    assert '<form class="qs" id="qs-form" role="search">' in s
    assert (
        'askDory(t("search_ask", { q: x }))' in s
    )  # Dory's search covers chat, files, wiki, tasks, meetings
    assert "(ev.metaKey || ev.ctrlKey)" in s and '$("qs").focus()' in s
    ask = between("function askDory(text) {", "\n}")
    assert "chatPage.w.ask(text)" in ask and "panel.ask = text; panelOpen();" in ask
    assert '$("bell").hidden = !(orgId && pageVisible("monitor"))' in s  # only real attention items
    assert 'href="#/monitor?tab=attention"' in s
    for k in ("qs_ph", "qs_label", "search_ask", "lang_label", "sub_overview", "sub_noorg"):
        assert f"{k}:" in th and f"{k}:" in en, k


def test_first_run_page_and_its_help_ask_dory():
    s = html()
    th, en = s.split("\nen: {", 1)
    first = between("function noOrg(full) {", "\n}")
    assert (
        'onclick: () => askDory(t("help_q"))' in first
    )  # no documentation page exists: ask Dory instead
    assert "/docs" not in first and "http" not in first
    assert first.count('class: "itile ') == 1 and '["shield", "orange", "can_safe"]' in first
    assert (
        't("ask_after_org", { q: panel.ask })' in s
    )  # without a company, the question waits and says so
    assert 'get("orgs") === "0") mockApi.s.orgs = []' in s  # ?mock=1&orgs=0 shows the first run
    for k in (
        "can_h",
        "can_members_h",
        "can_know_p",
        "can_tools_h",
        "can_safe_p",
        "help_h",
        "help_p",
        "help_b",
        "help_q",
        "ask_after_org",
    ):
        assert f"{k}:" in th and f"{k}:" in en, k


def test_company_profile_sections_use_the_existing_editor_and_links():
    view = between("VIEWS.overview = async (body, my) => {", "\n};")
    assert 'infoCard("file", t("cp_about"), editB(t("cp_about"), "about")' in view
    assert 'infoCard("scale", t("lg_h"), editB(t("lg_h"), "legal")' in view
    assert 'href: "#/members" }, ic("users"), t("cp_manage"))' in view
    assert 'sessionStorage.setItem("center_mtab", "chart")' in view and "foot: false" in view
    assert '(at === "about" ? about : at === "legal" ? F.registered_name : F.name).focus()' in view


def test_no_cat_assets_left_in_the_command_center():
    for name in ("center.html", "dory/theme.css"):
        src = (PAGE.parent / name).read_text("utf-8")
        assert (
            "cat-avatar" not in src and "dory-profile.webp" not in src and "cat-hero" not in src
        ), name
    assert (
        '<div class="mark" aria-hidden="true">S</div>' not in html()
    )  # the letter was the old name's


# ---------- audit fixes (27 Oct 2026): icons, the Live button, the chat title, mock samples ----------
def test_interface_icons_are_svg_not_emoji_or_symbol_glyphs():
    """The taste audit flags emoji and dingbats used as icons (same ranges as its probe)."""
    s = html()
    assert not re.search(r"[\U0001F300-\U0001FAFF\u2600-\u27BF]", s)
    icons = between("const IC = {", "\n};")
    assert 'stroke-width="1.75"' in between("const icHtml = ", "\n")
    nav = re.findall(r'\["\w+", "n_\w+", "(\w+)"\]', between("const NAV_SECTIONS = [", "\n];"))
    used = set(nav) | set(re.findall(r'ic\("(\w+)"\)', s))
    used |= set(re.findall(r'"(\w+)"', between("const MON_ICON = {", "};")))
    used |= set(re.findall(r'data-ic="(\w+)"', s))  # the page's static icons, same set
    assert used and all(f"  {n}: '" in icons for n in used), used - set(
        re.findall(r"  (\w+): '", icons)
    )


def test_live_button_is_flat_and_the_side_menu_floats_only_when_open():
    s = html()
    live = re.search(r"\.livebtn \{[^}]*\}", s).group(0)
    assert "gradient" not in live and "shadow" not in live
    assert "body.nav-open #side { transform: none; box-shadow: var(--shadow-lg); }" in s


def test_chat_page_has_a_visible_h1_and_a_sentence_case_rail_label():
    s = html()
    assert 'h1.classList.add("sr")' not in s
    assert 'el("div", { class: "grow" }, h1, ' in s  # the page title sits in the chat header
    rail = re.search(r"\.chatpage \.rail-h \{[^}]*\}", s).group(0)
    assert "uppercase" not in rail and "letter-spacing" not in rail


def test_mock_samples_follow_the_interface_language():
    """Every Thai sample string in the mock API has an English twin, and every mock answer goes through it."""
    s = html()
    assert ".then(mockLang);" in s and 'if (lang === "th") return x;' in s
    table = set(re.findall(r'"((?:[^"\\]|\\.)*)":', between("const MOCK_EN = {", "\n};")))
    mock = between("function mockApi(method, path, body) {", "/* ---------- boot ---------- */")
    thai = {x for x in re.findall(r'"((?:[^"\\]|\\.)*)"', mock) if re.search(r"[\u0e00-\u0e7f]", x)}
    assert thai and thai <= table, thai - table
