"""Playwright smoke of the travel cards in the "Talk to Dory" panel (`/center?mock=1`): the mock chat
plays Dory's brain (cards with the filters it heard, one question when details are missing, the
no-AI fallback with Try again) and the cards call the real public /api/travel. Every card says it is a
sample (fictional hotels, a generic aircraft icon), Non-stop changes the count, See more appends,
Select flight posts a fare review, View rooms lists the rooms, axe WCAG 2.2 AA, and nothing scrolls
sideways in a 320 px panel."""

import pytest
from axe_playwright_python.sync_playwright import Axe
from playwright.sync_api import expect

pytestmark = pytest.mark.e2e

ASK = "Find a flight from Bangkok to Singapore and a hotel there for 2 people next week"
WCAG = {
    "runOnly": {"type": "tag", "values": ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]},
    "resultTypes": ["violations"],
}
OVERFLOW = """() => { const p = document.querySelector('#panel').getBoundingClientRect(), bad = [];
  for (const n of document.querySelectorAll('#panel *')) {
    if (n.closest('.sr')) continue;
    const r = n.getBoundingClientRect();
    if (r.width && (r.right > p.right + 0.5 || r.left < p.left - 0.5)) bad.push(n.className || n.tagName);
  }
  return { scroll: document.documentElement.scrollWidth, inner: innerWidth, bad }; }"""


def say(page, text):
    page.goto("/center?mock=1")
    page.locator("#fab").click()
    page.locator("#p-in").fill(text)
    page.keyboard.press("Enter")
    return page.locator("#panel")


def ask(page, text=ASK):
    panel = say(page, text)
    expect(panel.locator(".tv-flight")).to_have_count(1)
    expect(panel.locator(".tv-hotel")).to_have_count(1)
    return panel


def test_every_card_says_it_is_a_sample(page):
    panel = ask(page)
    flight, hotel = panel.locator(".tv-flight"), panel.locator(".tv-hotel")
    expect(flight).to_contain_text("Sample itinerary · Sample price")
    expect(hotel).to_contain_text("Fictional property · Sample rating and reviews")
    expect(panel.locator(".tv-note")).to_have_text(
        "Demo results—not live availability or a confirmed booking."
    )
    logo = flight.locator(".tv-logo")  # one generic aircraft, never an airline code or brand
    expect(logo).to_have_attribute("aria-hidden", "true")
    expect(logo.locator("svg")).to_have_count(1)
    expect(logo).to_have_text("")


def test_the_brains_filters_start_pressed(page):
    panel = ask(
        page,
        "Find non-stop flights from Bangkok to Singapore and a hotel with free cancellation next week",
    )
    expect(panel.get_by_role("button", name="Non-stop")).to_have_attribute("aria-pressed", "true")
    expect(panel.locator(".tv-count").first).to_have_text("Showing 1 of 9 sample flights")
    free = panel.get_by_role("button", name="Free cancellation")
    expect(free).to_have_attribute("aria-pressed", "true")


def test_missing_details_get_one_question_and_no_cards(page):
    panel = say(page, "find me a flight")
    expect(panel.locator(".msg.bot.last")).to_contain_text("Where would you like to go")
    expect(panel.locator(".trv")).to_have_count(0)


def test_ai_down_still_shows_cards_with_a_notice_and_retry(page):
    panel = ask(page, "Find a flight to Singapore and a hotel next week error")
    last = panel.locator(".msg.bot.last")
    expect(last).to_contain_text("I couldn't interpret this with Dory's AI just now")
    expect(last.locator(".tv-flight")).to_have_count(1)
    users = panel.locator(".msg.me").count()
    last.get_by_role("button", name="Try again").click()  # asks the brain again, no new question
    expect(panel.locator(".trv")).to_have_count(2)
    assert panel.locator(".msg.me").count() == users


def test_cards_filter_page_review_and_rooms(page):
    panel = ask(page)
    flights, hotels = panel.locator(".tv-count").first, panel.locator(".tv-count").nth(1)
    expect(panel.get_by_role("button", name="Non-stop")).to_have_attribute("aria-pressed", "false")
    expect(flights).to_have_text("Showing 1 of 12 sample flights")
    expect(hotels).to_have_text("Showing 1 of 8 sample hotels")
    expect(panel.locator(".tv-flight")).to_contain_text("THB 6,380")  # 2 travellers, taxes in
    nonstop = panel.get_by_role("button", name="Non-stop")
    nonstop.click()
    expect(nonstop).to_have_attribute("aria-pressed", "true")
    expect(flights).to_have_text("Showing 1 of 9 sample flights")
    panel.get_by_role("button", name="See more flights").click()
    expect(panel.locator(".tv-flight")).to_have_count(4)
    expect(flights).to_have_text("Showing 4 of 9 sample flights")
    panel.get_by_role("button", name="Select flight").first.click()
    expect(panel.locator(".tv-flight.sel")).to_have_count(1)
    review = panel.locator(".msg.bot.last .tv-review")
    expect(review).to_contain_text("nothing has been booked")
    expect(review).to_contain_text("Total (THB 3,190 × 2 travellers)")
    rooms = panel.get_by_role("button", name="View rooms")
    rooms.click()
    expect(panel.get_by_role("button", name="Hide rooms")).to_have_attribute(
        "aria-expanded", "true"
    )
    expect(panel.locator(".tv-room")).to_have_count(3)


