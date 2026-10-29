# Voice warmth, name spotting, endpointing and spoken text (cascade voice)

Research note, 2026-10-27, for the one-GPU cascade in `deploy/glm_voice/cascade.py`
(Parakeet-TDT 0.6B v3 -> LLM -> Kokoro-82M, RMS `Endpointer` in `server.py`: `rms_min` 250,
`silence_s` 0.8, `min_speech_s` 0.3). Every claim below was checked against the current source on
that date; "judgment" marks my own recommendation. Nothing here is installed yet: `rapidfuzz`,
`jellyfish`, `silero-vad`, `kokoro` are all absent from the project venv (checked with `uv run`).

## 1. Softer, warmer Kokoro output

**Voice list and grades** (official [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md),
columns Traits / Target quality / Training duration / Overall grade). The sheet gives letter grades and
trait emoji only; it never says "warm" or "bright".

| `a` US English | grade | `a` US English | grade | `b` British | grade |
| --- | --- | --- | --- | --- | --- |
| **af_heart** ❤️ | **A** | am_fenrir | C+ | **bf_emma** (HH hours) | **B-** |
| **af_bella** 🔥 (target A, HH hours) | **A-** | am_michael | C+ | bf_isabella | C |
| **af_nicole** 🎧 (HH hours) | B- | am_puck | C+ | bf_alice | D |
| af_aoede, af_kore, af_sarah | C+ | am_echo, am_eric, am_liam, am_onyx | D | bf_lily | D |
| af_alloy, af_nova | C | am_santa | D- | bm_fable, bm_george | C |
| af_sky | C- | am_adam | F+ | bm_lewis | D+ |
| af_jessica, af_river | D | | | bm_daniel | D |

