"""Recognising Dory's name in free text (Thai and Latin, misspellings included)."""

from __future__ import annotations

import re

# Thai spellings of ดอรี่ (ดอรี, โดรี่, ดอร์รี่, ดอหรี่ and the r/l swap ดอลี่ / โดลี่ that Thai speech
# produces) and the Latin forms. "ดอลลี่" (Dolly) has a double ล, so it never matches here (it is a
# risky mishearing below). Latin forms must not sit inside a longer word ("dorito").
_WAKE_RE = re.compile(
    r"(?:(?:โด|ด[อ่]อ?|ดอร์|ดอห)\s?(?:ร|ล|หร)[ิี][่้]?"
    r"|(?<![a-z])(?:dory|dori|dorie|doree|dorry|dorey|do\s?ry)(?![a-z]))",
    re.I,
)
# Custom emoji (<:dory:123>) and links carry names that are not people talking to Dory.
_NOISE_RE = re.compile(r"<a?:\w+:\d+>|https?://\S+")


def mentions_name(text: str) -> bool:
    """True when Dory's name appears in `text`, with or without an @mention."""
    return _WAKE_RE.search(_NOISE_RE.sub(" ", text or "")) is not None


# Misheard names in SPEECH transcripts: ดอลลี่ / Dolly, ทอรี่ / โทรี่ / Tory, ตอรี่. They count
# only as an address: with a greeting, a politeness particle, "น้อง", or alone at the start / end
# of the utterance, never in the middle of a sentence ("ตุ๊กตาดอลลี่ของผม").
# "โดลลี่ / โทลี่" are how the speech model writes the name after "เฮ้". They count only right
# after a greeting (below), never alone.
_FUZZY = r"(?:ดอลลี่|ทอรี่|โทรี่|ตอรี่|dolly|tory)"
_FUZZY_GREETED = r"(?:โดลลี่|โทลี่|ดอลลี่|ทอรี่|โทรี่)"
_GREET = r"(?:หวัดดี|สวัสดี|ว่าไง|เฮ้|hey|hi|hello|ok)"
_PART = r"(?:ครับ|ค่ะ|คะ|นะ|จ๋า|จ้า)"
_FUZZY_RE = re.compile(
    rf"(?:{_GREET}\s*{_PART}?\s*(?P<a>{_FUZZY}|{_FUZZY_GREETED})(?![ก-๙a-z])"
    rf"|(?<![ก-๙a-z])(?P<b>{_FUZZY})\s*{_GREET}"
    rf"|น้อง\s?(?P<c>{_FUZZY})"
    rf"|(?<![ก-๙a-z])(?P<d>{_FUZZY})\s*{_PART}(?![ก-๙])"
    rf"|^[\s,.!?]*(?P<e>{_FUZZY})(?=[\s,.!?]|$)"
    rf"|(?:^|[\s,])(?P<f>{_FUZZY})[\s.!?]*$)",
    re.I,
)


def find_call(text: str) -> tuple[int, int] | None:
    """(start, end) of Dory's name in a spoken transcript, else None. The usual spellings always
    count; the risky mishearings (ดอลลี่, ทอรี่, Dolly...) only when used as an address."""
    text = text or ""
    m = _WAKE_RE.search(text)
    if m is not None:
        return m.start(), m.end()
    m = _FUZZY_RE.search(text)
    if m is None:
        return None
    g = next(k for k in "abcdef" if m.group(k) is not None)
    return m.start(g), m.end(g)


_LEAD_JUNK = " \t\n,.:;!?-–—…/@"
_NAME_AT_START = re.compile(rf"^(?:{_WAKE_RE.pattern})", _WAKE_RE.flags)
# Politeness / filler words that may trail a typed command ("เข้าประชุมหน่อยนะครับ", "be quiet please").
_TRAIL_POLITE = re.compile(
    r"(?:[\s,.!?…]+|^)(?:ครับ|ค่ะ|คะ|นะ|จ้ะ|จ๊ะ|จ้า|หน่อย|ด้วย|เถอะ|ซิ|เลย|please|pls|plz)$"
    r"|(?:ครับ|ค่ะ|คะ|นะ|จ้ะ|จ๊ะ|จ้า|หน่อย|ด้วย|เถอะ|เลย)$",
    re.I,
)


