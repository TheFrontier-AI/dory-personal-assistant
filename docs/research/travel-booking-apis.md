# Flight + hotel booking sandboxes for the voice demo (researched 27 Oct 2026)

> **Update 28 Oct 2026: Amadeus is gone.** developers.amadeus.com now says "Amadeus for Developers
> self-service portal has been decommissioned on July 17th, this website is for Amadeus Enterprise API
> Portal only", and `test.api.amadeus.com` has no DNS record. Enterprise access is by request, not free.
> `trips.py` now uses only free sandboxes, each checked on its live site that day: **Duffel test mode**
> for flights ("use the Duffel API risk-free, with no danger of spending any money", tokens
> `duffel_test_...`; Duffel Stays needs an access request, so it is not used for hotels) and the
> **LiteAPI (Nuitee Connect) sandbox** for hotels ("Every account has free access to a sandbox key",
> "No credit card is required", bookings paid with the simulated `ACC_CREDIT_CARD`). The comparison
> below is the 27 Oct research and is out of date where it recommends Amadeus.

Goal: a Python 3.12 / `httpx` voice assistant that can **search flights, price one, book it (sandbox
order with a confirmation code), search a hotel and book it**, with results that look real on stage
(BKK → SIN / HKG / TYO, hotel in Singapore). No money, no real tickets. Demo 30 Oct 2026.

## Recommendation

**Primary: Amadeus for Developers, Self-Service *test* environment.** Key in minutes (register,
activate the email, "Create New App" gives API key + secret, test environment by default). Real
airline codes, real airports and real-looking fares in THB (`currencyCode=THB`); `Flight Create
Orders` returns an order id **and a PNR** (`associatedRecords[].reference`), `Hotel Booking v2`
returns a `confirmationNumber` + PNR. Free monthly quota, nothing to pay. Downside: test data is a
limited cached copy; the docs only promise "most origin and destination cities/airports" for flights
and name LON / NYC for hotels. **BKK→SIN and SIN hotels are not documented as covered: run the probe
in section 5 on the day you get the key.**

**Fallback: Duffel test mode.** Account in about a minute, token `duffel_test_...` from the
dashboard, same five calls, bookings always succeed thanks to the built-in airline "Duffel Airways"
(IATA `ZZ`) and the "Duffel Test Hotel". Downside, in Duffel's own words: "you won't see realistic
flight schedules or prices" in test mode, and the test hotels sit at fake coordinates in the
Pacific. Use it if Amadeus test inventory is empty or exhausted; use the in-code fake (section 6)
if both are down.

Everything else (SerpApi, Travelpayouts, Booking.com, Kiwi) is read-only, partner-gated or closed.

## Comparison

| | Amadeus Self-Service (test) | Duffel (test mode) | SerpApi Google Flights | Travelpayouts | Booking.com Demand API | Kiwi.com Tequila |
|---|---|---|---|---|---|---|
| Key in | minutes (email activation + create app) | about 1 minute (sign up, create test token) | minutes | Data API: minutes; live Flight Search: 50,000 MAU required | contract via account manager, no self-serve | self-serve closed 2024, B2B channel only (third-party report) |
| Auth | OAuth2 client_credentials → Bearer, token expires (`expires_in`) | static Bearer token + `Duffel-Version: v2` | `api_key` query param | token | API key + `X-Affiliate-Id` | n/a |
| Search flights | `GET /v2/shopping/flight-offers` | `POST /air/offer_requests` | `engine=google_flights` (real data) | cached prices only | no | n/a |
| Price / confirm | `POST /v1/shopping/flight-offers/pricing` | `GET /air/offers/{id}` | no | no | no | n/a |
| Book flight → code | `POST /v1/booking/flight-orders` → order id + PNR | `POST /air/orders` → `ord_…` + `booking_reference` | no | no | no | n/a |
| Hotels | list by city → offers v3 → `POST /v2/booking/hotel-orders` → confirmation + PNR | `/stays/search` → rates → quote → `/stays/bookings` → `bok_…` + `reference` | Google Hotels engine, read-only | no | accommodation (contract) | n/a |
| Looks real | real carriers / airports / fares (cached) | fake `ZZ` airline, unrealistic times & prices | real | real but stale | real | n/a |
| Test coverage | "most cities/airports" (flights); LON/NYC named for hotels; BKK/SIN unverified | any route gets ZZ offers; test hotels only at lat -24.38, lng -128.32 | any route | n/a | sandbox after contract | n/a |
| Limits | 10 TPS, 1 req / 100 ms, free monthly quota then 429 | 60 requests per 60 s window (subject to change), 429 `rate_limit_exceeded` | free: 250 searches/month, 50/hour | n/a | n/a | n/a |
| Cost | free in test | free in test; live: $3/order + 1% managed content + excess-search fee | $0 free plan | free | contract | n/a |

