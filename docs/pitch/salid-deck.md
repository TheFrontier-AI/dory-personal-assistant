# Salid: Google Cloud AI Builder Cup 2026 pitch deck

Draft v2 · 19 Oct 2026 · matches the Canva deck "Salid — AI Builder Cup 2026 pitch deck (The Frontier)" as saved on 19 Oct 2026 (15 slides, 1920×1080, from the template "The Frontier.pptx"). v1 (18 Oct) told the older "teammate that remembers, follows up and keeps secrets" story.

How to read the tags on every claim:

| Tag | Meaning |
| --- | --- |
| **[code]** | Verified in this repository (file in §8). Local `main` is commit 1cf0179; where `origin/main` (c35fed8, 19 Oct) differs, it says so |
| **[live]** | Checked against the running product on 18 Oct 2026 |
| **[team]** | Confirmed by the team, not independently checked for this document |
| **[ext]** | External source, cited in §8 |
| **Assumption** / **To validate** / **Information needed** | Not verified; must be confirmed or removed before export |

⏳ = waiting for data.

---

## 0. Hackathon rules that shape this deck [ext]

- Submit the deck as a **PDF, in English**. Also: a live URL on Cloud Run (✅ https://salid.frontier-tech.app), a public GitHub repo (✅), and a demo video (✅ https://youtu.be/a3RWpdnwCXg). The FAQ says "under 3 minutes" and the T&C say "three to four minutes", so **aim for 2:55–3:00**.
- Judging: Technical Merit & Gen AI Implementation **40%**, Problem Alignment & Impact **25%**, Innovation & Creativity **25%**, UX & Solution Design **10%**.
- Evaluation runs 19 Oct–6 Nov; finalists present at Demo Day in Singapore on 4 Dec.
- **Consequence:** judges read the deck without a presenter. Every slide must stand on its own, so its headline states the point. The speaker notes double as the video narration and the Demo Day script.

## 1. Pitch strategy

**Theme.** Accelerated Communication.

**Tagline (slides 1 and 15, video end card).** Work naturally. Stay informed. Just ask.

**Supporting line (slide 15).** Less searching. Fewer unnecessary meetings. Better coordination.

**One-sentence pitch.** Salid is an AI companion inside the chat and meetings a team already uses: anyone can just ask, by text or aloud in the middle of a meeting, what is happening and get an answer with sources; she turns talk into tasks with owners and tells each person only what they may know, in Thai and English, built on Gemini and Google ADK on Google Cloud.

**Narrative arc.**

| Beat | Message | Slide |
| --- | --- | --- |
| Problem | As teams grow, what matters gets lost in conversations | 2 |
| Cost of it | People pay in searching, catching up, status meetings and unclear ownership | 2 |
| Insight | Note-takers summarize meetings in one app; nobody answers anyone's question across chat, meetings and voice | 3 |
| Solution | Just ask: one companion keeps everyone informed, makes meetings count and keeps work moving | 4–5 |
| Experience | A day without a status meeting | 6, 11 |
| Technical innovation | An intelligence layer: one ADK agent with scope fixed in code, Gemini model routing, hybrid memory, live voice | 7–9 |
| Feasibility | About $260 a month for a 20-person team (an estimate) | 10 |
| Proof | Live on Discord, LINE and the web; 6,082 passing tests; guardrails on every AI call | 11–12 |
| Future | Slack, Telegram and WhatsApp, plus Google Workspace | 13 |

**The opening moment** (first beat of the video). Someone types *"What's the latest on the ABC launch?"* and Salid answers with owners, due dates, the one risk and links to the source messages. No status meeting needed.

**The "wow" moment** (video centrepiece, slide 6's 10:00 stop). In a Discord voice meeting someone asks *"สลิด เมื่อกี้เราตกลงอะไรกัน"* ("Salid, what did we just agree?"). Salid answers aloud. After the meeting the minutes are posted, every person receives a task card and taps **Accept**. Speech, understanding and action, all on Gemini.

**The trust moment.** A junior asks about something only managers can see. Salid does not reveal it; she asks the owner, the owner taps Approve, and the junior gets exactly that item and nothing more.

**Where each judging criterion is earned.**
- Technical merit (40%): slides 7, 8, 9, 12
- Problem fit (25%): slides 2, 3, 10
- Innovation (25%): slides 3, 9 and the voice Q&A moment
- UX (10%): slides 4, 5, 6, 11

**Words to avoid:** "revolutionary", "seamless", "AI-powered" on its own, "never", "all", "free, no limits", "only answers from what you can read" (that last one is false: managers see their juniors' work).

## 2. Ghost deck (headlines only; read top to bottom)

1. Salid · Accelerated Communication. Work naturally. Stay informed. Just ask.
2. As teams grow, what matters gets lost in conversations, and people pay in searching, catching up and status meetings.
3. Note-takers summarize meetings; Salid answers anyone's question across chat, meetings and voice, without a new app.
4. Just ask: one companion keeps everyone informed, makes meetings count and keeps work moving.
5. Work naturally: Salid listens, understands, acts and follows up, with no commands to learn.
6. A day without a status meeting: a morning brief, answers on demand, and minutes that become tasks.
7. An intelligence layer, not another platform: existing chat and voice → Cloud Run → one ADK agent on Gemini.
8. Gemini does six jobs in Salid, each on the model that fits its cost and speed.
9. The more Salid connects, the more access matters: who may know what is decided in code, not by the model.
10. About $260 a month runs Salid for a 20-person team (≈ $13 per person), and most of it is Gemini usage.
11. It's live today: a Discord teammate and a web command center, deployed on Cloud Run.
12. Built in six days with production guardrails: 6,082 passing tests and hard limits on every AI call.
13. Next: the same companion on Slack, Telegram and WhatsApp, plus Google Workspace. *(Canva still says "on Slack and LINE"; change it, LINE is live.)*
14. See it live, read the code, watch it work.
15. Work naturally. Stay informed. Just ask.

Slide order note: the template's spare slide 14 (blank) became slide 9 "Trust by design". Moving it up keeps the safety story next to the architecture.

---

## 3. Slide by slide

Design system for every slide: keep the template's black header bar with the Google Cloud / AI Builder Cup / H2S logos. Put the template's original slot label as a small grey tag (16 pt, uppercase) above a bold headline (36–40 pt, dark ink #1F2240). Body in IBM Plex Sans (Thai: IBM Plex Sans Thai), with indigo #3B3F99 and lavender #B9A9F0 as the only accent colours, taken from the product's theme. One exhibit per slide. Captions 14 pt grey. Source lines 11 pt at the bottom left.

### Slide 1 · Title (template page 1)

- **Purpose:** name, theme, value proposition, team, problem statement in five seconds.
- **On-slide text** (white area under the banner):
  - **Salid**
  - Accelerated Communication. Work naturally. Stay informed. Just ask.
  - AI companion in your team's chat and meetings · Thai & English · Gemini + Google ADK
  - Team The Frontier · Team leader: Chawin Sriviset · Theme: Future of Work & Enterprise Productivity
  - Problem statement: Enterprise knowledge is fragmented, and decisions are difficult to reuse.
- **Layout:** the template's top banner stays. Text block left-aligned in the white area. Salid's avatar (`src/meeting_scribe/static/salid/cat-avatar.webp`) at the right edge.
- **Speaker notes:** "We're The Frontier. Work happens in conversations: messages, meetings, calls. As a team grows, what matters gets scattered across them. Salid is an AI companion that lives inside the chat and meetings people already use, so anyone can just ask what is happening. Work naturally. Stay informed. Just ask."
- **Evidence:** product description [code]; team leader from the template; the problem statement is kept word for word from the registration [team].
- **Open:** full team names, if the template allows (Information needed).

### Slide 2 · Problem statement (template page 2)

- **Purpose:** make judges feel the problem and size it.
- **Headline:** As teams grow, what matters gets lost in conversations, and people pay in searching, catching up and status meetings.
- **Exhibit, left: "Where the time goes"**, four pain points:
  1. **Searching for answers:** "What price did we agree with client ABC?" means minutes of scrolling.
  2. **Catching up:** miss a day and come back to hundreds of unread messages.
  3. **Status meetings:** a meeting just to hear where the project stands.
  4. **Unclear ownership:** "I'll send it Friday" is said once, and nobody tracks who owns it.
- **Exhibit, right: "The numbers"**, four stat cards, big number on top and a source line under each:
  1. **3.3M** Thai SMEs employ **~69%** of the formal workforce. *OSMEP data via Bank of Thailand, 2025*
  2. **55%** say next steps are unclear at the end of meetings. *Microsoft Work Trend Index 2023 (31 markets)*
  3. **25%** of the workweek is spent searching for information. *Atlassian State of Teams 2025 (6 countries)*
  4. **20%** say their team has a good way to share decisions. *Atlassian State of Teams 2025*
- **Bottom line ("why now"):** 92% of Thai knowledge workers already use AI at work (*Microsoft Work Trend Index 2024, Thailand*).
- **Speaker notes:** "Work already runs on conversations, and that is where information gets lost. People search for answers, catch up on what they missed, sit in meetings just to hear status, and still don't know who owns what. A quarter of the workweek goes to searching; only one in five teams has a good way to share decisions; more than half of people leave meetings unsure of next steps. Thailand's 3.3 million SMEs employ about seven in ten formal workers, and 92% of Thai knowledge workers already use AI at work."
- **Evidence:** stats [ext] (§8). The four pain points are a **team observation** from running The Frontier on Discord; the card examples are illustrative. Atlassian (12,000 knowledge workers, 6 countries) is not Thailand-specific; WTI 2023 covers 31 markets including Thailand.
- **Wording rules:** say "formal workforce" (OSMEP's base is social-security employment), never "all jobs". Never say "Thai SMEs" for ETDA's 17.8% (it covers organisations in 10 sectors).
- **No longer on the slide** (kept in §8 for Q&A): LINE's 56 million monthly Thai users (DataReportal 2026); 88% lack time or energy (WTI 2025 Thailand).
- **Open:** target customer wording is an **Assumption** (Thai SMEs and growing teams).

### Slide 3 · Opportunities: how different, how it solves, USP (template page 3)

- **Purpose:** the insight, and why existing tools don't solve it.
- **Headline:** Note-takers summarize meetings; Salid answers anyone's question across chat, meetings and voice, without a new app.
- **Exhibit (left): comparison matrix.** Vendor pages checked 18 Oct 2026; see §4F for the cell evidence.

  | | Inside existing chat | Thai | Talk → tasks + follow-ups | Voice Q&A in meetings | Joins voice meetings | Role-aware memory |
  | --- | --- | --- | --- | --- | --- | --- |
  | **Salid** | Yes | Yes | Yes | Yes | Yes | Yes |
  | Gemini in Workspace | Yes | Partial | Partial | Partial | Yes | — |
  | Microsoft 365 Copilot | Yes | Partial | Partial | Partial | — | — |
  | Slack AI | Yes | — | — | — | Partial | Partial |
  | Otter.ai | No | No | Partial | Yes | Yes | — |
  | Read.ai | Partial | Yes | Partial | — | — | Partial |

  Legend under the table: Partial = some of it, per the vendor's own page (voice Q&A: questions are typed in a side panel or chat, not spoken) · — = not stated on the vendor's public pages (checked 18–19 Oct 2026) · Salid: Discord, LINE and the web app today; Slack, Telegram and WhatsApp bridges are built but not yet deployed.
- **Footnote (must change in Canva):** it still says "Salid: Discord today; Slack, LINE, Telegram and WhatsApp bridges are built but not yet deployed." Replace with: **"Salid: Discord and LINE today; Slack, Telegram and WhatsApp bridges are built but not yet deployed."**
- **Right, the template's three questions:**
  - **How is it different?** Not another platform: an intelligence layer inside the chat and meetings people already use.
  - **How does it solve the problem?** Listens where work happens → answers anyone who asks, with sources → turns talk into tasks and minutes → follows up.
  - **Unique selling point:** Thai-first, answers by voice mid-meeting, acts instead of only summarizing, and access enforced in code.
- **Speaker notes:** "Great AI note-takers exist, including Gemini in Google Meet. They live in one meeting app or one suite and stop at the summary. Salid is an intelligence layer inside the chat and meetings teams already use: anyone can ask, by text or by voice in the middle of a meeting, and she turns talk into tasks while respecting who may know what."
- **Evidence:** Salid row [code] (Discord voice answers when called by name: `meeting.py`, `live_voice.py`). Competitor cells [ext] (§4F).
- **Open:** the "Voice Q&A in meetings" column was filled from official vendor pages on 19 Oct 2026 (§8): only Otter's Meeting Agent takes spoken questions (Zoom first, rolling out, no languages listed); Gemini in Meet and Microsoft 365 Copilot take typed questions (Partial). If a judge raises Otter: it answers by voice too, but not in Thai and not inside the team's chat. Keep the tone respectful toward Gemini in Workspace: position Salid as reaching teams *outside* Workspace, not as beating it.

### Slide 4 · List of features (template page 4)

- **Purpose:** what she does, grouped into five jobs (no feature dump).
- **Headline:** Just ask: one companion keeps everyone informed, makes meetings count and keeps work moving.
- **Exhibit:** five equal cards, each with a title, two lines and an example:
  1. **Just ask.** By text or voice: "What's the latest on our project?" "What did I miss?" Answers link to the source. *Example: "What decisions have been made?" → answer + links*
  2. **Better meetings.** Captures decisions and action items, posts minutes. Ask aloud mid-meeting in Discord voice; she answers when called by name. *Example: "Salid, what did we just agree?" → spoken answer*
  3. **Who's doing what.** Tasks heard in chat and meetings get an owner and a due date. Accept / Edit / Decline cards, nudges, a morning brief. *Example: "Who is working on what?" → owners + due dates*
  4. **Knows the company.** Wiki, documents, people and roles, projects with progress, plus cited web search for research. *Example: "Who knows our VAT process?" → the right person*
  5. **No new app.** Canva text: "Discord text and voice plus the web app today, in Thai and English. Slack and LINE are built and come next." **Change to:** "Discord text and voice, LINE and the web app today, in Thai and English. Slack, Telegram and WhatsApp are built and come next." *Example: @Salid in a channel, or "Salid" in a voice room*
- **Footer strip:** Also: receipts → expense ledger · web command center · 9 languages · images and slide decks · reminders, votes, approvals.
- **Speaker notes:** "Just ask. By text or voice, anyone can ask what is happening and get an answer with a link to the source. In meetings she captures decisions and action items and answers aloud when called by name. Tasks heard in conversation get an owner and a due date. She knows the company's wiki, documents and people, and searches the web with citations. And there is no new app: she lives in Discord and LINE today, with Slack, Telegram and WhatsApp built and coming next." (Canva notes still say "Discord today, with Slack and LINE built"; update them.)
- **Evidence:** [code] `search.py` `search_everything` and `catchup.py` `catch_up` (answers with sources, "what did I miss"); `projects.py` `project_show` and `progress.py` (project status); `meeting.py` + `live_voice.py` (voice answers when called by name) and `meeting_scribe` (Meet recorder); `TaskTracker` + `task_handshake.py` (owners, due dates, Accept / Edit / Decline) and `coo_tools.py` `my_day`; `wiki.py`, `library.py`, `people_tools.py` `who_to_ask`, `web_search.py` (Google-grounded, cited); receipts ledger (`extract.py`, `store.py`) under "Also"; i18n (9 languages). LINE live [team]; bridges in `src/salid/platforms/` and, on `origin/main`, `scripts/deploy_platforms.sh` (the Canva note "no deploy script" is out of date). Examples are illustrative.

### Slide 5 · Process flow (template page 5)

- **Purpose:** show how it works for a user in one glance.
- **Headline:** Work naturally: Salid listens, understands, acts and follows up, with no commands to learn.
- **Exhibit:** four chevrons (§4B) with an example lane below.
  1. **Listen:** chat, files and voice in channels Salid may read.
  2. **Understand:** Gemini reads; memory keeps day summaries and embeddings.
  3. **Act:** the ADK agent picks from up to 171 tools, with scope fixed in code.
  4. **Follow up:** task cards, nudges, a morning brief and an evening report.
  - Example lane, labelled *illustrative*: in a meeting, "Ploy will send the quote by Friday." → Salid hears a task: owner Ploy, due Friday → Ploy gets a task card and taps **Accept** → it stays in her morning brief until done; the evening report shows it finished.
  - Closing line: the same flow answers questions: "Who is working on the ABC launch?" → owners, due dates and links to the source.
- **Speaker notes:** "Nobody types a command. People talk the way they always do; Salid listens, understands, acts, and keeps following up until the work is done. The same loop answers questions: ask who is working on something and she replies with owners, due dates and links."
- **Evidence:** [code] memory scheduler → `TaskTracker` (action items → tasks) → task handshake cards; briefings (morning brief); reports (evening report); `coo_tools.py` `list_tasks` and `my_day`; `search.py` `search_everything`; tool count from `SecretaryBot._agent_kwargs` plus `qa.ask_async` (counted at 1cf0179).
- **Change from v1:** the "55% say next steps are unclear" proof line moved to slide 2.

### Slide 6 · Wireframes / mock diagrams → "A day without a status meeting" (template page 6)

- **Purpose:** the user experience, as a story (UX 10%).
- **Headline:** A day without a status meeting: a morning brief, answers on demand, and minutes that become tasks.
- **Exhibit:** a horizontal timeline with five mock-up stops:
  - **08:30 Morning brief:** "Good morning! Today: send the ABC quote (due Fri), review the Q4 budget, 1:1 at 14:00."
  - **10:00 Voice meeting:** You: "Salid, what did we just agree?" Salid, aloud: "Launch on 1 Nov. Ploy sends the quote by Friday."
  - **10:45 Minutes + task cards:** "Task for Ploy: send the quote to ABC, due Friday." [Accept] [Edit] [Decline]
  - **14:00 No status meeting:** You: "Where are we on the ABC launch?" Salid: "On track. Ploy sent the quote; design is due Wed. One risk: the launch date."
  - **18:00 Evening report:** "For leaders: 5 tasks done, 2 overdue, ฿8,400 spent, 1 risk: the ABC launch date."
- **Caption:** Mock-up of real flows; times, names and amounts are illustrative. Real screens are on the snapshots slide.
- **Speaker notes:** "A day with Salid. At 8:30 each person gets a morning brief in their private Salid channel: what to focus on today. At 10:00, in the voice meeting, someone asks 'Salid, what did we just agree?' and she answers aloud. After the meeting the minutes are posted and each person gets a task card to accept. At 14:00, instead of calling a status meeting, someone just asks where the ABC launch stands and gets owners, dates and the one risk. At 18:00 leaders get the evening report."
- **Evidence:** [code] `briefings.py` and `coo_tools.py` `my_day` (morning brief), `meeting.py` + `live_voice.py` (voice answers), `task_handshake.py` (Accept / Edit / Decline), `projects.py` `project_show` + `progress.py` and `search.py` (status answers with sources), `reports.py` (evening report in a private leadership channel).
- **Open:** none (real screens are on slide 11).

### Slide 7 · Architecture diagram (template page 7)

- **Purpose:** credibility; judges should see a real, Google-native system.
- **Headline:** An intelligence layer, not another platform: existing chat and voice → Cloud Run → one ADK agent on Gemini.
- **Exhibit:** the draw.io diagram with the official Google Cloud icon set, `docs/pitch/assets/salid-architecture.drawio` (export `salid-architecture.drawio.png`); spec in §4A. Legend: solid arrow = request · dashed arrow = asynchronous · dashed grey card = built but not deployed, or planned.
- **Updated 19 Oct (Canva draft):** LINE is a solid card with its own Cloud Run service `salid-platforms` (webhook arrow); Slack · Telegram · WhatsApp stay dashed; the brain box adds "One brain for Discord, LINE and the web app". Regenerate with `docs/pitch/assets/salid-architecture.gen.py` (needs the official icon folders as arguments).
- **Source line (on slide):** codebase review (`scripts/deploy_salid.sh`, `scripts/deploy_platforms.sh`, `scripts/deploy.sh`, `salid/qa.py`, `salid/config.py`); drawn in draw.io with the official Google Cloud icon set.
- **Speaker notes:** "Cloud Run runs it: an always-on worker pool for the Discord bot and voice, a web service for the command center and the Meet recorder, and the LINE bridge. All of them run the same brain: a Google ADK agent on Gemini that is built for each request with only the tools and data that person may use. Memory, ledger and tasks live in Firestore; files in Cloud Storage. The Meet recorder's finalize step goes through Pub/Sub with OIDC, and the meeting summary is an ADK multi-agent graph: three Flash agents in parallel, then Gemini 3.1 Pro."
- **Evidence:** [code] `scripts/deploy_salid.sh` (worker pool `salid-bot`, 1 instance), `scripts/deploy.sh` (service `meeting-scribe`, max 1 instance, Pub/Sub push, OIDC), `Dockerfile.salid`, `salid/qa.py` (`build_agent`), `meeting_scribe/agents.py`, `salid/config.py` models; on `origin/main`, `scripts/deploy_platforms.sh` deploys the bridges as Cloud Run service `salid-platforms` (1 instance, CPU always allocated, 1 GiB). [live] the product URL returned 200 on 18 Oct 2026. LINE live [team]. Calendar / Gmail / Drive: connectors marked coming soon.
- **Open:** confirm the worker pool is running now (CLAUDE.md says deployed 17 Oct; not checked on Cloud Run). Confirm which Cloud Run workload serves LINE in production (`salid-platforms` per the script; To validate).

### Slide 8 · Technologies to be used (template page 8)

- **Purpose:** the Gen-AI depth slide (40% criterion).
- **Headline:** Gemini does six jobs in Salid, each on the model that fits its cost and speed.
- **Exhibit:** routing table.

  | Job | Google technology | Why this one |
  | --- | --- | --- |
  | Think & act | Gemini 3.5 Flash in a Google ADK `LlmAgent` | Fast tool calling; a fresh agent per request |
  | Gate, summarize, read docs | Gemini 3.5 Flash-Lite | High volume at low cost |
  | Meeting minutes | ADK Sequential → Parallel (3 × Flash) → Gemini 3.1 Pro | Quality where it matters |
  | Talk live | Gemini Live 2.5 Flash native audio | Real-time speech; hands hard questions to the full agent |
  | Remember | gemini-embedding-001 (256-d) + keyword search, fused by RRF | Finds Thai and English by meaning |
  | Create | Nano Banana 2.1 | Images and promo cards |

- **Strip below:** Also: Cloud TTS Chirp 3 HD (Thai voice) · Google Search grounding · URL context · Gemini CLI · Cloud Run · Firestore · Cloud Storage · Pub/Sub · Secret Manager · Cloud Build · Google Sign-In
- **Callout (lavender box):** "Stable prompt first, so Gemini's implicit context caching can reuse it (Google: 90% discount on cached tokens)."
- **Footnote:** Models served on Gemini Enterprise Agent Platform (formerly Vertex AI). Gemini 3.1 Pro is in public preview.
- **Speaker notes:** "We route each job to the right Gemini model. Flash thinks and calls tools; Flash-Lite handles high-volume checks and summaries; the meeting summarizer is a real ADK multi-agent graph, with three Flash agents in parallel and Gemini 3.1 Pro to synthesize; Gemini Live gives her a voice; embeddings plus keyword search give her a memory in Thai and English."
- **Evidence:** [code] `salid/config.py` defaults (`gemini_model` gemini-3.5-flash, `gate_model` gemini-3.5-flash-lite, `live_model` gemini-live-2.5-flash-native-audio in us-central1, `embed_model` gemini-embedding-001 at 256 dims, `image_model` gemini-nano-banana-2.1), `meeting_scribe/agents.py` (SequentialAgent → ParallelAgent → synthesizer on gemini-3.1-pro-preview), `qa.py` (stable / volatile prompt split, RRF_K = 60 hybrid search), `embed.py`, `live_voice.py`, `speech.py`; [ext] model pages, ADK docs, caching docs. The Live model retires 13 Dec 2026 (successor gemini-3.8-live).
- **Open:** none.

### Slide 9 · Trust by design (template spare page 14, moved up)

- **Purpose:** the differentiator most competitors don't show; answers "can a company trust this?", and why it matters more as Salid connects more chat apps.
- **Headline:** The more Salid connects, the more access matters: who may know what is decided in code, not by the model.
- **Exhibit:** three rules, each with a mini diagram (§4D) and a code label:
  1. **Scope before the AI runs.** Company and caller are bound in code. They are never tool parameters the model could change. *`LedgerTools(guild_id, forced_submitter_id)`*
  2. **Answer for the whole room.** A channel's memory is used only if the asker *and everyone who will read the reply* can read that channel. *reply audience ⊆ viewers of the source channel*
  3. **Rank and consent.** Higher roles see lower roles' work, never the reverse. A hidden item unlocks only when its owner taps **Approve**, and only for that person. *`DisclosureButton` → unlocked for one grantee*
- **Bottom strip:** Meetings and emails need a second confirmation · No Administrator permission requested · Discord voice audio is never stored.
- **Source line (on slide):** codebase review (`qa.py`, `memory_access.py`, `disclosure.py`, `coo.py`, `secretary.py`, `app.py`, `meeting.py`).
- **Speaker notes:** "The model never decides what it may read. Before it runs, code fixes the company, the person and the audience of the answer. A junior can't extract a manager's discussion, and a secret is only shared when its owner says yes."
- **Evidence:** [code] `qa.py` binds `LedgerTools(guild_id, forced_submitter_id)` and `MemoryTools` to allowed channels per request (tenant and submitter are in no tool schema); `memory_access.py` `allowed_channel_ids` (audience ⊆ viewers) and `hierarchy_authors` (asker and every audience member must outrank the author); `disclosure.py` + `coo.py` `DisclosureButton` (only the owner approves; `unlocked_ids` unlocks exactly those messages for one grantee); `secretary.py` (meetings and email need the same request again within 30 minutes); `app.py` (Discord permission integer has no Administrator bit); `meeting.py` (Discord voice audio not persisted).
- **Do not say:** "no files stored" (receipts and documents are archived in Cloud Storage) or "transcripts are discarded" (voice transcripts are kept as text in team memory).

### Slide 10 · Estimated implementation cost (template page 9)

- **Purpose:** feasibility and adoptability: what one team pays per month.
- **Headline:** About $260 a month runs Salid for a 20-person team (≈ $13 per person), and most of it is Gemini usage.
- **Exhibit, top: three scenario cards** (20 people, 22 workdays):

  | Scenario | Per month | Per person | In THB |
  | --- | ---: | ---: | ---: |
  | Light · 2 questions a day each | ≈ $140 | ≈ $7 | ≈ ฿4,600 |
  | **Typical · 5 questions a day each** | **≈ $260** | **≈ $13** | **≈ ฿8,700** |
  | Heavy · 10 questions a day each | ≈ $880 | ≈ $44 | ≈ ฿29,400 |

- **Exhibit, bottom: "Where a typical month goes"** (US$, rounded; bars split Gemini pay-per-use vs fixed infrastructure):

  | Line | Model / service | $ |
  | --- | --- | ---: |
  | Answers to questions | Gemini 3.5 Flash | 121 |
  | Always-on Discord bot + LINE bridge | Cloud Run worker pool `salid-bot` (1 vCPU, 2 GiB, 24/7) $38 + service `salid-platforms` (1 vCPU, 1 GiB, always on) $58 | 96 |
  | Morning & evening briefs | Gemini 3.5 Flash | 14 |
  | Meeting transcripts & minutes | Flash + 3.1 Pro (Discord voice $9 + Meet recorder $2) | 11 |
  | Live voice | Gemini Live 2.5 | 8 |
  | Memory, tasks & people | Flash-Lite | 5 |
  | Web app & data | Cloud Run service, Firestore, Storage, Pub/Sub, Secrets, Registry | 3 |
  | Images | Nano Banana 2.1 | 1 |

  Google Search grounding, Text-to-Speech and embeddings: $0, inside Google's monthly free tiers at this volume.
- **"What drives the bill":** 62% is Gemini usage, so cost grows with use, not with seats · fixed floor ≈ $100 a month (always-on Discord bot, LINE bridge, web app), shared by every company on the service · biggest unknown: tokens per answer; we measure it from the bot's token log before quoting a price.
- **Assumptions line (on slide):** 22 workdays; ~3 model calls per question at ~20k input tokens each (60% cached); 2 briefs per person a day; 17 h of voice meetings and 20 min of live voice a day; 20 images a month. Light and heavy scale usage down and up.
- **Source line (on slide):** official Google Cloud pricing pages (Gemini Enterprise Agent Platform, Cloud Run asia-southeast1, Firestore, Cloud Storage, Text-to-Speech), read 18–19 Oct 2026; ฿33.541 per US$ (Bank of Thailand). Model: `docs/pitch/cost_model.py`. **An estimate, not a measured bill.**
- **Speaker notes:** "For a 20-person company Salid costs about $260 a month at typical use, roughly $13 per person. Light use is about $140, heavy use about $880. Gemini usage is about three fifths of the typical bill, so cost follows value rather than headcount. The fixed floor is about $100: the always-on Discord bot, the always-on LINE bridge and the web app, shared by every company on the same service, so this per-company figure is conservative. The biggest unknown is how many tokens each answer uses, so before quoting a customer price we measure it from the bot's own token log."
- **Method and evidence:** official price × stated usage assumption, every line in `docs/pitch/cost-research.md` (prices, sources [1]–[13], the low / base / high assumption table) and `docs/pitch/cost_model.py` (`python3 -I docs/pitch/cost_model.py`). Model totals $136 / $258 / $876 a month, shown rounded as ≈ $140 / $260 / $880; per person $6.79 / $12.90 / $43.78; chat cost per question $0.023 / $0.055 / $0.159. Key prices: Gemini 3.5 Flash $1.50 in / $0.15 cached / $9.00 out per 1M tokens; Flash-Lite $0.30 / $2.50; 3.1 Pro preview $2 / $12; Gemini Live audio $3 in / $12 out; worker pool 1 vCPU, 2 GiB, 24/7 = $43 list, $38 after free tier; LINE service (instance-based, $0.0000216 per vCPU-s, $0.0000024 per GiB-s) 1 vCPU, 1 GiB = $63 list, $58 after free tier; free tiers are a spending-based discount at us-central1 prices. Infrastructure sizes [code] `scripts/deploy_salid.sh`, `scripts/deploy_platforms.sh` (origin/main), `scripts/deploy.sh`.
- **Labels:** usage per scenario is an **Assumption** (no measured token usage yet; the bot logs `tok_in` / `tok_cached` / `tok_out` / `tok_thought` per answer, but no values were collected). Caveats: the Live model retires 13 Dec 2026; 3.1 Pro is preview; meeting transcription runs on a regional endpoint (+10%, so its Flash lines are slightly low); tool declarations may push input tokens above the 20k assumption; free tiers are pooled per billing account.
- **Open:** the LINE service size comes from `scripts/deploy_platforms.sh` (min 1 instance, CPU always allocated, 1 GiB, default 1 vCPU), not from the live service (To validate with `gcloud run services describe salid-platforms`; needs project access).

### Slide 11 · Snapshots of the prototype (template page 10)

- **Purpose:** proof it exists.
- **Headline:** It's live today: a teammate in Discord and LINE, plus a web command center, all on Cloud Run.
- **Exhibit:** six real screenshots, each with a one-line caption:
  1. Landing page (live): salid.frontier-tech.app
  2. Command center: company profile (sample data)
  3. Command center: filing cabinet (sample data)
  4. LINE: Chat with Salid on Apple Watch
  5. Discord: Task cards with Accept / Edit / Decline
  6. Discord: Minutes of meeting (sample data)
- **Caption (on slide):** Command-center shots use the built-in sample-data preview; replace them with signed-in screens if available. Blur real names, emails and avatars.
- **Speaker notes:** "Everything on this slide is the working product: the landing page and command center at salid.frontier-tech.app, Salid in a LINE chat on an Apple Watch, and in Discord the task cards and the minutes she posts after a voice meeting. All of it runs on Cloud Run." Presenter note: LINE takes text, images and files; do not say Salid hears LINE voice messages.
- **Evidence:** [live] landing page captured 18 Oct 2026; command-center shots from `/center?mock=1` (sample data, mock bar cropped); LINE, task-card and minutes screenshots from the team [team].
- **Resolved 19 Oct:** the LINE bridge reads text, images and files and has no audio-message handling (`src/salid/platforms/line.py` on `origin/main`), so the caption now reads "LINE: Chat with Salid on Apple Watch".

### Slide 12 · Prototype performance report / benchmarking (template page 11)

- **Purpose:** engineering credibility without invented metrics.
- **Headline:** Built in six days with production guardrails: 6,082 passing tests and hard limits on every AI call.
- **Exhibit:** six KPI tiles:
  - **6,082** automated tests passed, 0 failed (offline suite, every external service mocked; 7 skipped). Full offline run in 3 min 52 s on a laptop, 18 Oct 2026, commit 1cf0179.
  - **6 days** · 13–18 Oct 2026: 354 commits and 78 merged pull requests
  - **120 s** answer deadline · 60 s per model call · automatic retries on 408 / 429 / 5xx
  - **≤ 10** tool rounds per typed answer (5 when spoken), then tools are removed, so she always answers (`qa.py` `MAX_ROUNDS` / `SPOKEN_MAX_ROUNDS` on `origin/main`, PR #55)
  - **2 s:** if meaning search is slow, she falls back to keyword search
  - **25 min** real Thai meeting: 34 audio chunks, 309 utterances transcribed with speaker labels
- **Honest line:** Not yet measured: production response time, usage, retrieval quality.
- **Source line (on slide):** offline pytest run on 18 Oct 2026; git history; `salid/config.py`, `llm.py` and `qa.py`; recorded meeting e6379be86dfd (project notes). 69 live tests against real Google Cloud exist but were not run for this deck.
- **Speaker notes:** "We don't have user metrics yet, so here's what we can prove: a large automated test suite, strict limits on every AI call, and a real 25-minute Thai meeting processed end to end, which is how we found and fixed a speaker-label drift bug."
- **Evidence:** [code] `uv run pytest -q` on 18 Oct 2026 (6,082 passed, 7 skipped, 69 deselected live, 0 failed), git history (first commit 13 Oct 2026), `config.py` (`answer_timeout_seconds` = 120), `llm.py` (`REQUEST_TIMEOUT_MS` = 60000, `with_retry`), `qa.py` (`MAX_ROUNDS` = 6 at 1cf0179, the 2 s fallback); CLAUDE.md reference meeting `e6379be86dfd`.
- **Open:** see the QC checklist for two items that keep the slide text unchanged but must be tracked (2 order-dependent test failures being fixed; tool-round limit changed on `origin/main`). Optional measured latency, if the team approves reading production logs.

### Slide 13 · Additional details / future development (template page 12)

- **Purpose:** show momentum and an honest boundary between built and next.
- **Headline (change in Canva):** Next: the same companion on Slack, Telegram and WhatsApp, plus Google Workspace. *(Canva still says "on Slack and LINE".)*
- **Badge (change in Canva):** "Live today on Discord" → "Live today on Discord and LINE".
- **Exhibit:** three phase columns:
  - **Phase 1 · Built — Core intelligence:** meeting intelligence, enterprise knowledge, document intelligence, project intelligence, workflow automation (tasks, approvals, reminders). LINE bridge live since 19 Oct 2026 [team].
  - **Phase 2 · Next — Everywhere:** deploy the Slack, Telegram and WhatsApp bridges (built; deploy script exists); wire Google Calendar / Meet scheduling (code exists); Gmail and Drive connectors.
  - **Phase 3 · Later — Scale & trust:** run more than one instance; measure retrieval quality; self-service "forget me" and data export; move live voice to the successor model before 13 Dec 2026; authentication on the recorder API.
- **Closing line (change in Canva):** "Most of what we first planned as phases 2 and 3 already works. Next, the same companion goes to every chat app small teams use, starting with LINE." → "... Next, the same companion goes to more chat apps small teams use: Slack, Telegram and WhatsApp."
- **Before / after for the team:** the template's draft had Document + Project Intelligence as Phase 2 and Workflow Automation + Multi-Agent as Phase 3. Most of that is already built, so leaving it there undersells the product.
- **Speaker notes:** "Most of what we planned as phases two and three already works, and since 19 October she is live on LINE as well as Discord. Next, the same brain goes to Slack, Telegram and WhatsApp and plugs into Google Workspace."
- **Evidence:** [code] built: `docs.py`, `library.py`, `projects*.py`, `progress.py`, `task_handshake.py`, `approvals.py`, `reminders.py`, ADK multi-agent summarizer in `meeting_scribe/agents.py`. Next: `src/salid/platforms/` and `scripts/deploy_platforms.sh` (`origin/main`); `google_tools.py` docstring says "not wired into any bot yet", but on `origin/main` `platforms/calendar_glue.py` offers the Calendar tools on the platform bridges (PR #44), not on Discord; `connectors/__init__.py` lists Drive / Gmail / Calendar as coming soon; deploy scripts pin one instance; risk register lists no forget-me / export and unmeasured retrieval quality; [ext] Live model retirement date; recorder API has no auth (known limitation).

### Slide 14 · Links (template page 13)

- **Headline:** See it live, read the code, watch it work.
- **On-slide text**, three rows, each with a QR code:
  - Live product (Cloud Run): https://salid.frontier-tech.app [live]
  - Public GitHub repository: https://github.com/CU-DrAgon/agentic-coworker-assistance [live]
  - Demo video (3 minutes): https://youtu.be/a3RWpdnwCXg · "YouTube: Demo Video: Salid (an AI companion)"
- **Evidence:** product and repo returned HTTP 200 on 18 Oct 2026; their QR codes were generated with segno and decoded with OpenCV to the exact URLs.
- **Open:** decode the video QR code to confirm it opens https://youtu.be/a3RWpdnwCXg (To validate); the Canva link text shows a long `youtube.com/watch?...&feature=youtu.be` form and the link carries a `?si=` share parameter, consider the short URL. Canva notes still say "the demo video link is still needed"; update them. The video's real length is Information needed (the label says 3 minutes).

### Slide 15 · Close (template page 15)

- **On-slide text:** **Work naturally. Stay informed. Just ask.** · salid.frontier-tech.app · Less searching. Fewer unnecessary meetings. Better coordination.
- **Speaker notes:** "Work happens in conversations. Salid makes them count: anyone can just ask, meetings end with owners and dates, and people get answers without another status meeting, on Gemini and Google ADK on Google Cloud. Work naturally. Stay informed. Just ask."

---

## 4. Diagram specifications

### 4A · Architecture (slide 7; source `docs/pitch/assets/salid-architecture.drawio`)

Four vertical lanes, left to right. Boxes are rounded rectangles; arrows are left to right.

1. **Users & channels** (white boxes)
   - Discord: team text and voice rooms (solid)
   - Web app: command center, PM, Meet recorder (solid)
   - LINE (solid, live since 19 Oct 2026 [team]) *(the current file still groups it with the dashed card; change it)*
   - Slack · Telegram · WhatsApp (dashed, "bridges built, not yet deployed")
2. **Cloud Run · asia-southeast1**
   - `salid-bot` worker pool: Discord gateway and voice (solid)
   - `meeting-scribe` service: web app, APIs, Meet recorder (solid)
   - LINE bridge: Cloud Run service, `salid-platforms` per `scripts/deploy_platforms.sh` (solid; production name To validate)
   - All arrow into a central box: **Salid brain = Google ADK agent, built for each request · up to 171 tools: memory, tasks, ledger, meetings, web · company, person and audience fixed in code, never by the model · meeting minutes: Sequential → Parallel ×3 Flash → Gemini 3.1 Pro**
3. **AI on Google Cloud: Gemini Enterprise Agent Platform** (formerly Vertex AI)
   - Gemini 3.5 Flash · Flash-Lite (answers and tool calls · fast checks)
   - Gemini 3.1 Pro (meeting synthesis, preview)
   - Gemini Live 2.5 native audio (real-time voice, us-central1)
   - gemini-embedding-001 (memory search by meaning)
   - Google Search grounding (cited web answers · URL context)
   - Nano Banana 2.1 (images and promo cards) · Cloud Text-to-Speech (Chirp 3 HD voices, Thai included)
4. **Data**
   - Firestore: memory, ledger, tasks, orgs
   - Cloud Storage: recordings, receipts, files
   - Pub/Sub: meeting finalize, push with OIDC
   - Secret Manager: bot token, webhook URL

Planned items, as dashed grey cards: Google Calendar · Gmail · Drive.

Reads in 10 s: "existing chat and voice → Cloud Run → ADK + Gemini → Firestore".

### 4B · Process flow (slide 5)

Four chevrons, **Listen → Understand → Act → Follow up**, each with an icon (ear, sparkle, gear, bell) and one line of text. Beneath them, a thin swim lane for the illustrative example, with small UI chips: a chat bubble, a task card with an Accept button, and a ✅ in the report.

### 4C · AI workflow: voice meeting → tasks (slide 6 inset or backup)

Discord voice → per-speaker segments (cut at 1.2 s of silence, ≤ 20 s; the speaker is known from Discord, so no diarization) → Gemini transcription → text into team memory.

The wake word "สลิด …" → Gemini Live answers aloud and calls `ask_salid` for anything that needs data.

On leave: summary → action items → task cards → **Accept** → morning brief / evening report.

### 4D · Trust flow (slide 9)

Three mini panels:
1. A lock on a tool icon: "company + person bound in code".
2. A Venn diagram: "people who can read the source channel" ⊇ "everyone in the reply channel" → allowed.
3. A sequence: junior asks → Salid DMs the owner with [Approve] [Decline] → Approve → that one item is shown to that junior only.

### 4E · Meeting Scribe multi-agent (slide 8 inset, optional)

`SequentialAgent` [ `ParallelAgent` [decisions · action items · speaker names] (Gemini 3.5 Flash) → synthesizer (Gemini 3.1 Pro) ] → a code check (any name not in the participant list becomes "Unknown") → Firestore → Discord embed + transcript.

### 4F · Comparison matrix evidence (slide 3)

| Cell | Source (checked 18 Oct 2026) |
| --- | --- |
| Gemini in Workspace, Thai Partial | Workspace language table: Thai available for the Gemini app, the side panel and Meet translation, but "Take notes for me" lists no Thai |
| Gemini, tasks Partial | Meet notes include "next steps"; follow-up not stated |
| M365 Copilot, Thai Partial | Thai in Copilot's work/school language list; Teams recap language not stated |
| Slack AI, role-aware Partial | "AI-generated responses only include information available to you"; huddle summaries Partial |
| Otter.ai, Thai No | Pricing page: transcription in English, Spanish, French, German, Japanese, Chinese |
| Read.ai, Thai Yes | Read.ai blog: Thai added |
| Gemini, Voice Q&A Partial | Ask Gemini in Meet: "Enter questions about the meeting" in a text box; no voice; languages listed exclude Thai (support.google.com/meet/answer/16024610, 19 Oct 2026) |
| M365 Copilot, Voice Q&A Partial | Copilot in Teams meetings: questions in the compose box; Facilitator answers @mentions in the meeting chat (support.microsoft.com, "Use Copilot in Microsoft Teams meetings" and "Facilitator in Microsoft Teams meetings") |
| Slack AI, Voice Q&A — | Huddle AI = notes and transcript only (slack.com/help/articles/31377193680019) |
| Otter.ai, Voice Q&A Yes | Otter Meeting Agent: "voice-activated AI meeting agent … responding to queries" (otter.ai blog, 25 Mar 2025; Zoom first, rolling out, no languages listed) |
| Read.ai, Voice Q&A — | Ask Read searches meetings after they happen; no live Q&A stated (read.ai/assistant) |
| Salid, Voice Q&A in meetings Yes | [code] `meeting.py`, `live_voice.py` (answers aloud in Discord voice when called by name) |

Full URLs are in §8.

### 4G · Before / after (optional)

| Before | After |
| --- | --- |
| Scroll for the decision | Ask Salid, get a link |
| Come back to hundreds of unread messages | "What did I miss?" |
| A status meeting to hear where things stand | "Where are we on the ABC launch?" |
| Chase people | Cards + nudges |
| Know-how leaves | Handover from memory |

---

## 5. Screenshots and assets

| # | Asset | For | Status |
| --- | --- | --- | --- |
| 1 | Landing page hero | 11 | ✅ on slide 11 · `docs/pitch/assets/landing-hero.png` |
| 2 | `/center` company profile and filing cabinet | 11 | ✅ on slide 11 · `docs/pitch/assets/center-overview-mock.png`, `center-documents-mock.png` (from `?mock=1`, sample data; a signed-in shot with real data is better if the team has one) |
| 3 | LINE: chat with Salid on Apple Watch | 11 | ✅ on slide 11 [team] (caption check in §3 slide 11) |
| 4 | Discord task cards with Accept / Edit / Decline | 11, video | ✅ on slide 11 [team] |
| 5 | Discord minutes after a voice meeting | 11, video | ✅ on slide 11 (sample data) [team] |
| 6 | "What's the latest on the ABC launch?" answered with source links | video, Demo Day backup | needed for the video's opening scene |
| 7 | Consent DM with Approve / Decline | video, Demo Day backup | needed |
| 8 | "What did I miss?" answer | video | needed |
| 9 | Evening report in `รายงานจากสลิด` | Demo Day backup | optional (slide 6 is a mock-up) |
| 10 | Receipt photo → recorded-receipt reply | video ("also" moment) | optional |
| 11 | `/pm` project cards with the two progress bars | Demo Day backup | optional, not on the current slides |
| 12 | Salid avatar | 1 | ✅ `src/meeting_scribe/static/salid/cat-avatar.webp` |
| 13 | Architecture diagram | 7 | ✅ `docs/pitch/assets/salid-architecture.drawio(.png)`, needs the LINE update |

Rules: crop to 16:9 or 4:3; use demo data; blur real names, emails and avatars; never show the `run.app` URL (keep it private); show the custom domain only. All materials must be in English, so add English captions to Thai screenshots.

---

## 6. Demo video script (target 2:55, English narration, English subtitles over Thai)

Published video: **https://youtu.be/a3RWpdnwCXg** (linked on slide 14). Information needed: whether the published cut already follows this script and its exact length. If it runs over 3:00, trim it; if it still tells the receipts-first story, re-cut it to this script.

Setup before recording:
- Use **The Frontier** server. It is linked to an org licence; a new, unlicensed server has every feature switched off.
- Company language English, the presenter's personal language Thai. Salid then answers in both, which shows the bilingual feature and keeps the video in English.
- Seed: an "ABC launch" project in `/pm` with owners, due dates and one risk; a few days of chat that mention it; a managers-only channel with one topic; one member who was away for a day (for the catch-up scene).
- Thai lines below are illustrative. Salid speaks with the female particle ค่ะ / คะ, never ครับ. Never script her replies: record what she actually says.

| Time | Scene | Narration (English) |
| --- | --- | --- |
| 0:00–0:08 | **Hook.** A busy Discord server scrolls past; overlay "Work happens in conversations." | "As teams grow, what matters gets lost in conversations." |
| 0:08–0:35 | **Just ask.** Someone types "@Salid What's the latest on the ABC launch?" → she replies with status, owners, due dates and the one risk, each with a link to the source message | "Anyone can just ask. Salid answers from the team's chat, meetings and projects, with links to the source. No status meeting needed." |
| 0:35–1:15 | **Wow: voice Q&A mid-meeting.** Three people talk in a Discord voice room; one asks "สลิด เมื่อกี้เราตกลงอะไรกัน" ("Salid, what did we just agree?") → Salid answers aloud, e.g. "ตกลงเปิดตัววันที่ 1 พฤศจิกายนค่ะ พลอยจะส่งใบเสนอราคาให้ ABC ภายในวันศุกร์ค่ะ" ("We agreed to launch on 1 November. Ploy sends ABC the quote by Friday.") | "In the middle of a meeting, just ask out loud. She answers by voice, in Thai or English." |
| 1:15–1:45 | **Minutes → task card.** Leave the room → minutes posted in the channel → Ploy gets a task card and taps **Accept** → the giver gets a one-line confirmation | "When the meeting ends, the minutes are posted, and every action item becomes a task card its owner accepts with one tap." |
| 1:45–2:05 | **What did I miss?** A teammate back from a day off types "What did I miss?" (or `/catchup`) → a short list of decisions, their tasks and meetings since they left | "Back from a day off? Ask what you missed: only from the rooms you can read." |
| 2:05–2:35 | **Trust.** A junior asks about the managers-only topic → Salid does not reveal it and offers to ask its owner → the manager taps **Approve** in a DM → the junior gets that one item, nothing more | "The model never decides what it may read. Code does, and a hidden item needs its owner's consent." |
| 2:35–2:47 | **Also.** Quick montage: `/center` command center; a receipt photo → recorded in the ledger (2 s); LINE on Apple Watch (optional) | "Leaders see the whole company on the web. She also files receipts, and she's on LINE too." |
| 2:47–2:55 | Architecture diagram, then the end card with the tagline and salid.frontier-tech.app | "Gemini and Google ADK on Google Cloud. Work naturally. Stay informed. Just ask." |

**Contingency:**
- Record each scene separately with 2–3 takes. Cut waiting time in the edit and add a small "edited for time" caption. Never fake an output.
- If the just-ask answer has no source links or misses the project, check that the project is seeded in `/pm` and the `projects` and `search` flags are on, then retake.
- If live voice fails, use the classic voice path (automatic fallback, `live_fallback`) or re-record. Keep a backup clip of the minutes and task cards from a successful run (the slide 11 screenshots come from one).
- If "What did I miss?" comes back empty (the start is the asker's last message before their latest 4 h silence), ask "What did I miss since yesterday?" instead.
- The trust scene needs a junior and a manager with different ranks; rehearse it the day before.
- If Vertex is slow or rate-limited during recording, wait and retake; do not script fake replies.
- Demo Day backup (finalists): the slide 11 screenshots, the §5 backup shots, plus `/center?mock=1` (offline sample data, with a visible "MOCK MODE" bar).
- Before recording: check the guild licence, check the `voice_meetings` / `task_handshake` / `briefings` / `catchup` / `projects` / `search` flags in `/hub`, and smoke `/health`.

---

## 7. Final quality-control checklist

**Accuracy**
- [ ] Every number on a slide has a tag and a source in §8. No ⏳ left.
- [ ] None of the false claims appear: "ครับ", "no files stored", "Google Meet scheduling", "only answers from what you can read", "free, no limits", "tokens encrypted", "deleted automatically / 90 days", "LINE not deployed", "Salid answers LINE voice messages".
- [ ] **LINE is live (19 Oct 2026, [team]); Slack, Telegram and WhatsApp are built, not deployed.** Canva text that still says otherwise: slide 3 footnote; slide 4 "No new app" card and notes; slide 7 diagram and notes; slide 13 headline, Phase 2 list, closing line, "Live today on Discord" badge and notes.
- [x] Slide 3 "Voice Q&A in meetings" column filled from vendor pages (19 Oct 2026).
- [ ] Slide 10: totals match `cost_model.py` ($136 / $258 / $876 → ≈ $140 / $260 / $880, LINE bridge included); "An estimate, not a measured bill" stays on the slide.
- [ ] Slide 11: real screenshots in place (landing page, command center profile and filing cabinet, LINE chat on Apple Watch, Discord task cards, Discord minutes); names, emails and avatars blurred; the Apple Watch caption does not imply LINE audio handling (fixed 19 Oct).
- [ ] Slide 12: a later full run on 18 Oct showed **2 order-dependent test failures, being fixed now**; the 6,082 figure is from commit 1cf0179. The tool-round tile now says "≤ 10" per typed answer (5 spoken), matching `origin/main`.
- [ ] Slide 1: check the space or line break between "Accelerated Communication." and "Work naturally." (the Canva text reads "Communication.Work").
- [ ] Slide 14: the video QR code decodes to the video URL; Canva notes no longer say the link is missing.
- [ ] Model names match the code; 3.1 Pro is labelled preview.

**Storytelling**
- [ ] The headlines alone tell the story (§2): Accelerated Communication → just ask → no status meeting → trust → cost → proof → next.
- [ ] One message per slide; the voice Q&A moment is visible on slides 4 and 6 and in the video.
- [ ] Receipts appear only as an "also" (slide 4 footer, a 2 s video moment).

**Technical credibility**
- [ ] Architecture shows only real components, with LINE solid and Slack / Telegram / WhatsApp dashed.
- [ ] The ADK multi-agent graph and the code-enforced scope are explained in one line each.

**Visual clarity**
- [ ] Template header kept; two accent colours only; ≥ 24 pt body on content slides; each slide readable in 10 s.

**Hackathon alignment**
- [ ] PDF export, English only.
- [ ] Links slide has the repo, the video and the product (✅ all three).
- [ ] Gemini is visible on slides 1, 7 and 8.
- [ ] Video ≤ 3:00 (published length: Information needed).

**Timing**
- [ ] Video 2:55.
- [ ] Demo Day talk ≈ 5 min = slides 1–12 at about 25 s each. **Information needed:** the Demo Day format.

**Disclosure**
- [ ] If the rules ask about AI-assisted development, say so (git at 1cf0179: 179 of 276 non-merge commits authored by Claude).

---

## 8. Sources

**Canva deck** read on 19 Oct 2026 (design "Salid — AI Builder Cup 2026 pitch deck (The Frontier)", text and speaker notes). Team confirmation of the LINE deployment: 19 Oct 2026.

**Codebase (Source: codebase review, commit 1cf0179; `origin/main` c35fed8 where noted)**
- Agent and scope: `src/salid/qa.py` (`build_agent`, `LedgerTools`, `MemoryTools`, `MAX_ROUNDS`, `stable_prompt` / `volatile_prompt`), `src/salid/bot.py` (`_agent_kwargs`)
- Just ask / catch-up: `src/salid/search.py` (`search_everything`), `src/salid/catchup.py` (`catch_up`), `src/salid/projects.py`, `src/salid/progress.py`
- Access control: `src/salid/memory_access.py`, `src/salid/disclosure.py`, `src/salid/coo.py`
- Models: `src/salid/config.py`, `src/meeting_scribe/config.py`; multi-agent: `src/meeting_scribe/agents.py`
- Memory: `src/salid/memory.py`, `src/salid/embed.py`, `src/salid/memory_index.py`
- Voice: `src/salid/meeting.py`, `src/salid/live_voice.py`, `src/salid/web_live.py`, `src/salid/speech.py`
- Reliability: `src/salid/llm.py`, `src/salid/config.py` (`answer_timeout_seconds`)
- Deploy: `scripts/deploy.sh`, `scripts/deploy_salid.sh`, `Dockerfile.salid`; `scripts/deploy_platforms.sh` (`origin/main`, Cloud Run service `salid-platforms`)
- LINE bridge: `src/salid/platforms/line.py` (text, image and file messages), `docs/platforms/line.md`; LINE User Data Policy (ids only, no org-wide linking by default): commit f677b13 (PR #50)
- Cost: `docs/pitch/cost-research.md`, `docs/pitch/cost_model.py`
- Status of unbuilt parts: `src/salid/google_tools.py`, `src/salid/platforms/calendar_glue.py` (`origin/main`), `src/salid/connectors/__init__.py`, `src/salid/platforms/`, `docs/Google Hackathon - The Frontier - Risk Assessment (status 2026-10-18).csv`

**External [ext]** (fetched 18 Oct 2026)
- Hackathon: aibuildercup.com (FAQ, themes, rewards, T&C)
- Demo video: https://youtu.be/a3RWpdnwCXg
- ADK: https://adk.dev · https://adk.dev/agents/llm-agents/ · https://adk.dev/agents/workflow-agents/parallel-agents/ · https://adk.dev/agents/workflow-agents/sequential-agents/
- Models (Gemini Enterprise Agent Platform): docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-5-flash, …/3-5-flash-lite, …/3-1-pro, …/2-5-flash-live-api (retires 13 Dec 2026; US/EU regions), …/nano-banana-2-1
- Implicit caching: docs.cloud.google.com/gemini-enterprise-agent-platform/models/context-cache/context-cache-overview
- Grounding with Google Search: …/models/grounding/grounding-with-google-search · URL context: …/models/url-context
- Cloud TTS Chirp 3 HD (th-TH): docs.cloud.google.com/text-to-speech/docs/chirp3-hd
- Cloud Run worker pools: docs.cloud.google.com/run/docs/deploy-worker-pools
- Gemini CLI: https://github.com/google-gemini/gemini-cli
- Pricing (slide 10): the official pages listed as [1]–[13] in `docs/pitch/cost-research.md` (Gemini Enterprise Agent Platform, Cloud Run, Firestore, Cloud Storage, Text-to-Speech, Pub/Sub, Secret Manager, Cloud Build, Artifact Registry, Bank of Thailand exchange rate), read 18 Oct 2026
- Competitors:
  - knowledge.workspace.google.com/admin/generative-ai/google-workspace-with-gemini-language-support
  - support.microsoft.com/en-us/microsoft-365-copilot/supported-languages-for-microsoft-365-copilot
  - slack.com/help/articles/25076892548883
  - otter.ai/pricing
  - read.ai/post/six-new-languages-now-supported
- Market data (slide 2; the last two are not on the current slides, kept for Q&A):
  - Bank of Thailand, "สรุปสถานการณ์ SME ไทย ณ ไตรมาส 4 ปี 2568" (OSMEP MSME data): bot.or.th/content/dam/bot/documents/th/financial-innovation/การเงินเพื่อครัวเรือนและ-sme/sme/SME_snapshort_Q42568.pdf
  - Atlassian, "The State of Teams 2025": atlassianblog.wpengine.com/wp-content/uploads/2025/03/the-state-of-teams-2025.pdf
  - Microsoft, Work Trend Index 2023 "Will AI Fix Work?": https://www.microsoft.com/en-us/worklab/work-trend-index/will-ai-fix-work
  - Microsoft Source Asia, WTI 2024 Thailand (92%): https://news.microsoft.com/source/asia/2024/06/19/wti2024-en/
  - DataReportal / Kepios, "Digital 2026: Thailand" (56 million monthly LINE users, LINE's figures Oct 2025): https://datareportal.com/reports/digital-2026-thailand
  - Microsoft Source Asia, WTI 2025 Thailand (88%): news.microsoft.com/source/asia/2025/05/02/microsoft-work-trend-index-2025-report-reveals-the-frontier-firms-is-born-a-new-organization-blueprint-is-emerging-th/
- Do not use (misquoted or outdated): "1.8 hours a day searching" (McKinsey says ~20%, 2012); "42% of knowledge lost to turnover" (a misquote of Panopto 2018); LINE 85.7% (superseded by 82.6%); WTI 2026 Thai figures (Thailand not in that survey's 10 markets).

---

## 9. Judge Q&A prep (Demo Day and video comments)

| Likely question | Answer (true today) |
| --- | --- |
| Thailand runs on LINE. Why Discord? | Salid is on LINE too: the LINE bridge went live on 19 Oct 2026, on the same brain as Discord (56 million Thais use LINE every month, DataReportal 2026). Discord gives a bot voice rooms, roles and rich buttons, which Salid needs for voice meetings, role-aware memory and task cards; on LINE she reads text, images and files. Slack, Telegram and WhatsApp bridges are built and deploying them is next. |
| How do you stop the AI leaking secrets? | The model never chooses its scope. Company, caller and the answer's audience are fixed in code before it runs; hidden items need the owner's Approve. |
| What does the LINE bot keep? | Ids only, and no org-wide linking by default (LINE User Data Policy, PR #50). |
| What does it cost to run? | About $260 a month for a 20-person team at typical use, ≈ $13 per person; light ≈ $140, heavy ≈ $880. It is official Google Cloud prices × stated usage assumptions, an estimate, not a measured bill. About 62% is Gemini usage, so cost follows use, not seats; the fixed floor is ≈ $100 (always-on Discord bot, always-on LINE bridge, web app) and is shared by every company on the service. Before quoting a price we measure tokens per answer from the bot's token log. |
| Do others answer by voice in meetings? | Salid answers aloud mid-meeting in Discord voice when called by name. We are still checking each competitor's page for the same feature (slide 3), so don't claim they lack it. |
| Do you have users? | The Frontier runs on it. No external usage metrics yet. |
| Can it scale? | Today it runs as a single instance by design (in-process caches and locks). Scaling out is Phase 3. |
| What about Google Workspace? | Calendar / Meet tools exist: on the latest code they are offered on the Slack / LINE / Telegram / WhatsApp bridges behind per-member Google consent, not in the Discord bot yet (whether they are on in the live LINE bot: To validate). Gmail and Drive connectors are planned. |
| Is the recorder secure? | The Meet recorder API has no authentication yet (a known limitation, in Phase 3). Keep that URL private. |
| Did you use AI to build it? | Yes, AI coding agents worked alongside the team (git at 1cf0179: 179 of 276 non-merge commits). Every change went through PRs and the test suite. |
