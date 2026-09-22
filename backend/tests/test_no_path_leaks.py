"""A gap's detail is published. It must not carry the build machine's filesystem.

Found by looking at a screenshot: the Sign-off screen was showing

    FileNotFoundError: no SpendSort export for 2024-06 at
    C:\\Users\\<name>\\Desktop\\...\\fixtures\\spendsort\\2024-06.csv

Gap details are rendered in the UI **and written into the issued markdown and PDF**, so an
absolute path puts a directory layout and a username into a document that gets distributed.
The period and the remedy are what a reader needs; the path is what the developer needs, and
the developer has the traceback.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.adapters.base import resolve_binding
from app.adapters.spendsort_adapter import SpendSortAdapter
from app.assemble.engine import assemble, default_adapters
from app.template.schema import Selector

# Windows drive paths, POSIX home paths, and UNC shares.
_ABSOLUTE = re.compile(r"[A-Za-z]:[\\/]|(?:^|\s)/(?:home|Users|root|mnt)/|\\\\[A-Za-z0-9]")


def _leaks(text: str) -> bool:
    return bool(_ABSOLUTE.search(text))


def test_a_missing_fixture_gap_names_no_absolute_path():
    result = resolve_binding(
        {"spendsort": SpendSortAdapter()},
        Selector(source="spendsort", select="categories"),
        "1999-01",
    )
    assert result.is_gap
    assert not _leaks(result.detail), f"gap detail leaks a path: {result.detail}"
    # It still has to be actionable.
    assert "1999-01" in result.detail
    assert "make fixtures" in result.detail


def test_no_gap_in_a_real_pack_leaks_a_path(template, period, adapters):
    pack = assemble(template, period, adapters)
    for gap in pack.gaps:
        assert not _leaks(gap["detail"]), f"{gap['section_key']}: {gap['detail']}"


def test_a_pack_with_missing_fixtures_still_leaks_nothing(template):
    """2024-06 has no SpendSort export, which is the case that produced the bug."""
    pack = assemble(template, "2024-06", default_adapters())
    gaps = pack.gaps
    assert len(gaps) >= 3, "expected the un-fixtured period to produce several gaps"
    for gap in gaps:
        assert not _leaks(gap["detail"]), f"{gap['section_key']}: {gap['detail']}"


def test_the_issued_document_carries_no_absolute_path(db_session):
    """The end of the chain: what actually gets distributed."""
    from app import service
    from app.issue.archive import archive_dir

    pack = service.create_pack(db_session, "monthly_management_pack", "2024-06")
    data = service.pack_to_json(db_session, pack)
    for section in data["sections"]:
        service.approve_section(db_session, section["id"], "A. Controller")
    waivers = [
        {"section_key": g["section_key"], "reason": "Accepted for this period."}
        for g in data["gaps"]
        if g["required"]
    ]
    issued = service.signoff(db_session, pack.id, "A. Controller", waivers)

    markdown = (archive_dir(issued.id) / "pack.md").read_text(encoding="utf-8")
    offenders = [line for line in markdown.splitlines() if _leaks(line)]
    assert not offenders, f"the issued document leaks a path: {offenders[:2]}"


@pytest.mark.parametrize("name", ["pack.md", "MANIFEST.json"])
def test_archive_artifacts_are_portable(db_session, period, name):
    """An archive should be readable by someone who was never on this machine.

    `md_ref` / `snapshot_ref` in the DB are absolute by design — they point at local files.
    The *documents* are what travel, and they must stand alone.
    """
    from app import service
    from app.issue.archive import archive_dir

    pack = service.create_pack(db_session, "monthly_management_pack", period)
    data = service.pack_to_json(db_session, pack)
    for section in data["sections"]:
        service.approve_section(db_session, section["id"], "A. Controller")
    issued = service.signoff(
        db_session,
        pack.id,
        "A. Controller",
        [
            {"section_key": g["section_key"], "reason": "Accepted."}
            for g in data["gaps"]
            if g["required"]
        ],
    )

    content = (Path(archive_dir(issued.id)) / name).read_text(encoding="utf-8")
    offenders = [line for line in content.splitlines() if _leaks(line)]
    assert not offenders, f"{name} leaks a path: {offenders[:2]}"
