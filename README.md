# Meeting Scribe

Record a Google Meet from your browser, get a live Thai transcript with speaker labels, and have a
structured summary (key points, decisions, action items with owners, open questions) posted to Discord
when the meeting ends. Built for the hackathon.

The code, UI and docs are English; the meeting audio and the transcript/summary are Thai.

## Architecture

Diagrams (open in a browser): [architecture map](docs/diagrams/architecture.html) (source:
`docs/diagrams/architecture.archify.json`) and [meeting sequence](docs/diagrams/meeting-sequence.html).

```
 Browser (Chrome)                       Cloud Run: meeting-scribe (FastAPI)
 ┌──────────────────────┐   chunk/45s   ┌──────────────────────────────────────────┐
 │ Meet tab audio + mic │ ────────────▶ │ POST /api/meetings/{id}/chunks           │
 │ mixed (Web Audio),   │  (sequential) │   ffmpeg → 16 kHz FLAC                   │
 │ MediaRecorder/45 s   │               │   ├─▶ Cloud Storage (audio)              │
 │                      │ ◀──────────── │   └─▶ Gemini on Vertex AI (transcribe,   │
 │ live transcript +    │  poll 5 s     │        diarize) ─▶ Firestore             │
 │ final summary        │               │                                          │
 └──────────────────────┘               │ POST /api/meetings/{id}/finish           │
                                        │   └─▶ Pub/Sub topic meeting-finalize     │
                                        │                  │ push (OIDC-signed)    │
                                        │ POST /pubsub/finalize ◀──────────────────┘
                                        │   ADK agents on Vertex AI:               │
                                        │   [decisions ‖ action items ‖ speaker    │
                                        │    names] → synthesizer → Summary        │
                                        │   ─▶ Firestore  ─▶ Discord webhook       │
                                        └──────────────────────────────────────────┘
```

## Google Cloud services

- **Cloud Run** (`asia-southeast1`): hosts the web UI and API; scales to zero.
- **Vertex AI / Gemini** (`gemini-3.5-flash` for transcription and extraction, `gemini-3.1-pro-preview`
  for the final summary): Thai speech-to-text with speaker diarization and the summarization.
- **Agent Development Kit (ADK)**: multi-agent summarizer. Three extractors run in parallel, then a
  synthesizer merges their output into the final summary.
- **Firestore** (native mode): meetings and per-chunk transcripts.
- **Cloud Storage**: converted FLAC audio per chunk.
- **Pub/Sub**: decouples "Stop" from the slow summarization step. The push subscription has a 600 s
  ack deadline and retries on failure; the endpoint is idempotent.
- **Secret Manager**: holds the Discord webhook URL.
- **IAM**: a runtime service account with least-privilege roles, and a separate pusher service account
  whose OIDC token the app verifies on `/pubsub/finalize`.

## Local development

