"""Counterparties and the alias variants a bank statement actually shows.

Bank feeds rarely carry the counterparty's legal name. They carry whatever the
payer typed, truncated to the bank's field width and shouted in caps. Those
variants are what break naive string matching, so the ``alias_rate`` knob decides
how often a transaction refers to a counterparty by an alias instead.
"""

from __future__ import annotations

from ledgerfab.models import Counterparty
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng

_STEMS = [
    "Acme",
    "Bluefin",
    "Copperfield",
    "Dunmore",
    "Eastgate",
    "Fairhaven",
    "Greylock",
    "Hollowway",
    "Ironvale",
    "Jarrow",
    "Kestrel",
    "Langdale",
    "Marchmont",
    "Northgate",
    "Orrell",
    "Pentland",
    "Quarrydale",
    "Redmayne",
]

_QUALIFIERS = ["Supplies", "Logistics", "Consulting", "Systems", "Partners", "Industrial"]
_SUFFIXES = ["Ltd", "Limited", "LLP", "PLC", "& Co"]
_COUNTRIES = ["GB", "GB", "GB", "IE", "NL", "DE"]  # weighted toward domestic


def _alias_variants(canonical: str, rng: Rng) -> list[str]:
    """Plausible ways the same company appears on a statement line."""
    words = canonical.split()
    stem = words[0]
    without_suffix = " ".join(
        w for w in words if w not in {"Ltd", "Limited", "LLP", "PLC", "&", "Co"}
    )

    candidates = [
        without_suffix,  # "Acme Supplies"
        stem,  # "Acme"
        canonical.upper(),  # "ACME SUPPLIES LTD"
        without_suffix.upper().replace(" ", ""),  # "ACMESUPPLIES"
        f"{stem.upper()} {rng.randint(1000, 9999)}",  # "ACME 4471" — bank ref style
        canonical.replace("Limited", "Ltd").replace("Ltd", "LTD"),
    ]

    # Deduplicate while preserving order; never alias to the canonical name itself.
    seen: set[str] = set()
    out: list[str] = []
    for c in candidates:
        if c and c != canonical and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def generate_counterparties(rng: Rng, profile: Profile) -> list[Counterparty]:
    stems = rng.sample(_STEMS, profile.n_counterparties)
    out: list[Counterparty] = []

    for i, stem in enumerate(stems, start=1):
        qualifier = rng.choice(_QUALIFIERS)
        suffix = rng.choice(_SUFFIXES)
        canonical = f"{stem} {qualifier} {suffix}"

        out.append(
            Counterparty(
                id=f"CP-{i:03d}",
                canonical_name=canonical,
                aliases=_alias_variants(canonical, rng),
                payment_terms_days=rng.choice([14, 30, 30, 45, 60]),
                country=rng.choice(_COUNTRIES),
            )
        )

    return out
