"""Spec 00 A3: *"Seeded → reproducible (same seed+profile = identical dataset,
hash-verifiable)"*.

Both halves matter. Reproducibility alone is satisfied by a generator that ignores its
seed entirely, so every "same input, same output" assertion here is paired with a
"different input, different output" one.
"""

from __future__ import annotations

import inspect
from decimal import Decimal
from pathlib import Path

import pytest

from ledgerfab.statements import PROFILES, emit_statements, statement_hash
from ledgerfab.statements.hashing import canonicalise

PROFILE_NAMES = sorted(PROFILES)
STATEMENTS_DIR = Path(__file__).resolve().parents[1] / "ledgerfab" / "statements"


# ------------------------------------------------------------ reproducible --


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_same_inputs_are_byte_identical(profile: str) -> None:
    a = emit_statements(profile, seed=42, periods=8, grain="quarter")
    b = emit_statements(profile, seed=42, periods=8, grain="quarter")
    assert statement_hash(a) == statement_hash(b)


def test_reproducible_across_a_fresh_import() -> None:
    """No module-level state accumulates between calls.

    The vendored engine's contract is *"the package holds no clock, no UUIDs and no
    global state"*, and the extension inherits it. A generator that memoised anything
    would pass the test above and fail this one.
    """
    first = statement_hash(emit_statements("squeeze", seed=99))
    for _ in range(3):
        emit_statements("distress", seed=1)
        emit_statements("growth", seed=2, periods=3, grain="month")
    assert statement_hash(emit_statements("squeeze", seed=99)) == first


# --------------------------------------------------------------- sensitive --


@pytest.mark.parametrize("profile", PROFILE_NAMES)
def test_a_different_seed_changes_the_set(profile: str) -> None:
    assert statement_hash(emit_statements(profile, seed=42)) != statement_hash(
        emit_statements(profile, seed=43)
    )


def test_a_different_profile_changes_the_set() -> None:
    hashes = {name: statement_hash(emit_statements(name, seed=42)) for name in PROFILE_NAMES}
    assert len(set(hashes.values())) == len(PROFILE_NAMES), f"profiles collide: {hashes}"


def test_shape_changes_change_the_set() -> None:
    base = statement_hash(emit_statements("steady", seed=42, periods=8, grain="quarter"))
    assert base != statement_hash(emit_statements("steady", seed=42, periods=6, grain="quarter"))
    assert base != statement_hash(emit_statements("steady", seed=42, periods=8, grain="month"))


def test_switching_anomalies_off_changes_the_set() -> None:
    """`anomalies=()` is the documented way to isolate the underlying business."""
    with_them = emit_statements("squeeze", seed=42)
    without = emit_statements("squeeze", seed=42, anomalies=())
    assert statement_hash(with_them) != statement_hash(without)
    assert without.ground_truth.anomalies == ()


def test_anomaly_streams_are_independent() -> None:
    """Adding an injector must not shift the numbers another one draws.

    The vendored ``Rng`` gives each generator its own named sub-stream so that adding a
    counterparty cannot move the invoice generator's draws. Anomalies inherit that, and
    it is what keeps eval cases stable as the anomaly set grows: a set generated with
    `(margin_compression,)` today must still be that set after a seventh injector is
    written next month.
    """
    one = emit_statements("steady", seed=42, anomalies=("margin_compression",))
    also_one = emit_statements("steady", seed=42, anomalies=("margin_compression",))
    assert statement_hash(one) == statement_hash(also_one)

    # The same injector applied first, with a second appended, must produce the same
    # *first-injector* effect — checked via the revenue series, which `inventory_build`
    # does not touch.
    two = emit_statements("steady", seed=42, anomalies=("margin_compression", "inventory_build"))
    assert one.series("revenue") == two.series("revenue")


# ------------------------------------------------------------------ money --


def test_every_amount_is_a_decimal() -> None:
    """PLAN.md **D-005**. A single float would make the cent-exact invariants flaky."""
    st = emit_statements("distress", seed=42)
    offenders = [
        (ln.period_id, ln.line_code, type(ln.amount).__name__)
        for ln in st.lines
        if not isinstance(ln.amount, Decimal)
    ]
    assert not offenders, f"non-Decimal amounts: {offenders[:5]}"


def test_hashing_refuses_a_float() -> None:
    """The canonicaliser raises rather than rounding a stray float away.

    Rounding it would be the polite thing to do and exactly wrong: the one step whose
    job is proving the data did not change must not be the step that hides a change.
    """
    with pytest.raises(TypeError, match="float reached statement hashing"):
        canonicalise({"amount": 1.23})


def test_amounts_serialise_as_fixed_two_dp_strings() -> None:
    payload = emit_statements("steady", seed=42, periods=1, grain="year").to_dict()
    for line in payload["lines"]:
        assert isinstance(line["amount"], str)
        assert line["amount"].count(".") == 1
        assert len(line["amount"].split(".")[1]) == 2


# ---------------------------------------------------- no clock, no globals --


def test_the_extension_reads_no_clock_and_no_unseeded_randomness() -> None:
    """A generator that reads the clock is not reproducible — "same seed, same data"
    would quietly become "same seed, same data, same day".

    Source-level rather than behavioural, because the failure it guards against is a
    future edit, and by the time a behavioural test catches a clock read the committed
    eval fixtures have already drifted.
    """
    banned = ("datetime.now", "date.today", "time.time", "uuid4", "random.random")
    offenders: list[str] = []
    for path in STATEMENTS_DIR.rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        # `import random` is legitimate only inside the vendored rng module, which is
        # not in this directory.
        for token in banned:
            if token in source:
                offenders.append(f"{path.name}: {token}")
        if "import random" in source:
            offenders.append(f"{path.name}: import random")
    assert not offenders, f"unseeded or clock-dependent code in the emitter: {offenders}"


def test_the_extension_never_imports_the_application() -> None:
    """PLAN.md **C7**: `ledgerfab.statements` imports only from `ledgerfab.*`.

    That one-way rule is what makes lifting this directory into the shared engine a
    move rather than a refactor, and it is the brief's requirement that the extension
    be *"designed cleanly for reuse by later projects"*.
    """
    offenders = [
        f"{path.name}: {line.strip()}"
        for path in STATEMENTS_DIR.rglob("*.py")
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith(("import ", "from ")) and ("statementlens" in line or "numcheck" in line)
    ]
    assert not offenders, f"the emitter reached into the application: {offenders}"


def test_emit_statements_signature_is_the_documented_one() -> None:
    """The reuse contract another project codes against (`statements/README.md`)."""
    params = list(inspect.signature(emit_statements).parameters)
    assert params == ["profile", "seed", "periods", "grain", "first_start", "anomalies"]
