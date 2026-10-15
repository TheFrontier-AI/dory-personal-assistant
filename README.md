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
server; Dory posts a short Thai welcome. (2) Post receipt photos in a channel whose name contains
`ใบเสร็จ` or `receipt`, or @mention Dory with an image/PDF in any channel: it works immediately.
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
  `/ภาษา` `/language`, `/เข้าประชุม` `/join`, `/ออกประชุม` `/leave`, `/ตั้งค่า` `/setup`). The name is recognised in
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
  server default): `th` (default, the old behaviour), `en`, or `auto` (answer in the language of the message:
  any Thai character means Thai, otherwise English; with no text, e.g. a slash command, the user's Discord
  locale). Resolution: channel override, else the guild's `default_language`; DMs use `auto`. It applies to
  everything Dory says: fixed replies (catalog in `src/dory/i18n.py`), Q&A and voice answers (system prompt),
  meeting summaries, the daily digest, receipt replies and deep-task reports. Only managers/executives may
  change it; others get a short refusal. A voice meeting uses the language of the voice channel's text chat as
  it was when the meeting started.
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

**Voice meetings (`/เข้าประชุม`, alias `/join`).** A member in a voice channel types `/เข้าประชุม` (or
`@Dory เข้าประชุม`); Dory joins, announces itself in the channel's text chat, and transcribes every speaker by
Discord name (per-user audio, so no diarization). Calling "ดอรี่ ..." out loud gets a text answer in that chat, using
the last ~5 minutes of transcript as context; the same transcript is context for text messages to Dory in that
chat ("เมื่อกี้ตกลงอะไรกัน"). `/ออกประชุม` (`/leave`), everyone leaving, or 3 hours ends it with a Thai summary
(decisions, action items with owners, open questions). Audio and transcript are kept in memory only, never stored.
Needs the **Connect** permission, the voice-states intent (non-privileged), `libopus` + `ffmpeg` (in
`Dockerfile.dory`) and `discord-ext-voice-recv` + `davey` (Discord's DAVE end-to-end encryption; see
`src/dory/meeting.py`). Toggle: hub feature `voice_meetings`.

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
   newer than the summary; outputs are capped (6,000 / 4,000 characters).

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
- **UX**: `/โหมด` off to anything else posts a one-time notice in that channel; modes are described with the
  retention in `/โหมด`; `/ความจำ` shows on/off, retention, recorded modes and import progress; the hub shows the
  same progress. Feature flags `memory` and `image_memory` per guild. `listen` mode now answers when tagged.
- `MemoryService.delete_guild(guild_id)` wipes a guild's memory; the bot does not call it on removal because it
  keeps every other guild record too (retention expires the data).

Discord setup (once, by the operator):

1. Create an application and bot at the Discord Developer Portal (name it **Dory**); copy the bot token.
2. Enable the **Message Content** and **Server Members** privileged intents. The public invite link
   (`dory_invite_url`: scopes `bot` + `applications.commands`, permissions 1166416) is built from
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
