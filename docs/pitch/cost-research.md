# Dory cost estimate: research notes (18 Oct 2026, LINE bridge added 19 Oct)

Working notes for deck slide 10 (Estimated implementation cost). Rule: every number is official price x a stated assumption; label assumptions; cite sources. No measured token usage exists yet (the bot logs `tok_in/tok_cached/tok_out/tok_thought` per answer at src/dory/bot.py:2727, but no values were collected).

## Cost drivers in the code (codebase review)

- **Cloud Run `dory-bot` worker pool**: 1 instance, 1 vCPU, 2 GiB, manual scaling, always on (scripts/deploy_dory.sh:33,139-143). Bills 24/7.
- **Cloud Run `dory-platforms` service (LINE bridge, live since 19 Oct 2026 per the team)**: min 1 / max 1 instance, `--no-cpu-throttling` (instance-based billing), 1 GiB, default 1 vCPU (scripts/deploy_platforms.sh:74-82 on origin/main). Bills 24/7. Size taken from the script, not read from the live service.
- **Cloud Run `meeting-scribe` service**: 1 vCPU, 1 GiB, max 1 instance, concurrency 20, request-based CPU (scripts/deploy.sh:72). Bills only while serving.
- **Models**: chat/briefs/meeting transcription and summary = gemini-3.5-flash; gates, day summaries, image descriptions, task/project/people listeners = gemini-3.5-flash-lite; Meet minutes synthesizer = gemini-3.1-pro-preview (3 Flash extractors first); live voice = gemini-live-2.5-flash-native-audio (us-central1); TTS = Cloud TTS Chirp 3 HD (voice Leda); embeddings = gemini-embedding-001 (256-d); images = gemini-nano-banana-2.1 (1K default); deep tasks = gemini-3-flash-preview via Gemini CLI (src/dory/config.py:37,55,62,69-80,206-207,233-240; src/meeting_scribe/config.py:25-27; agents.py:106-165).
- **Chat answer**: up to 6 tool rounds (5 spoken), max_llm_calls = rounds + 2 (qa.py:61-62,2477). Thinking LOW (chat) / MINIMAL (voice). Stable prompt first for implicit caching. Stable prompt size measured: ~15k chars (no tools) to ~56k chars (all tool families), excluding tool declarations and history.
- **Passive work**: day summaries every 30 messages or 20 quiet min (Flash-Lite, <=150 msgs/call, <=4,096 out tokens); each summary update triggers 3 Flash-Lite listener calls (tasks, projects, people); 1 Flash-Lite call per image seen; gates only in call/join modes (not listen); morning + evening brief per person on Flash (08:30/18:00, on by default).
- **Meetings**: Discord voice segments <=20 s per speaker, each transcribed with Flash; summary on leave with Flash. Meet recorder: 45 s FLAC chunks to Flash; minutes = 3 Flash extractors + 1 Pro synthesizer.
- **Live voice**: web session cap 30 min; Discord live hears the channel for the meeting (whether silence is streamed is unverified).
- **Media caps (per guild)**: images 20/day (5/user), promo kits 20/day, concept images 20/day, deep research 10/day, video ads OFF by default (10/month cap; hero/music off).
- **Embeddings**: only day-summary items + each query (cached); negligible volume.
- **Storage**: Firestore one doc per remembered message + day summaries (kept forever, retention 0); Cloud Storage receipt/document originals (if bucket set) and Meet FLAC chunks (no lifecycle rule).
- **Existing notes**: README.md:703-706 says the always-on worker costs "roughly tens of USD per month"; dory-deck.md says never show a guess.

## Official prices (read 18 Oct 2026, USD)

| Item | Price | Source |
|---|---|---|
| gemini-3.5-flash input (text/audio) / cached / output, global, <=200k | $1.50 / $0.15 / $9.00 per 1M tok | [1] |
| gemini-3.5-flash-lite input / cached / output | $0.30 / $0.03 / $2.50 per 1M tok | [1] |
| gemini-3.1-pro-preview input / output (<=200k) | $2.00 / $12.00 per 1M tok | [1] |
| Gemini Live 2.5 Flash: audio in / audio out (context re-billed every turn) | $3.00 / $12.00 per 1M tok; ~25 tok/s | [1][2] |
| Nano Banana 2.1 image | ~$0.034 (1K) / ~$0.05 (2K) per image | [1] |
| Search grounding (Gemini 3+) | 5,000 queries/month free, then $14 per 1,000 | [1] |
| Audio input | 32 tokens per second | [3] |
| Cloud TTS Chirp 3 HD | $30 per 1M chars, first 1M/month free | [5] |
| Cloud Run worker pool, asia-southeast1 (Tier 2) | $0.000013493 per vCPU-s, $0.000001482 per GiB-s; free 384,204 vCPU-s + 728,744 GiB-s/month | [6] |
| Cloud Run service, instance-based billing, asia-southeast1 | $0.0000216 per vCPU-s, $0.0000024 per GiB-s; free 240,000 vCPU-s + 450,000 GiB-s/month | [6] |
| Cloud Run free tiers | "applied as a spending based discount using Tier 1 pricing" = $5.22/month per kind (read 19 Oct 2026) | [6] |
| Cloud Run request-based, asia-southeast1 | $0.0000336 vCPU-s active, $0.0000035 GiB-s; free 180k vCPU-s, 360k GiB-s, 2M requests | [6] |
| Firestore asia-southeast1 | reads $0.0369 / writes $0.1107 per 100k, $0.1846 GiB-month; free 50k reads + 20k writes per day | [7] |
| Cloud Storage Standard asia-southeast1 | $0.02 per GiB-month (US-only free tier) | [8] |
| Pub/Sub / Secret Manager / Artifact Registry / Cloud Build | $40/TiB (10 GiB free) / $0.06 per version (6 free) / $0.10 GiB-month (0.5 free) / 2,500 min free | [9]-[12] |
| USD to THB | 33.541 (Bank of Thailand, 15 Oct 2026) | [13] |

