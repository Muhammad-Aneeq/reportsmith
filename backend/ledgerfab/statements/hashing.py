"""Determinism proof for a statement set (spec 00 A3).

A local hash rather than a change to the vendored `ledgerfab.hashing`. Upstream's
``canonicalise`` handles ``float`` and would raise on a ``Decimal``, and editing it
would widen the fork surface for a small variant (PLAN.md **D-002**; finsight made the
same call in its D-017).

The variant matters. Money canonicalises to a fixed 2-dp **string**, never through a
float. Serialising a Decimal via float at the one step whose entire job is proving the
data did not change would be an unusually good way to hide a change.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import Any


def canonicalise(value: Any) -> Any:
    """Recursively convert to stable, JSON-safe primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):  # pragma: no cover - the emitter holds no floats
        raise TypeError(
            "a float reached statement hashing; money in this extension is Decimal "
            "(ledgerfab/statements/money.py). Find the float — do not round it away."
        )
    if isinstance(value, dict):
        return {k: canonicalise(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonicalise(v) for v in value]
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        canonicalise(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def statement_hash(statement_set: Any) -> str:
    """SHA-256 over the canonical form. Stable across processes and runs."""
    return hashlib.sha256(canonical_json(statement_set.to_dict()).encode("utf-8")).hexdigest()
