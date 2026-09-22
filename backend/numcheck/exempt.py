"""The exemption list. It has two entries, and a test asserts it has exactly two.

**Exemption creep is how this class of checker quietly dies.** Every exemption is a hole a
fabricated number can walk through, and each one arrives individually reasonable: dates,
then percentages of percentages, then "round numbers", and at some point the gate is
green because it stopped looking.

So the list is closed, its exact contents are asserted by a test, and the rule for
anything else is: **if the narrative may legitimately cite a number, supply it as a
`FigureRef`.** A figure the caller is willing to vouch for is data. A figure the caller
wants the checker to ignore is a hole.
"""

from __future__ import annotations

import re

from numcheck.models import NumericToken

# 1. Period labels the caller declared. Not "any four-digit number that looks like a
#    year" — only the exact labels this narrative was told it is writing about, so
#    "2024" passes while an invented "2019" does not.
# 2. Ordinals in list markers: the "1." beginning a numbered line. Structure, not a claim.
_LIST_MARKER = re.compile(r"(?:^|\n)\s*\d{1,2}[.)]\s")


def is_exempt(token: NumericToken, text: str, periods: frozenset[str]) -> tuple[bool, str]:
    """Is this token structure rather than a claim about the data?

    Returns (exempt, why) so a verdict can explain itself.
    """
    # 1 — a declared period label.
    #
    # By **span containment**, not by string equality. A label like "2024-07" tokenises
    # as two numbers — `2024`, then `-07` read as a negative — so comparing token text to
    # the label misses both halves and the sentence gets dropped for citing its own
    # period. Asking instead "does this token lie inside an occurrence of a declared
    # label?" is exact, and works for every spelling a caller might declare: 2024-07,
    # Jul 2024, 2024/07, Q3 2024.
    for period in periods:
        start = text.find(period)
        while start != -1:
            if start <= token.start and token.end <= start + len(period):
                return True, f"inside declared period label {period!r}"
            start = text.find(period, start + 1)

    # A bare, whole-number token that *is* a declared label on its own ("2024").
    if token.unit == "bare" and token.precision == 0 and token.text.strip() in periods:
        return True, "declared period label"

    # 2 — an ordinal that opens a list item.
    for marker in _LIST_MARKER.finditer(text):
        if marker.start() <= token.start < marker.end():
            return True, "ordinal list marker"

    return False, ""


# Exported so the test can assert the list has not grown.
EXEMPTIONS: tuple[str, ...] = ("declared period label", "ordinal list marker")
