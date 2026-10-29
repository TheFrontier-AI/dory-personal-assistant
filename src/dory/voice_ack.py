"""A request-specific spoken acknowledgment for a slow voice turn (docs/voice_behaviour.md C8): one
cheap text call prepared while the brain works, so Dory says what she is doing ("Checking Friday
flights to Singapore") instead of a stock holding phrase. Pure: no discord, no socket."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from google.genai import types
from pydantic import BaseModel

from .i18n import lang_name
from .llm import generate

logger = logging.getLogger(__name__)

MAX_CHARS = 60
STOCK = (
    "one moment",
    "let me see",
    "just a sec",
    "hold on",
    "give me a second",
    "bear with me",
    "แป๊บ",
    "สักครู่",
)
PROMPT = (
    'You are Dory, an upbeat assistant on a voice call. The person just said: "{q}"\n'
    "Write ONE short spoken acknowledgment in {language} (2 to 7 words) that names what you are "
    "about to do or look up for them, in your own words. Never a stock holding phrase such as "
    '"one moment", "let me see", "just a sec" or "hold on"; no emoji; no question. '
    "If there is nothing to check, answer with an empty string."
)


class _Ack(BaseModel):
    ack: str


def ack_line(client, model: str, question: str, lang: str) -> str:
    """The line, or "" on any failure, a stock phrase or an over-long answer (the caller then
    speaks a canned `ack_voice_*` line instead)."""
    try:
        resp = generate(
            client,
            model,
            PROMPT.format(q=question[:300], language=lang_name(lang)),
            types.GenerateContentConfig(
                temperature=0.8,
                max_output_tokens=40,
                response_mime_type="application/json",
                response_schema=_Ack,
            ),
        )
        line = _Ack.model_validate(json.loads(resp.text)).ack.strip().splitlines()[0].strip()
    except Exception as e:  # noqa: BLE001 - a filler is never worth an error
        logger.debug("voice ack: %s", type(e).__name__)
        return ""
    if not line or len(line) > MAX_CHARS or any(s in line.lower() for s in STOCK):
        return ""
    return line


def make_ack(client, model: str) -> Callable[[str, str], str]:
    """`ack(question, lang)` for `GlmVoice(ack=...)`."""
    return lambda question, lang: ack_line(client, model, question, lang)
