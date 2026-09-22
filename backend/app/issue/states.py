"""The sign-off state machine — an explicit transition table with named guards.

    draft ──submit──> in_review ──signoff──> signed ──issue──> issued

Spec 13 F5 and F6. Everything this product claims about governance reduces to the guards
below, so they are written once, here, and every API path goes through `apply`. A guard
enforced in a screen is not enforced.

`signoff` and `issue` are separate transitions even though one endpoint performs both
(PLAN.md **D-013**). Spec 13 §7's API surface lists no `issue` endpoint, so adding one
would be a gratuitous divergence — but keeping the edge in the machine is what lets
`test_state_machine.py` assert that `issued` is unreachable from `in_review`, which is the
property that actually matters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class Status(StrEnum):
    DRAFT = "draft"
    IN_REVIEW = "in_review"
    SIGNED = "signed"
    ISSUED = "issued"


class Event(StrEnum):
    SUBMIT = "submit"
    SIGNOFF = "signoff"
    ISSUE = "issue"
    REOPEN = "reopen"


class TransitionError(RuntimeError):
    """An illegal transition, or a guard that refused. The message is user-facing."""


# (from, event) → to. A pair absent from this table is illegal, full stop. Modelling it as
# a table rather than as `if` statements is what makes the exhaustive test possible: the
# suite iterates every (Status × Event) pair and asserts the ones missing here raise.
TRANSITIONS: dict[tuple[Status, Event], Status] = {
    (Status.DRAFT, Event.SUBMIT): Status.IN_REVIEW,
    (Status.IN_REVIEW, Event.SIGNOFF): Status.SIGNED,
    (Status.SIGNED, Event.ISSUE): Status.ISSUED,
    # Reopening a signed pack is allowed — a signer may spot something after signing and
    # before issuance, and forcing them to rebuild the pack would encourage the opposite.
    (Status.SIGNED, Event.REOPEN): Status.IN_REVIEW,
    (Status.IN_REVIEW, Event.REOPEN): Status.DRAFT,
}


@dataclass(frozen=True, slots=True)
class GuardFailure:
    code: str
    message: str

    def to_json(self) -> dict[str, str]:
        return {"code": self.code, "message": self.message}


@dataclass(frozen=True, slots=True)
class PackView:
    """What the guards need to know. A plain snapshot, so guards stay testable."""

    status: Status
    sections: list[dict[str, Any]]  # {key, title, required, approved, type, gaps:[...]}
    waived_gap_keys: frozenset[str] = frozenset()
    already_issued: bool = False

    @property
    def unapproved(self) -> list[dict[str, Any]]:
        return [s for s in self.sections if not s["approved"]]

    @property
    def open_required_gaps(self) -> list[dict[str, Any]]:
        """Required sections with gaps nobody has waived."""
        return [
            s
            for s in self.sections
            if s["required"] and s["gaps"] and s["key"] not in self.waived_gap_keys
        ]


def check_guards(view: PackView, event: Event) -> list[GuardFailure]:
    """Everything standing between this pack and that event. All of it, not the first."""
    failures: list[GuardFailure] = []

    if event is Event.SIGNOFF:
        unapproved = view.unapproved
        if unapproved:
            names = ", ".join(s["title"] for s in unapproved[:5])
            more = f" and {len(unapproved) - 5} more" if len(unapproved) > 5 else ""
            failures.append(
                GuardFailure(
                    "sections_unapproved",
                    f"{len(unapproved)} section(s) not approved: {names}{more}",
                )
            )
        for section in view.open_required_gaps:
            reasons = ", ".join(g["reason"] for g in section["gaps"])
            failures.append(
                GuardFailure(
                    "gap_unresolved",
                    f"required section {section['title']!r} has an unresolved gap ({reasons}). "
                    f"Resolve it, or record a waiver saying why the pack is being issued without it.",
                )
            )

    if event is Event.ISSUE and view.already_issued:
        failures.append(
            GuardFailure("already_issued", "this pack has already been issued; archives are immutable")
        )

    return failures


def apply(view: PackView, event: Event) -> Status:
    """The only way a pack's status changes. Raises rather than returning a bad state."""
    key = (view.status, event)
    if key not in TRANSITIONS:
        legal = sorted(e for (s, e) in TRANSITIONS if s == view.status)
        raise TransitionError(
            f"cannot {event} a pack that is {view.status}; "
            f"legal from here: {legal or 'nothing — this is a terminal state'}"
        )

    failures = check_guards(view, event)
    if failures:
        raise TransitionError(
            f"cannot {event}: " + "; ".join(f.message for f in failures)
        )

    return TRANSITIONS[key]
