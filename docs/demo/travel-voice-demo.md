# Dory books the trip — live voice demo (Nebius x NVIDIA Global AI Hackathon)

For the presenter. Two surfaces, one brain: the website call at https://dory.frontier-tech.app/center
and the Discord voice room of the test server "The Frontier Company Limited". English first.
Stack on the day: brain GLM-5.3 on Nebius Token Factory (tool calling), receipt images Nemotron 3.5
Super VL, voice = ASR -> brain -> TTS cascade on a Nebius GPU VM, bookings in free sandboxes
(Duffel test mode for flights, LiteAPI sandbox for hotels: no real tickets, no money; Amadeus
Self-Service was decommissioned on 17 July 2026). Flight and hotel numbers below are from a rehearsal;
whatever the sandbox returns on the day is fine, Dory reads it out.

## 1. Pitch and the three wow moments

Dory is the AI coworker who already sits in the team's chat and knows the company: its calendar, its
travel policy, its people, its ledger. So "book my trip for the Lumen kickoff" needs no dates, no city,
no seat preference and no form. She finds the meeting, applies the policy, asks the boss with one button
when a choice is out of policy, books in two spoken steps, files the e-receipt, sets the check-in
reminder and puts the trip in tomorrow's brief. All of it by voice, on the web and in Discord.

1. **One sentence, zero questions.** "Book my trip for the Lumen kickoff" -> Dory reads the company
   calendar and the travel profile and comes back with one in-policy flight, window seat, vegetarian meal.
2. **The boss approves live, by button.** The hotel at Marina Bay is SGD 118 a night over the Singapore cap.
   Dory names the cap, sends Prae an Approve / Decline card in Discord, Prae taps on a phone, Dory books.
3. **The loop closes without typing.** In the team's voice room: who else is going (Boom, same flight), a
   task card to Boom (he taps Accept), a receipt photo filed by Nemotron VL, "what did we spend on
   travel this month", check-in reminder, tomorrow's brief.

## 2. Cast, seed data and build gates

Fictional people (never real names). Second presenter plays Prae with a phone; a third plays Boom, or
the main presenter switches Discord accounts on the laptop.

| Person | Role in the story | Discord | Private Dory channel |
| --- | --- | --- | --- |
| Mint Srisuwan | Head of Partnerships, the traveller (web + voice room) | member, role `Partnerships` | `dory-mint` |
| Prae Thongdee | COO, Mint's line manager, the approver (phone) | Administrator role `COO` (executive) | `dory-prae` |
| Boom Rattanakul | Sales, colleague already booked on the same trip (voice room) | member, role `Sales` | `dory-boom` |
| Lumen Logistics Pte Ltd | the Singapore partner (fictional company), office at Marina Bay | glossary entry | |

Trip: Lumen partner kickoff, Thu 13 Nov 2026 10:00-12:00 SGT on-site. Out BKK -> SIN Wed 12 Nov morning,
back Fri 14 Nov, two nights. BKK-SIN is 2 h 25 -> economy by policy. Hotel cap Singapore SGD 220.

### Seed checklist (D-1, demo server; run the same list in the rehearsal server first)

Type each line in the named channel. Admin items apply at once (`teach_company`); verify with the
read-back query. Tick every box the evening before.

- [ ] Hub `/hub` -> server settings: company language **English**, language mode **company only**
      (all-English mode), `voice_meetings` + `auto_join_meetings` on, `approvals`, `reminders`,
      `briefings`, `company_learning`, `task_handshake` (mode notify), `memory`, `receipts`, `search` on;
      `wake_policy` natural. Every member's web language = en.
- [ ] Prae in `dory-prae`: `Dory, add a company rule: Travel policy: economy class on flights under 5 hours.
      Business class only over 5 hours and only with the line manager's approval.`
- [ ] Prae: `Dory, add a company rule: Hotel caps per night: Singapore SGD 220, Tokyo JPY 25,000, Thailand
      domestic THB 2,500. Anything above a cap needs the line manager's approval before booking.`