def strip_leading_name(text: str) -> tuple[str, bool]:
    """Remove Dory's name from the START of `text` ("Dory เข้าประชุมหน่อย" -> "เข้าประชุมหน่อย").
    Returns (rest, True) when a name was removed, else (text, False). Does not touch trailing
    words; see `strip_trailing_polite` for those."""
    s = (text or "").lstrip(_LEAD_JUNK)
    m = _NAME_AT_START.match(s)
    if not m:
        return text, False
    return s[m.end() :].lstrip(_LEAD_JUNK), True


def strip_trailing_polite(text: str) -> str:
    """Drop trailing politeness words (หน่อย ด้วย ครับ ค่ะ นะ please ...), repeatedly."""
    s = (text or "").strip()
    while True:
        new = _TRAIL_POLITE.sub("", s).rstrip(" \t\n,.!?…")
        if new == s or not new:
            return new or s
        s = new


def command_text(text: str) -> tuple[str, bool]:
    """Text to feed the typed-command parsers: a leading name and trailing politeness removed.
    The bool says whether a leading name was present (an untagged command needs one)."""
    rest, named = strip_leading_name(text)
    return strip_trailing_polite(rest), named


# ---- is an utterance FOR Dory, or ABOUT her? (the cascade voice path decides from the ASR text)
_CUES = {"hey", "hi", "hello", "ok", "okay", "thanks", "thank", "please", "so", "um", "yo"}
_MENTION_NEXT = {
    "said",
    "told",
    "was",
    "has",
    "had",
    "did",
    "went",
    "already",
    "also",
    "is",
    "will",
}
_REQUEST_RE = re.compile(
    r"\?|ไหม|มั้ย|หรือเปล่า|หรือไม่|ช่วย|ขอ|หน่อย|(?<![a-z])(?:what|who|when|where|why|how|which|can"
    r"|could|would|please|tell|book|find|check|remind|send|show)(?![a-z])",
    re.I,
)
_LATIN_TOKEN_RE = re.compile(r"[A-Za-z'-]+|[,?!.]")


def _phonetic_key(word: str) -> str:
    """dory / dori / dorie / dorey / dorry / doory / dora -> "d-r-"; story -> "st-r-"; door -> "d-r"."""
    w = re.sub(r"[^a-z]", "", re.sub(r"'s$", "", word.lower()))
    return re.sub(r"[aeiouy]+", "-", re.sub(r"(.)\1+", r"\1", w))


def address_kind(text: str) -> str | None:
    """None = her name is not in the utterance. "addressed" = said TO her (the name opens or closes
    it, follows a cue word like "hey" / "ok", or stands before a comma or question mark; every
    spelling `find_call` knows plus the phonetic key for Dori / Dorey / Doory / Dora). "mentioned" =
    a sentence ABOUT her ("Dory booked it", "ask Dory later"). "unclear" = mentioned in a sentence
    shaped like a request ("can Dory check that?"): worth a brief "Yes?", never an interruption."""
    raw = _NOISE_RE.sub(" ", text or "").strip()
    if not raw:
        return None
    found = [(m.group(), m.start()) for m in _LATIN_TOKEN_RE.finditer(raw)]
    toks = [t for t, _ in found]
    words = [t for t in toks if t[0].isalpha()]
    hit = next(
        (i for i, t in enumerate(toks) if t[0].isalpha() and _phonetic_key(t) == "d-r-"), None
    )
    span = find_call(raw) if hit is None else None
    if hit is None and span is None:
        return None
    if hit is None:  # a spelling the key misses (Dolly after "hey"): the token under the span
        hit = next((i for i, (_, at) in enumerate(found) if span[0] <= at < span[1]), None)
    if hit is None or not words:  # Thai (no spaces): the name's place in the text decides
        head, tail = raw[: span[0]], strip_trailing_polite(raw[span[1] :])
        head = re.sub(r"(?:ครับ|ค่ะ|คะ|นะ|เฮ้|เฮ้ย|หวัดดี|สวัสดี|ว่าไง|น้อง|\W)+$", "", head)
        if not head or not tail:
            return "addressed"
        return "unclear" if _REQUEST_RE.search(raw) else "mentioned"
    prev = toks[hit - 1].lower() if hit else ""
    nxt = toks[hit + 1].lower() if hit + 1 < len(toks) else ""
    if nxt in _MENTION_NEXT or (nxt.endswith("ed") and nxt.isalpha()):
        return "mentioned"
    word_pos = sum(1 for t in toks[:hit] if t[0].isalpha())
    if prev in _CUES or nxt in (",", "?", "!") or word_pos == 0 or word_pos >= len(words) - 2:
        return "addressed"
    return "unclear" if _REQUEST_RE.search(raw) else "mentioned"
