# GLM for Dory's voice: what the owner's decision needs (26 Oct 2026)

Owner's decision (26 Oct 2026): English first; use GLM-4-Voice, GLM-5.3 and GLM-5.3-Flash.
Done the same day in code: the text brain is GLM-5.3 and the cheap gate tier GLM-5.3-Flash on
Nebius Token Factory (`DORY_BRAIN_MODEL`, `DORY_FAST_MODEL`; `src/dory/llm.py`). Images stay on
NVIDIA Nemotron 3.5 Super VL so the Nebius x NVIDIA submission keeps a Nemotron call.
GLM-4-Voice is NOT wired: this note says what it takes and asks for the approval it needs.

## GLM-4-Voice, the facts (README read 2026-10-26)

- Three parts: a Whisper-based tokenizer (12.5 tokens per second of audio), GLM-4-Voice-9B
  (GLM-4-9B aligned to speech), and a streaming decoder retrained from CosyVoice that can start
  speaking after 10 audio tokens. Confirmed.
- Languages: Chinese and English speech in and out. No Thai. Confirmed.
- Serving: `python model_server.py --model-path THUDM/glm-4-voice-9b --dtype bfloat16|int4` plus
  `web_demo.py` with the tokenizer and the decoder. No OpenAI-compatible or Live-style API,
  no server VAD, no function calling in the model or its server. Confirmed from the README;
  the absence of tool calling is an Assumption until the model card and `model_server.py`
  are read line by line.
- Code licence Apache-2.0; the weights' licence was not checked (the research survey found no
  licence tag on the HF card). Last commit 2024-12-05 (phase 4 survey).
- Not on Token Factory (no audio models there, verified 2026-10-25), so it is a GPU VM job.

## Why it cannot simply replace Gemini Live

Dory's voice is "the same Dory": a speech layer that hands every company question or action to
`ask_dory`, the text agent with all her tools and permissions. GLM-4-Voice answers from its own
9B weights only. Three shapes exist:

| Option | What the person gets | Cost of building it |
| --- | --- | --- |
| A. GLM-4-Voice as an English small-talk voice | Fast, expressive English chat; no receipts, tasks, documents, reminders, settings | GPU VM + a new `WebLive`-like backend speaking its HTTP protocol + browser unchanged; 2-3 days (Assumption) |
| B. GLM-4-Voice for listening, Dory's brain for the answer, a TTS for speaking | Keeps the tools; GLM-4-Voice is then an expensive ASR (its tokenizer is Whisper) | Same as A plus a TTS; Whisper or Typhoon ASR does the listening part better and cheaper |
| C. Gemini Live for turn-taking, ASR and TTS; GLM-5.3 behind `ask_dory` (shipped today) | Same Dory, English and Thai, barge-in and resumption already built | Done |

Recommendation: C now, A only as a demo toggle for an English-only room once the GPU is approved,
never B.

## What A needs from the owner

1. Approval for one Nebius GPU VM. An L40S (48 GB, from $1.55/h, prices page read 2026-10-25) holds
   the 9B model in bf16 plus the decoder and tokenizer (Assumption from the sizes; int4 is the
   fallback). About $37 per day while it runs.
2. Whether English-only voice without company data is acceptable for the demo.
3. Two to three engineering days before 30 Oct, which is the deadline itself.

Approved by the owner on 26 Oct 2026 ("Approved to use the GLM-4-Voice"), taken as approving the
GPU spend and the English-only, no-company-data voice. Built the same day, offline-tested:
`deploy/glm_voice/server.py` (the GPU side, headless `web_demo.py` loop + Dory's socket protocol,
`--selftest`), `src/dory/glm_voice.py` (Dory's backend, swapped in by `DORY_GLM_VOICE_URL`),
`deploy/glm_voice/README.md` (VM, install, run). Not done: the VM itself (no Nebius Cloud CLI or
credentials on the dev machine; the owner creates it or installs the `nebius` CLI) and the first
live call, which will decide the persona line and the latency.
