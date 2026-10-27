"""`naming.address_kind`: for Dory, about Dory, or unclear, from an ASR transcript (cascade rooms,
docs/voice_behaviour.md C4). Spellings beyond the regex ride on the phonetic key `d-r-`."""

import pytest

from dory.naming import _phonetic_key, address_kind

CASES = [
    ("Dory, book my trip for the Lumen kickoff.", "addressed"),
    ("Hey Dori can you check the calendar", "addressed"),
    ("book it for Friday, Dory", "addressed"),
    ("Dory?", "addressed"),
    ("Okay Dorey what did we spend", "addressed"),
    ("Thanks Dory.", "addressed"),
    ("hey dolly what's up", "addressed"),  # the fuzzy spelling after a cue word
    ("Dory ยอด?", "addressed"),
    ("ดอรี่ช่วยเช็กปฏิทินหน่อย", "addressed"),
    ("ช่วยสรุปหน่อยดอรี่", "addressed"),
    ("ดอรี่คะ", "addressed"),
    ("Dory booked it yesterday, nice.", "mentioned"),
    ("I think Dory said Friday", "mentioned"),
    ("we should ask Dory later about the invoice", "mentioned"),
    ("เมื่อวานดอรี่จองให้แล้วนะ", "mentioned"),
    ("can Dory check that for us?", "unclear"),
    ("ให้ดอรี่เช็กให้ได้ไหม", "unclear"),
    ("That's a nice story about the door.", None),
    ("glory to the team", None),
    ("the dolly is on the cart", None),
    ("เรามาประชุมกันเลย", None),
    ("", None),
]


@pytest.mark.parametrize(("text", "kind"), CASES)
def test_address_kind(text, kind):
    assert address_kind(text) == kind


def test_phonetic_key_folds_the_spellings_the_asr_produces_but_not_story():
    assert {
        _phonetic_key(w)
        for w in ("Dory", "dori", "Dorie", "Dorey", "dorry", "Door-y", "Dory's", "Dora")
    } == {"d-r-"}
    assert _phonetic_key("story") == "st-r-" and _phonetic_key("door") == "d-r"
