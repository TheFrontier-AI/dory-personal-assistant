"""Linking a Discord server with its /ตั้งค่า code also verifies the person's Discord account (the server does
both). The website shows the new server AND the verified account at once, with no reload: the page fetches
/api/center/me again after the link."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_linking_a_discord_server_shows_my_discord_account_without_a_reload(page):
    page.on("dialog", lambda d: d.accept())  # the Unlink confirmation
    page.goto("/center?mock=1#/account")
    row = page.locator(".idrow").filter(has=page.locator("strong", has_text="Discord"))
    expect(row.locator(".badge.ok")).to_be_visible()  # the sample owner starts verified on Discord
    row.locator(".btn.danger").click()  # unlink it, so the page's copy of "me" has no Discord
    expect(row.locator(".badge.ok")).to_have_count(0)

    page.locator("#side").get_by_role("link", name="Workspaces").click()
    page.get_by_label("Link code").fill("ABCD-1234")
    page.get_by_role("button", name="Link", exact=True).click()
    expect(
        page.locator(".wsgrid .card strong", has_text="New server")
    ).to_be_visible()  # the new card

    page.locator("#side").get_by_role("link", name="My profile").click()  # (the avatar is one too)
    row = page.locator(".idrow").filter(has=page.locator("strong", has_text="Discord"))
    expect(row.locator(".badge.ok")).to_be_visible()  # verified by the link, no reload