Requirements: Python 3.12+, [uv](https://docs.astral.sh/uv/), ffmpeg, and Application Default
Credentials for the project (`gcloud auth application-default login`).

```bash
uv sync
uv run pytest -q                      # offline tests, everything external is mocked
uvx ruff check . && uvx ruff format --check .   # lint + format

# Run against real GCP (Firestore, GCS, Vertex AI); /finish summarizes in-process.
cp .env.example .env                  # then set DISCORD_WEBHOOK_URL; without it the Discord post is skipped
uv run uvicorn meeting_scribe.app:app --port 8080
# Fully in memory (still calls Vertex AI and GCS): STORE=memory uv run uvicorn ...
```

Settings (see `src/meeting_scribe/config.py`) come from environment variables or `.env`:
`GCP_PROJECT`, `AUDIO_BUCKET`, `USE_PUBSUB`, `DISCORD_WEBHOOK_URL`, model names, `MEETING_LANGUAGE`.

`scripts/make_synthetic_sample.sh` (macOS) builds a scripted Thai test meeting in `samples/`.
`.env` is git-ignored; never commit the webhook URL.

## Deploy

```bash
gcloud auth login && gcloud config set project dory-personal-assistant
scripts/deploy.sh
```

The script is idempotent. It enables the needed APIs, creates the `meeting-scribe-run` and
`meeting-scribe-pusher` service accounts with their roles, stores `DISCORD_WEBHOOK_URL` from `.env`
in Secret Manager (via stdin, never echoed), deploys the service with `gcloud run deploy --source .`,
and creates or updates the `meeting-finalize-push` subscription. It sets `PUBSUB_VERIFY_AUDIENCE` and
`PUSHER_SA_EMAIL` so only the pusher identity can call `/pubsub/finalize`. It prints the service URL.

Prerequisites it does not create: the `meeting-finalize` topic, the audio bucket and the Firestore
database.

Note: Cloud Run's frontend reserves `/healthz`, so use `/health` for deployed health checks.

## Using it with Google Meet

1. Open the Meeting Scribe URL in **Chrome** (or Edge) on desktop, in a separate window from the Meet tab.
2. Enter a title and, optionally, participant names (they help the model label speakers), then click **Record**.
3. In the browser's sharing dialog choose the **Chrome Tab** option, pick the **Google Meet tab**, and
   tick **Share tab audio**. The app warns if no audio track was shared.
4. Allow microphone access so your own voice is included. **Wear headphones**; otherwise the microphone
   can capture remote voices already present in tab audio, causing echo, duplicate words and worse diarization.
5. **Keep the Meet tab shared** for the whole meeting. Stopping the share ends the capture.
6. Click **Stop** when done. The app uploads the last part, then shows the summary and posts it to Discord.

You can also use **Upload a recording** to process an existing audio file instead.

## ดอรี่ / Dory — receipts & expense Q&A bot

### How to use Dory

Talk to Dory like a colleague: no commands to learn. Type, or send a file, a photo, a voice
message or a link, and say what you need.

- "ฝากบอกพี่มิวด้วยว่าลูกค้าโทรมา" or "tell Mew the customer called": Dory tags them (or sends a DM if you say so).
- "เดือนนี้จ่ายค่าวัตถุดิบไปเท่าไร": answers from the ledger. Send a receipt photo or PDF and it is recorded.
- Drop a PDF, a clip or a link: Dory says it needs a moment, reads it, and answers in the same message.
- "เมื่อวานในห้องบัญชีคุยอะไรกัน", "นัดประชุมกับคุณเอพรุ่งนี้บ่ายสอง", "ส่งรายงานเดือนนี้เป็น PDF เข้า DM ผม".
- Settings are just sentences: "ห้องนี้ไม่ต้องตอบนะ", "ช่วยพูดอังกฤษในห้องนี้", "จำแค่ 30 วันพอ"
  (admins and executives). The slash commands (`/โหมด`, `/ภาษา`, `/ความจำ`, ...) stay as optional shortcuts.

A second package, `src/dory/`, is a Discord bot. Staff post receipt photos or PDFs in a receipt
channel; Gemini (Vertex AI) extracts vendor, date, totals and a category into a ledger, flags
low-confidence or duplicate receipts, and replies in Thai. Executives ask questions in Thai
("how much did we spend on ingredients this week?") and get answers from ledger tool calls, plus an
optional daily digest. Non-executives only see their own receipts.

Duplicate bills (the same invoice sent twice, e.g. a PDF and a screenshot) are detected by one rule:
same total and currency, dates within 3 days, and a similar vendor or the same invoice number.
Ask Dory "which bills are duplicates?" and it lists each group (which copy stays, which would be
deducted, the amount) and asks for confirmation; after an executive confirms, the extra copies are
**voided** (soft delete: excluded from every total, list, digest and export, never hard-deleted,
reversible with "restore"). Replying "ซ้ำ" / "duplicate" to a receipt reply voids it, "กู้คืน" /
"restore" brings it back. The daily digest shows "possible duplicates awaiting review".

**Multi-tenant.** Any Discord server (guild) can add Dory with the public invite link and gets its own
isolated ledger and settings with no technical setup. The tenant key is the guild id: every receipt,
dedupe check, Q&A tool, digest, deep-task export and hub view is scoped to one guild.

Customer flow: (1) open the invite link (the hub's "เพิ่ม Dory เข้า Discord" button) and add Dory to the
server; Dory posts a short Thai welcome. (2) Post receipt photos or PDFs in any channel: Dory recognises receipts by their content (never by the
channel name), or @mention Dory with an image/PDF: it works immediately. A channel that took 3 or more
receipts in the last 30 days (or one set in the hub) is read directly, and receipts posted elsewhere are
copied to the busiest receipt channel.
(3) Optional: a server owner / Administrator / Manage Server member types `/ตั้งค่า` (or `/setup`) and
opens the private one-time link (valid 15 minutes) to manage the server in the hub after signing in with
Google. Executives are the owner, members with Administrator or Manage Server, members with a role in the
server's executive role names (default `ผู้บริหาร`, `Executive`) and `DORY_EXEC_USER_IDS`.

- **Files to Dory (agent).** Send Dory an image, PDF or small text file (up to 4 files, 15 MB each, 20 MB
  total) by @mention, name, reply, DM, in a chat-mode channel or inside the 3-minute conversation window. The
  Google ADK agent (Gemini) reads the files itself, says what is inside, and decides what to do next:
  receipts, tax invoices and transfer slips are recorded in the ledger (tool `record_receipt`, bound in code
  to that message, author and server, honouring the `receipts` switch; replying to Dory's message still
  corrects the receipt), documents, screenshots and charts are summarised with team memory and 1-3 suggested
  next steps, questions written in an image are answered, and heavy analysis can start a deep task
  (`start_deep_task`, executives only, `deep_tasks` switch). Receipt channels (and unaddressed images
  elsewhere) keep the direct receipt pipeline.
  A receipt recorded outside a receipt channel (or by DM, when the sender shares one server with Dory) is
  also copied to the server's main receipt channel (hub setting, else the first receipt channel Dory can
  post in), re-uploading the files with a link to the original; replies there correct or void it. The
  original is never deleted. Switch: `receipt_forward` (default on). Nothing is posted for history import.
- **Channel modes** (`/โหมด` or `/mode`, or the hub's "โหมดของแต่ละห้อง"): per channel, `🔇 off` (ignore the
  channel), `👂 listen` (receipts get an emoji reaction only; an @mention gets 👂), `🙋 call` (default:
  answers when @mentioned or called by name, `ดอรี่` and misspellings but not `สลิป`; for 3 minutes
  afterwards a cheap gate model, `DORY_GATE_MODEL`, decides whether each message is meant for Dory, then a
  short sign-off), `🎧 join` (call, plus Dory may chime in on questions after the channel is quiet for 30 s,
  at most 3 times per hour per channel) and `💬 chat` (answers every message; the `คุยกับน้องดอรี่` channel
  and ask channels). Only server managers or executives may change a mode. `@Dory เงียบก่อน` makes the
  channel `listen` for an hour; `@Dory คุยได้แล้ว` ends it. The old "any channel named dory answers
  everything" rule is gone.
- **Thai and English commands**: every typed command (an @mention followed by the words, matched only at the
  start of the message, case-insensitive) has both forms: `เข้าประชุม` / `join`, `join the meeting`, `come to the
  meeting`; `ออกประชุม` / `leave`, `leave the meeting`, `end meeting`, `stop meeting`; `เงียบก่อน` / `be quiet`,
  `quiet`, `shh`, `shush`, `mute`, `hush`, `snooze`; `คุยได้แล้ว` / `you can talk`, `talk again`, `unmute`,
  `unsnooze`, `wake up`, `come back`. Slash commands have Thai names with English aliases (`/โหมด` `/mode`,
  `/ภาษา` `/language`, `/โทน` `/tone`, `/เข้าประชุม` `/join-meeting`, `/ออกประชุม` `/leave-meeting`, `/ตั้งค่า` `/setup`). The name is recognised in
  Latin letters too ("hey dory, what did we spend?").
- **Deleting and cancelling.** Reply to one of Dory's messages with just `ลบ` / `ลบข้อความ` / `ยกเลิกข้อความ` /
  `เอาออก` / `delete` / `remove` / `unsend` and Dory deletes it (all chunks of a long answer, tracked for about
  24 h), then reacts 👍. Allowed for the person Dory was answering, server managers and executives. On a receipt
  reply `ลบ` / `ยกเลิก` voids the receipt (restorable); `ลบข้อความ` / `delete message` also deletes Dory's
  receipt message. `@Dory ยกเลิกงาน` / `cancel task` or `/ยกเลิก` `/cancel` stops the running deep task (kills
  the Gemini CLI process) for whoever started it, managers and executives.
- **Currencies.** Amounts are never added across currencies: summaries return `totals_by_currency`
  (`total` only when a single currency is present), no FX conversion; a receipt with no currency counts as THB.
- **Reply language** (`/ภาษา` or `/language`, `@Dory พูดภาษาอังกฤษ` / `speak English` / `English please`,
  `พูดไทย` / `speak Thai`, `ภาษาอัตโนมัติ` / `auto language`, or the hub's per-channel language select and the
  server default): `en` (default), `th`, or `auto` (answer in the language of the message:
  any Thai character means Thai, otherwise English; with no text, e.g. a slash command, the user's Discord
  locale). **Default language is English, and each server picks its main language when Dory joins**: she
  posts one menu (English + Thai, admins and executives only) in her chat channel and from then on does
  everything in that language (`language_chosen`; servers that never answered, or that already set
  `default_language`, see `dory.language_ask`; until chosen a server runs on `auto`, so Thai writers still get Thai).
  Resolution: channel override, else the guild's `default_language`; DMs use the person's own language, else the company's chosen one, else `auto`. It applies to
  everything Dory says: fixed replies (catalog in `src/dory/i18n.py`), Q&A and voice answers (system prompt),
  meeting summaries, the daily digest, receipt replies and deep-task reports. Only managers/executives may
  change it; others get a short refusal. A voice meeting uses the language of the voice channel's text chat as
  it was when the meeting started.
  **Seven more languages / ภาษาอื่นอีก 7 ภาษา** (second tier, after Thai and English): Chinese `zh`, Hindi `hi`,
  Malay `ms`, Indonesian `id`, Vietnamese `vi`, Korean `ko`, Japanese `ja`. Say "speak Japanese" / `พูดญี่ปุ่น` /
  `日本語で` / `한국어로` / `nói tiếng Việt` / `हिंदी में`, pick it in `/ภาษา` `/language`, in the hub (the hub itself
  stays Thai / English), or in a profile. `auto` also detects them by script (kana -> ja, Hangul -> ko, Han -> zh,
  Devanagari -> hi, Vietnamese letters -> vi); Malay and Indonesian are only set explicitly. Dory's answers, briefs,
  minutes and spoken replies come out in that language; the fixed system messages are machine-translated catalogs
  (`src/dory/locales/*.json`, missing keys fall back to English). Voice uses Chirp 3 HD voices (Malay uses the
  Indonesian voice). PDFs / cards / decks use Noto CJK or Devanagari fonts (`fonts-noto-cjk`, `fonts-noto-core`; if
  they are missing the document is made in English and Dory says so).
  ภาษาไทยและอังกฤษยังเป็นสองภาษาหลักที่เขียนเอง; อีก 7 ภาษาใช้ข้อความระบบที่แปลโดยโมเดลและให้ดอรี่ตอบเป็นภาษานั้น
  (พูด "พูดญี่ปุ่น", "พูดจีน", "พูดเกาหลี", "พูดเวียดนาม", "พูดฮินดี", "พูดมาเลย์", "พูดอินโดนีเซีย").
- **Tone of voice** (`/โทน` or `/tone`, `@Dory เปลี่ยนโทนเป็นทางการ` / `change tone to professional`,
  `โทนอะไร` / `what tone`, `พูดให้ทางการหน่อย` / `speak formally`, or the hub's server and per-channel tone
  selects): five presets, each in Thai and English: `cheerful` สดใส ร่าเริง (the default), `friendly` เป็นกันเอง
  สบายๆ, `professional` สุภาพ ทางการ, `concise` กระชับ, `calm` ใจเย็น อบอุ่น. Only the style changes (emoji,
  exclamations, sentence length, small talk, greeting): she stays "ดอรี่" / Dory, ค่ะ / คะ, and every rule on
  accuracy, permissions and confidentiality is the same. Resolution: a member's own tone in their private
  channel and DMs, else the channel's tone, else the server default (`/tone` with `scope: server` or "use the
  professional tone across the whole server"). Executives and server managers set channel and server tones; anyone
  sets their own in their private channel or DMs; an optional server wording note (up to 200 characters, e.g.
  "always call customers คุณลูกค้า") is refused when it touches permissions or the persona. Chat, voice, briefs and
  reports use the same tone; the confirmation is already written in the new tone.
- **Q&A runs on Google ADK**: an `LlmAgent` (Gemini on Vertex) with four ledger `FunctionTool`s that
  are built per request around the asker's scope, so the model cannot widen it. At most 4 tool rounds.
- **Read links and search the web (`web` feature, default on)**: the `read_web(request)` tool makes a
  separate Gemini call (`dory/web_read.py`) with Google's built-in `url_context` and `google_search`
  tools (they cannot be mixed with function tools in one agent). Web pages are fetched by Google, never
  by our servers (no SSRF). YouTube links (watch, youtu.be, shorts) go in as video parts. At most 5 links
  per call; the answer comes back as text plus sources. Isolation: the outbound request is built only from
  the current user message (text and links) and the model's `request` capped at 500 characters, so ledger,
  memory and chat history are never forwarded. Logs carry domains only. Admins can switch it off per
  server in the hub ("อ่านลิงก์และค้นอินเทอร์เน็ต"); then the tool is not registered.
- **Summaries**: `/สรุป` (`/summary`, open to everyone) summarises a period (today, yesterday, 7 or 30
  days) of one channel or all channels the member can see, with an optional focus topic and a private
  (ephemeral) option; the memory scope is computed for the member and for where the reply is posted.
  Replying to any message with just "สรุป" / "summarize" / "tl;dr" while addressing Dory, or the message
  context menu "Summarize with Dory" (Thai: "สรุปด้วยดอรี่"), summarises that one message including its
  attachments and links.
- **Storage**: `DORY_STORE=sqlite` (default, local dev) or `firestore` (collection
  `DORY_FIRESTORE_COLLECTION`, default `dory_receipts`, doc id `{guild_id}_{sha256}`). Each query filters
  `guild_id ==` server-side (automatic single-field index only, no composite index); the date range and
  the rest are done in Python over that guild's receipts, which is fine at shop scale. Existing SQLite
  ledgers are migrated on open (old rows become guild 0). Optionally archive the original receipt files to
  Cloud Storage with `DORY_RECEIPT_BUCKET` (object prefix `dory-receipts/{guild_id}/`, the `gs://` URI
  is saved on the record).
- **Per-guild settings**: Firestore `dory_guilds/{guild_id}` (`DORY_GUILD_COLLECTION`): feature flags,
  extra receipt/ask channels, digest channel and time, executive role names, `admin_emails`, and what the
  bot syncs (name, icon, text channels, `installed_at`, `active`). The bot caches it ~60 s per guild;
  a missing document means defaults (every feature on). With `DORY_STORE=sqlite` an in-memory copy is
  used so local dev needs no Firestore. Env channel lists and `DORY_EXEC_ROLE_NAMES` still apply as
  defaults. `/ตั้งค่า` writes a one-time doc in `dory_link_codes/{code}`.
- **Deep tasks (executives only)**: send `งานใหญ่: <task>` or `/deep <task>`. Dory acknowledges at
  once, exports the receipts the caller may see into a throwaway workspace and runs **Gemini CLI** headless
  there (isolated HOME, minimal environment, file-only tools, timeout `DORY_DEEP_TASK_TIMEOUT`), then posts
  the Thai report (attached as `report.md` when long) with seconds, tokens and the models actually used.
  Gemini CLI is an external Node binary that `uv` does not install: set `DORY_GEMINI_CLI_PATH`, otherwise
  deep tasks are disabled. Model pinning caveat: with Vertex, the CLI rewrites `gemini-3.5-flash` to
  `gemini-3.8-flash`, so the default is `DORY_DEEP_TASK_MODEL=gemini-3-flash-preview`.

The bot is prepared for a Cloud Run worker pool (see below) but not deployed.

**Voice meetings (`/เข้าประชุม`, alias `/join-meeting`).** A member in a voice channel types `/เข้าประชุม` (or
`@Dory เข้าประชุม`); Dory joins, announces itself in the channel's text chat, and transcribes every speaker by
Discord name (per-user audio, so no diarization). Calling "ดอรี่ ..." out loud gets a text answer in that chat, using
the last ~5 minutes of transcript as context; the same transcript is context for text messages to Dory in that
chat ("เมื่อกี้ตกลงอะไรกัน"). `/ออกประชุม` (`/leave-meeting`), everyone leaving, or 3 hours ends it with a Thai summary
(decisions, action items with owners, open questions). Audio and transcript are kept in memory only, never stored.
Needs the **Connect** permission, the voice-states intent (non-privileged), `libopus` + `ffmpeg` (in
`Dockerfile.dory`) and `discord-ext-voice-recv` + `davey` (Discord's DAVE end-to-end encryption; see
`src/dory/meeting.py`). Toggle: hub feature `voice_meetings`.

**Secretary: meetings, PDFs, email.** Dory acts on its own judgement but asks before anything outward-facing:
the first call of `schedule_meeting`, `cancel_meeting`, `reschedule_meeting` or `send_email` only shows a proposal /
draft, and the action runs only when the same call arrives again in a *later* message (enforced in code in
`src/dory/secretary.py`, not only in the prompt). Hub features: `scheduling`, `documents`, `email`.

- *Scheduling* (`src/dory/scheduling.py`): "นัดประชุมกับคุณเอ วันจันทร์บ่ายสอง" creates a Discord Scheduled Event
  (voice-channel event, or an external event with a Google Meet / Zoom / Teams / any URL as its location). Needs the
  **Create Events** and **Manage Events** permissions (invite permissions integer 17600777145424); without them Dory
  explains how to grant them. Attendees get a DM invite. Meetings live in `dory_meetings` (SQLite or Firestore).
  Reminders (`DORY_MEETING_REMIND_MINUTES`, default 10) go out before the start and at the start, in the meeting's
  text channel and by DM, with a one-click link (voice channel URL or the meeting link). For voice meetings, attendees
  missing `DORY_MEETING_NOSHOW_MINUTES` (default 5) after the start get a friendly DM nudge; when `voice_meetings` is
  on Dory joins to take notes and leaves after `DORY_MEETING_EMPTY_MINUTES` (default 2) of an empty channel; the
  summary is linked to the meeting. An attendee who replies to a reminder/nudge DM ("ติดลูกค้า", "ไปช้า 10 นาที") has
  the reason recorded and relayed to the meeting's channel, and it appears in the attendance line after the meeting.
  Events people create directly in Discord are tracked too (interested members are reminded). Calendar access is
  behind `CalendarBackend`; only the Discord implementation exists (Google Calendar could be added).
- *PDF documents* (`src/dory/pdf_report.py`): `make_report_pdf` builds expense summaries, receipt lists, meeting
  minutes and custom documents with fpdf2 + uharfbuzz text shaping (Thai tone marks render correctly). Totals are per
  currency, void receipts are excluded, executives see everyone and others only their own receipts. The font is the
  first Thai-capable file found among `DORY_PDF_FONT`, `src/dory/fonts/` (drop Sarabun-Regular/Bold.ttf there to
  bundle it) and the system TLWG fonts (`fonts-thai-tlwg`, installed in `Dockerfile.dory`); with no Thai font a Latin
  fallback is used and a warning is logged.
- *Email* (`src/dory/email_out.py`): executives, managers (Manage Server) and roles listed in the guild document's
  `email_senders` may have Dory draft and send email (max 20 per guild per day, addresses validated, a PDF made in
  the conversation can be attached). Every draft and send is stored in `dory_emails` with who confirmed it. Without
  Gmail configured the default `LogOnlySender` only records the email and Dory says sending is not set up.

  Configure Gmail sending (instructions only, nothing is sent until you do this): create a dedicated Google account
  for Dory; in Google Cloud Console enable the Gmail API, configure the OAuth consent screen and create an OAuth
  client (type *Desktop app*); authorise that account once with the scope
  `https://www.googleapis.com/auth/gmail.send` (for example with the OAuth Playground using your own client) to get a
  refresh token; store it in Secret Manager and expose it to the worker as `DORY_GMAIL_REFRESH_TOKEN`, together with
  `DORY_GMAIL_CLIENT_ID`, `DORY_GMAIL_CLIENT_SECRET` and `DORY_GMAIL_SENDER` (the account's address). All four must
  be set, otherwise sending stays in log-only mode.

**Staying in the meeting.** Dory leaves only on /ออกประชุม, /leave-meeting, a typed or spoken "ออกประชุม"/"leave",
after `DORY_MEETING_LEAVE_EMPTY_SECONDS` (default 30; the old `DORY_MEETING_LEAVE_EMPTY_MINUTES` still overrides it) without humans in the channel (the summary is posted as usual) (an auto-joined meeting nobody
came to: `DORY_MEETING_EMPTY_MINUTES`, default 2), or at the 6 h cap (warned 10 min before). The active meeting is
stored (`dory_active_meetings`); after a restart `on_ready` rejoins it (transcript reloaded from the memory log)
or, if the channel is empty, posts the summary. An unexpected voice drop is retried 3 times before ending.

**Voice helpers (Dory · 2, · 3).** Discord allows one voice connection per bot account per guild, so Dory
"splits" across extra voice-only bot accounts driven by the main bot process (same event loop; text, memory, answers
and TTS stay in the main bot, a helper only listens and plays audio). The main bot is body #0.

- *Create a helper*: Discord Developer Portal -> New Application (name it "Dory · 2") -> Bot -> Reset Token -> copy
  the token. Add it to `.env` with an editor, never paste it in chat: `DORY_VOICE_TOKENS=tokenA,tokenB`
  (comma-separated, may be empty; tokens are never logged). No privileged intents are needed (the helper uses only
  guilds + voice states). Restart the bot; a helper that cannot log in is logged as "voice helper N unavailable".
- *Invite it* to each server with the voice-only link (View Channel, Connect, Speak, Use Voice Activity):
  `https://discord.com/oauth2/authorize?client_id=<helper application id>&scope=bot&permissions=36701184`
  (`permissions.helper_invite_url`; `show_settings` lists the bodies, whether each is in this server, and the
  invite links of helpers that are not). A helper that is not in a guild is skipped for that guild.
- *Auto-join*: when a person is in a voice channel (not mode `off`, hub feature `auto_join_meetings` on, default on)
  Dory joins at once and announces it in the channel's text chat (`DORY_AUTO_JOIN_MIN_HUMANS=1`;
  `DORY_AUTO_JOIN_DELAY_SECONDS=0` is an optional stability wait, 0 = no timer; rapid duplicate events for a
  channel share one attempt). A channel where someone told Dory to leave (`/ออกประชุม`, "ดอรี่ ออกประชุม") is not
  auto-joined for 60 minutes (`DORY_AUTO_JOIN_COOLDOWN_MINUTES`). Sessions are keyed by (server, voice channel), so
  two meetings run on two bodies; leaving in one room ends only that room.
- *Importance* (when every body is busy): scheduled meeting now +100 > executive/manager +30 each (max 2) > people
  +5 each, earlier start breaks ties; one person alone scores below any multi-person room. A newcomer takes the body of the
  weakest *auto-joined* session if it outranks it by 20 (a scheduled meeting always does; a person alone yields to
  any room of 2+). The old room gets "ขอไปช่วยประชุมที่นัดไว้ก่อนนะครับ ส่วนที่คุยมาสรุปไว้ให้แล้ว" and its summary.
  Sessions started by a person's command or by a schedule are never preempted. `/เข้าประชุม` with no free body
  follows the same rules or says which rooms occupy the bodies.
- Restart: each record in `dory_active_meetings` is per (server, channel) with its body index; resume reuses that body
  when it is still available.

**Spoken replies.** When called by name in a voice meeting, Dory also says a 1-2 sentence version of
the answer out loud (Gemini TTS `DORY_TTS_MODEL`, default `gemini-2.5-flash-tts`, voice `DORY_TTS_VOICE`,
default `Puck`); the full answer still goes to the chat. While Dory is speaking and for 1.5 s after,
wake words are ignored so its own voice coming back through someone's speakers cannot re-trigger it.
Turn it off with `DORY_VOICE_REPLY=false`.

**Live voice mode (`DORY_VOICE_MODE=live`, the default).** Instead of the wake-word pipeline, a Gemini Live
native-audio session (`DORY_LIVE_MODEL`, `DORY_LIVE_LOCATION=us-central1`, voice `DORY_LIVE_VOICE`) hears the
whole voice channel and answers about 1.5 s after someone stops talking, like a voice assistant. Everyone's audio is
mixed into one 16 kHz stream (`src/dory/live_voice.py`); with proactive audio on, Dory stays silent unless it is
addressed by name or clearly asked something, and anyone can talk over it (barge-in stops it at once). The session is
opened when Dory joins, resumes after the server's periodic disconnects, and what Dory says is also posted to the
channel's text chat as `🔊 ...`. Money questions use the same ledger tools as the text Q&A, but because the mixed
stream does not say who is speaking they only work when **everyone in the voice channel is an executive**; otherwise
Dory says to ask in the text chat. The per-speaker transcription keeps running for the transcript and summary but no
longer answers wake words in this mode. If the Live session cannot connect (4 tries), that meeting falls back to the
classic wake-word mode. `DORY_VOICE_MODE=classic` restores the old behaviour; `DORY_VOICE_REPLY=false` turns off
speech in both modes. Audio is streamed to Vertex AI for the duration of the meeting (never stored by Dory), and a Live
session is billed by audio time while people are talking.

**Team memory (องค์ความรู้).** Dory remembers what is said in the channels whose mode is not `off`, so it can
answer "what did we discuss yesterday?", "where is customer X's job?" or "who owns the ad budget?" without
spending many tokens and without leaking channels. Three layers (code in `src/dory/memory*.py`):

1. **Raw log, no LLM.** Every human message and Dory's own replies (kind `dory`), threads under their parent
   channel (private threads are skipped), voice-meeting segments (kind `voice`, channel = the voice channel),
   with author, UTC time, `local_date` (`DORY_TZ`), text plus short attachment descriptors, and the jump URL.
   Edits update the text; deletes remove the record and mark that channel-day summary `dirty`. Writes run in a
   background queue and can never slow or break a reply. Stores: SQLite (same file as the ledger) or Firestore
   (`dory_messages/{guild}_{message}`, `dory_day_summaries/{guild}_{channel}_{date}`,
   `dory_memory_channels/{guild}_{channel}`, `dory_memory_guilds/{guild}`), chosen by `DORY_STORE`; every read
   takes the guild and an explicit set of allowed channels. Firestore needs no composite index (equality and
   single-field range queries only).
2. **Per-channel day summaries, cheap model, batched.** `DORY_GATE_MODEL` (Flash-Lite) updates today's summary
   when a channel has `DORY_MEMORY_UPDATE_EVERY` (30) new messages, or any new message and
   `DORY_MEMORY_QUIET_MINUTES` (20) of quiet, sending only the previous summary plus the new messages (each
   message is read about once). Summaries are structured (overview, topics, decisions, action items, numbers,
   open questions). After the local day ends a summary is finalised and never rewritten, except once after a
   deletion. At most 3 updates per tick.
3. **Answering, access in code.** ADK tools `chat_search`, `chat_days` and `chat_messages` are bound to the guild
   and an allowed-channel set computed from Discord permissions (`dory/memory_access.py`): the asker must be able
   to read the channel, and when the answer is posted in channel X everyone who can read X must be able to read
   the source (DMs: the asker's channels). The model cannot widen it. `chat_days` also returns today's raw messages
   newer than the summary; outputs are capped (6,000 / 4,000 characters). Voice wake-word answers use the same
   tools, scoped to the voice channel's chat.
4. **Hybrid search (keyword + meaning).** Every summary item (overview, topic, decision, action item, number, open
   question) is embedded once by `DORY_EMBED_MODEL` (default `gemini-embedding-001`, 256 dimensions) when the
   summary is written; unchanged items keep their vector, and a backfill (10 summaries per tick) covers older
   summaries. Vectors live on the summary record, so retention, deletion and regeneration apply to them too.
   `chat_search` takes the user's question as `query` plus a few keywords, ranks day/channel groups by keyword hits
   and by cosine similarity (Thai and English match each other), and fuses both with reciprocal rank fusion. Raw
   messages are scanned for the last 3 days and read for the top 5 older hits only (quotes and links); for an exact
   code in older messages the model uses `chat_messages`. Summaries and vectors are served from an in-process
   per-guild index (64 MB cap, LRU, one load query per guild); it is correct only with one bot process, which is
   how the bot is deployed. Join-mode hints stay keyword-only (no embedding calls). Kill switch:
   `DORY_EMBED_MODEL=` (empty) gives keyword-only search.

- **Retention** is per guild: hub field "เก็บความจำไว้กี่วัน" or `/ความจำ days:<1-3650>` (`/memory`), default
  `DORY_MEMORY_RETENTION_DAYS` (90). The daily purge deletes by the guild's *current* setting (no stored expiry,
  so there is deliberately no Firestore TTL policy: a TTL on a stored date would ignore later changes). Shortening
  applies to existing data at the next purge; lengthening triggers an import of the newly covered older range.
- **History import** (`dory/memory_import.py`): for every readable non-`off` channel and thread (active and
  archived) Dory imports the messages from now minus retention, including from before memory was enabled; on
  startup it also catches up on downtime. Per channel progress (`imported_from`, `last_message_at`) makes it
  resumable and idempotent. Throttled: one channel at a time, pages of 100, a pause between pages, at most
  `DORY_MEMORY_IMPORT_GUILD_CAP` (20,000) messages per guild per run (a capped run resumes 10 minutes later).
  Past channel-days with 3+ messages get one final summary through a queue capped at
  `DORY_MEMORY_IMPORT_SUMMARIES_PER_DAY` (200) per guild per day, newest first.
- **Images** (feature flag `image_memory`): each image (max 4 per message, 8 MB each) is described once by the cheap
  multimodal model (description, all legible text verbatim, type) in a background task and added to the message's
  record, so search and summaries see it; bytes are never stored. Images the receipt pipeline reads are not read
  twice (the stored text is built from the extracted receipt). Historical images are described through a queue
  capped at `DORY_MEMORY_IMPORT_IMAGES_PER_DAY` (300) per guild per day, newest first; the rest keep
  `[image: name]` until reached (`[image-unread: name]` when the message is gone or the image unreadable).
- **Audio, video and voice messages** (`src/dory/media.py`, feature flag `media_memory`): attachments with
  audio/video types or extensions (mp3 m4a wav ogg opus aac flac webm mp4 mov mkv) and Discord voice messages are
  never sent as video: ffmpeg extracts mono 16 kHz FLAC (max 100 MB file, first 90 minutes), long audio is split
  into ~10 minute chunks with a 2 s overlap, and one Gemini call per chunk returns timestamped, speaker-labelled
  verbatim segments (Thai/English, `[inaudible]`, no invention); chunk offsets are added in code and overlap
  duplicates dropped. Sent to Dory (tag, reply, chat mode, DM) the transcript goes to the agent as a text part
  (`[ถอดเสียงจากไฟล์ #N: name, ยาว M:SS]`, about 30k chars) and it summarises, lists decisions and action items with
  timestamps and answers the question; a voice message of at most 2 minutes with no text is the question itself.
  In every non-off channel the transcript is also stored in the message's memory record
  (`[เสียง: 3:42] summary | Speaker A: ...`, capped) by a background task that never delays replies, limited to
  `DORY_MEDIA_MINUTES_PER_DAY` (120) minutes per guild per day; the history backlog counts against the same cap,
  newest first. Live voice meetings are unchanged.
- **Documents** (`src/dory/docs.py`, feature flag `doc_memory`): PDF, docx, xlsx (first 500 rows per sheet), pptx
  (slides, tables, notes), txt/csv/md/json are read in code (`extract_document`); old `.doc` needs `antiword`, `.xls`
  is not read (the user is told to save as .docx/.xlsx/PDF). Sent to Dory the text (about 30k chars, truncation
  noted) goes to the agent. In remembered channels a note `[PDF: name, N หน้า, ประเภท] summary | ข้อความสำคัญ: ...`
  is stored; scanned PDFs (no text layer) are sent (first 30 pages, 20 MB) to the cheap model for OCR + summary.
  Receipts already read by the receipt pipeline reuse `receipt_note` plus the text and are never ingested twice.
  Limit `DORY_DOC_PAGES_PER_DAY` (500) pages per guild per day, backlog newest first. The agent's `open_file`
  tool re-reads a remembered attachment (document text, OCR, transcript) from its message link, only for channels
  the asker may read.
- **Promo post kit** (`src/dory/promo.py`, `cards.py`, `promo_bot.py`, feature flag `promo`): send Dory a product
  photo with the offer ("ทำโพสต์โปร ลาเต้เย็น 59 บาท ลด 20%") and the `make_promo_kit` tool returns three JPEGs,
  `promo-1x1.jpg` (feed, LINE), `promo-4x5.jpg` (Facebook / Instagram feed) and `promo-9x16.jpg` (Stories, Reels,
  TikTok; text kept out of the platforms' button zones), plus a caption with hashtags in the reply. One image-model
  call per kit (`DORY_PROMO_IMAGE_MODEL`, default `gemini-nano-banana-2.1`, location `global`) restyles only the
  scene around the unchanged product; the model never draws text. Headline, price, call to action and shop name are
  typeset by Dory with the bundled Kanit font (Pillow RAQM shaping, which needs the system `libfribidi`:
  `libfribidi0` in `Dockerfile.dory`, `brew install fribidi` locally). `DORY_PROMO_KITS_PER_DAY` (20 per guild,
  counted before each call; 0 = AI scenes off). Blocked, failed or over-the-cap requests still get a kit built from
  the original photo, and the reply says why. Changes within 30 minutes ("ขอโทนอุ่นกว่านี้", "เปลี่ยนราคาเป็น 49")
  reuse the remembered photo (process memory only, never stored). Check the look with
  `uv run python scripts/dory_sample_promo.py <photo>` (offline; `--live` makes one billed call) and the live test
  `pytest tests/dory/test_dory_live.py -m live -k promo -s`.
- **UX**: `/โหมด` off to anything else posts a one-time notice in that channel; modes are described with the
  retention in `/โหมด`; `/ความจำ` shows on/off, retention, recorded modes and import progress; the hub shows the
  same progress. Feature flags `memory` and `image_memory` per guild. `listen` mode now answers when tagged.
- **Short-term context**: the room's last messages (30 lines, 3 hours) come from an in-memory buffer fed by gateway
  events (edits and deletes included); a channel is read from Discord once to prime it, and again after a reconnect.
- **Observability**: one log line per answer (`answer guild=... ms_total=... ms_context=... ms_agent=... tools=...
  tok_in=... tok_cached=... tok_out=... tok_thought=...`) and per memory search (`memory search ... ms_embed=...
  raw_queries=... keyword=... meaning=... both=...`); ids, timings and counts only, never content. The system
  prompt puts its stable part first so Gemini's implicit cache can reuse it (`tok_cached` shows it).
- `MemoryService.delete_guild(guild_id)` wipes a guild's memory; the bot does not call it on removal because it
  keeps every other guild record too (retention expires the data).

### How to answer Dory (สัญลักษณ์และวิธีตอบ)

Dory explains these on every message that expects a typed answer; "Dory help" / "ดอรี่ ใช้งานยังไง"
shows the guide at any time (the text lives in `src/dory/hints.py`, `help_tasks`).

**English**
- Three ways to hand out work: just talk and Dory picks tasks up, tag Dory under a message that gives work, or tell Dory directly ("give @Toey the slides by friday").
- The assignee gets a card: Accept / Edit / Not mine. If Dory cannot tell who owns a task she asks the giver: Mine / Someone else / Not a task.
- You can type instead of pressing a button: "task #id done", "task #id to @name", "mine", "not a task".
- `#id` is the task id; `@name` tags a person (type @ and pick the name); due dates: today, tomorrow, friday, 2026-10-20.
- Status symbols: ⏳ awaiting confirmation, 🔏 awaiting approval, ❓ owner pending, ⚠️ overdue, ✅ done.
- See your tasks with "my tasks" or on the `/pm` page (Workspace Settings shows the same legend).

**ภาษาไทย**
- สั่งงานได้ 3 ทาง: พูดคุยตามปกติ ดอรี่จับงานเอง, แท็กดอรี่ใต้ข้อความที่มอบงาน, หรือบอกดอรี่ตรงๆ ("ให้ @เตย ทำสไลด์ศุกร์นี้")
- คนรับงานจะได้การ์ด กดรับงาน / แก้ไข / ไม่ใช่ของฉัน ถ้าดอรี่ไม่รู้ว่าเป็นงานของใคร จะถามคนมอบ: ของฉัน / ให้คนอื่น / ไม่ใช่งาน
- พิมพ์ตอบแทนปุ่มได้: "งาน #รหัส เสร็จแล้ว", "งาน #รหัส ให้ @ชื่อ", "ของฉัน", "ไม่ใช่งาน"
- `#รหัส` คือรหัสงาน, `@ชื่อ` คือแท็กคน (พิมพ์ @ แล้วเลือกชื่อ), กำหนดส่ง: วันนี้ พรุ่งนี้ ศุกร์ 2026-10-20
- สัญลักษณ์สถานะ: ⏳ รอยืนยัน, 🔏 รออนุมัติ, ❓ รอระบุผู้รับ, ⚠️ เลยกำหนด, ✅ เสร็จ
- ดูงานได้ที่ "งานของฉัน" หรือหน้า `/pm` (หน้าตั้งค่ามีสัญลักษณ์เดียวกัน)

### Company language and personal language (ภาษาบริษัทและภาษาส่วนตัว)

**English.** Each server has one company language (chosen once, `/language` or the hub). Dory writes and speaks it everywhere, and documents, reports, minutes and `/pm` always use it. Each person can add a personal language ("talk to me in Thai"; "use the company language" removes it): anything addressed to them, and a voice room with them in it, then carries the company language first and their language after it. Dory never switches because of the language somebody wrote or spoke, and always understands Thai and English. An executive can say "company language only" (or "Dory, English only in this meeting" for one meeting) to turn the extra languages off; "allow personal languages" turns them back on. Dory says which mode it is in once when it joins a room or a private channel.

**ภาษาไทย.** แต่ละเซิร์ฟเวอร์มีภาษาบริษัทหนึ่งภาษา (เลือกครั้งเดียว ด้วย `/ภาษา` หรือหน้า hub) ดอรี่พิมพ์และพูดเป็นภาษานี้ทุกที่ และเอกสาร รายงาน รายงานการประชุม และหน้า `/pm` ใช้ภาษาบริษัทเสมอ แต่ละคนเพิ่มภาษาส่วนตัวได้ ("ดอรี่ คุยกับฉันเป็นภาษาไทย", "ใช้ภาษาบริษัท" เพื่อเอาออก) ข้อความที่ถึงคนนั้นและห้องเสียงที่มีเขาอยู่จะมีภาษาบริษัทก่อน แล้วตามด้วยภาษาของเขา ดอรี่ไม่เปลี่ยนภาษาเองเพราะคนพิมพ์หรือพูดภาษาอื่น และฟังไทยกับอังกฤษได้เสมอ ผู้บริหารสั่ง "ใช้ภาษาบริษัทอย่างเดียว" (หรือ "ดอรี่ ประชุมนี้ใช้ภาษาอังกฤษอย่างเดียว" เฉพาะการประชุม) เพื่อปิดภาษาเพิ่ม และ "ตอบหลายภาษาได้" เพื่อเปิดกลับ ดอรี่บอกโหมดที่ใช้ครั้งเดียวตอนเข้าห้องหรือห้องส่วนตัว

### Project pictures and Gantt import (ภาพความคืบหน้าและนำเข้าแผน Gantt)

**English.** Ask "which projects are running?", "how is project X going?" or "what is Toey working on?" and Dory answers with one line per project and attaches a picture: real progress (work done) and, separately, how much of the time to the deadline is used, how many days are left, and a state colour (on track, behind, at risk). Send a Gantt chart (a picture, PDF, Excel/CSV, or just type the steps) and Dory shows a preview table; reply "confirm" and she creates the project with its phases as milestones and the steps 1-2-3 as tasks with owners, dates, how far each is done and how far each is from its deadline. Sending the same plan again updates the steps instead of duplicating them. Same `projects` switch as the rest of the PM tools; the numbers also show on the `/pm` cards (two bars: "Work done" and "Time").

**ภาษาไทย.** ถามว่า "ตอนนี้มีโปรเจกต์อะไรรันอยู่", "โปรเจกต์ X ถึงไหนแล้ว" หรือ "เตยทำอะไรอยู่" ดอรี่จะตอบเป็นบรรทัดเดียวต่อโปรเจกต์พร้อมแนบภาพ: งานเสร็จจริงกี่ % แยกจากเวลาที่ผ่านไปกี่ % เหลือกี่วัน และสี (ตามแผน / ช้ากว่าแผน / เสี่ยงไม่ทัน) ส่งแผน Gantt มา (รูป, PDF, Excel/CSV หรือพิมพ์ขั้นตอนมาเลย) ดอรี่จะแสดงตารางตัวอย่างก่อน ตอบ "ยืนยัน" แล้วดอรี่สร้างโปรเจกต์ ช่วงงานเป็นเหตุการณ์สำคัญ และขั้นที่ 1-2-3 เป็นงานพร้อมผู้รับผิดชอบ วันที่ เสร็จไปกี่ % และเหลืออีกกี่วันถึงกำหนด ส่งแผนเดิมซ้ำจะอัปเดตขั้นเดิมไม่สร้างซ้ำ ใช้สวิตช์ `projects` เดียวกับเครื่องมือโปรเจกต์อื่น และตัวเลขขึ้นที่การ์ดในหน้า `/pm` ด้วย (สองแถบ: "งานเสร็จ" กับ "เวลา")

### Executive assistant / COO mode

Dory acts as the team's executive assistant: it watches what people do on its own (nobody reports to it),
tracks work, follows up, reports to leadership and keeps confidential information by the Discord role hierarchy.
Code: `coo.py` (Discord side), `memory_access.py` (rules), `tasks.py`, `disclosure.py`, `reports.py`, `coo_tools.py`.

- **Role hierarchy.** Rank = the member's highest role position; the guild owner is above everyone and
  Administrator counts as top. Information *about a person's work* from a channel the asker cannot read is visible
  only if the asker strictly outranks that person (or is that person); the same rank sees each other only through
  channels both can read. Public channels stay open to everyone who can read them. Such hierarchy-granted
  information is only used in DMs / private replies, or when *every* reader of the answering channel is that person
  or outranks them, so nothing reaches a wider audience (pure rules and tests: `memory_access.hierarchy_authors`,
  `message_visible`). The memory tools take an optional `person` (name or @mention).
- **Disclosure requests.** If a question hits information the asker may not see, the memory tools withhold it
  (the code counts the hidden matches, never shows them) and Dory offers to ask the owner. After the asker agrees,
  the agent's `request_disclosure(topic)` DMs the owner (the highest-ranked author of the hidden records) with the
  asker, the question and a neutral description (count, dates, place; no content) and **Approve / Decline**
  buttons. The buttons are persistent (`discord.ui.DynamicItem`, request id in the custom id), so they work after a
  restart. Approval stores a grant in `dory_disclosures` (guild, owner, grantee, topic, message ids, granted_at,
  optional expiry); exactly those messages become visible to that one person (in DMs), and Dory DMs them the
  answer. A decline is relayed politely. Private DM notes are never even hinted at.
- **DM channel.** A member's DM to Dory (when they share exactly one server with it) is recorded as a `dm` note under
  a private per-user scope: "พรุ่งนี้ผมลา", "ลูกค้า X ขอเลื่อนส่งของเป็นศุกร์". Higher ranks can read it; saying
  "เรื่องนี้เก็บเป็นความลับ" / "private" marks it owner-only (a bare marker flips the previous notes), and private notes
  are not summarised or reported. The first DM carries a one-time notice explaining this.
- **Tasks and follow-ups.** After each channel-day summary update the memory scheduler calls the task tracker: the
  summary's `action_items` (meetings are voice channels, DM notes included) become tasks in `dory_tasks` (assignee
  resolved from names or mentions, due date parsed, duplicates merged by text similarity), and one batched
  Flash-Lite call marks open tasks done when the new messages say so. Every day at `followup_time` (default 10:00)
  each member with tasks due or overdue gets a DM; replying updates the task (`update_task`: members only their own,
  executives any). `list_tasks(person, status)` follows the hierarchy. Feature flag `followups` (the 10:00 DM is
  sent only when `briefings` is off: the morning brief replaces it).
- **Personal briefings** (`dory.briefings`, `dory.briefing_bot`; feature flag `briefings`, default on; hub: flag +
  morning/evening times). Each member gets a morning brief DM (default 08:30, weekdays: today's meetings with
  one-click links, tasks due / overdue, important documents since yesterday's evening brief, asks still waiting for
  their reply) and an evening brief (default 18:00: meetings attended with decisions, tasks assigned / done today,
  tomorrow's meetings, pending asks). Composed by the main model from capped structured input with a plain fallback;
  nothing is sent when every section is empty; closed DMs are skipped and logged. **Important-document alerts**: the
  existing PDF / Office / image note call also returns the type, main amount and addressees (no extra call); contracts,
  legal / official letters, invoices or quotations above `DORY_DOC_ALERT_MIN_AMOUNT` (50,000) and anything
  addressed to or mentioning members DM the people it concerns (mentioned members, the replied-to author, named
  addressees, executives for contracts / invoices) who can read the channel, never the uploader, at most 10 a day per
  person and once per document. **Pending asks**: a message that user-mentions a member and matches a Thai / English
  request regex is tracked (no model); a later post by that member in the same channel / thread or a reaction answers
  it; still open after `DORY_ASK_REMINDER_HOURS` (2) the member gets one gentle reminder (08:00-20:00 only), and open
  asks appear in the briefs. Members tune everything by talking (`set_my_notifications` / `show_my_notifications`:
  morning / evening on-off and times, weekends, `doc_alerts` all | important | off, ask reminders), stored per
  (guild, user) in `dory_notif_prefs`.
- **Personal preferences** (`dory.profiles`, agent tools `remember_my_preference` / `show_my_preferences` /
  `forget_my_preferences`). "เรียกผมว่าพี่ปัส", "ตอบสั้นๆ", "สนใจเรื่องการตลาด", "สรุปเป็นภาษาอังกฤษ", "ไม่ต้องใส่อีโมจิ",
  "ผมดูแลบัญชี": a `Profile` per (guild, user) in `dory_profiles` (nickname <= 40 chars, `reply_length`
  short | normal | detailed, `language` th | en, <= 8 focus topics, role note <= 120, <= 8 style notes). The tools are
  bound in code to the speaker, so nobody edits another person's profile; only lasting preferences are saved. The
  asker's own profile (never anyone else's) goes into the prompt as a quoted data block that cannot change
  permissions, scoping or factual rules. `language` applies in DMs, personal briefs and `auto` channels; a channel set
  to th / en keeps its language. Briefs also use the recipient's length and focus. Profiles are not in reports or memory
  search; "forget" deletes them.
- **Deliver files** (`dory.deliver`, agent tool `deliver_file`). "ส่งเอกสารนี้ไปห้อง… แล้วแท็ก…" (also as a reply to the
  file): Dory posts the file(s) in the channel (fuzzy Thai / English name match; a Thai-to-Latin guess asks first), DMs
  a person, or drafts an email with the file (normal confirm flow), with a short polite note, real `@[name]` mentions
  (nothing else pings) and "ส่งต่อจาก @you · [ต้นฉบับ](link)". In code: the requester must read the source channel and
  be able to send in the destination, Dory needs Send + Attach; if people at the destination cannot read the source
  channel a confirmation in a later message is required; files over 25 MB are linked, not attached; every delivery
  is logged in `dory_deliveries`.
- **Evening report.** At `report_time` (default 18:30, hub and guild settings; feature flag `reports`) Dory posts a
  report for leadership in the private channel `รายงานจากดอรี่` (created with permission overwrites for the owner,
  Administrator / Manage Server roles, the executive roles and Dory; without Manage Channels it asks the owner by DM
  once a day; or pick your own channel in the hub): company brief (spend today / this month per currency, receipts to
  review, duplicates), per-person work (2-4 lines each), meetings with decisions and action items, risks and
  suggested next actions. It is generated by the main model from compact inputs (day summaries, task list, ledger
  summary; capped at 12,000 characters, never raw logs) restricted to what every reader of the channel may see, with
  a plain deterministic fallback if the model fails. `/รายงาน` (`/report`, executives and managers) posts it now for
  today or a `date`; `/รายงาน ของฉัน` (`mine`) or "วันนี้ผมทำอะไรไปบ้าง" gives anyone their own day.

**Slide decks (สไลด์นำเสนอ).** Ask Dory for a presentation ("@Dory ทำสไลด์สรุปค่าใช้จ่ายเดือนนี้", "make a
5-slide pitch for our new menu", "ทำสไลด์สรุปประชุมเมื่อวาน") and it replies with an editable PowerPoint file
(`.pptx`). The chat agent gathers what it needs with its usual tools (ledger, team memory), then calls the
`create_deck` tool with a structured outline (`dory/deck.py`): a title slide is added automatically, then up to 12
slides of four kinds (section, bullets, two columns, chart) with speaker notes. Chart slides are data-bound: the
outline names a query (spending by category, vendor, submitter or day for a date range) and code fills the numbers
from the ledger with the asker's scope (non-executives see only their own receipts), so the model never types
numbers into a chart; charts are native and editable. One 16:9 theme, Thai text in the complex-script font slot
(Leelawadee UI), fixed strings in the reply language. Decks are built in memory, attached to the reply like
the other generated files and never stored; at most 2 MB. Offered only for normal text
answers (not voice or unprompted join-mode answers), behind the per-guild feature flag `decks` (hub toggle
"สไลด์นำเสนอ"). `uv run python scripts/dory_sample_deck.py /tmp/deck.pptx` renders a sample Thai deck offline.

Discord setup (once, by the operator):

1. Create an application and bot at the Discord Developer Portal (name it **Dory**); copy the bot token.
2. Enable the **Message Content** and **Server Members** privileged intents. The public invite link
   (`dory_invite_url`: scopes `bot` + `applications.commands`, permissions 17600777145424, which adds Create Events and Manage Events for scheduling) is built from
   `DORY_DISCORD_CLIENT_ID` and shown on the home page and in the hub.
3. Put `DORY_DISCORD_TOKEN` in `.env`. The slash commands are registered globally at startup (Discord can
   take up to an hour to show new global commands).
4. Optional local defaults, applied to every guild: `DORY_RECEIPT_CHANNEL_IDS`, `DORY_ASK_CHANNEL_IDS`,
   `DORY_DIGEST_CHANNEL_ID`, `DORY_EXEC_USER_IDS`, `DORY_EXEC_ROLE_NAMES`. `DORY_HUB_URL` is the web
   service the `/ตั้งค่า` link points to (defaults to the Cloud Run URL).

Other keys: `DORY_DIGEST_TIME`, `DORY_STORE`, `DORY_DB_PATH`, `DORY_FIRESTORE_COLLECTION`,
`DORY_RECEIPT_BUCKET`, `DORY_GEMINI_CLI_PATH`, `DORY_DEEP_TASK_TIMEOUT`, `DORY_DEEP_TASK_MODEL`,
`DORY_GCP_PROJECT`, `DORY_GEMINI_LOCATION`, `DORY_GEMINI_MODEL`, `DORY_TZ`, `DORY_MEMORY_*` (see `.env.example`). All Dory variables carry the `DORY_` prefix so they
never collide with Meeting Scribe's.

```bash
uv run python -m dory                                   # run the bot (needs ADC for Vertex AI)
uv run python scripts/dory_seed_demo.py ./data/demo.db  # seed a demo ledger
DORY_DB_PATH=./data/demo.db uv run python -m dory.cli ask "สรุปค่าใช้จ่ายสัปดาห์นี้" --as-exec
uv run python -m dory.cli extract receipt.png           # run extraction on a local file
DORY_GEMINI_CLI_PATH=/path/to/gemini DORY_DB_PATH=./data/demo.db \
  uv run python -m dory.cli deep "วิเคราะห์ค่าใช้จ่ายเดือนนี้ แล้วเขียนรายงาน" --as-exec
uv run pytest -m live -q                                 # one real Vertex call (skipped by default)
```

### Travel time and weather (Google Maps Platform)

Off by default. Enable `routes.googleapis.com`, `places.googleapis.com` and `weather.googleapis.com`
on the project, give the Cloud Run service account access (it authenticates with ADC, no key), then
set `DORY_MAPS_ENABLED=true`. Per guild the `maps` flag (hub) turns it off. If the Weather API
rejects OAuth, put an API key in Secret Manager and expose it as `DORY_MAPS_API_KEY` (fallback
only, never logged). Optional WeatherNext 2 ensemble: `DORY_WEATHERNEXT_BQ_DATASET=<project>.<dataset>`.

## Deploying Dory

Dory runs as a Cloud Run **worker pool** (no HTTP port; it holds the Discord gateway connection).

```bash
export DORY_DISCORD_TOKEN=...            # from your shell, never from a command line or git
scripts/deploy_dory.sh                   # dry run (default): prints every command, changes nothing
scripts/deploy_dory.sh --apply           # really deploy
scripts/deploy_dory.sh --configure-hub   # optional, separate: set hub env vars on meeting-scribe
```

The script is idempotent: it enables missing APIs, creates the `dory-bot` service account with least
privilege (`datastore.user`, `aiplatform.user`, `logging.logWriter`, `secretmanager.secretAccessor` on
the one secret, `storage.objectAdmin` on `DORY_RECEIPT_BUCKET` only if set), stores the token in the
`dory-discord-token` secret via stdin (new version only if none exists, or with `--rotate-token`),
builds `Dockerfile.dory` with Cloud Build (`cloudbuild.dory.yaml`) and deploys the pool with
`DORY_STORE=firestore`. Optional defaults (`DORY_RECEIPT_CHANNEL_IDS`, `DORY_GUILD_COLLECTION`,
`DORY_HUB_URL`, ...) are passed through from your environment. It never touches the existing Meeting Scribe resources, except the optional
`--configure-hub` step, which only runs `gcloud run services update --update-env-vars` (needs
`HUB_GOOGLE_CLIENT_ID`, `DORY_DISCORD_CLIENT_ID` and optionally `HUB_ADMIN_EMAILS` in your environment).

**Cost.** One always-on instance (`--instances 1`: two would answer every Discord message twice),
1 vCPU / 2 GiB. 2 GiB because the Gemini CLI (Node) runs beside the Python bot during deep tasks;
1 vCPU because the bot is I/O bound. It bills around the clock (roughly tens of USD per month; check
the Cloud Run pricing page for asia-southeast1).

**Stop it** (keeps config and secret, stops billing for instances):
`gcloud run worker-pools update dory-bot --region asia-southeast1 --instances 0`; restart with
`--instances 1`. Remove it completely with `gcloud run worker-pools delete dory-bot --region asia-southeast1`.

## Dory command center (`/hub`)

A bilingual (Thai / English) web page in the same app and Cloud Run service, multi-guild. A TH | EN toggle in the header switches every string without a reload (choice kept in `localStorage`, default from the browser language: `th*` = Thai, else English); the dictionary is an inline JSON block in `static/hub.html` and a test checks both languages have the same keys. Anyone signs in with Google (any
verified account); a guild switcher at the top lists the servers that account administers. Per server:
the latest receipts, Dory expense Q&A as an executive, feature switches (receipts, Q&A, daily digest,
deep tasks, links and web search), receipt/ask/digest channels picked from the channel list the bot synced, the digest time and
the executive role names, and per-channel modes plus reply languages (with a server default for each). A user with no server sees a big "เพิ่ม Dory เข้า Discord" button and the two
steps: 1. add Dory to the server, 2. type `/ตั้งค่า` in Discord and open the link.

How an account becomes a guild admin, with no OAuth secret and no bot token in the web service:
`/ตั้งค่า` (owner / Administrator / Manage Server only) creates `dory_link_codes/{random 32 bytes}`
(`guild_id`, Discord user, `expires_at` = now + 15 min, `used=false`) and replies *ephemerally* with
`{DORY_HUB_URL}/hub?link=<code>`. After Google sign-in the page calls `POST /api/hub/link`; a Firestore
transaction checks the code is unused and unexpired, marks it used and adds the verified email to the
guild's `admin_emails`. The page removes `?link=` from the address bar immediately.

API (Bearer Google ID token, verified against `HUB_GOOGLE_CLIENT_ID`; 503 when that is empty):
`GET /api/hub/me`, `GET /api/hub/guilds`, `POST /api/hub/link`, and per guild
`GET|PUT /api/hub/guilds/{id}/settings`, `GET .../activity`, `POST .../ask`, all 403 unless the email is in
that guild's `admin_emails` (or is a super admin). `HUB_ADMIN_EMAILS` is now an optional comma-separated
list of super admins who see every guild and the meeting items in activity (meetings are not per guild
yet, so guild admins never see them). Saved channel ids must exist in the guild's synced channel list.

One manual setup step: in Google Cloud Console (APIs & Services, Credentials) create an
**OAuth 2.0 Client ID** of type *Web application*. Authorized JavaScript origins: the Cloud Run URL
and `http://localhost:8080`. No redirect URI or client secret is needed. Then set
`HUB_GOOGLE_CLIENT_ID` (the public client id). Optional: `DORY_DISCORD_CLIENT_ID` for the
Add-to-Discord button, `HUB_ADMIN_EMAILS` for super admins. `DORY_GUILD_COLLECTION` (default
`dory_guilds`) must match between the web service and the bot. The web service reads the same
`DORY_STORE` settings as the bot, so set `DORY_STORE=firestore` there to see the real ledger.
Deep tasks are Discord-only.

## Limitations

- Desktop Chrome/Edge only; tab-audio capture is not available on mobile or Firefox/Safari.
- Audio is uploaded in ~45 s segments, one at a time, so the live transcript lags by roughly a segment
  plus transcription time.
- Speaker labels come from the model and can drift across segments. When the host lists participants,
  every label is one of those names or "Unknown"; otherwise generic "Speaker A/B/C" labels are used and
  the summarizer maps each one to a name found in the transcript, or to "Unknown".
- A single upload is capped at 32 MB (Cloud Run request limit) and finalization at one Pub/Sub
  delivery per 600 s; very long meetings may need a larger limit.
- No authentication on the web UI or meeting API: anyone with the URL can create meetings. Add IAP or
  another front door before sharing it publicly.
- Transcription quality on overlapping speech, noisy audio or a lot of English code-switching is limited
  by the model.
- Tests are offline and mock every external service; the end-to-end paths were verified manually.

## License

Copyright (c) 2026 The Frontier Company Limited.

This project is source-available under the [PolyForm Noncommercial License 1.0.0](LICENSE.md). You may read, run and modify it for noncommercial purposes. Any commercial use requires a separate license from The Frontier Company Limited.

**Voice meeting behaviour (Live mode).** Turn-taking: `DORY_LIVE_SILENCE_MS` (1200), `DORY_LIVE_PREFIX_PADDING_MS` (300),
`DORY_LIVE_START_SENSITIVITY=high`, `DORY_LIVE_END_SENSITIVITY=low`, `DORY_LIVE_PROACTIVE_AUDIO=true`. Meetings stay voice:
`DORY_MEETING_TEXT_ECHO=false` posts no echoes, answers or join text (only the end summary, notes, and replies to typed
messages). Dory joins silently; when joined by itself and nobody addresses it within `DORY_CONSENT_DELAY_SECONDS` (20) of the
first speech it asks once (text by default) whether this is a meeting; "no" -> not_recording (nothing logged, no summary).
Notes: Live tools `post_note` / `ask_consent` / `set_recording` / `set_minutes_destination`; classic mode batches a gate every
`DORY_NOTES_BATCH_SECONDS` (60). `DORY_PERSONA_PARTICLE` (ค่ะ; old name `DORY_VOICE_PARTICLE` still works) sets the particle of typed AND spoken lines. Minutes go to the channel
named by voice/text ("ส่งมติการประชุมไปห้อง X"); later "ส่งสรุปประชุมเมื่อกี้ไปห้อง X" uses `deliver_minutes`.
`DORY_AUTO_JOIN_COOLDOWN_MINUTES` now defaults to 10 and is cleared when the channel empties.

**Listening / engaged.** A voice session is *listening* (notes only, silent) until someone says Dory's name (also misheard:
สะหลิด, สลิต, ซาลิด, ซะลิด, dory, saleed; สนิท / สิริ / Siri only as an address: greeting, particle, "น้อง", start/end of the utterance).
Then it is *engaged* and answers every utterance without the name; "ขอบคุณครับ", "พอแล้ว", "ยุติได้", "thanks, that's all" or
`DORY_ENGAGED_TIMEOUT_SECONDS` (90) of nobody addressing it return to listening. "ออกประชุม / ออกจากห้อง / ไปได้แล้ว / leave" leave the room.
In Live mode the model is told the state; if it has not started answering after the name, a cue forces a turn: `DORY_LIVE_NAME_REPLY_SECONDS` (1.5) after the speaker went quiet when the name was seen in the Live input transcript, `DORY_LIVE_FORCE_REPLY_SECONDS` for the classic transcription. A spoken "one moment" clip plays while ask_dory runs (`DORY_LIVE_FILLER`).