- [ ] Prae: `Dory, add a company rule: Travel is booked through Dory. The e-receipt is filed to the expense
      ledger under Travel with the meeting it is for, and the traveller gets an online check-in reminder.`
- [ ] Prae: `Dory, add to the glossary: Lumen (also heard as Loomin, Lumin) = Lumen Logistics Pte Ltd, our
      Singapore distribution partner, office at Marina Bay, contact Ms Ong, Partnerships.`
      (aliases cover ASR mishearings)
- [ ] Prae: `Dory, add an FAQ: Who approves travel? The traveller's line manager. For Partnerships and
      Sales that is Prae.`
- [ ] Read-back: `Dory, show the company playbook` -> 3 rules, 1 glossary, 1 FAQ.
- [ ] Prae: `Dory, schedule a meeting: Lumen Logistics partner kickoff, Thursday 13 November 10:00 to 12:00
      Singapore time, on-site at Lumen's office, Marina Bay, with Mint and Boom.` -> `schedule_meeting`
      (Discord Scheduled Event + meeting record). Read-back as Mint: `Dory, list upcoming meetings`.
- [ ] Mint in `dory-mint`: `talk to me in English` and `call me Mint` (profile).
- [ ] Mint: `Dory, my travel profile: passport name SRISUWAN/MINT, window seat, morning departures, no
      red-eyes, hotel with a gym, vegetarian meal, Star Alliance Gold.` -> `travel_profile`.
      Read-back: `Dory, show my travel profile`.
- [ ] Mint: `Dory, send my morning brief at 07:30` (NotifPrefs `morning_time`).
- [ ] Boom in `dory-boom` (typed, the whole flow): `Dory, book my trip for the Lumen kickoff, cheapest in
      policy, hotel in policy near Marina Bay.` -> confirm -> booked, receipt filed. This is the
      "colleague's trip" and it makes Boom's D-day 07:30 brief show the trip (screenshot it).
- [ ] Boom in `#sales`: `Flying to Singapore Wednesday morning for the Lumen kickoff, two nights near
      Marina Bay. I did the Singapore import permits last time, ask me if you need the forms.`
      (team memory + people dossier). Then run `uv run python scripts/dory_people_backfill.py --guild
      <id> --days 7 --apply` (human approval) so `who_to_ask("Singapore customs")` names Boom.
- [ ] Two fictional receipt photos in the receipts channel dated this month (Grab to the airport THB 450;
      a domestic e-ticket THB 4,890 "Chiang Mai site visit") so "travel this month" has history.
- [ ] Discord: Dory in voice channel `#team-room` with `voice_talk` may_talk, hush cleared,
      `DORY_VOICE_MODE=glm` on the `dory-bot` pool. Prae's phone: Discord app, `dory-prae` open.
- [ ] Read-back from Mint, typed: `who else is going to the Lumen kickoff?` -> Boom; `what did we spend on
      travel this month?` -> three receipts; `list my reminders` -> none (cancel rehearsal ones);
      no pending approvals (`Dory, my pending approvals` as Prae; decide any leftovers).

### Build gates (must be green in the rehearsal server before the first full run)

- `search_flights` / `search_hotels`: since 29 Oct 2026 the ONLY searches are `src/dory/travel_search.py`'s card
  tools (spoken in voice, drawn as cards in chat; `docs/demo/travel-search-cards.md`) over ONE sample catalogue
  (BKK <-> SIN flights, fictional Singapore hotels, THB). Every result carries a `booking_ref` that `book_trip`
  books; no agent search reaches Duffel / LiteAPI any more, so the SGD prices and hotel names in the script
  below predate that change and must be re-checked against the catalogue before a rehearsal.
- `book_trip` two-step: the first call answers `needs_confirmation` with the quote, the same call in a LATER
  message books (the secretary confirm gate); an `approval_id` books only when that approval is Mint's own and
  `approved` (checked in code, never by the model). On success: one ledger `Receipt` per item (category
  ค่าเดินทาง, vendor = airline / hotel, note = purpose + reference), a `dory_trips` record that `list_trips`
  shows to the whole company (amounts only to the traveller and executives) and a `once` check-in reminder
  24 h before departure. Not built: the trip in the morning brief / `my_day` (the script does not claim it).