## Amadeus test environment: the five calls with `httpx`

Base URL `https://test.api.amadeus.com`. Rate limit 10 TPS and at least 100 ms between calls; the
monthly free quota is per account and a 429 means it is used up. POST bodies use
`Content-Type: application/vnd.amadeus+json` (what the spec declares and the SDKs send).

### Auth

```python
import time, httpx

BASE = "https://test.api.amadeus.com"
_tok: dict = {}


def token(client_id: str, client_secret: str) -> str:
    if _tok and _tok["exp"] > time.time() + 60:
        return _tok["t"]
    r = httpx.post(
        f"{BASE}/v1/security/oauth2/token",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
        },
        timeout=20,
    )
    r.raise_for_status()
    j = r.json()  # {"access_token", "expires_in", ...}
    _tok.update(t=j["access_token"], exp=time.time() + j["expires_in"])
    return _tok["t"]


def api(tok: str) -> httpx.Client:
    return httpx.Client(
        base_url=BASE,
        timeout=40,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/vnd.amadeus+json"},
    )
```

### 1. Search flights (Flight Offers Search v2)

```python
r = c.get(
    "/v2/shopping/flight-offers",
    params={
        "originLocationCode": "BKK",
        "destinationLocationCode": "SIN",
        "departureDate": "2026-11-12",
        "adults": 1,
        "currencyCode": "THB",
        "max": 5,
    },
)
offers = r.json()["data"]  # [] when the cached test data has nothing
o = offers[0]
# read: o["id"], o["price"]["grandTotal"], o["price"]["currency"],
#       o["validatingAirlineCodes"][0], o["numberOfBookableSeats"],
#       seg = o["itineraries"][0]["segments"][0]
#       seg["carrierCode"], seg["number"], seg["departure"]["iataCode"], seg["departure"]["at"],
#       seg["arrival"]["iataCode"], seg["arrival"]["at"], o["itineraries"][0]["duration"]
# r.json()["dictionaries"]["carriers"]["TG"] -> "THAI AIRWAYS INTERNATIONAL" (airline names)
```

### 2. Price / confirm (Flight Offers Price v1)

```python
r = c.post(
    "/v1/shopping/flight-offers/pricing",
    headers={"X-HTTP-Method-Override": "GET"},  # required header per the spec
    json={"data": {"type": "flight-offers-pricing", "flightOffers": [o]}},
)
priced = r.json()["data"]["flightOffers"][0]  # same shape, final price
# read: priced["price"]["grandTotal"]; keep the WHOLE priced object for the order
```

### 3. Book (Flight Create Orders v1) — sandbox PNR

```python
traveler = {
    "id": "1",
    "dateOfBirth": "1990-03-14",
    "name": {"firstName": "SOMCHAI", "lastName": "JAIDEE"},
    "gender": "MALE",
    "contact": {
        "emailAddress": "somchai@example.com",
        "phones": [{"deviceType": "MOBILE", "countryCallingCode": "66", "number": "812345678"}],
    },
    "documents": [
        {
            "documentType": "PASSPORT",
            "number": "AA1234567",
            "expiryDate": "2031-01-01",
            "issuanceCountry": "TH",
            "nationality": "TH",
            "holder": True,
        }
    ],
}
r = c.post(
    "/v1/booking/flight-orders",
    json={"data": {"type": "flight-order", "flightOffers": [priced], "travelers": [traveler]}},
)
order = r.json()["data"]
# read: order["id"] (temporary in test), order["associatedRecords"][0]["reference"] -> PNR "2ZYVAL"
```