def test_axe_finds_no_wcag_aa_violations_in_the_travel_cards(page):
    page.emulate_media(reduced_motion="reduce")  # a hovered action row is never half faded in
    panel = ask(page)
    panel.get_by_role("button", name="View rooms").click()
    expect(panel.locator(".tv-room")).to_have_count(3)
    panel.get_by_role("button", name="Edit search").first.click()
    panel.get_by_role("button", name="Airlines").click()
    expect(panel.get_by_role("checkbox")).not_to_have_count(0)
    panel.get_by_role("button", name="Select flight").click()
    expect(panel.locator(".tv-review")).to_have_count(1)
    panel.get_by_role("button", name="Book in sandbox").click()  # the inline confirm step too
    expect(panel.locator(".tv-confirm .tv-dl")).to_have_count(1)
    res = Axe().run(page, context="#panel", options=WCAG)
    assert res.violations_count == 0, res.generate_report()


def test_nothing_overflows_a_320_px_panel(page):
    page.set_viewport_size({"width": 320, "height": 900})
    panel = ask(page)
    panel.get_by_role("button", name="View rooms").click()
    expect(panel.locator(".tv-room")).to_have_count(3)
    panel.get_by_role("button", name="Choose room").first.click()  # the long reference must wrap
    expect(panel.locator(".tv-review .tv-ref")).to_have_count(1)
    panel.get_by_role("button", name="Book in sandbox").click()  # and the confirm step
    expect(panel.locator(".tv-confirm .tv-dl")).to_have_count(1)
    panel.get_by_role("button", name="Edit search").first.click()
    panel.get_by_role("button", name="Airlines").click()
    got = page.evaluate(OVERFLOW)
    assert got["scroll"] <= got["inner"] and got["bad"] == [], got


def test_book_a_flight_straight_from_the_card(page):
    panel = ask(page)
    panel.get_by_role("button", name="Select flight").click()
    # not ".msg.bot.last": the booked line becomes the last message
    review = panel.locator(".tv-review").first
    expect(review.locator(".tv-ref")).to_contain_text("Booking reference: BKKSIN.SL106-")
    mine = panel.locator(".msg.me").count()
    review.get_by_role(
        "button", name="Book in sandbox"
    ).click()  # books in the card: no chat message
    confirm = review.locator(".tv-confirm")
    expect(confirm.get_by_role("checkbox")).to_have_count(1)  # the flight, always included
    expect(confirm.locator(".tv-dl .tot")).to_contain_text(["Total", "THB 6,380"])
    expect(confirm).to_contain_text("no money is charged")
    confirm.get_by_label("What is it for? (optional)").fill("Lumen kickoff")
    confirm.get_by_label("What is it for? (optional)").press("Tab")  # a new purpose = a new quote
    expect(confirm.get_by_role("button", name="Confirm booking")).to_be_enabled()
    confirm.get_by_role("button", name="Confirm booking").click()
    expect(review.locator(".tv-done")).to_contain_text("Booked in the sandbox · references KQ6YLN")
    expect(review.get_by_role("button", name="Booked")).to_be_disabled()
    booked = panel.locator(".msg.bot.last")
    expect(booked).to_contain_text("Booked in the sandbox: Thai Lion Air SL106")
    expect(booked).to_contain_text("no money is charged")
    assert panel.locator(".msg.me").count() == mine


def test_book_a_flight_and_a_room_together_from_the_cards(page):
    panel = ask(page)
    panel.get_by_role("button", name="Select flight").click()
    expect(panel.locator(".tv-review")).to_have_count(1)
    panel.get_by_role("button", name="View rooms").click()
    expect(panel.locator(".tv-room")).to_have_count(3)
    panel.get_by_role("button", name="Choose room").first.click()
    stay = panel.locator(".tv-review").nth(1)  # the flight's review is first
    expect(stay.locator(".tv-ref")).to_contain_text("Booking reference: SIN.")
    stay.get_by_role("button", name="Book in sandbox").click()
    confirm = stay.locator(".tv-confirm")
    boxes = confirm.get_by_role("checkbox")
    expect(boxes).to_have_count(2)  # the flight picked above + this room (always included)
    expect(boxes.nth(1)).to_be_disabled()
    expect(confirm.locator(".tv-dl dd.tot")).to_contain_text("THB 29,450")  # 6,380 + 23,070
    boxes.nth(0).uncheck()  # the room only
    expect(confirm.locator(".tv-dl dd.tot")).to_contain_text("THB 23,070")
    boxes.nth(0).check()
    expect(confirm.locator(".tv-dl dd.tot")).to_contain_text("THB 29,450")
    confirm.get_by_role("button", name="Confirm booking").click()
    expect(stay.locator(".tv-done")).to_contain_text("KQ6YLN, JKLMYA7B")
    expect(panel.locator(".msg.bot.last")).to_contain_text(
        "References: flight KQ6YLN, hotel JKLMYA7B"
    )
    # the flight's own review shows it as booked too
    expect(panel.get_by_role("button", name="Booked")).to_have_count(2)


def test_a_round_trip_draws_the_way_back(page):
    panel = say(page, "Find a round trip flight from Bangkok to Singapore and a hotel next week")
    expect(panel.locator(".tv-flight")).to_have_count(2)  # out and back, one block each
    heads = panel.locator(".tv-block h3")
    expect(heads.nth(0)).to_contain_text("Bangkok (BKK) → Singapore (SIN)")
    expect(heads.nth(1)).to_contain_text("Singapore (SIN) → Bangkok (BKK)")
    expect(panel.locator(".tv-hotel")).to_have_count(1)