Character descriptions exist only in third-party docs ([ttsforge voice list](https://ttsforge.readthedocs.io/en/latest/voices.html)):
af_heart "expressive, emotional", af_bella "warm, friendly", af_nicole "soft, gentle", af_sarah
"confident, clear", af_river "calm, flowing", bf_lily "gentle, soft", bf_emma "classic British".
Soft/calm candidates with a usable grade are therefore **af_nicole** (B-, the 🎧 trait) and
**af_bella** (A-); the only well-graded British voice is **bf_emma** (B-). Every male voice is C+ or
worse. `af_heart` is the right default for quality (the only A); for a softer Dory, try the blend
`af_heart,af_nicole` or `af_bella,af_nicole` and listen (judgment; the model card has samples of
af_bella, af_nicole and af_sarah: [model card](https://huggingface.co/hexgrad/Kokoro-82M)).

**Speed.** `KPipeline.__call__(text, voice, speed=1, split_pattern=r'\n+')`; `speed` may also be a
callable of the phoneme-string length ([pipeline.py](https://github.com/hexgrad/kokoro/blob/main/kokoro/pipeline.py)).
Hosted endpoints accept 0.25-4 ([DeepInfra](https://deepinfra.com/hexgrad/Kokoro-82M)); a third-party
guide advises staying in 0.8-1.2 ([eachlabs](https://www.eachlabs.ai/kokoro/kokoro/kokoro-82m)).
0.9-0.95 for a calm voice is inside that band (judgment; A/B it, 0.85 starts to drag).

**Blending is built in (kokoro 0.9.x).** `load_voice` docstring: "Single voice can be requested
(e.g. 'af_bella') or multiple voices (e.g. 'af_bella,af_jessica'). If multiple voices are requested,
they are averaged" (`torch.mean(torch.stack(packs), dim=0)`, equal weights). A `torch.FloatTensor`
is accepted anywhere a voice name is, so weighted blends are two lines:

```python
from kokoro import KPipeline
import torch

tts = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
soft = tts.load_voice("af_heart,af_nicole")  # equal average, cached under that key
warm = 0.7 * tts.load_single_voice("af_heart") + 0.3 * tts.load_single_voice("af_bella")  # weighted
for _, _, audio in tts("Hello, I'm Dory.", voice=warm, speed=0.92):
    ...  # audio: 24 kHz float tensor for this chunk
```

**Pitch: none.** `KModel.forward(phonemes, ref_s, speed)` has no pitch argument
([model.py](https://github.com/hexgrad/kokoro/blob/main/kokoro/model.py)); pitch comes only from the
voice pack (blend toward a lower voice) or post-processing (not recommended).

**Punctuation and pauses.** misaki keeps `;:,.!?—…"“”` as tokens in the phoneme string
(`PUNCTS` in [misaki/en.py](https://github.com/hexgrad/misaki/blob/main/misaki/en.py)), so commas and
ellipses shape prosody inside a chunk. Newlines never reach the model: the default `split_pattern`
`r'\n+'` cuts the text into chunks, each synthesised and yielded separately, and the library inserts
**no silence** between them (pipeline.py). So the pause between sentences is whatever you append.
Recommendation (judgment, with Alexa's rule "add spacing between phrases and sentences",
[benchmark 5](https://developer.amazon.com/blogs/alexa/post/d92c7822-d289-44fd-a9fe-9652874fc3c9/five-benchmarks-for-writing-dialog-that-sounds-great-to-alexa-customers)):
**250-350 ms** after a sentence, **500 ms** after a question or before a new topic, 0 ms inside a sentence.

```python
import numpy as np


def with_pause(audio: np.ndarray, ms: int = 300, rate: int = 24_000) -> np.ndarray:
    return np.concatenate([audio, np.zeros(int(rate * ms / 1000), dtype=audio.dtype)])
```

## 2. Hearing "Dory" without exact keyword matching

**What the ASR gives us.** Parakeet-TDT 0.6B v3 outputs punctuation and capitalisation and covers 25
European languages, **no Thai** ([model card](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3)).
Thai audio comes back as nonsense in a European language; "ดอรี่" is only spottable because Thai
speakers pronounce the name like the English one. NVIDIA's newer streaming model lists Thai as
"adaptation-ready", i.e. fine-tune before it transcribes
([Nemotron 3.5 ASR streaming](https://huggingface.co/nvidia/nemotron-3.5-asr-streaming-0.6b)), so for
this week Thai name spotting means an English-script name. Expected English renderings (judgment, no
published list; log and check with the probe): `Dory`, `Dori`, `Dorie`, `Dorey`, `Dorry`, `Dory's`,
`Door-y`, `Doory`, `Dora`, `Tory`; acoustic near-misses `story`, `door`, `glory`. "Story" must NOT match.

**Fuzzy matching without deps.** Nothing fuzzy is installed. Stdlib `difflib.SequenceMatcher.ratio()`
("a ratio() value over 0.6 means the sequences are close matches",
[difflib docs](https://docs.python.org/3/library/difflib.html)) is too blunt here: ratio("dory","story")
= 0.67 and ratio("dory","dorie") = 0.67, so no cutoff separates them. `rapidfuzz.fuzz.ratio`
(normalised Indel, 0-100, [rapidfuzz docs](https://rapidfuzz.github.io/RapidFuzz/Usage/fuzz.html)) has
the same problem; `jellyfish` offers Metaphone/Soundex/NYSIIS but not Double Metaphone
([jellyfish docs](https://jamesturk.github.io/jellyfish/)). A 3-line phonetic key does the job: strip
non-letters, collapse doubled letters, fold vowel runs. `dory/dori/dorie/dorey/door-y/dorry/dora ->
"d-r-"`, `story -> "st-r-"`, `door -> "d-r"`. Verified on the 12 spellings and 10 sentences below.

```python
import re

CUES = {"hey", "hi", "ok", "okay", "thanks", "thank", "please", "so"}
MENTION_NEXT = {"said", "told", "was", "has", "had", "did", "went", "already", "also"}
NAME_KEYS = {"d-r-", "t-r-"}  # Dory and the ASR's "Tory"


def key(w: str) -> str:
    w = re.sub(r"[^a-z]", "", re.sub(r"'s$", "", w.lower()))  # door-y -> doory, dory's -> dory
    return re.sub(r"[aeiouy]+", "-", re.sub(r"(.)\1+", r"\1", w))  # dorry -> dory -> d-r-


def spot(text: str) -> str | None:  # "addressed" | "mentioned" | None
    toks = re.findall(r"[A-Za-z'-]+|[,?!.]", text)
    hits = [i for i, t in enumerate(toks) if key(t) in NAME_KEYS]
    if not hits:
        return None
    i = hits[0]
    prev = toks[i - 1].lower() if i else ""
    nxt = toks[i + 1].lower() if i + 1 < len(toks) else ""
    if nxt.endswith("ed") or nxt in MENTION_NEXT:  # "Dory booked it yesterday", "Dory said..."
        return "mentioned"
    if prev in CUES or nxt in (",", "?", "!") or i <= 1 or i >= len(toks) - 2:
        return "addressed"  # vocative: start, end, after a cue, before a comma
    return "mentioned"  # mid-sentence subject/object
```

Scoring in words: name as the first or last word, after "hey/ok/thanks/so", or before a comma or
question mark = addressed (an imperative or question follows); name followed by a past-tense or
reporting verb = mentioned even at sentence start. Parakeet's own commas make the vocative case
reliable. `shortcut: one name per utterance and English only; upgrade to a POS tagger only if the log
shows real misses.`

**Engaged window ("follow-up mode").** Alexa's Follow-Up Mode keeps the mic open for about **5 s**
after a reply, off by default, ends on "stop / cancel / thank you", stays off while audio plays, and
Alexa "won't keep listening if ... she isn't sure you were talking to her"
([How-To Geek](https://www.howtogeek.com/345447/how-to-use-alexa%E2%80%99s-new-follow-up-commands/),
[Tom's Guide](https://www.tomsguide.com/us/alexa-follow-up-mode,review-5204.html)). Google's Continued
Conversation listens "for about 10 seconds for your follow-up questions"; Gemini Live on Google Home
"up to 15 seconds", with a visible listening indicator
([Google Nest help](https://support.google.com/googlenest/answer/7685981?hl=en)). Rule for Dory
(judgment): `engaged_until = now + 12 s` after her last audio chunk; while engaged, any utterance is
addressed without the name; the window restarts on every exchange; "thanks / that's all / stop" ends it;
show the lantern while engaged. Clarification "Was that for me?" only when (a) not engaged, (b) no name,
(c) the sentence is a request to a second person ("can you", "please", "?"), (d) not asked in the last
2 min; otherwise stay silent. Dory's own reply text must never re-trigger `spot` (she says her name).

**Audio-based alternative.** [openWakeWord](https://github.com/dscripka/openWakeWord): shipped models are
trained on "100% synthetic speech", the Colab notebook trains "a basic wake word model in <1 hour", one
core of a Raspberry Pi 3 runs 15-20 models in real time (80 ms frames, Google speech-embedding backbone);
a 2026 community notebook reports 75-90 min on Colab Pro and that the official notebook needs dependency
fixes ([openwakeword-colab-2026](https://github.com/alfiedennen/openwakeword-colab-2026)). The README
publishes no false-accept-per-hour figure for custom models. NeMo's alternative is not keyword spotting
but **word boosting**: GPU-PB "is applied only at the decoding step in shallow fusion mode", supports
"CTC, RNN-T/TDT, and AED" models, takes `boosting_tree.key_phrases_list`, needs the phrase capitalised
for PnC models, recommended `context_score` 1.0 and `depth_scaling` 2.0
([NeMo word boosting](https://docs.nvidia.com/nemo/speech/latest/asr/asr_customization/word_boosting.html)).
MatchboxNet still exists for speech commands but needs its own training data
([NeMo speech classification](https://docs.nvidia.com/nemo/speech/latest/asr/speech_classification/models.html)).
**Recommendation for this week: transcript matching is enough.** The transcript is already there, the
key costs nothing, and boosting `Dory` with GPU-PB is the one cheap upgrade if the log shows odd
spellings. A trained wake word adds a model, a Colab day and no Thai.

## 3. Endpointing and barge-in

**Silero VAD vs the RMS gate.** [Silero VAD](https://github.com/snakers4/silero-vad): MIT, "JIT model is
around two megabytes", "one audio chunk (30+ ms) takes less than 1 ms to be processed on a single CPU
thread", 8 kHz or 16 kHz, 512-sample (32 ms) chunks at 16 kHz
([wiki examples](https://github.com/snakers4/silero-vad/wiki/Examples-and-Dependencies)). pip
`silero-vad` ships `VADIterator(model, threshold=0.5, sampling_rate=16000, min_silence_duration_ms=100,
speech_pad_ms=30)` ([utils_vad.py](https://github.com/snakers4/silero-vad/blob/master/src/silero_vad/utils_vad.py)).
It wants a float tensor, so from the 16 kHz int16 frames:

```python
import numpy as np, torch
from silero_vad import load_silero_vad, VADIterator

vad = VADIterator(
    load_silero_vad(), threshold=0.5, sampling_rate=16000, min_silence_duration_ms=100
)


def is_speech(pcm16: bytes) -> dict | None:  # exactly 512 samples = 1024 bytes per call
    x = torch.from_numpy(np.frombuffer(pcm16, np.int16).astype(np.float32) / 32768.0)
    return vad(x, return_seconds=True)  # {'start': s} / {'end': s} / None
```

Keep the RMS gate as the cheap first stage and let Silero decide "voiced": RMS fires on keyboard noise and
on Dory's own echo, Silero does not; the extra cost is under 1 ms per 32 ms frame.

**End-of-utterance silence.** Industry defaults: pipecat `VADParams(confidence=0.7, start_secs=0.2,
stop_secs=0.2, min_volume=0.6)` ([pipecat Silero](https://docs.pipecat.ai/server/utilities/audio/silero-vad-analyzer));
LiveKit endpointing `min_delay` 0.5 s, `max_delay` 3.0 s (the turn closes at the larger of the VAD silence
and `min_delay`; `max_delay` is how long a mid-sentence "thinking" pause is tolerated before the turn is
forced closed) ([LiveKit turn handling](https://docs.livekit.io/reference/agents/turn-handling-options.md)).
Recommendation (judgment): keep **0.8 s** as the normal end (conversational pauses are 500-800 ms), but
stretch to **1.5 s** when the utterance so far ends in a filler or an open clause ("and", "um", "so",
a comma, no sentence punctuation from the ASR), capped at 3 s as LiveKit does.

**Barge-in.** LiveKit's reference interruption block: `min_duration` 0.5 s, `min_words` 0,
`false_interruption_timeout` 2.0 s, `resume_false_interruption` true (a stop that is not followed by a
transcript within 2 s resumes the reply). pipecat needs 0.2 s of speech before SPEAKING. Rules for Dory
(judgment): interrupt playback only after **300 ms** of Silero-voiced audio (`min_speech_s` already 0.3),
require a non-empty transcript within 2 s or resume the reply, and ignore voiced audio that starts within
the first 300 ms of her own playback (echo onset). Echo itself: in a Discord room the bot receives one
stream per user, so Dory's voice is only in the input when a member's speakers leak into their mic; the
Discord client's own "Echo Cancellation" toggle (Voice Processing section of Voice & Video) handles that
([TechRadar](https://www.techradar.com/computing/windows/how-to-improve-your-discord-audio-quality)),
and Krisp noise suppression runs on the member's device
([Discord blog](https://discord.com/blog/tune-into-discord-with-krisp-noise-suppression-on-ios-and-android)).
On the web path request `getUserMedia({audio: {echoCancellation: true}})`, a Baseline constraint
([MDN](https://developer.mozilla.org/en-US/docs/Web/API/MediaTrackConstraints/echoCancellation)).

## 4. Emoji-free, speech-ready text

Emoji live in the Unicode blocks Miscellaneous Symbols and Pictographs U+1F300-1F5FF (skin tones
U+1F3FB-1F3FF inside it), Emoticons U+1F600-1F64F, Transport and Map U+1F680-1F6FF, Supplemental
Symbols and Pictographs U+1F900-1F9FF, Symbols and Pictographs Extended-A U+1FA70-1FAFF, Miscellaneous
Symbols U+2600-26FF, Dingbats U+2700-27BF, Miscellaneous Symbols and Arrows U+2B00-2BFF, regional
indicators U+1F1E6-1F1FF, plus the joiners VS16 U+FE0F, ZWJ U+200D and keycap U+20E3
([Blocks.txt 18.0](https://www.unicode.org/Public/UCD/latest/ucd/Blocks.txt), [UTS #51](https://www.unicode.org/reports/tr51/)).

Kokoro's normaliser (misaki `get_number`) reads digits with `num2words`, strips thousands commas, does
ordinals and decimals, but knows only `$ £ €` (`CURRENCIES`), and reads a bare 4-digit number as a
**year** unless a known currency precedes it ("2026 baht" -> "twenty twenty-six baht"; "1,500 baht" is
safe) ([misaki/en.py](https://github.com/hexgrad/misaki/blob/main/misaki/en.py)). So rewrite THB and
`฿` yourself and keep thousands separators. Verified output of the function below on a markdown reply:
`"Booked. Hotel: Nimman House, 13,700 baht. Map at 7 pm. Saved 12 percent on this one"`.

```python
import re

EMOJI = re.compile("[\U0001f300-\U0001faff\U0001f1e6-\U0001f1ff☀-➿⬀-⯿️‍⃣]+")
MD = [
    (r"```.*?```", " "),
    (r"`([^`]*)`", r"\1"),
    (r"!?\[([^\]]*)\]\([^)]*\)", r"\1"),  # code, links
    (r"(?m)^\s{0,3}#{1,6}\s*", ""),
    (r"(?m)^\s*(?:[-*•]|\d+[.)])\s+", ""),  # headers, bullets
    (r"(\*\*|__|~~)(.+?)\1", r"\2"),
    (r"(?<!\w)[*_](.+?)[*_](?!\w)", r"\1"),
]  # bold, italic
CUR = {
    "THB": "baht",
    "฿": "baht",
    "USD": "dollars",
    "$": "dollars",
    "EUR": "euros",
    "€": "euros",
    "GBP": "pounds",
    "£": "pounds",
}


def speakable(s: str) -> str:
    s = EMOJI.sub("", s)
    for rx, rep in MD:
        s = re.sub(rx, rep, s, flags=re.S)
    s = re.sub(
        r"(THB|USD|EUR|GBP|[฿$€£])\s?(\d[\d,]*(?:\.\d+)?)",
        lambda m: f"{m.group(2)} {CUR[m.group(1)]}",
        s,
    )
    s = re.sub(r"(\d)\s?%", r"\1 percent", s)
    s = re.sub(r"\s*\n+\s*", ". ", s)  # a line break becomes a sentence end (a pause)
    return re.sub(r"\.\s*\.", ".", re.sub(r"[ \t]+", " ", s)).strip()
```

`shortcut: ASCII emoticons, tables and HTML are left alone; upgrade when the LLM is seen producing them.`

## 5. Tone rules for the spoken persona (prompt text, with sources)

1. "Acknowledge in two words, then act." Google: without an acknowledgement "your persona seems hasty or
   even rude"; vary them, "Great", "Got it", "Okay", and skip some so they do not become a tic
   ([Google acknowledgements](https://developers.google.com/assistant/conversation-design/acknowledgements)).
2. "Direct answers: 1-2 short sentences", a turn a person could say in one breath. OpenAI's Verbosity
   block ("Direct answers: Use 1-2 short sentences") ([OpenAI Realtime prompting](https://developers.openai.com/api/docs/guides/realtime-models-prompting));
   Alexa: "Write responses that can be read out by a human in one or two breaths", cut 2-5 words from
   every line ([Alexa Haus, Be brief](https://www.developer.amazon.com/en-US/alexa/alexa-haus/design-principles/be-brief), [five benchmarks](https://developer.amazon.com/blogs/alexa/post/d92c7822-d289-44fd-a9fe-9652874fc3c9/five-benchmarks-for-writing-dialog-that-sounds-great-to-alexa-customers)).
3. "Ask one question at a time" and "give one step at a time unless asked for the full procedure"
   (OpenAI Verbosity block, same page).
4. "Never read a list: offer one option, at most three, and put the rest in the chat." Alexa: "Give only
   one to a few options at a time", avoid "long lists of options", "send a card" for data that is hard to
   remember (Alexa Haus). Pair it with rule 4's `speakable()`: no bullets, headers or emoji ever reach TTS.
5. "Say the person's name at most once per conversation, and your own name never; do not reuse the same
   opener twice in a row." OpenAI "Reduce Repetition": sample phrases get overused and sound "robotic or
   repetitive", so add a variety rule (same page).
6. "Contractions and active voice: 'I can help', not 'I would like to be able to help you'" (Alexa
   benchmark 4: "reduce your verb phrases to contractions"; Alexa Haus: "Speak in active voice").
7. "Say only what bears on the decision right now." Google grounds this in Grice's maxims of Quantity and
   Relevance ([Learn about conversation](https://developers.google.com/assistant/conversation-design/learn-about-conversation)).
8. "On money, health, conflict or bad news: slower, no exclamation marks, one calm sentence, then one
   next step." OpenAI's tone example "Warm, concise, confident, never fawning" with a separate Pacing
   block ("fast, but do not sound rushed"); the same guide swaps vague adjectives for explicit
   trigger-action rules, so name the triggers (same page).
9. "If the audio was unclear, say so once and ask for the one missing word; never guess." OpenAI tip:
   the wording "unintelligible" handled noisy input better than "inaudible" (same page).
10. "Reply only in the company language; a Thai utterance does not switch you." OpenAI "Language
    Constraint" (lock the output language in noisy or multilingual rooms); Dory's own audience rules
    already decide the language (`audience.py`).
11. "When you need an answer, end on the question and stop talking." Amazon's voice design guide: end the
    prompt right after the question so people do not answer over Alexa
    ([What Alexa says](https://developer.amazon.com/fr/designing-for-voice/what-alexa-says/), the page is
    served under the fr path; the English path returned 404 on 2026-10-27).

## What was not verified

- No published list of Parakeet's spellings of "Dory"; the renderings in section 2 are expectations to
  confirm with `scripts/dory_tool_calls_probe.py`-style logging of real transcripts.
- Kokoro "warm/soft" wording is third-party; the official sheet has grades only. Listen before choosing.
- The engaged-window length (12 s), pause lengths and the 300 ms barge-in gate are judgment calls
  bracketed by the Alexa / Google / LiveKit / pipecat values cited, not measured on Dory.
- `VADIterator` and the regexes were run offline (venv python, `-I`); Silero itself was not installed.
