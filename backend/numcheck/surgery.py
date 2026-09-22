"""Sentence surgery: split prose, and drop only the sentences that failed.

Spec 12 F5's rule ends *"mismatches fail the draft, one retry, else that sentence is
dropped."* Dropping one sentence rather than the whole paragraph is what keeps the
mechanism usable: a draft with nine good sentences and one unsupportable figure should
lose the figure, not the draft.

The splitter is decimal- and abbreviation-aware, because the text it operates on is full
of both. Splitting "£1.4m." on the decimal point produces two fragments, neither of which
is a sentence, and the drop then removes half of a good one.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from numcheck.models import FigureRef
from numcheck.verify import verify

# Abbreviations whose full stop does not end a sentence. Short and closed — the same
# discipline as the exemption list, for the same reason.
_ABBREVIATIONS = frozenset(
    {"ltd", "plc", "inc", "llp", "co", "no", "vs", "approx", "e.g", "i.e", "etc", "dr", "mr", "ms"}
)

# A boundary is: [.!?] + whitespace + something that starts a sentence. The lookbehind
# excludes a digit, so "1.4" never splits.
_BOUNDARY = re.compile(r"(?<=[.!?])\s+(?=[A-Z£$€¥(])")


def split_sentences(text: str) -> list[str]:
    """Split into sentences, preserving the original spacing inside each."""
    if not text.strip():
        return []

    pieces = _BOUNDARY.split(text.strip())
    out: list[str] = []
    for piece in pieces:
        # Re-join when the previous fragment ended on a known abbreviation, which the
        # regex cannot know about on its own.
        if out:
            tail = out[-1].rstrip()
            last_word = re.split(r"[\s(]", tail)[-1].rstrip(".").lower()
            if last_word in _ABBREVIATIONS:
                out[-1] = f"{out[-1]} {piece}"
                continue
        out.append(piece)
    return out


def drop_failing_sentences(
    text: str,
    refs: Iterable[FigureRef],
    periods: Iterable[str] = (),
) -> tuple[str, list[str]]:
    """Return (surviving text, dropped sentences).

    Each sentence is verified on its own. A sentence carrying an unsupportable figure is
    removed whole — not edited, not patched. Rewriting it here would mean this module
    inventing prose, which is exactly the authority it must not have: its job is to
    remove claims, never to make them.
    """
    ref_list = list(refs)
    kept: list[str] = []
    dropped: list[str] = []

    for sentence in split_sentences(text):
        if verify(sentence, ref_list, periods).ok:
            kept.append(sentence)
        else:
            dropped.append(sentence)

    return " ".join(kept).strip(), dropped
