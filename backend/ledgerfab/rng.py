"""Seeded randomness. Every random decision in ledgerfab routes through here.

Determinism contract (spec 00 A3): same seed + profile => byte-identical dataset.
That holds only if nothing in the package calls ``random``, ``uuid4`` or
``datetime.now`` directly. This module is the single sanctioned source.

Streams: each generator draws from its own named sub-stream, derived from the
root seed by hashing. Adding a counterparty therefore cannot shift the numbers
drawn by the invoice generator — a property that keeps eval cases stable as the
engine grows.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date, timedelta


def derive_seed(root_seed: int, stream: str) -> int:
    """Deterministically derive a sub-stream seed from a root seed and a name."""
    digest = hashlib.sha256(f"{root_seed}:{stream}".encode()).digest()
    return int.from_bytes(digest[:8], "big")


class Rng:
    """Thin deterministic wrapper over ``random.Random`` with domain helpers."""

    def __init__(self, seed: int, stream: str = "root") -> None:
        self.seed = seed
        self.stream = stream
        self._r = random.Random(derive_seed(seed, stream))

    def child(self, stream: str) -> Rng:
        """A new independent stream derived from the same root seed."""
        return Rng(self.seed, f"{self.stream}/{stream}")

    # -- primitives ----------------------------------------------------------
    def chance(self, probability: float) -> bool:
        """True with the given probability. ``chance(0)`` is never True."""
        if probability <= 0.0:
            return False
        if probability >= 1.0:
            return True
        return self._r.random() < probability

    def randint(self, low: int, high: int) -> int:
        return self._r.randint(low, high)

    def uniform(self, low: float, high: float) -> float:
        return self._r.uniform(low, high)

    def choice(self, seq):  # type: ignore[no-untyped-def]
        return self._r.choice(list(seq))

    def sample(self, seq, k: int):  # type: ignore[no-untyped-def]
        items = list(seq)
        k = min(k, len(items))
        return self._r.sample(items, k)

    def shuffled(self, seq):  # type: ignore[no-untyped-def]
        items = list(seq)
        self._r.shuffle(items)
        return items

    # -- domain helpers ------------------------------------------------------
    def money(self, low: float, high: float) -> float:
        """An amount rounded to cents — money never carries float dust."""
        return round(self._r.uniform(low, high), 2)

    def pct_of(self, amount: float, low_pct: float, high_pct: float) -> float:
        """A percentage slice of an amount, rounded to cents."""
        return round(amount * self._r.uniform(low_pct, high_pct), 2)

    def date_between(self, start: date, end: date) -> date:
        """A date in [start, end]. Fixed endpoints in, deterministic date out."""
        span = (end - start).days
        if span <= 0:
            return start
        return start + timedelta(days=self._r.randint(0, span))

    def jitter_days(self, base: date, low: int, high: int) -> date:
        return base + timedelta(days=self._r.randint(low, high))
