"""verify(text, refs, periods) → a verdict per numeric token."""

from __future__ import annotations

from collections.abc import Iterable

from numcheck.exempt import is_exempt
from numcheck.match import find_match
from numcheck.models import CheckResult, FigureRef, TokenVerdict
from numcheck.tokens import tokenize


def verify(
    text: str,
    refs: Iterable[FigureRef],
    periods: Iterable[str] = (),
) -> CheckResult:
    """Check every number in ``text`` against the figures it is allowed to cite.

    ``periods`` are the period labels this narrative was told it is writing about. They
    are the only dates that pass unchallenged — an invented year is a failure, which is
    the behaviour you want from something guarding a signed document.
    """
    ref_list = list(refs)
    period_set = frozenset(str(p) for p in periods)
    verdicts: list[TokenVerdict] = []

    for token in tokenize(text):
        exempt, why = is_exempt(token, text, period_set)
        if exempt:
            verdicts.append(TokenVerdict(token=token, ok=True, reason=why))
            continue

        match = find_match(token, ref_list)
        if match is not None:
            verdicts.append(TokenVerdict(token=token, ok=True, matched_ref=match.ref_id))
            continue

        # The message names the closest ref by unit, because the overwhelmingly common
        # real failure is a right figure with the wrong unit or a transposed digit — and
        # "no figure matches 27.9%" sends a reviewer hunting, while "closest: gross
        # margin 27.86%" ends the question.
        same_unit = [r for r in ref_list if r.unit == token.unit]
        closest = min(same_unit, key=lambda r: abs(r.value - token.value)) if same_unit else None
        detail = (
            f"; closest same-unit figure: {closest.label or closest.ref_id} = {closest.value}"
            if closest
            else "; no figure of that unit was supplied"
        )
        verdicts.append(
            TokenVerdict(
                token=token,
                ok=False,
                reason=f"no supplied figure supports {token.text!r}{detail}",
            )
        )

    return CheckResult(verdicts=verdicts)