- Voice cascade: one spoken filler per tool round (`fillers.FillerWriter`, kind `voice`, fallback
  `ack_voice_1..8`), spoken the moment the brain starts, so a 3-round turn sounds like three short
  sentences, not 12 s of silence. The `/center` panel shows "Dory is checking: ..." (`live_checking`).
- Discord GLM room has the SAME tools as the web call (`ask_dory`); today's `GlmRoom` has none.
- Reminders and task cards fire from the voice room (`set_reminder`, `add_task` are voice action tools).

## 3. Run of show (7 min)

Screen: left half Chrome on `/center` (Talk to Dory panel open), right half Discord desktop with
`#team-room` and `dory-prae`; Prae's phone mirrored in a small window (QuickTime) for the approval tap.
Filler = what Dory says immediately while the tool runs (3-6 s each); "Dory" = her answer after it.

| Time | Who | Spoken line | Dory (approx) | On screen | Tool / feature | Filler while it runs |
| --- | --- | --- | --- | --- | --- | --- |
| 0:00 | Presenter | "This is Dory, the AI coworker in our Discord. She already knows our calendar, our travel policy and our people. Watch Mint book a trip without typing a thing." | | `/center` Company -> Calendar, the Lumen kickoff on Thu 13 Nov | calendar | |
| 0:20 | Mint | clicks Talk to Dory -> call | "Hi Mint. What can I do for you?" | panel: lantern on, fish stage | `web_live` greet (`greet(lang)`) | |
| 0:30 | Mint | "Dory, book my trip for the Lumen kickoff." | "The kickoff is Thursday the 13th at ten, at Lumen's office in Marina Bay. So Bangkok to Singapore Wednesday morning, back Friday, two nights. You like mornings and a window seat, let me find flights." | "Dory is checking: the Lumen kickoff" | `list_meetings` -> `travel_profile` -> `search_flights` (3 rounds), policy from `company_block` | "On it, pulling up the Lumen kickoff and your travel profile." / "Checking Wednesday morning flights to Singapore." |
| 1:10 | Dory | | "Two in policy: Thai 403 at 08:00, arriving 11:25, economy, 13,700 baht return, or Singapore Airlines 705 at 09:40 for 14,900. It is a 2-hour-25 flight, so economy per policy. Window seat and vegetarian meal from your profile. Take the 08:00?" | panel transcript | | |
| 1:30 | Mint | "The 08:00 is fine. And a hotel right next to Lumen's office." | "Right at Marina Bay there is the PARKROYAL Collection at 338 Singapore dollars a night, that is 118 over the Singapore cap of 220. In policy, the Carlton City is 210, about 1.5 km away. Want the closer one? I would need Prae's approval first." | "Dory is checking: hotels in Singapore" | `search_hotels`, cap rule from the playbook | "Looking at hotels around Marina Bay for the 12th and 13th." |
| 2:10 | Mint | "Ask Prae. The kickoff starts at ten and I don't want to be late." | "Sent to Prae with your reason. I'll wait for the answer." | phone: card in `dory-prae`: "Hotel over cap, SGD 236 over two nights, reason: ...", Approve / Decline | `request_approval(kind=expense, amount=676 SGD, approver=Prae)` -> `ApprovalButton` | "Sending it to Prae now." |
| 2:30 | Prae (phone) | "Fine by me, that street is a nightmare at nine." taps **Approve** | | phone card turns green; `dory-mint` gets "Prae approved: hotel over cap" | `handle` decide -> `deliver_to_person` | |
| 2:45 | Mint | "Prae approved it. Book both." | "Thai 403 and 404, 13,700 baht, and the PARKROYAL for two nights, 676 Singapore dollars, about 31,600 baht all in, for the Lumen kickoff. Shall I book it?" | "Dory is checking: booking the trip" | `book_trip` step 1 (quote; the approval id must be approved and Mint's own, read in code) | "Pulling the quote together, one moment." |
| 3:05 | Mint | "Yes, book it." | "Booked. Flight reference <PNR>, hotel confirmation <8 digits>. Both e-receipts are filed under Travel for the Lumen kickoff, and I'll remind you to check in on Tuesday at 08:00. Anything else?" | `/center` Documents -> Finance refreshes with the two e-receipts (`refreshView`) | `book_trip` step 2 (same arguments, later message) -> `dory_trips` + two ledger `Receipt`s + `once` reminder | "Confirming with the airline and the hotel." |
| 3:25 | Mint | "That's all for now, thanks." ends the call | "Safe travels, Mint." | | `end_conversation` | |
| 3:30 | Presenter | "Same Dory, now in the team's voice room, where Boom is working. She joined by herself." Switch reason: the team lives in Discord; cards, buttons and colleagues are there. | | Discord `#team-room`: Dory + Mint + Boom in the channel | `auto_join_meetings`, `GlmRoom` | |
| 3:45 | Mint | "Dory, who else is going to the Lumen kickoff?" | "Boom is. He booked yesterday, same 07:05 flight, two nights near Marina Bay. Prae is on the invite but has not booked." | captions in the room's text chat | `search_everything` (trips + meeting attendees + chat memory) | "Let me check the team's plans." |
| 4:10 | Boom | "Dory, who handled Singapore customs paperwork last time?" | "You did, Boom, the import permits for the last shipment. Mint, ask him for the forms." | | `who_to_ask` (people dossier) | "Checking who did that." |
| 4:30 | Mint | "Dory, give Boom a task: the Lumen deck, ready by Monday." | "Done. Boom has the Lumen deck by Monday 10 November. I sent him the card." | `dory-boom`: task card with Accept / Edit / Decline; Boom taps **Accept**; `dory-mint` gets "Boom accepted" | `add_task` -> `TaskButton` handshake | "Writing that down for Boom." |
| 5:00 | Mint | "And remind me to check in online 24 hours before my flight." | "Set for Tuesday 11 November at 07:05, in your private channel." | `dory-mint`: reminder confirmation | `set_reminder(at=2026-11-11 07:05, where=me)` | "Setting that reminder." |
| 5:20 | Mint | drops a photo of a Grab receipt (fictional, THB 450) in `#team-room` text, says "Dory, that's my taxi to the airport last week." | "Filed: Grab, 450 baht, 21 October, Travel." | receipt card reply in the text channel | content intake -> Nemotron 3.5 Super VL extraction -> ledger | typed ack line (`ack.py`) |
| 5:45 | Prae (phone, joins the room) | "Dory, what did we spend on travel this month?" | "Travel in October: 32,200 baht over four receipts plus 1,096 Singapore dollars for the two hotels: today's flight 13,700, Boom's 13,700, the Chiang Mai e-ticket 4,890 and the Grab." (approximate; `spending_summary` groups by currency) | breakdown posted as text in the room | `spending_summary(group_by=category)` (executive scope) | "Adding up October's travel." |
| 6:15 | Mint | "Dory, what's on my plate tomorrow?" | "Tomorrow: the Lumen prep call at two, Boom's deck due Monday, and your Singapore trip is Wednesday, Thai 403 at 08:00 with Boom." | the room's text chat shows the trip list | `my_day` + `list_trips` | "One second." |
| 6:40 | Mint | "Thanks Dory, that's all." | "Bye, Mint." | | `end_conversation` | |
| 6:45 | Presenter | "Calendar, policy, approval, booking, receipt, reminder, brief: one conversation, two surfaces, GLM-5.3 on Nebius with Nemotron reading the receipts. The URL is on the slide; sign in with Google and ask her yourself." | | end slide: URL + stack line | | |

Optional 10-second variant (only if rehearsed): Boom's personal language Thai and language mode
`audience` -> his task card arrives in English with a `*(Thai translation)*` block. Off by default: in the
voice room Dory would then speak every block twice (`MeetingSession.langs`), doubling latency.

## 4. The 3-minute video (cut list)

Record each segment as its own take right after a clean rehearsal; screen + phone mirror + a lapel mic.
Keep ONE unedited filler of 4-5 s (segment 2) so judges see the real latency once; trim the rest to 1-2 s.

| Clip | Timestamp | Content |
| --- | --- | --- |
| 1 | 0:00-0:12 | Calendar with the kickoff. Mint: "Dory, book my trip for the Lumen kickoff." Caption: no dates, no city. |
| 2 | 0:12-0:45 | Her first answer (meeting found, profile applied), the uncut filler, the flight choice. |
| 3 | 0:45-1:20 | Hotel over cap -> "Ask Prae" -> split screen: phone card, Prae taps Approve, `dory-mint` notified. |
| 4 | 1:20-1:45 | "Confirm" -> booked, reference read out -> Documents / Finance shows the e-receipts. |
| 5 | 1:45-2:10 | Discord room: "who else is going" (Boom, same flight) -> task card -> Boom taps Accept. |
| 6 | 2:10-2:35 | Grab receipt photo filed by Nemotron VL -> "what did we spend on travel this month". |
| 7 | 2:35-2:50 | Check-in reminder + "what's on my plate tomorrow" (trip in the brief). "Thanks Dory, that's all." |
| 8 | 2:50-3:00 | End card: demo URL, "GLM-5.3 on Nebius Token Factory · Nemotron 3.5 Super VL · voice on a Nebius GPU", repo. |

## 5. Failure modes and fallbacks

| Failure | What you see | Fallback | What the presenter says |
| --- | --- | --- | --- |
| Duffel or LiteAPI sandbox down / slow / key rejected | search turn > 25 s, or `source: sample` in the log | automatic: sample provider with the numbers in this script, same shapes; force with `DORY_TRAVEL_PROVIDER=sample` before the show if the morning check fails | nothing, prices are plausible |
| Voice VM down | panel "Waking the voice server, about two minutes" (`live_waking`) | `VmWaker` starts it; if not up in 2 min: typed chat in the same Talk to Dory panel, same tools, presenter types Mint's lines; Discord part typed in `#team-room` | "The voice box is cold; same brain, I'll type." |
| Voice up but no audio out in Discord | Dory present, silent | finish the Discord moments on the website call (`/center`), and keep the Discord-only bits (task card, approval card, receipt photo) in Discord text on the phone | "Let's take her back to the web call." |
| ASR mishears "Lumen" | Dory asks which meeting | glossary aliases (Loomin, Lumin); otherwise say "the Singapore kickoff on Thursday" | repeat with the date |
| Latency spike > 8 s on one turn | filler, then silence | do NOT repeat the question (a second utterance interrupts and cancels the turn); after 12 s say "Dory, say that again"; the answer is also in the text log | "She is hitting the airline sandbox live, nothing is cached." |
| Approval card not on the phone | Prae's phone shows nothing | Prae taps the same card in `dory-prae` in the Discord desktop window (always keep it open); else Prae in the room: "Dory, approve Mint's hotel" (`review` by the approver) | "Prae's got it on the laptop." |
| Brain books without the confirm step, or books an unapproved over-cap hotel | | impossible by code (quote id + `confirm`, approval status read in code); if the gate test fails on D-1, demo with the in-policy hotel and skip the approval moment | |
| Dory answers in Thai | | `company_only` + `conform_language`; if it still happens: "Dory, in English please" | |
| Token Factory 429 / outage | error after the filler | retry once ("Dory, try again"); then typed fallback; if the brain is gone, play the video | "Shared hackathon quota; here is this morning's take." |
| Browser mic / autoplay blocked | no greeting | click the page once, reload, re-grant the mic; Chrome only, one tab with audio | |
| Discord asks Dory to hush / wake policy strict | Dory ignores a line | say her name at the start of every line; hub `wake_policy` natural | |

## 6. Rehearsal checklist (demo day)

- [ ] D-1 evening: seed list done in the demo server, all read-backs green; rehearsal receipts, reminders,
      approvals and bookings live only in the rehearsal server (per-guild tenant, so the demo ledger stays
      clean). Full run twice: once `DORY_TRAVEL_PROVIDER=sample`, once on the sandbox. `grep voice_latency`
      on the service logs: p95 e2e under 8 s or shorten the chains (ask for the flight first, then the hotel).
- [ ] T-60 min: voice VM up on an ON-DEMAND instance (`deploy/glm_voice/vm.sh create --on-demand`,
      never the preemptible one), `/health` on the voice server, `DORY_GLM_VOICE_URL` reachable from the
      Cloud Run service, idle shutdown disabled for the day (`GLM_IDLE_SHUTDOWN_CMD` empty or
      `--idle-shutdown-min 180`), the 16:30 UTC stop timer not inside the slot.
- [ ] T-45 min: Token Factory key: one chat turn (the flight / hotel searches are the sample catalogue, no
      provider key to check). Cloud Run
      `meeting-scribe` warm (`/health`, open `/center`), worker pool `dory-bot` at 1 instance, Dory online in
      the server, in `#team-room`.
- [ ] T-30 min: Discord audio: Dory's output audible through the room speakers (Discord output device =
      system), presenter mic input level -12 dB, noise suppression on, push-to-talk OFF, `voice_talk`
      may_talk, hush cleared. Phone: Discord as Prae, `dory-prae` open, notifications on, brightness up,
      mirrored in QuickTime.
