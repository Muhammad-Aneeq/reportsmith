"""The vendored engine works, and it is still the engine we vendored.

PLAN.md P1: *"Run the vendored engine's own determinism check before building on it —
prove the seed works first."* Everything in `ledgerfab/statements/` will be built on
top of this package's `Rng` and hashing machinery, so a broken or drifted seed would
surface later as a mysterious failure in the statement emitter.

Two separate claims are tested here, and they fail for different reasons:

1. **The engine works** — `generate()` produces a world, and the spec 00 A3
   determinism contract holds (same seed+profile → identical hash; different seed →
   different hash).
2. **The vendored files have not changed silently** — the SHA-256 manifest in
   `ledgerfab/VENDORED.md` still describes the files on disk. An undocumented edit to
   vendored code is how a fork stops being copyable, so it is a test failure rather
   than a code-review hope.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from ledgerfab import PROFILES, dataset_hash, generate

LEDGERFAB_DIR = Path(__file__).resolve().parents[1] / "ledgerfab"
VENDORED_MD = LEDGERFAB_DIR / "VENDORED.md"


# ------------------------------------------------------------ the engine works --


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_generate_produces_a_populated_world(profile: str) -> None:
    world = generate(profile, seed=42)

    assert world.company.id == "CO-001"
    assert world.profile_name == profile
    assert world.accounts, "chart of accounts is empty"
    assert world.invoices, "no invoices generated"
    assert world.transactions, "no bank transactions generated"
    assert world.gl_entries, "no GL entries generated"
    assert world.ground_truth.matches or world.ground_truth.exceptions


def test_gl_is_balanced_per_invoice() -> None:
    """The base engine books an expense debit and a payables credit per invoice.

    Asserted because `statements/` derives a trial balance, and it inherits this
    engine's convention that `GLEntry.amount` is debit-positive. If that ever
    stopped holding, the statement emitter's balancing would be wrong in a way that
    is hard to see from the statements themselves.
    """
    world = generate("realistic", seed=42)
    total = sum(e.debit - e.credit for e in world.gl_entries)
    assert round(total, 2) == 0.0


@pytest.mark.parametrize("profile", sorted(PROFILES))
def test_same_seed_and_profile_is_byte_identical(profile: str) -> None:
    """Spec 00 A3: *"same seed+profile = identical dataset, hash-verifiable"*."""
    assert dataset_hash(generate(profile, seed=42)) == dataset_hash(generate(profile, seed=42))


def test_a_different_seed_changes_the_dataset() -> None:
    """The other half of determinism: the seed has to actually do something.

    Without this, a generator that ignored its seed entirely would pass the
    reproducibility test above.
    """
    assert dataset_hash(generate("realistic", seed=42)) != dataset_hash(
        generate("realistic", seed=43)
    )


def test_a_different_profile_changes_the_dataset() -> None:
    assert dataset_hash(generate("clean", seed=42)) != dataset_hash(generate("nightmare", seed=42))


# ------------------------------------------------- the vendored files are intact --


def _manifest() -> dict[str, str]:
    """Parse the `SHA-256, first 12 hex chars` manifest out of VENDORED.md."""
    text = VENDORED_MD.read_text(encoding="utf-8")
    block = re.search(r"```\n((?:[0-9A-F]{12}\s+\S+\n)+)```", text)
    assert block, "VENDORED.md has no file manifest block"
    return {
        path: digest
        for digest, path in (line.split() for line in block.group(1).strip().splitlines())
    }


def _short_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()[:12].upper()


def test_vendored_manifest_covers_every_vendored_file() -> None:
    on_disk = {
        p.relative_to(LEDGERFAB_DIR).as_posix()
        for p in LEDGERFAB_DIR.rglob("*.py")
        if "__pycache__" not in p.parts
        # LOCAL CHANGE (ReportSmith). Upstream excluded `statements/` because there it
        # was authored, not vendored. Here BOTH halves are vendored, so excluding it
        # would leave the code every figure in the pack comes from unprotected against
        # silent drift — the opposite of what this test is for. See ledgerfab/VENDORED.md.
    }
    assert on_disk == set(_manifest()), (
        "ledgerfab/VENDORED.md's manifest and the vendored files on disk disagree. "
        "If a file was added or removed on purpose, update the manifest in the same commit."
    )


def test_vendored_files_are_unmodified() -> None:
    drifted = [
        path
        for path, expected in _manifest().items()
        if _short_sha256(LEDGERFAB_DIR / path) != expected
    ]
    assert not drifted, (
        f"vendored files changed without the manifest changing with them: {drifted}. "
        "Record the change and the reason in VENDORED.md's 'Local changes' section, "
        "and update the manifest — that is what keeps the fork copyable."
    )
