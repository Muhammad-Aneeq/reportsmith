"""Tracked edits: the AI draft is preserved, and every human change is a recorded diff.

Spec 13 F5: *"human edits tracked as diffs (AI draft preserved alongside final)."*

Two rules, both enforced here rather than by convention:

**`ai_draft_json` is written once.** `record_edit` never touches it. So the draft cannot be
lost by editing, which is what makes "the AI draft is preserved" a property of the code
rather than a promise.

**Editing an approved section revokes its approval** (PLAN.md **D-012**). Without that, the
sign-off guard "all sections approved" could be true of text nobody approved — and that is
precisely the case where the guarantee matters.
"""

from __future__ import annotations

import difflib
from typing import Any


def make_diff(before: str, after: str, *, context: int = 2) -> dict[str, Any]:
    """A unified diff plus the counts the UI shows without re-diffing."""
    before_lines = before.splitlines(keepends=False)
    after_lines = after.splitlines(keepends=False)
    unified = list(
        difflib.unified_diff(
            before_lines, after_lines, fromfile="before", tofile="after", n=context, lineterm=""
        )
    )
    added = sum(1 for line in unified if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in unified if line.startswith("-") and not line.startswith("---"))

    return {
        "unified": unified,
        "lines_added": added,
        "lines_removed": removed,
        "words_before": len(before.split()),
        "words_after": len(after.split()),
        "before": before,
        "after": after,
    }


def word_diff(before: str, after: str) -> list[dict[str, str]]:
    """Word-level opcodes for the Review screen's inline diff.

    Word-level, not line-level: a narrative section is one paragraph, so a line diff
    reports "the paragraph changed" and shows the reviewer nothing. The reviewer's
    question is always *which words did a person change* — that is the whole point of
    tracked edits, and answering it needs this granularity (PLAN.md **D-019**).
    """
    before_words = before.split()
    after_words = after.split()
    matcher = difflib.SequenceMatcher(a=before_words, b=after_words, autojunk=False)

    out: list[dict[str, str]] = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            out.append({"op": "equal", "text": " ".join(before_words[i1:i2])})
        elif tag == "delete":
            out.append({"op": "delete", "text": " ".join(before_words[i1:i2])})
        elif tag == "insert":
            out.append({"op": "insert", "text": " ".join(after_words[j1:j2])})
        else:  # replace — emitted as a delete/insert pair so the UI can style both
            out.append({"op": "delete", "text": " ".join(before_words[i1:i2])})
            out.append({"op": "insert", "text": " ".join(after_words[j1:j2])})
    return out


def summarise(diff: dict[str, Any]) -> str:
    """One line for the edit history."""
    delta = diff["words_after"] - diff["words_before"]
    direction = "+" if delta > 0 else ""
    return (
        f"{diff['lines_added']} line(s) added, {diff['lines_removed']} removed "
        f"({direction}{delta} words)"
    )