No payment block: Self-Service never takes payment in this API (a form of payment is rejected with
INVALID FORMAT), which is exactly what a no-money demo wants.

### 4. Search hotels (Hotel List v1 → Hotel Search v3)

```python
r = c.get(
    "/v1/reference-data/locations/hotels/by-city",
    params={"cityCode": "SIN", "radius": 5, "radiusUnit": "KM"},
)
hotel_ids = [h["hotelId"] for h in r.json()["data"]][:20]  # also h["name"], h["geoCode"]
r = c.get(
    "/v3/shopping/hotel-offers",
    params={
        "hotelIds": ",".join(hotel_ids),
        "adults": 1,
        "checkInDate": "2026-11-12",
        "checkOutDate": "2026-11-14",
        "roomQuantity": 1,
        "currency": "SGD",
    },
)
stays = [h for h in r.json()["data"] if h.get("available")]
h = stays[0]
offer = h["offers"][0]
# read: h["hotel"]["name"], h["hotel"]["hotelId"], offer["id"], offer["price"]["total"],
#       offer["price"]["currency"], offer["room"]["description"]["text"],
#       offer["policies"]["cancellations"][0].get("deadline")
```

### 5. Book hotel (Hotel Booking v2)

```python
r = c.post(
    "/v2/booking/hotel-orders",
    json={
        "data": {
            "type": "hotel-order",
            "guests": [
                {
                    "tid": 1,
                    "title": "MR",
                    "firstName": "SOMCHAI",
                    "lastName": "JAIDEE",
                    "phone": "+66812345678",
                    "email": "somchai@example.com",
                }
            ],
            "travelAgent": {"contact": {"email": "somchai@example.com"}},
            "roomAssociations": [
                {"guestReferences": [{"guestReference": "1"}], "hotelOfferId": offer["id"]}
            ],
            "payment": {
                "method": "CREDIT_CARD",
                "paymentCard": {
                    "paymentCardInfo": {
                        "vendorCode": "VI",
                        "cardNumber": "4151289722471370",  # test card from the spec example
                        "expiryDate": "2030-08",
                        "holderName": "SOMCHAI JAIDEE",
                    }
                },
            },
        }
    },
)
ho = r.json()["data"]
# read: ho["id"], ho["hotelBookings"][0]["bookingStatus"] ("CONFIRMED"),
#       ho["hotelBookings"][0]["hotelProviderInformation"][0]["confirmationNumber"],
#       ho["associatedRecords"][0]["reference"] (PNR, e.g. "WH6TRZ")
```

### Amadeus gotchas (all from the official docs)

- Test data is a cached, limited copy "as a security measure"; flights: "most origin and destination
  cities/airports"; hotels: "content comes directly from the hotel providers … use big cities like
  LON or NYC", some chains "might not be accessible in test environment".
- Hotel Booking v2 takes `hotelOfferId` = `offers[].id` from **Hotel Search v3** (`OFFER NOT FOUND`
  38420 otherwise). `POST /v1/booking/hotel-bookings` (`offerId`, `payments`, `rooms`) is the older v1.
- Flight Offers Price needs `X-HTTP-Method-Override` (spec marks it required, default `GET`).
- Test inventory is shared: booking many seats empties it → 400 `SEGMENT SELL FAILURE` (34651).
  Price moved → 400 `PRICE DISCREPANCY` (37200): re-run step 2 then book again.
- Order ids from Flight Create Orders are temporary in test; LCCs and American Airlines never appear,
  British Airways depends on market; only published fares.
