# Voice-to-voice research for Dory (2026-10-25)

Systematic research (deep-research skill, 6 phases + a phase-0 code audit) on production real-time voice-to-voice
for Dory: end-to-end speech-to-speech vs modular ASR -> LLM -> TTS, Nemotron speech on Nebius, Gemini Live, turn
detection, barge-in, latency and cost, with Thai as the hard requirement. Start with `phase6_report/report.md`.

| Path | What |
| --- | --- |
| `phase0_current_system/dory_voice_stack.md` | Audit of Dory's two voice paths (Discord rooms, web Live) with file:line refs, 10 improvements, open questions |
| `phase1_frontier/frontier.md` | 2025-2026 papers in 6 trending directions (+ Thai/SEA section); `search_results/` raw arXiv JSONL |
| `phase1_frontier/industry_frontier.md` | Managed voice APIs (Gemini Live, OpenAI, others), prices with arithmetic, turn-detection products, Thai speech vendors, 70+ dated sources |
| `phase2_survey/survey.md` | 8-cluster taxonomy over the 82-paper database; reading list |
| `paper_db.jsonl` | Master database (82 papers, 51 peer-reviewed; `paper_db_all_unfiltered.jsonl` = 361 before curation) |
| `phase3_deep_dive/` | `selection.md`, `deep_dive.md` (12 papers read in full, latency table, 5 takeaways), `deep_dive_papers.jsonl` |
| `phase4_code/code_repos.md` | 82 repositories (frameworks, S2S models, ASR, VAD, TTS, serving, transport, benchmarks), Python compatibility, 3-tier bill of materials |
| `phase4_code/nvidia_nebius_stack.md` | NVIDIA speech models vs Thai, reference voice agent, Nebius Token Factory + GPU prices, Thai ASR/TTS options, hackathon options |
| `phase5_synthesis/synthesis.md`, `gaps.md` | Taxonomy, comparative tables, trade-offs with verdicts, Dory latency budget, reconciled conflicts; research/product/verification gaps |
| `phase6_report/report.md` | Final phased report (A: now -> 2026-10-30, B: -> 2026-12-13, C: 2027 Q1), targets, owner questions, skills found |
| `phase6_report/references.bib` | BibTeX for every `[@key]` (generated from `paper_db.jsonl` + 2 hand entries) |
| `phase6_report/examples/voice_examples.py` | The report's code examples as runnable pytest (stdlib only) |

Regenerate / verify (nothing is added to the project environment):

```bash
S=~/.claude/skills/deep-research/scripts
uv run --no-project --python 3.12 python $S/paper_db.py stats --input paper_db.jsonl
uv run --no-project --python 3.12 python $S/bibtex_manager.py --jsonl paper_db.jsonl --output phase6_report/references.bib
uv run --no-project --python 3.12 --with pytest python -I -m pytest -q phase6_report/examples
```

Labels used everywhere: Confirmed (paper / official page / code with file:line, read 2026-10-25), Secondary,
Assumption, Recommendation, Hypothesis; `(preprint)` marks papers without a peer-reviewed venue. Citation counts are
OpenAlex (Semantic Scholar rate-limited the run). Prices, model ids and versions drift: re-check before quoting.
