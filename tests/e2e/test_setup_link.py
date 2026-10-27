"""/setup in Discord gives `/center?link=<code>`: once signed in, the server joins the person's
organization (that switches Dory on there) without them copying the code anywhere. With no
organization the code waits until they create one."""

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e


def test_a_setup_link_connects_the_server_to_my_only_organization(page):
    page.goto("/center?mock=1&link=ABCD-1234")  # the sample person owns exactly one org
    expect(page.locator(".wsgrid .card strong", has_text="New server")).to_be_visible()
    assert "link=" not in page.url and page.url.endswith("#/ws")
    assert page.evaluate("sessionStorage.getItem('dory_link')") is None  # used once


def test_without_an_organization_the_link_waits_for_the_new_one(page):
    page.goto("/center?mock=1&orgs=0&link=ABCD-1234")
    assert page.evaluate("sessionStorage.getItem('dory_link')") == "ABCD-1234"
    page.get_by_role("button", name="Create organization").first.click()
    page.get_by_role("dialog").get_by_role("textbox").fill("New Co")
    page.get_by_role("dialog").get_by_role("button", name="Create").click()
    page.locator("#side").get_by_role("link", name="Workspaces").click()
    expect(page.locator(".wsgrid .card strong", has_text="New server")).to_be_visible()
    assert page.evaluate("sessionStorage.getItem('dory_link')") is None


def test_with_several_organizations_the_code_waits_on_workspaces(page):
    page.goto("/center?mock=1")
    page.locator("#new-org").click()  # now the owner of two organizations
    page.get_by_role("dialog").get_by_role("textbox").fill("Second Co")
    page.get_by_role("dialog").get_by_role("button", name="Create").click()
    page.evaluate("sessionStorage.setItem('dory_link', 'ABCD-1234'); start()")
    expect(page.locator("#w-code")).to_have_value("ABCD-1234")  # pick the org, then press Link
    expect(page.locator("#toast")).to_contain_text("Choose this server")
    page.get_by_role("button", name="Link", exact=True).click()
    expect(page.locator(".wsgrid .card strong", has_text="New server")).to_be_visible()
    assert page.evaluate("sessionStorage.getItem('dory_link')") is None
