# Talk to Dory: flight and hotel search cards (web + Discord)

A working prototype of one travel search journey on two platforms, built on sample data:
ask -> compact search summary + results -> edit / filter / see more -> select a flight or view
rooms -> a review step that keeps the search. Nothing is booked and no payment exists. Every card
says what it is (flights "Sample itinerary · Sample price", hotels "Fictional property · Sample
rating and reviews"), every reply carries "Demo results—not live availability or a confirmed
booking.", and every API answer carries `data: {source: "sample", live_availability: false,
bookable: false, notice}`.

## Assumptions and design rationale

- **One brain, two presentations.** `src/dory/travel_search.py` (no `discord` import) holds the
  sample catalogue and every rule: filters, sorting, pages, tags, price maths, fare review, rooms,
  stay review, per-person sessions and the typed-request parser. The web page and the Discord bot
  only word and lay out the dicts it returns, so the same search gives the same ids, totals and
  order on both.
- **The repo's own stack**, not a new one: FastAPI + the vanilla `static/center.html` chat panel,
  and discord.py 2.7.1 in the bot. The brief's React/Node default applied only without a repo.
- **One cohesive sample trip.** Bangkok (BKK) -> Singapore (SIN), departing Tuesday of next week,
  2 travellers, Economy; Singapore hotel from the same day, 3 nights, 1 room, 2 guests. All prices
  are THB and already include taxes and fees. 12 flights (9 non-stop, 3 one-stop via KUL / SGN,
  one landing after midnight) and 8 hotels with 1-3 room rates each, enough to see filters and
  pages change results. Local times use each airport's offset (BKK UTC+7, SIN UTC+8).
- **Fictional hotels** in real Singapore neighbourhoods: a guest score next to a real hotel's name
  would be a made-up review. Airlines are real names shown with ONE generic aircraft icon (no
  airline marks or invented branding), with sample schedules and fares.
- **Prices are unambiguous.** Flights: "THB 6,380 total for 2 travellers" with "THB 3,190 per
  traveller" underneath. Hotels: "THB 7,690 per room, per night" and "THB 23,070 total for 3 nights,
  1 room", both "taxes included". The hotel card always shows the cheapest room that fits the guests
  AND the active filters, so turning on "Free cancellation" visibly moves the price to the flexible
  rate.
- **The conversational path**: user message -> Dory's brain interprets it -> a validated
  `search_flights` / `search_hotels` tool call (`travel_search.card_tools`) -> the shared service ->
  the web draws cards / Discord draws native components. The tools return typed results (the model
  only talks about those), answer `need_details` instead of guessing (the brain then asks ONE focused
  question and no cards are drawn), continue each person's trip ("and a hotel there for 3 nights"
  reuses the flight's city, date and travellers) and keep filters while the route / city stays the
  same. On the web (a Discord-linked company, through the headless bot) typed chat and the Live voice
  call get the same two tools next to trips.py's `book_trip`: chat draws cards, voice speaks the
  results. Every result carries a `booking_ref`; typed "book <ref>" goes to Dory, who quotes it, and a
  plain yes books it in the sandbox (references, receipts, check-in reminder; no ticket, no money).
  The fare / stay review's "Book in sandbox" books straight from the card, without the AI (below). A round
  trip draws the way back as its own flights block (`travel.return_flights`). A web-only company (no
  headless bot) gets the two searches and no `book_trip`. If the brain FAILS and
  `parse_request` still reads a trip from the message, the reply shows the cards anyway with an explicit
  "I couldn't interpret this with Dory's AI just now ..." line and Try again (`travel_fallback`);
  otherwise the usual error + Retry. Filters, Edit search and See more call `/api/travel/*`, so the
  cards keep working when the AI does not. **Discord entry points** = `/dory flights` and
  `/dory hotels`, and the same tools in chat.
- Primary visual reference = the tall single-column panel. The two-column wide layout of the second
  screenshot was not built.

## Where things live

| Part | File |
| --- | --- |
| Shared models, sample data, search logic, sessions, parser | `src/dory/travel_search.py` |
| Web API (`/api/travel/*`), its limits and error shape, the AI-down fallback line | `src/meeting_scribe/travel_api.py` |
| Card tools in the web brain, `travel` + `travel_fallback` on the reply, `travel` on the stored turn | `src/meeting_scribe/center.py` (`answer_question`, `with_card_tools`, `chat`, `ChatReply`, `Turn`) |
| Web cards, filters, edit form, reviews, states, strings (en + th) | `src/meeting_scribe/static/center.html` (`.trv` / `.tv-*`, `tv_*` keys) |
| Discord commands, Components V2 views, buttons, menus, modal | `src/dory/travel_search_bot.py` (`TravelSearchMixin`) |
| Discord strings (th + en) | `src/dory/i18n.py` (`cmd_dory*`, `discord.*`: one complete message per key) |
| Discord chat path: card tools in typed chat, cards after the answer, failure hint | `travel_search_bot.py` (`_travel_card_tools`, `_post_travel_cards`, `_travel_fail_hint`), called from `bot.py` |
| Untranslated messages, reviewed | `tests/dory/locale_gaps.json` (checked by `tests/dory/test_languages.py`) |
| Discord preview (real payloads drawn as HTML) | `scripts/dory_travel_discord_preview.py` |

Web API (POST, JSON, validated; `today` = Bangkok date): `/api/travel/flights` and `/hotels`
`{query, filters, offset, limit<=10}`, `/flights/review {query, id}`, `/hotels/rooms {query, hotel_id}`,
`/hotels/review {query, hotel_id, room_id}`, and `GET /api/travel/airports`. Bodies are bounded
(16 KB, extra fields refused, offset <= 1000, limit <= 10, list and string lengths capped).

Booking from the website's cards, no AI (`POST /api/center/orgs/{org_id}/travel/book`, signed-in
member, licence check, 30 per hour per person, errors in the same one shape with codes
`unauthorized`, `license`, `forbidden`, `invalid`, `rate_limited`, `booking_unavailable`, `travel_off`):
body `{flight_ref?, return_ref?, room_ref?, purpose? (<= 200), confirm}`, refs <= 80 characters, a
flight or a room required, a way back only with its outbound. `confirm=false` returns the quote
(`center.card_quote`: priced from the catalogue with trips.py's own `catalog_flight` /
`catalog_hotel`, WITHOUT touching book_trip's confirm gate, so asking again never books) and
remembers for 10 minutes that this person saw it. `confirm=true` books only a quote this same person
was shown (consumed: a double click or a second confirm answers the quote again,
`needs_confirmation`; another member's confirm books nothing for me): the headless bot's own
`book_trip`, built for this person exactly like the chat agent's tools (`center.web_person`, also
used by `headless_kwargs`), called as a proposal and then a confirmation (two fresh requests), so
the booking, receipts (THB, ค่าเดินทาง), trip record and check-in reminder are the chat's. The answer
carries `text`, a "Booked in the sandbox: ..." line also stored in the chat history. A company on
the website only books the same way in its web workspace (its own ledger and trip record; no
check-in reminder: nothing delivers one to a web-only person). No headless bot -> 409
`booking_unavailable`; travel turned off -> 409 `travel_off`. On the page the
review's "Book in sandbox" opens an inline step: every item picked in that reply's cards (outbound,
way back, room; the clicked one always included) as checkboxes, "What is it for?", the quote, then
"Confirm booking" -> the review shows the references and Dory posts the booked line.

Protection (public on purpose: the cards must work without sign-in and without the AI; sign-in would
not replace rate limiting): a token bucket per client IP (the last `X-Forwarded-For` entry, which
Cloud Run's front end appends, else the socket address), one for everyone, and a cap on searches
running at once. Settings (web env, all optional):

| Variable | Default | Past it |
| --- | --- | --- |
| `TRAVEL_RATE_PER_MIN` | 120 per client IP | 429 `rate_limited` + `Retry-After` |
| `TRAVEL_BURST` | 40 requests at once per client | then the rate applies |
| `TRAVEL_GLOBAL_RATE_PER_MIN` | 1200, all clients together | 429 `rate_limited` + `Retry-After` |
| `TRAVEL_MAX_CONCURRENT` | 8 searches at the same time | 503 `busy` + `Retry-After: 1` |

One error shape for every `/api/travel` error, with the sample status:
`{"error": {"code", "message", "fields"?}, "data": {...sample status}}`; codes `invalid`,
`past_date`, `too_far` (422), `not_found` (404, unknown ids and unknown paths), `too_large` (413),
`rate_limited` (429), `busy` (503), `server_error` (500). `fields` names the field and the problem,
never the input. Other routes of the app keep FastAPI's own error bodies.

Before a real provider is connected: provider credentials stay server-side (Secret Manager, never in
a response), per-provider quotas, usage monitoring and spending caps, and authentication where account
access or the provider's cost justifies it.

## Run it locally

No secrets: the cards use sample data only. The optional `TRAVEL_*` limits are listed commented in
`.env.example` ("Travel demo API"); it already lists everything else (`DORY_DISCORD_TOKEN` for the
bot, `HUB_GOOGLE_CLIENT_ID` for a real sign-in).

**Website** (mock mode needs no sign-in):

```bash
uv sync
STORE=memory uv run uvicorn meeting_scribe.app:app --port 8080
# open http://localhost:8080/center?mock=1 , open "Talk to Dory" (bottom right), and send:
#   Find a flight from Bangkok to Singapore and a hotel there for 2 people next week
```

Mock mode stands in for the brain: a message with a city and a date gets cards (with "non-stop" /
"free cancellation" pre-pressed when said), "Find me a flight" gets one question and no cards, and a
trip message containing "error" shows the AI-down fallback with Try again, "round trip" adds the way
back, typed "book <ref>" gets a canned quote ("Shall I book it?") that a "yes" turns into a canned
sandbox booking, and the cards' "Book in sandbox" uses a mock `/travel/book` (the quote priced through
the real public `/api/travel` reviews, a confirm only after a quote, sample references). Signed in for real
(`/center`), the message goes through Dory's brain and its search tools; the cards come back after a
reload (the search, not the reviews, is stored with the turn).

**Discord** (needs the bot's token and a test server; the bot was never run for this prototype):
start the bot as usual (`uv run python -m dory`), wait for the global commands to sync, then run
`/dory flights from:BKK to:SIN travellers:2` or `/dory hotels city:SIN`. Replies are visible only to
the person who asked. In chat, "@Dory non-stop flights Bangkok to Singapore next Tuesday for 2" makes
the brain call `search_flights`; the answer is followed by the same results message, posted in the
channel, whose buttons only work for the person who asked (anyone else gets "This search belongs to
someone else or has expired. Start your own with /dory flights or /dory hotels."). Typed chat and
voice rooms get the SAME `search_flights` / `search_hotels` next to `book_trip` (chat draws cards,
voice speaks). Booking straight from the cards (no brain): selecting a flight or choosing a room
records it as the person's pick (`Trips.pick`: flight / way back / room); "Book in sandbox" on the
fare or stay review answers with a NEW ephemeral quote for all their picks (priced from the
catalogue by `by_booking_ref`; a "What to book" menu when there is more than one; Confirm booking /
Cancel; never on a public card). Confirm booking calls `book_trip` as the person (a quote, then a
new request that books; one call when the chat already quoted the same refs), shows the references,
total, receipts and check-in reminder, and clears the booked picks; Cancel keeps them; anyone else's
click gets the expired / not-yours line. Typing "book <ref>" (the review shows the ref) then a plain
"yes" still books through the brain. When the brain fails on a trip request, the apology adds
"You can still search with /dory flights or /dory hotels." The server's `travel` feature flag (on by
default) must stay on.

**Discord preview without Discord:**

```bash
uv run python scripts/dory_travel_discord_preview.py --out /tmp/dory-discord --png
```

## Weather cards (web)

A chat reply whose brain called the `weather` tool carries `travel.weather = {kind, place, lat, lng, days}` (flights and
hotels may be null). The page draws one forecast card next to the travel cards (floating panel and `#/chat`, live
replies and history) and fetches the card itself, fresh, from `POST /api/travel/weather`
`{place, lat, lng, days: 3|5, lang?}`: the same public router and protection as the searches (`guard`, bounded body,
`extra="forbid"`), coordinates rounded to 2 decimals (about 1 km) before `dory.weather.weather_card`, answer
`{card, data: {kind: "forecast", estimate: true, source, credit}}`. Errors keep the router's one shape (their `data` is
still the sample-travel status): `weather_off` 503 (`DORY_WEATHER_PROVIDER=off`), `weather_unavailable` 503 (the source
is down; no raw error). The card: place + its local time, now (temperature, condition in words + icon, feels like,
humidity, wind, rain chance), a 3 / 5 day toggle, one row per day, the travel tip, "Forecast · estimate", the source's
credit (Open-Meteo is CC BY 4.0: the credit is visible and links to https://open-meteo.com/), Refresh, a skeleton at
the card's size, an error line with Try again, an offline line. It never shows the sample-travel note. A Thai page
shows the icon's Thai name when the source's condition text is English (Open-Meteo's always is). Mock (`?mock=1`): a
message with "weather" gets a weather card (with "flight" too: both), the card's fetch is a canned forecast (no
network), "weather error" makes that fetch fail once.

## Tests

```bash
uv run pytest -q tests/dory/test_travel_search.py      # shared logic: prices, filters, pages, selection, isolation, parser
uv run pytest -q tests/test_travel_api.py tests/dory/test_travel_chat.py tests/test_center_page.py
uv run pytest -q tests/dory/test_travel_search_bot.py  # Discord payloads, limits, paging, owner isolation, modal errors, chat cards
uv run pytest -q tests/dory/test_languages.py          # per-message translation coverage + the reviewed gaps list
# browser: Playwright + axe WCAG 2.2 AA, 320 px overflow check (install chromium once)
uvx --from 'uv>=0.10' uv run --no-sync playwright install chromium
uvx --from 'uv>=0.10' uv run --no-sync pytest -m e2e tests/e2e/test_travel_smoke.py tests/e2e/test_weather_smoke.py
uv run pytest -q tests/dory/test_trips.py              # booking: refs, round trip, receipts, reminder, approvals, plain yes (chat + voice)
# LIVE probe (billed, Token Factory key from .env; every call metered by tests/dory/live_budget.py):
PROBE_DRY=1 uv run pytest -m live -s "tests/dory/test_travel_live_probe.py::test_web_flow[sqlite]" tests/dory/test_travel_live_probe.py::test_discord_flow   # free size estimate
uv run pytest -m live -s "tests/dory/test_travel_live_probe.py::test_web_flow[sqlite]" tests/dory/test_travel_live_probe.py::test_discord_flow           # <= $2 (PROBE_CAP_USD)
```

## Discord: verified limits and the compromises they forced

Checked on 29 Oct 2026 against Discord's docs ([components reference](https://discord.com/developers/docs/components/reference),
[receiving and responding](https://discord.com/developers/docs/interactions/receiving-and-responding),
[messages](https://discord.com/developers/docs/resources/message)) and the installed discord.py 2.7.1.

| Limit | Value | Our use |
| --- | --- | --- |
| Components per Components V2 message (nested count) | 40 | flight page 25-26, hotel page 23, reviews 6-12 |
| Text across text displays (discord.py `LayoutView.content_length`) | 4,000 | about 1,100-1,400 per page |
| Action row | 5 buttons or 1 select | Previous / Next / Edit search / Clear filters; one menu per row |
| Select options / max values | 25 / 25 | stops + times, airlines, sort, price steps |
| `custom_id` | 100 chars | `dory:trv:<act>:<session>[:<id>]`, about 45 |
| Modal: title / components / label | 45 / 5 / 45 | exactly 5 inputs per modal |
| First response / interaction token | 3 s / 15 min | defer at once; edits within the token |
| V2 flag | no `content` or `embeds` | Components V2 only, no embeds |

Compromises: max price is a menu, not a modal field (the modal is full at 5 inputs); "Page 1 of 4" is
text, not a disabled button; closed menus show the chosen option, so sort and price options carry the
menu's name ("Sort by: Cheapest"); the edit modal uses text inputs (airport codes are typed); all
views use `timeout=None` because a timed-out view un-registers the dynamic item patterns other
searches still need. A click after a restart, after 30 minutes, or by someone else gets one line:
"This search belongs to someone else or has expired. Start your own with /dory flights or /dory hotels."
Every message says "Demo results—not live availability or a confirmed booking."; each flight card
"Sample itinerary · Sample price"; each hotel card "Fictional property · Sample rating and reviews".
No airline logos or branding, names only.

## Limitations and production follow-ups

- **Sample data only.** A real provider plugs in at `travel_search.flight_offers` /
  `hotel_offers`: map Duffel / LiteAPI offers (already wrapped in `trips.py` for the voice demo) into
  the same dicts and keep the ids stable. Since 29 Oct 2026 the catalogue is the ONLY search the
  agent has (trips.py's own `search_flights` / `search_hotels` are gone), so the Duffel test-mode and
  LiteAPI sandbox searches are not reachable from Dory until such an adapter exists; their provider
  code and `trips.SampleProvider` (which books the catalogue's offers) stay.
- **`/api/travel` is public, protected by the limits above.** The buckets and the concurrency cap are
  per process (Cloud Run instance); several instances multiply the global numbers. Before a real
  provider: credentials server-side, quotas, usage monitoring, spending controls, and auth where
  account access or cost justifies it.
- **Sandbox booking only.** Every search result carries a `booking_ref` (flight:
  `BKKSIN.SL106-20261110-E.2` = route, flight, date, cabin, travellers; room:
  `SIN.harbourlight.deluxe-king.20261110.3.1.2` = city, hotel, room, check-in, nights, rooms, guests).
  `book_trip` re-prices the ref from the catalogue (a model cannot change a price by retyping it),
  quotes it, books only after the person's later "yes" (a plain yes right after the quote is booked
  by code), through `trips.SampleProvider`: a hash reference, no ticket, no money; receipts go to the
  ledger (ค่าเดินทาง) and a check-in reminder is set. A round trip = the way back's ref as
  `return_flight_offer_id`, booked as one flight. A ref names a public sample fare, so anyone may book
  it for themselves; search state stays per person. The web-only path (no headless bot) can search
  but has no `book_trip`. A real flow still needs traveller details, live re-pricing, payment and
  the approval step (`approvals.py`).
- **Varied wording, not every wording.** The brain interprets the message; how well depends on the
  model. Live probe 29 Oct 2026 (`tests/dory/test_travel_live_probe.py`, GLM-5.3 on Token Factory,
  synthetic data, $0.80 metered of a $2 cap): website and Discord both searched, quoted, booked on a
  plain yes and asked a clarifying question with no tool call; no invented prices; one wording slip
  ("AirAsia" for Thai AirAsia) on the full ~140-tool list. The flows ran with only the `travel`
  feature on (about 30K prompt tokens a call instead of about 76K) to fit the cap. The keyword parser only serves
  the AI-down fallback. Web trips (`center.TRIPS`, owner `web:<email>`) and the bot's trips live in
  process memory: a restart forgets the current trip.
- Web reviews are not stored in chat history (the search cards are). Discord sessions live in process
  memory (one bot process, like `recent.py`); a restart expires every search, and a modal submitted
  after a restart fails.
- **Translations.** Every Discord string is one complete catalog message with named placeholders
  (`discord.flight.priceTotal`: "THB {total} total for {count} travellers (THB {each} per traveller),
  taxes included", with a separate singular message where grammar needs one; dates are whole-date
  messages filled from weekday / month name messages). The coverage test is per message: a
  translatable message with no (or an empty) translation in a second-tier locale fails by name unless
  it is listed in `tests/dory/locale_gaps.json`, and a listed message that is translated everywhere
  (or gone) fails as stale. The gaps list is empty since 29 Oct 2026: the 176 gaps of the
  refactor (167 travel + 9 older voice / trip-booking messages) were translated into all seven
  locales by Claude (one translator per language, the script's own style rules), checked with the
  script's `valid()` (placeholders, "Dory"), written with its `sha()` source hashes and file layout,
  and the pricing, cancellation, sample-label and error messages were reviewed by hand. The
  Vertex run (`env -u GOOGLE_APPLICATION_CREDENTIALS GOOGLE_CLOUD_QUOTA_PROJECT=meeting-scribe-hackathon
  uv run python scripts/dory_translate_catalog.py --only-missing`) got 403 for the signed-in
  account, nothing billed. Note: the script reads `CATALOG` without importing the feature modules,
  so messages a module registers on import (`trips.py`'s `trip_*`) are invisible to it; the
  coverage test imports every module and catches them. `test_every_view_of_the_journey_fits_discord`
  renders every view and the edit form in all nine languages against Discord's limits. No existing
  translation had the same meaning to reuse except the "Date" field name (`pdf_date`). In the edit
  form people still type the cabin as economy / business (or the Thai words): the parser accepts
  only those, and every translation says so.
- Not verified on real Discord: rendering, the edit-original-response after a defer for a V2 message,
  and menus with `min_values=0`. Only the docs and the library's serialization were checked.
- Not built: the wide two-column layout, hotel photos (an inline SVG placeholder tinted per hotel is
  drawn instead), real airline logos, multi-city or return flights.
