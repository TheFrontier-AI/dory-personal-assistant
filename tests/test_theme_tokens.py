"""The shared design tokens (static/dory/theme.css): the contrast the proposal promises is checked here."""

import re
from pathlib import Path

CSS = (Path(__file__).parents[1] / "src/meeting_scribe/static/dory/theme.css").read_text("utf-8")
HEX = dict(re.findall(r"(--[a-z0-9-]+):\s*(#[0-9A-Fa-f]{6})\b", CSS))


def lum(h: str) -> float:
    def ch(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (int(h[i : i + 2], 16) / 255 for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def ratio(a: str, b: str) -> float:
    hi, lo = sorted((lum(HEX.get(a, a)), lum(HEX.get(b, b))), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_text_tokens_meet_aa_on_both_themes():
    for fg, bg in (
        ("--ink-900", "--sand-50"),
        ("--ink-600", "--sand-50"),
        ("--ink-500", "--sand-50"),  # subtle text: replaces #8A8FA6 (3.0:1)
        ("--ink-500", "--sand-100"),
        ("--plankton-600", "--sand-50"),
        ("#FFFFFF", "--plankton-800"),
        ("#FFFFFF", "--ocean-700"),  # the user's chat bubble
        ("--ocean-50", "--ocean-950"),
        ("--ocean-300", "--ocean-950"),
        ("--ocean-300", "--ocean-800"),
        ("--ocean-400", "--ocean-950"),
        ("--ocean-400", "--ocean-800"),
        ("--ocean-950", "--lantern-300"),  # the primary button on dark
        ("--glow-300", "--ocean-950"),
    ):
        assert ratio(fg, bg) >= 4.5, (fg, bg, round(ratio(fg, bg), 2))


def test_control_borders_meet_non_text_contrast():
    for fg, bg in (
        ("--ink-400", "--sand-0"),
        ("--ink-400", "--sand-50"),
        ("--ocean-500", "--ocean-950"),
        ("--ocean-500", "--ocean-800"),
    ):
        assert ratio(fg, bg) >= 3, (fg, bg, round(ratio(fg, bg), 2))


def test_dark_is_a_scope_and_old_names_follow_it():
    assert '[data-theme="deep"] {' in CSS and "prefers-color-scheme" not in CSS
    assert (
        ":root, [data-theme] {" in CSS
    )  # legacy names re-declared per scope, so --ink etc. follow it
    assert "--faint: var(--color-text-subtle)" in CSS
    assert (
        "border: 1px solid var(--color-border-control)" in CSS
    )  # inputs no longer use the 1.3:1 divider
    assert 'url("/static/dory/dory-mark.svg")' in CSS and "cat-avatar" not in CSS
