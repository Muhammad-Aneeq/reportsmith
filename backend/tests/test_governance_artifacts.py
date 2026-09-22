"""Tracked edits, the write-once AI draft, and archive immutability."""

from __future__ import annotations

from pathlib import Path

import pytest
from app import service
from app.issue.archive import archive_dir, verify_archive
from app.issue.edits import make_diff, word_diff


# --------------------------------------------------------------------- edits --


def test_word_diff_marks_what_a_person_changed():
    ops = word_diff("Revenue was £3.8m in the month.", "Revenue rose to £3.8m in the month.")
    assert any(o["op"] == "insert" for o in ops)
    assert any(o["op"] == "delete" for o in ops)
    assert any(o["op"] == "equal" and "month" in o["text"] for o in ops)


def test_diff_counts_words_both_ways():
    diff = make_diff("one two", "one two three")
    assert diff["words_before"] == 2
    assert diff["words_after"] == 3


def _first_narrative(db, pack):
    data = service.pack_to_json(db, pack)
    return next(s for s in data["sections"] if s["type"] == "narrative" and not s["gaps"])


def test_editing_preserves_the_ai_draft(db_session, period):
    pack = service.create_pack(db_session, "monthly_management_pack", period)
    section = _first_narrative(db_session, pack)
    original_draft = section["ai_draft"]["text"]
    assert original_draft

    service.edit_section(db_session, section["id"], "A human wrote this instead.", "reviewer")
    from app.models import SectionRow

    after = service.section_to_json(db_session.get(SectionRow, section["id"]))

    assert after["ai_draft"]["text"] == original_draft, "the AI draft was overwritten"
    assert after["content"]["text"] == "A human wrote this instead."
    assert after["edit_count"] == 1
    assert after["word_diff"]


def test_editing_an_approved_section_revokes_its_approval(db_session, period):
    """D-012 — otherwise 'all sections approved' can be true of text nobody approved."""
    pack = service.create_pack(db_session, "monthly_management_pack", period)
    section = _first_narrative(db_session, pack)

    approved = service.approve_section(db_session, section["id"], "A. Controller")
    assert approved.approved

    edited = service.edit_section(db_session, section["id"], "Changed after approval.", "reviewer")
    assert not edited.approved
    assert edited.approved_by is None


def test_tables_are_not_editable(db_session, period):
    """D-011 — editing a computed table would make the archive hash a claim about nothing."""
    pack = service.create_pack(db_session, "monthly_management_pack", period)
    data = service.pack_to_json(db_session, pack)
    table = next(s for s in data["sections"] if s["type"] == "table" and not s["gaps"])

    with pytest.raises(service.ServiceError, match="computed from the data"):
        service.edit_section(db_session, table["id"], "nonsense", "reviewer")


def test_an_unchanged_edit_records_nothing(db_session, period):
    pack = service.create_pack(db_session, "monthly_management_pack", period)
    section = _first_narrative(db_session, pack)
    same = section["content"]["text"]
    service.edit_section(db_session, section["id"], same, "reviewer")
    refreshed = _first_narrative(db_session, pack)
    assert refreshed["edit_count"] == 0


# ------------------------------------------------------------------- archive --


def _issue(db, period):
    pack = service.create_pack(db, "monthly_management_pack", period)
    data = service.pack_to_json(db, pack)
    for section in data["sections"]:
        service.approve_section(db, section["id"], "A. Controller")
    waivers = [
        {"section_key": g["section_key"], "reason": "Accepted for this period."}
        for g in data["gaps"] if g["required"]
    ]
    return service.signoff(db, pack.id, "A. Controller", waivers)


def test_archive_has_all_four_artefacts(db_session, period):
    pack = _issue(db_session, period)
    out = archive_dir(pack.id)
    assert (out / "pack.md").exists()
    assert (out / "data_snapshot.json").exists()
    assert (out / "MANIFEST.json").exists()
    # PDF is allowed to be absent; the manifest must say which.
    manifest = verify_archive(pack.id)["manifest"]
    assert manifest["pdf_available"] == (out / "pack.pdf").exists()


def test_a_fresh_archive_verifies(db_session, period):
    pack = _issue(db_session, period)
    assert verify_archive(pack.id)["ok"]


def test_tampering_is_detected_and_named(db_session, period):
    pack = _issue(db_session, period)
    md = archive_dir(pack.id) / "pack.md"
    md.write_text(md.read_text(encoding="utf-8") + "\nA line nobody signed.\n", encoding="utf-8")

    result = verify_archive(pack.id)
    assert not result["ok"]
    assert any("pack.md" in p for p in result["problems"])


def test_snapshot_tampering_is_detected(db_session, period):
    pack = _issue(db_session, period)
    snapshot = archive_dir(pack.id) / "data_snapshot.json"
    snapshot.write_text('{"tampered": true}', encoding="utf-8")

    result = verify_archive(pack.id)
    assert not result["ok"]
    assert any("data_snapshot" in p for p in result["problems"])


def test_cannot_reissue(db_session, period):
    from app.issue.states import TransitionError

    pack = _issue(db_session, period)
    with pytest.raises((TransitionError, service.ServiceError)):
        service.signoff(db_session, pack.id, "A. Controller", [])


def test_the_archive_records_what_was_waived(db_session, period):
    pack = _issue(db_session, period)
    manifest = verify_archive(pack.id)["manifest"]
    assert manifest["waivers"], "a waived gap must be recorded in the archive itself"
    assert manifest["waivers"][0]["signer"] == "A. Controller"
    markdown = (archive_dir(pack.id) / "pack.md").read_text(encoding="utf-8")
    assert "Waived" in markdown or "waived" in markdown


def test_gapped_sections_appear_in_the_document(db_session, period):
    """Spec 13 F2 — an issued pack must not silently lack a section."""
    pack = _issue(db_session, period)
    markdown = (archive_dir(pack.id) / "pack.md").read_text(encoding="utf-8")
    assert "Performance by segment" in markdown
    assert "Not available" in markdown


def test_no_update_or_delete_against_archives_anywhere_in_the_app():
    """Immutability by construction, asserted by inspection of every module."""
    app_dir = Path(__file__).resolve().parents[1] / "app"
    offenders: list[str] = []
    for module in app_dir.rglob("*.py"):
        text = module.read_text(encoding="utf-8").lower()
        for pattern in ("update(archiverow", "delete(archiverow", "archiverow).where"):
            if pattern in text:
                offenders.append(f"{module.name}: {pattern}")
        # A bare `db.delete(...)` on an archive object would also do it.
        if "db.delete(pack.archive" in text or "session.delete(pack.archive" in text:
            offenders.append(f"{module.name}: deletes an archive")
    assert not offenders, f"archives must be INSERT-only; found {offenders}"