- Hotel booking in test is forwarded to each provider: 500s / timeouts happen ("if many requests are
  sent to a particular hotel, they may choose to block them"). Retry once, then fall back.
- Quota exhausted → 429 for the rest of the month. Keep the demo rehearsal count small and cache
  search results in memory during the show.

## Duffel test mode: the five calls, condensed (fallback)

Headers on every call: `Authorization: Bearer duffel_test_…`, `Duffel-Version: v2`,
`Accept: application/json`, `Content-Type: application/json`. Base `https://api.duffel.com`.
Search can take up to 20 s (`supplier_timeout` 2–60 s), order creation up to 120 s: set the client
timeout to 130 s. 60 requests per 60 s window.

```python
d = httpx.Client(
    base_url="https://api.duffel.com",
    timeout=130,
    headers={
        "Authorization": f"Bearer {DUFFEL_TEST_TOKEN}",
        "Duffel-Version": "v2",
        "Accept": "application/json",
        "Content-Type": "application/json",
    },
)
# 1 search
req = d.post(
    "/air/offer_requests",
    params={"return_offers": "true", "supplier_timeout": 10000},
    json={
        "data": {
            "slices": [{"origin": "BKK", "destination": "SIN", "departure_date": "2026-11-12"}],
            "passengers": [{"type": "adult"}],
            "cabin_class": "economy",
        }
    },
).json()["data"]
pax_id = req["passengers"][0]["id"]
off = req["offers"][0]
# read: off["id"], off["total_amount"], off["total_currency"], off["owner"]["iata_code"] ("ZZ"),
#       s = off["slices"][0]["segments"][0]: s["departing_at"], s["arriving_at"],
#       s["origin"]["iata_code"], s["destination"]["iata_code"],
#       s["marketing_carrier"]["iata_code"], s["marketing_carrier_flight_number"]
# 2 price = refresh the offer (offers expire)
off = d.get(f"/air/offers/{off['id']}").json()["data"]
# 3 book
order = d.post(
    "/air/orders",
    json={
        "data": {
            "type": "instant",
            "selected_offers": [off["id"]],
            "payments": [
                {
                    "type": "balance",
                    "currency": off["total_currency"],
                    "amount": off["total_amount"],
                }
            ],
            "passengers": [
                {
                    "id": pax_id,
                    "title": "mr",
                    "gender": "m",
                    "given_name": "Somchai",
                    "family_name": "Jaidee",
                    "born_on": "1990-03-14",
                    "email": "somchai@example.com",
                    "phone_number": "+66812345678",
                }
            ],
        }
    },
).json()["data"]
# read: order["id"] ("ord_…"), order["booking_reference"] (e.g. "RZPNX8")
# 4 hotels: test hotels ONLY at these coordinates in test mode
res = d.post(
    "/stays/search",
    json={
        "data": {
            "location": {
                "radius": 2,
                "geographic_coordinates": {"latitude": -24.38, "longitude": -128.32},
            },
            "check_in_date": "2026-11-12",
            "check_out_date": "2026-11-14",
            "guests": [{"type": "adult"}],
            "rooms": 1,
        }
    },
).json()["data"]["results"]
sr = res[0]  # sr["id"] "srr_…", sr["accommodation"]["name"], sr["cheapest_rate_total_amount"]
rates = d.post(f"/stays/search_results/{sr['id']}/actions/fetch_all_rates").json()["data"]
rate_id = rates["accommodation"]["rooms"][0]["rates"][0]["id"]  # "rat_…"
quote = d.post("/stays/quotes", json={"data": {"rate_id": rate_id}}).json()["data"]  # "quo_…"
# 5 book (payment omitted = pay with balance)
bk = d.post(
    "/stays/bookings",
    json={
        "data": {
            "quote_id": quote["id"],
            "email": "somchai@example.com",
            "phone_number": "+66812345678",
            "guests": [{"given_name": "Somchai", "family_name": "Jaidee"}],
        }
    },
).json()["data"]
# read: bk["id"] ("bok_…"), bk["reference"] (e.g. "AFE33SE2"), bk["status"] ("confirmed")
```

Duffel gotchas: every test search returns Duffel Airways (`ZZ`) offers, reliable but "you won't see
realistic flight schedules or prices"; real-airline sandboxes may also appear and may be down or
"used up". Reserved test routes change behaviour (LHR→LGW order error, LGW→STN insufficient balance,
STN→LHR timeout, PVD→RAI no flights, JFK→EWR hold orders, LHR→DXB connecting, DXB→AMS stops,
LTN/SEN→STN 200/202 card responses): never use them in the demo. Passenger ids come from the offer
request. The Stays guide lists "Request access to Duffel Stays" (contact form) as a prerequisite:
check the dashboard on day one; if Stays is not enabled, hotels come from the fake provider.
Live mode would cost $3 per confirmed order; test mode is free.

## Test routes and cities known to return data

Documented or used in official material (nothing in the docs names BKK, SIN, HKG or TYO):

- Flights: MAD→BCN (developer guide), SYD→BKK (Python and Node SDK READMEs, Flight Offers Search +
  Price + seat map), BOS origin (Flight Cheapest Date Search), AF/BA/IB/AZ carriers in examples.
- Hotels: hotel ids `HLPAR266` (Hilton Paris Opera), `RTPAR001`, `ACPARF58` (guides, PAR),
  `ARMADAIT` (AC by Marriott Aitana, Hotel Booking v2 spec example, MAD); LON / NYC are the cities the
  test-data page tells you to use; Hotel Ratings covers 10 London + 14 New York hotels.
- Duffel: any route gets `ZZ` offers; hotels only at lat -24.38, lng -128.32.

Probe to run the moment the Amadeus key exists (one call per line, 150 ms apart, print counts only):
`BKK→SIN`, `BKK→HKG`, `BKK→NRT`, `BKK→HND` for a date 2–4 weeks out with `currencyCode=THB`, then
`hotels/by-city?cityCode=SIN` and `hotel-offers` for the first 20 ids. Any route or city that returns
`[]` is served by the fake provider on stage; a `SEGMENT SELL FAILURE` means that itinerary's test
inventory is gone, pick the next offer.

## Fallback fake provider (in code, deterministic)

Same return shape as the real adapter (a small pydantic `FlightOffer` / `HotelOffer` / `Booking`),
selected by `TRAVEL_PROVIDER=fake` and used automatically when the sandbox raises, times out
(flights > 25 s, hotels > 25 s) or returns an empty list. Confirmation codes are derived, not random
(`hashlib.sha256(f"{route}{date}{name}").hexdigest()` → 6 chars from `ABCDEFGHJKLMNPQRSTUVWXYZ23456789`
for a PNR, 8 digits for a hotel confirmation), so a re-run shows the same code. Timings and prices
below are illustrative (plausible for late 2026, not live fares); label them "sample" in logs only,
never on stage.

| Route | Flights (local times) | One-way economy, THB |
|---|---|---|
| BKK→SIN 2 h 25 m | TG403 08:00→11:25, TG409 14:10→17:35, SQ705 09:40→13:05, SQ711 15:30→18:55, SQ713 20:10→23:35 | TG 6,850 / 7,900; SQ 7,450 / 8,600 / 9,200 |
| BKK→HKG 2 h 55 m | TG600 08:00→11:55, CX700 09:05→12:55, TG628 13:40→17:35 | 8,400 / 9,100 / 9,750 |
| BKK→NRT 6 h 20 m | TG640 23:50→07:30+1, JL708 09:00→17:05, TG676 08:00→15:50 | 14,900 / 17,200 / 18,500 |

Return legs mirror these (SIN→BKK SQ706 / TG404). Seats: 9 bookable, cabin `ECONOMY`, 1 checked bag.

Singapore hotels near Marina Bay (nightly, SGD, room only, free cancellation until 48 h before):

| Hotel | Area | Room | SGD / night |
|---|---|---|---|
| Marina Bay Sands | Bayfront Ave | Deluxe Room, City View | 689 |
| The Fullerton Hotel Singapore | Fullerton Square | Courtyard Room | 455 |
| PARKROYAL COLLECTION Marina Bay | Raffles Blvd | Garden Room | 338 |

A fake booking returns `status="CONFIRMED"`, the PNR / confirmation code, the total in THB (flights)
or SGD (hotel) and `provider="sample"` so the UI can keep the same card layout as the live path.

## Sources

- Amadeus test data: https://developers.amadeus.com/self-service/apis-docs/guides/developer-guides/test-data/ (source markdown: https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/test-data.md)
- Amadeus data collection (test env): https://github.com/amadeus4dev/data-collection (README, `data/hotelchains.md`, `data/hotelratings.md`)
- Amadeus quick start (sign-up, keys): https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/quick-start.md
- Amadeus authorization: https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/API-Keys/authorization.md
- Amadeus rate limits: https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/api-rate-limits.md
- Amadeus pricing / FAQ (quota, 429, limited data, hotel 500s): https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/pricing.md and https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/faq.md
- Amadeus flights guide (booking flow, errors 34651 / 37200, carrier notes): https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/resources/flights.md
- Amadeus hotels guide (hotel list → v3 offers → booking): https://raw.githubusercontent.com/amadeus4dev/developer-guides/master/docs/resources/hotels.md
- Amadeus OpenAPI specs (bodies and examples): https://github.com/amadeus4dev/amadeus-open-api-specification/tree/main/spec/json (`FlightOffersSearch_v2`, `FlightOffersPrice_v1`, `FlightCreateOrders_v1`, `HotelSearch_v3`, `HotelBooking_v2`)
- Amadeus SDK READMEs (temporary order id, SYD→BKK example, hotel_orders v2): https://raw.githubusercontent.com/amadeus4dev/amadeus-python/master/README.rst and https://cdn.jsdelivr.net/npm/amadeus@11.0.0/README.md
- Duffel test mode (Duffel Airways `ZZ`, test tokens, test cards): https://duffel.com/docs/api/overview/test-mode
- Duffel test your integration (reserved test routes): https://duffel.com/docs/api/overview/test-your-integration
- Duffel making requests (Bearer, `Duffel-Version`): https://duffel.com/docs/api/overview/making-requests
- Duffel response handling (rate limit 60 per 60 s, 429): https://duffel.com/docs/api/overview/response-handling
- Duffel response times (20 s search, 120 s orders): https://duffel.com/docs/api/overview/response-times
- Duffel flights guide and API: https://duffel.com/docs/guides/getting-started-with-flights, https://duffel.com/docs/api/v2/offer-requests, https://duffel.com/docs/api/v2/orders
- Duffel Stays guide ("Request access to Duffel Stays"), search, rates, quotes, bookings, test hotels: https://duffel.com/docs/guides/getting-started-with-stays, https://duffel.com/docs/guides/searching-for-stays, https://duffel.com/docs/api/v2/search/stays-search, https://duffel.com/docs/api/v2/search-result/fetch-all-rates, https://duffel.com/docs/api/v2/quotes/create-quote, https://duffel.com/docs/api/v2/bookings/create-booking, https://duffel.com/docs/guides/test-hotels
- Duffel pricing ($3 per order, 1 %, excess search): https://duffel.com/pricing
- SerpApi Google Flights API and pricing (free 250/month): https://serpapi.com/google-flights-api, https://serpapi.com/pricing
- Travelpayouts API access rules (Data API free; live search needs 50,000 MAU): https://support.travelpayouts.com/hc/en-us/articles/203956083-Requirements-for-Aviasales-data-API-access, https://support.travelpayouts.com/hc/en-us/articles/20384016664594-Brands-that-provide-access-to-APIs-and-data-feeds-for-Travelpayouts-partners
- Booking.com Demand API prerequisites (Managed Affiliate Partner, contract): https://developers.booking.com/demand/docs/getting-started/prerequisites
- Kiwi.com Tequila status (third-party: self-serve closed in 2024, B2B only): https://www.vervotech.com/hub/integrations/tequila-api/ ; portal https://tequila.kiwi.com/