- [ ] T-20 min: screen layout: Chrome 125 % on `/center` left (signed in as Mint, Talk to Dory panel open,
      mic permission granted, autoplay allowed), Discord desktop right (`#team-room` + `dory-prae`),
      phone mirror bottom right. macOS Do Not Disturb on (Discord banners off, cards still show). No other
      tab with audio. Captions on in the room.
- [ ] T-15 min: seed verification, read-only, typed as Mint: `list upcoming meetings`, `show my travel
      profile`, `who else is going to the Lumen kickoff?`, `list my reminders` (empty), `show the company
      playbook`; as Prae: `my pending approvals` (none).
- [ ] T-10 min: the Grab receipt photo on the desktop and on the phone; the 3-min video local and on a USB
      stick; the typed transcript of every Mint line printed.
- [ ] T-5 min: one live greeting on the website call ("Hi Mint") and one "Dory, what time is it?" in the
      Discord room. Then stop talking to her until the show.

## 7. Judging criteria -> the moments that prove them

| Criterion | Proven by |
| --- | --- |
| Technological implementation | GLM-5.3 tool calling over Dory's 140+ tools in one cached prompt (calendar + policy + profile + ledger in the same context), the ASR -> GLM -> TTS cascade with per-round fillers on a Nebius GPU (0:30, 1:30), Nemotron 3.5 Super VL reading a receipt photo (5:20), two-step booking with the approval gate in code (2:45-3:05), multi-tenant Discord + web on one Firestore store, persistent button cards (2:30, 4:30). |
| Design | Nothing is asked that Dory already knows (0:30); the policy is explained in one sentence with the number (1:30); one button for the boss (2:30); fillers instead of silence; the same voice on web and Discord (3:30); English-first, Thai available per person; the `/center` page refreshes itself after a tool turn (3:05); WCAG 2.2 AA pages (axe in CI). |
| Potential impact | Every SME trip = calendar + policy + approval + booking + receipt + reminder across three tools and two people today; here it is one conversation (0:30-3:25) and the finance question is answered at once (5:45). Any Discord server adds Dory with no setup; LINE / Slack / Telegram / WhatsApp bridges share the same brain. |
| Quality of the idea | Not a travel bot: a coworker with institutional memory who closes the loop (who else is going 3:45, task to Boom 4:30, reminder 5:00, brief 6:15). The hyper-personalisation is real data (profile, playbook, calendar, ledger), seeded by typing to her the day before, not a script. |
