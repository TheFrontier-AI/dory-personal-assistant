# Phase 3 (Deep Dive) — paper selection

Date: 2026-10-25. Topic: real-time voice-to-voice conversational AI (full-duplex speech-to-speech models vs modular ASR → LLM → TTS cascades, streaming ASR/TTS, turn-taking, barge-in, latency).

## How the papers were chosen

1. Every seed arXiv id was verified against the arXiv API (`export.arxiv.org/api/query?id_list=`); all 23 candidate ids resolved to the expected titles. "Thonburian Whisper" has no arXiv record (`ti:"Thonburian Whisper"` returns nothing), so it could not be used.
2. Venue and peer-review status come from the arXiv comment field and the Semantic Scholar `publicationVenue` for each id (fetched 2026-10-25). `(preprint)` means neither source names a peer-reviewed venue.
3. Each selected paper was downloaded as a PDF from arxiv.org and its full text extracted (PyMuPDF). Notes in `deep_dive.md` were written from the method and experiment sections, the result tables and the limitation/conclusion sections, not from the abstract alone. Where a paper gives no number, the note says "not reported".
4. Twelve papers received full notes. Two more (Freeze-Omni, Fast Conformer) were read because the seed list asked for a comparison; their numbers are used in the cross-paper latency table and inside the notes they support, but they did not get a separate note so that the count stays at 12.

## Selected papers (12)

| # | Paper | arXiv | Venue / status | Why it is in |
| --- | --- | --- | --- | --- |
| 1 | Moshi: a speech-text foundation model for real-time dialogue | 2410.00037 | Kyutai tech report (preprint) | The reference open full-duplex S2S system; gives the only explicit theoretical-vs-practical latency decomposition (160 / 200 ms), plus derived streaming ASR/TTS numbers. |
| 2 | Full-Duplex-Bench | 2503.04721 | ASRU 2025 | The only benchmark that measures turn-taking latency, takeover rate, backchannels and interruption handling on the same inputs for Moshi, dGSLM, Freeze-Omni and Gemini Live. |
| 3 | VoiceBench | 2410.17196 | TACL per Semantic Scholar (arXiv v3 still says "work in progress") | Head-to-head of an ASR+LLM pipeline against end-to-end voice assistants on knowledge, instruction following, safety and robustness to speaker / noise / content variation. |
| 4 | Beyond Turn-Based Interfaces: Synchronous LLMs (SyncLLM) | 2409.15594 | EMNLP 2024 (main) | Full-duplex from a stock text LLM with explicit network-latency tolerance (160–240 ms chunks); human MOS vs dGSLM. |
| 5 | Language Model Can Listen While Speaking (LSLM) | 2408.02622 | AAAI 2025 per Semantic Scholar (arXiv Aug 2024) | Minimal, measurable study of barge-in: a listening channel fused into a speaking model, with precision/recall of interruption detection under noise. |
| 6 | LLaMA-Omni | 2409.06666 | ICLR 2025 | Chosen over Freeze-Omni / Mini-Omni for the clearest latency analysis: a latency–quality curve (236 → 563 ms) against cascaded baselines with streaming TTS, measured on one L40. |
| 7 | Qwen2.5-Omni Technical Report | 2503.20215 | preprint | The strongest open omni model with a documented streaming design (block-wise encoders, Thinker-Talker, sliding-window DiT) and ASR/TTS numbers against Whisper and CosyVoice 2; chosen over Kimi-Audio / Step-Audio 2 because it is the one the others compare against. |
| 8 | Stateful Conformer with Cache-based Inference for Streaming ASR | 2312.17279 | ICASSP 2024 | NVIDIA's streaming recipe on top of Fast Conformer: WER as a function of look-ahead (0–1360 ms) vs buffered streaming; the Fast Conformer paper itself (2305.05084, ASRU 2023) was read and is folded into this note. |
| 9 | Whisper: Robust Speech Recognition via Large-Scale Weak Supervision | 2212.04356 | ICML 2023 | Baseline ASR everybody fine-tunes for Thai; gives the Thai Fleurs number (11.5 for large-v2) and the authors' own list of failure modes (loops, hallucination, 30 s windows). |
| 10 | Turn-taking and Backchannel Prediction with Acoustic and LLM Fusion | 2401.14717 | ICASSP 2024 | A 2024 LLM-based end-of-turn / backchannel predictor with ablations of acoustic vs text vs fusion; chosen over TurnGPT (2020, text only) and VAP (2022, acoustic only). |
| 11 | CosyVoice 2: Scalable Streaming Speech Synthesis with LLMs | 2412.10117 | tech report (preprint) | The streaming TTS most S2S systems use or compare to; documents the N:M text/speech interleaving and chunk-aware flow matching, and is honest that the latency is a formula, not a measured number. |
| 12 | Enhancing Low-Resource Language and Instruction Following Capabilities of Audio Language Models (Typhoon-Audio) | 2409.10999 | Interspeech 2025 | The only peer-reviewed Thai audio-LM paper: shows that multilingual audio LMs collapse on Thai (WER 95–98) and what data mixture fixes it. |

