"""numcheck — the numeric cross-check for LLM-drafted financial prose.

    from numcheck import verify, FigureRef

    refs = [FigureRef(ref_id="rev", value=Decimal("3815070.61"), unit="money", label="Revenue")]
    verify("Revenue was £3.8m.", refs).ok    # True  — 3.8m to one decimal place
    verify("Revenue was £3.9m.", refs).ok    # False — not supported by any figure

Standalone by design: this package imports nothing from its host application, and its
only third-party dependency is pydantic. See ORIGIN.md.
"""

from numcheck.harness import FidelityReport, score
from numcheck.match import find_match, matches
from numcheck.models import CheckResult, FigureRef, NumericToken, TokenVerdict, Unit
from numcheck.surgery import drop_failing_sentences, split_sentences
from numcheck.tokens import tokenize
from numcheck.verify import verify

__all__ = [
    "CheckResult",
    "FidelityReport",
    "FigureRef",
    "NumericToken",
    "TokenVerdict",
    "Unit",
    "drop_failing_sentences",
    "find_match",
    "matches",
    "score",
    "split_sentences",
    "tokenize",
    "verify",
]

__version__ = "0.1.0"
