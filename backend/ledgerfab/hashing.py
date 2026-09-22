"""Dataset hashing — the determinism proof required by spec 00 A3.

``generate(profile, seed)`` twice must produce the same hash; changing the seed
must change it. The hash is taken over a canonical form: keys sorted, dates as
ISO strings, floats rounded to cents. Without that canonicalisation the hash
would be sensitive to dict ordering and float formatting rather than to the data,
and the determinism test would pass or fail for the wrong reasons.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date
from enum import Enum
from typing import Any


def canonicalise(value: Any) -> Any:
    """Recursively convert a World payload into stable, JSON-safe primitives."""
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, float):
        # Money is cents; anything finer is float noise, not data.
        return round(value, 2)
    if isinstance(value, dict):
        return {k: canonicalise(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonicalise(v) for v in value]
    return value


def canonical_json(payload: dict[str, Any]) -> str:
    return json.dumps(
        canonicalise(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )


def dataset_hash(world: Any) -> str:
    """SHA-256 over the canonical form of a World. Stable across processes and runs."""
    return hashlib.sha256(canonical_json(world.to_dict()).encode("utf-8")).hexdigest()