## Read but not given a separate note

- **Freeze-Omni** (2411.00774, preprint). Its Table 4 is the most detailed end-to-end latency budget of any S2S paper (745 ms average statistical latency, ~1.2 s in real use); those numbers are in the cross-paper table and in the LLaMA-Omni and Full-Duplex-Bench notes. Dropped as a separate note because LLaMA-Omni is peer-reviewed and shows the latency–quality trade-off against cascades, which is what the review question needs.
- **Fast Conformer** (2305.05084, ASRU 2023). Read for the architecture facts (8x downsampling to 80 ms frames, 2.8x faster encoder, 675 min long-form on one A100). Folded into the streaming Conformer note because the streaming paper is the one with latency numbers.

## Rejected or replaced

- **Thonburian Whisper**: no arXiv paper; a model card is not a paper for this phase.
- **Typhoon 2** (2412.13702, 55-page tech report, preprint): its audio section repeats the Typhoon-Audio recipe with a newer LLM; the Interspeech paper is peer-reviewed and self-contained, and already reports the Typhoon2-Audio row.
- **GigaSpeech 2** (2406.11546, ACL 2025): a Thai/Indonesian/Vietnamese ASR corpus paper; relevant to training data, less so to real-time interaction. Kept as a pointer for Phase 4.
- **Mini-Omni** (2408.16725, preprint, "work in progress"): 0.5B model; VoiceBench shows it near the bottom (overall 37.5 for speech); no latency breakdown comparable to LLaMA-Omni.
- **Kimi-Audio** (2504.18425) and **Step-Audio 2** (2507.16632): both preprints; Qwen2.5-Omni covers the same design space with more comparable ASR/TTS tables.
- **TurnGPT** (2010.10874, Findings of EMNLP 2020) and **VAP** (2205.09812, Interspeech 2022): single-modality predecessors of the chosen fusion paper, which reports both as baselines in spirit (text-only GPT2 and acoustic-only HuBERT rows).
- **F5-TTS** (2410.06885, preprint): non-streaming flow-matching TTS; appears as a baseline row inside the CosyVoice 2 note.
- **Kyutai delayed streams modeling** (2509.08753, preprint): the streaming ASR/TTS generalisation of Moshi's Inner Monologue; the mechanism is already covered by the Moshi note (Section 5.7 / Appendix C).
- **TDT transducer** (2304.06795, ICML 2023): a decoder speed-up, orthogonal to the streaming/latency question; cited in the Conformer note only.

## Known gaps

- No paper in the set measures Thai end-to-end voice latency; Thai evidence is ASR/audio-LM accuracy only (Whisper, Typhoon-Audio).
- Citation counts are Semantic Scholar values on 2026-10-25 and will drift.