[1] cloud.google.com/gemini-enterprise-agent-platform/generative-ai/pricing · [2] docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/2-5-flash-live-api · [3] ai.google.dev/gemini-api/docs/audio · [5] cloud.google.com/text-to-speech/pricing · [6] cloud.google.com/run/pricing · [7] cloud.google.com/firestore/pricing · [8] cloud.google.com/storage/pricing · [9] cloud.google.com/pubsub/pricing · [10] cloud.google.com/secret-manager/pricing · [11] cloud.google.com/build/pricing · [12] cloud.google.com/artifact-registry/pricing · [13] bot.or.th exchange rates

Caveats: Live model retires 13 Dec 2026; 3.1 Pro is preview; non-global endpoints +10% (meeting transcription runs in asia-southeast1, so its Flash lines are ~10% low); grounding bills per query, not per prompt; free tiers are pooled per billing account.

## Model (script: docs/pitch/cost_model.py; run `python3 -I docs/pitch/cost_model.py`)

Reference customer: one 20-person company, 22 workdays/month.

| Assumption | Low | Base | High |
|---|---|---|---|
| Questions per person per workday | 2 | 5 | 10 |
| Model calls per question (tool rounds) | 2 | 3 | 4 |
| Input tokens per call (prompt + tools + history) / share cached | 10k / 60% | 20k / 60% | 40k / 50% |
| Output tokens per call (incl. thinking) | 500 | 500 | 750 |
| Messages heard per day (memory) | 150 | 300 | 600 |
| Briefs per person per workday | 1 | 2 | 2 |
| Discord voice meeting hours per month | 8 | 17 | 35 |
| Live voice minutes per workday | 5 | 20 | 60 |
| Meet recorder hours per month | 2 | 4 | 8 |
| Images per month | 10 | 20 | 200 |

| Line item | Low | Base | High |
|---|---:|---:|---:|
| Chat answers (Gemini 3.5 Flash) | $20 | $121 | $700 |
| Memory, tasks, people (Flash-Lite) | $2 | $5 | $10 |
| Morning/evening briefs (Flash) | $7 | $14 | $14 |
| Voice meetings: transcript + minutes (Flash) | $4 | $9 | $18 |
| Live voice (Gemini Live, context re-billed x3) | $2 | $8 | $25 |
| Meet recorder: transcript + 3.1 Pro minutes | $1 | $2 | $4 |
| Images (Nano Banana 2.1, 1K) | $0 | $1 | $7 |
| Search grounding, TTS, embeddings | $0 | $0 | $0 |
| Cloud Run worker pool (1 vCPU, 2 GiB, 24/7) | $38 | $38 | $38 |
| LINE bridge: Cloud Run service dory-platforms (1 vCPU, 1 GiB, always on) | $58 | $58 | $58 |
| Cloud Run service, Firestore, Storage, Pub/Sub, Secrets, Registry | $3 | $3 | $3 |
| **Total per month (20-person company)** | **$136** | **$258** | **$876** |
| Per person per month | $6.79 | $12.90 | $43.78 |
| Total in THB (33.541/USD) | ฿4,553 | ฿8,652 | ฿29,369 |

Worker pool list price $43.25/mo, after free tier $38.03 (19 Oct: free tier now applied as the official Tier 1 spending discount; the 18 Oct figure $36.98 subtracted free seconds at Tier 2 prices). LINE service list $63.07, after free tier $57.85. Fixed floor $98.9 (62% of the Base total is Gemini). Chat cost per question: Low $0.023 (880 q/mo), Base $0.055 (2,200 q/mo), High $0.159 (4,400 q/mo)

Biggest unknown: input tokens per chat call (dominates the bill). Measure it from the `tok_in/tok_cached` log line (src/dory/bot.py:2727) before quoting a final number; an always-on demo server with light use sits near the Low column (~$99 infra, Discord bot + LINE bridge + web, plus a few dollars of AI). The fixed floor serves every company on the deployment (multi-tenant), so per-company figures here are conservative.
