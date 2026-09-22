"""The governance suite: a pack cannot be issued unapproved, or with an unwaived gap.

Spec 13 §10 gates CI on this. The table-driven test below walks **every** (Status × Event)
pair, so an accidentally-added transition fails rather than quietly widening the machine.
"""

from __future__ import annotations

import itertools

import pytest

from app.issue.states import (
    TRANSITIONS,
    Event,
    PackView,
    Status,
    TransitionError,
    apply,
    check_guards,
)


def _section(key="s1", *, required=True, approved=True, gaps=None):
    return {
        "key": key,
        "title": key.title(),
        "required": required,
        "approved": approved,
        "type": "table",
        "gaps": gaps or [],
    }


def _clean_view(status=Status.IN_REVIEW, **kw):
    return PackView(status=status, sections=[_section()], **kw)


# ---------------------------------------------------------------- exhaustive --


@pytest.mark.parametrize("status,event", list(itertools.product(Status, Event)))
def test_every_status_event_pair_is_decided(status, event):
    """Legal pairs transition; everything else raises. No third outcome exists."""
    view = _clean_view(status)
    if (status, event) in TRANSITIONS:
        assert apply(view, event) == TRANSITIONS[(status, event)]
    else:
        with pytest.raises(TransitionError):
            apply(view, event)


def test_issued_is_terminal():
    for event in Event:
        with pytest.raises(TransitionError):
            apply(_clean_view(Status.ISSUED), event)


def test_cannot_reach_issued_from_in_review():
    """The property D-013 exists to protect: no jumping the sign-off."""
    with pytest.raises(TransitionError, match="cannot issue"):
        apply(_clean_view(Status.IN_REVIEW), Event.ISSUE)


# -------------------------------------------------------------------- guards --


def test_cannot_sign_with_an_unapproved_section():
    view = PackView(
        status=Status.IN_REVIEW,
        sections=[_section("a", approved=True), _section("b", approved=False)],
    )
    with pytest.raises(TransitionError, match="not approved"):
        apply(view, Event.SIGNOFF)


def test_cannot_sign_with_an_unwaived_gap_on_a_required_section():
    view = PackView(
        status=Status.IN_REVIEW,
        sections=[_section("a", gaps=[{"reason": "unknown_dataset", "detail": "no such dataset"}])],
    )
    with pytest.raises(TransitionError, match="unresolved gap"):
        apply(view, Event.SIGNOFF)


def test_a_waiver_unblocks_that_gap_and_only_that_gap():
    gap = [{"reason": "unknown_dataset", "detail": "d"}]
    view = PackView(
        status=Status.IN_REVIEW,
        sections=[_section("a", gaps=gap), _section("b", gaps=gap)],
        waived_gap_keys=frozenset({"a"}),
    )
    failures = check_guards(view, Event.SIGNOFF)
    assert len(failures) == 1
    assert "'B'" in failures[0].message or "b" in failures[0].message.lower()

    view_all = PackView(
        status=Status.IN_REVIEW,
        sections=[_section("a", gaps=gap), _section("b", gaps=gap)],
        waived_gap_keys=frozenset({"a", "b"}),
    )
    assert apply(view_all, Event.SIGNOFF) == Status.SIGNED


def test_a_gap_on_an_optional_section_does_not_block():
    view = PackView(
        status=Status.IN_REVIEW,
        sections=[_section("a", required=False, gaps=[{"reason": "empty_result", "detail": "d"}])],
    )
    assert apply(view, Event.SIGNOFF) == Status.SIGNED


def test_guards_report_every_problem_not_just_the_first():
    """A reviewer should see the whole list, not fix one thing and discover another."""
    view = PackView(
        status=Status.IN_REVIEW,
        sections=[
            _section("a", approved=False),
            _section("b", gaps=[{"reason": "binding_failed", "detail": "d"}]),
        ],
    )
    failures = check_guards(view, Event.SIGNOFF)
    codes = {f.code for f in failures}
    assert codes == {"sections_unapproved", "gap_unresolved"}


def test_cannot_reissue():
    view = PackView(status=Status.SIGNED, sections=[_section()], already_issued=True)
    with pytest.raises(TransitionError, match="already been issued"):
        apply(view, Event.ISSUE)


# ------------------------------------------------------- against the real API --


def test_full_flow_through_the_service(db_session, period):
    from app import service

    pack = service.create_pack(db_session, "monthly_management_pack", period)
    data = service.pack_to_json(db_session, pack)

    gapped = [g for g in data["gaps"] if g["required"]]
    assert gapped, "the default template should carry one honest structural gap"

    with pytest.raises(TransitionError):
        service.signoff(db_session, pack.id, "A. Controller", [])

    for section in data["sections"]:
        service.approve_section(db_session, section["id"], "A. Controller")

    with pytest.raises(TransitionError, match="unresolved gap"):
        service.signoff(db_session, pack.id, "A. Controller", [])

    waivers = [
        {"section_key": g["section_key"], "reason": "Accepted for this period."} for g in gapped
    ]
    issued = service.signoff(db_session, pack.id, "A. Controller", waivers)
    assert issued.status == Status.ISSUED
    assert issued.archive is not None
    assert issued.signoff.waivers_json[0]["reason"] == "Accepted for this period."
    assert issued.signoff.waivers_json[0]["signer"] == "A. Controller"


def test_waiver_without_a_reason_is_refused(db_session, period):
    from app import service

    pack = service.create_pack(db_session, "monthly_management_pack", period)
    data = service.pack_to_json(db_session, pack)
    for section in data["sections"]:
        service.approve_section(db_session, section["id"], "A. Controller")
    gapped = [g for g in data["gaps"] if g["required"]]

    with pytest.raises(service.ServiceError, match="needs a reason"):
        service.signoff(
            db_session,
            pack.id,
            "A. Controller",
            [{"section_key": gapped[0]["section_key"], "reason": "   "}],
        )


def test_cannot_waive_a_section_that_has_no_gap(db_session, period):
    from app import service

    pack = service.create_pack(db_session, "monthly_management_pack", period)
    with pytest.raises(service.ServiceError, match="has no gap"):
        service.signoff(
            db_session,
            pack.id,
            "A. Controller",
            [{"section_key": "pnl_summary", "reason": "because"}],
        )
