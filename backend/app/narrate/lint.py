"""The deterministic tone linter. Runs before the judge, and never invents prose.

Spec 13 F4: *"style linter enforces tone rules deterministically where possible (rounding,
taboo phrases) with violations auto-fixed or flagged."*

The rule that keeps this safe: **auto-fix is formatting-only and may never change a
figure's value.** It can turn `-£1,234` into `(£1,234)` because the pack's style says
negatives are parenthesised. It cannot turn `£1,234.56` into `£1,235` — that is a rounding
decision, and a module that rounds numbers on the way out of verification would be undoing
the guarantee numcheck had just established.

So the pipeline re-runs numcheck *after* the linter (PLAN.md **D-015**), and
`test_lint_preserves_figures.py` asserts that every fix leaves the verification verdict
unchanged.

Taboo phrases are **flagged, never fixed**. Choosing the honest replacement for
"significant" is a judgement about the business, and that judgement belongs to the reviewer
whose name goes on the sign-off.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from app.template.schema import PackStyle
from numcheck.surgery import split_sentences

Severity = Literal["error", "warning"]


@dataclass(frozen=True, slots=True)
class Violation:
    rule: str
    severity: Severity
    message: str
    excerpt: str
    fixed: bool = False

    def to_json(self) -> dict[str, object]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "message": self.message,
            "excerpt": self.excerpt,
            "fixed": self.fixed,
        }


# "-£1,234.00" → "(£1,234.00)". Only when the pack asks for parenthesised negatives.
_LEADING_MINUS_MONEY = re.compile(r"(?<![\w)])[-−]\s?([£$€¥]\s?[\d,]+(?:\.\d+)?)")

# Two spaces, a space before punctuation — cosmetic, always safe, never about a digit.
_DOUBLE_SPACE = re.compile(r"  +")
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.;:%])")

# "no recommendations", "do not recommend", "never recommend", "avoid recommending".
_RECOMMENDATION_BAN = re.compile(r"(no|not|never|avoid)[^.]{0,24}?recommend", re.I)


def lint(
    text: str, style: PackStyle, tone_rules: list[str] | None = None
) -> tuple[str, list[Violation]]:
    """Return (possibly-fixed text, violations).

    Fixes applied here are recorded with ``fixed=True`` so the Review screen can show the
    reviewer what was changed on their behalf rather than presenting it as the model's
    own words.
    """
    violations: list[Violation] = []
    out = text

    # -- auto-fixable: presentation only ------------------------------------
    if style.currency.negative == "parens":

        def _parenthesise(match: re.Match[str]) -> str:
            return f"({match.group(1)})"

        fixed_text, count = _LEADING_MINUS_MONEY.subn(_parenthesise, out)
        if count:
            violations.append(
                Violation(
                    rule="currency.negative",
                    severity="warning",
                    message=(
                        f"rendered {count} negative amount(s) in parentheses, "
                        f"per the pack style"
                    ),
                    excerpt="",
                    fixed=True,
                )
            )
            out = fixed_text

    collapsed, spaces = _DOUBLE_SPACE.subn(" ", out)
    tightened, tight = _SPACE_BEFORE_PUNCT.subn(r"\1", collapsed)
    if spaces or tight:
        violations.append(
            Violation(
                rule="whitespace",
                severity="warning",
                message="tidied spacing",
                excerpt="",
                fixed=True,
            )
        )
        out = tightened

    # -- flagged, never fixed -----------------------------------------------
    lowered = out.lower()
    for phrase in style.taboo_phrases:
        for match in re.finditer(rf"\b{re.escape(phrase)}\b", lowered):
            violations.append(
                Violation(
                    rule="taboo_phrase",
                    severity="error",
                    message=(
                        f"{phrase!r} is on this pack's banned list. Replace it with what the "
                        f"figures actually show — the honest wording is a judgement for the "
                        f"reviewer, not an automatic substitution."
                    ),
                    excerpt=out[max(0, match.start() - 30) : match.end() + 30].strip(),
                )
            )

    for sentence in split_sentences(out):
        words = len(sentence.split())
        if words > style.max_sentence_words:
            violations.append(
                Violation(
                    rule="max_sentence_words",
                    severity="warning",
                    message=f"{words} words; this pack's limit is {style.max_sentence_words}",
                    excerpt=sentence[:90] + ("…" if len(sentence) > 90 else ""),
                )
            )

    # Recommendation-shaped language, when the voice forbids it. Matched on a small,
    # explicit list rather than anything clever: a false positive here costs a reviewer
    # thirty seconds, and a vague heuristic would produce many.
    # Match a *prohibition*, not one exact phrase. The shipped pack says "Do not
    # recommend, forecast, or speculate"; an earlier exact-string check silently did
    # nothing for it, which is the worst outcome for a rule of this kind.
    if _RECOMMENDATION_BAN.search(style.voice):
        for pattern in (
            r"\bshould\b",
            r"\bmust\b",
            r"\brecommend(?:ed|s|ation)?\b",
            r"\bwe suggest\b",
        ):
            for match in re.finditer(pattern, lowered):
                violations.append(
                    Violation(
                        rule="voice.no_recommendations",
                        severity="error",
                        message=(
                            "this pack's voice forbids recommendations; "
                            "state what the figures show"
                        ),
                        excerpt=out[max(0, match.start() - 30) : match.end() + 30].strip(),
                    )
                )

    return out, violations


def has_blocking_violations(violations: list[Violation]) -> bool:
    """Errors block a section from being marked clean; warnings do not.

    Warnings are things the linter already handled. Errors are things only a person can.
    """
    return any(v.severity == "error" and not v.fixed for v in violations)
