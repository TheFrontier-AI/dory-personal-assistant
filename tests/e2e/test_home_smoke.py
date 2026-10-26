"""Playwright smoke of the homepage (`/`): the Pause motion control, the example tabs by keyboard, no
sideways scroll at 320 px, and an axe WCAG 2.2 AA scan of the whole page."""

import re

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}


def test_pause_motion_is_remembered(page):
    page.goto("/")
    pause = page.locator(".hero [data-motion-toggle]")
    expect(pause).to_have_text("Pause motion")
    pause.click()
    expect(page.locator("html")).to_have_class(re.compile(r"\bmotion-off\b"))
    page.reload()
    expect(page.locator("html")).to_have_class(
        re.compile(r"\bmotion-off\b")
    )  # saved in dory-motion


def test_example_tabs_work_by_keyboard(page):
    page.goto("/")
    tabs = page.locator("#pv-tabs [role=tab]")
    tabs.first.focus()
    page.keyboard.press("ArrowRight")
    expect(tabs.nth(1)).to_be_focused()
    expect(tabs.nth(1)).to_have_attribute("aria-selected", "true")


def test_no_sideways_scroll_on_a_small_phone(page):
    page.set_viewport_size({"width": 320, "height": 700})
    page.goto("/")
    assert page.evaluate("document.documentElement.scrollWidth") <= 320


def test_axe_finds_no_wcag_aa_violations_on_the_homepage(page):
    page.emulate_media(reduced_motion="reduce")  # everything visible at once, nothing mid-animation
    page.goto("/")
    res = Axe().run(page, options=WCAG)
    assert res.violations_count == 0, res.generate_report()
