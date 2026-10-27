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
    "chip_missed",
    "chip_tasks",
    "chip_spend",
    "chip_upload",
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


def test_the_fish_in_center_is_the_master_drawing():
    master = (PAGE.parent / "dory" / "dory.svg").read_text("utf-8")
    body = re.sub(
        r">\s+<",
        "><",
        master[master.index('<g class="dory-fish">') : master.rindex("</svg>")].strip(),
    )
    s = html()
    assert body in s, "FISH_SVG drifted from static/dory/dory.svg"
    defs = re.search(r'<svg id="dory-defs"[^>]*>', s).group(0)
    assert "position:absolute" in defs and "display:none" not in defs  # hidden defs would not paint
    assert '"data-theme": "deep"' in s  # the voice-call stage is the deep sea


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
