"""The service layer. Every state change in the product goes through here.

Deliberately one module rather than one per router: the guards in `issue/states.py` are
only worth anything if there is no second path around them, and a single service surface
is how that stays true as routers multiply.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assemble.engine import AssembledPack, assemble, default_adapters
from app.issue.archive import write_archive
from app.issue.edits import make_diff, word_diff
from app.issue.states import Event, PackView, Status, TransitionError, apply, check_guards
from app.models import ArchiveRow, EditRow, PackRow, SectionRow, SignoffRow, TemplateRow
from app.narrate.composer import Composer
from app.narrate.graph import compose_section
from app.settings import settings
from app.template.schema import NarrativeSection, Template
from app.template.store import parse_template


class ServiceError(RuntimeError):
    """A user-facing refusal. Routers turn this into a 4xx with the message intact."""


# ----------------------------------------------------------------- templates --


def get_template_row(db: Session, template_id: str, version: int | None = None) -> TemplateRow:
    query = select(TemplateRow).where(TemplateRow.template_id == template_id)
    if version is not None:
        query = query.where(TemplateRow.version == version)
    row = db.scalars(query.order_by(TemplateRow.version.desc())).first()
    if row is None:
        raise ServiceError(f"no template {template_id!r}" + (f" v{version}" if version else ""))
    return row


def load_template(row: TemplateRow) -> Template:
    return parse_template(row.yaml, source=row.ref)


def template_is_locked(db: Session, row: TemplateRow) -> bool:
    """Has any pack been built from this exact version?

    If so it is frozen: re-running it must reproduce what the archive attests to, and a
    version that can change after the fact makes `template_version` decorative.
    """
    return db.scalar(
        select(PackRow).where(
            PackRow.template_id == row.template_id, PackRow.template_version == row.version
        ).limit(1)
    ) is not None


def save_template(db: Session, yaml_text: str) -> TemplateRow:
    """Create or update a template. A locked version mints a new one instead."""
    template = parse_template(yaml_text, source="submitted template")
    existing = db.scalar(
        select(TemplateRow).where(
            TemplateRow.template_id == template.id, TemplateRow.version == template.version
        )
    )
    if existing is not None:
        if template_is_locked(db, existing):
            raise ServiceError(
                f"{existing.ref} has already been used to build a pack and cannot be edited. "
                f"Increment `version` to {existing.version + 1} to make a new one — that is what "
                f"keeps an issued pack's template reference meaningful."
            )
        existing.yaml = yaml_text
        existing.name = template.name
        db.commit()
        return existing

    row = TemplateRow(
        template_id=template.id, name=template.name, version=template.version, yaml=yaml_text
    )
    db.add(row)
    db.commit()
    return row


# --------------------------------------------------------------------- packs --


def create_pack(
    db: Session,
    template_id: str,
    period: str,
    *,
    version: int | None = None,
    composer: Composer | None = None,
    narrate: bool = True,
) -> PackRow:
    """Assemble a pack, then draft its narrative sections.

    Two passes on purpose: assembly is deterministic and inspectable, and a pack should be
    viewable before a model has touched it. If drafting fails or is skipped, the pack still
    exists with its tables and KPIs intact.
    """
    template_row = get_template_row(db, template_id, version)
    template = load_template(template_row)
    assembled: AssembledPack = assemble(template, period, default_adapters())

    pack = PackRow(
        template_pk=template_row.id,
        template_id=template.id,
        template_version=template.version,
        period=period,
        status=Status.DRAFT,
        structure_hash=assembled.structure_hash,
        value_digest=assembled.value_digest,
        snapshot_hash=assembled.snapshot_hash,
        model="mock" if not settings.live_llm else settings.model,
    )
    db.add(pack)
    db.flush()

    for section in assembled.sections:
        row_data = section.as_row()
        spec = template.section(section.section_key)
        content = row_data["content_json"]
        ai_draft: dict[str, Any] | None = None

        if narrate and isinstance(spec, NarrativeSection) and not section.has_gap:
            result = compose_section(spec, template, period, content, composer=composer)
            content = result.to_content(content)
            # Written once, here, and never again — see app/issue/edits.py.
            ai_draft = {
                "text": result.ai_draft,
                "model": result.model,
                "prompt_version": result.prompt_version,
                "verified": result.verified,
                "figures_checked": result.figures_checked,
            }

        db.add(
            SectionRow(
                pack_id=pack.id,
                section_key=row_data["section_key"],
                title=row_data["title"],
                type=row_data["type"],
                order_index=row_data["order_index"],
                required=row_data["required"],
                binding_status=row_data["binding_status"],
                content_json=content,
                ai_draft_json=ai_draft,
                gaps_json=row_data["gaps_json"],
            )
        )

    # Re-hash after drafting: the narrative figure refs are part of the value digest.
    db.flush()
    _store_snapshot(pack.id, assembled.snapshot)
    db.commit()
    return pack


_SNAPSHOTS: dict[int, dict[str, Any]] = {}


def _store_snapshot(pack_id: int, snapshot: dict[str, Any]) -> None:
    """Hold the bound data until issuance writes it to the archive.

    In-process rather than in a table: the snapshot is only needed between assembly and
    issuance, and a pack re-assembles deterministically from (template, period), so a lost
    cache costs a recompute rather than data. `snapshot_for` rebuilds on a miss, which is
    what makes a server restart mid-review harmless.
    """
    _SNAPSHOTS[pack_id] = snapshot


def snapshot_for(db: Session, pack: PackRow) -> dict[str, Any]:
    cached = _SNAPSHOTS.get(pack.id)
    if cached is not None:
        return cached
    template = load_template(get_template_row(db, pack.template_id, pack.template_version))
    rebuilt = assemble(template, pack.period, default_adapters())
    if rebuilt.snapshot_hash != pack.snapshot_hash:
        # The generated world is seeded, so this should be impossible. If it happens, the
        # honest move is to refuse rather than to archive data that is not what the pack
        # was built from.
        raise ServiceError(
            f"pack {pack.id} cannot be re-derived: snapshot hash changed "
            f"({pack.snapshot_hash[:12]} → {rebuilt.snapshot_hash[:12]}). "
            f"The underlying data or adapters have changed since assembly."
        )
    _SNAPSHOTS[pack.id] = rebuilt.snapshot
    return rebuilt.snapshot


def get_pack(db: Session, pack_id: int) -> PackRow:
    pack = db.get(PackRow, pack_id)
    if pack is None:
        raise ServiceError(f"no pack {pack_id}")
    return pack


def pack_view(db: Session, pack: PackRow) -> PackView:
    waived = {
        w["section_key"] for w in (pack.signoff.waivers_json if pack.signoff else [])
    }
    return PackView(
        status=Status(pack.status),
        sections=[
            {
                "key": s.section_key,
                "title": s.title,
                "required": s.required,
                "approved": s.approved,
                "type": s.type,
                "gaps": s.gaps_json or [],
            }
            for s in pack.sections
        ],
        waived_gap_keys=frozenset(waived),
        already_issued=pack.archive is not None,
    )


def pack_to_json(db: Session, pack: PackRow) -> dict[str, Any]:
    template = load_template(get_template_row(db, pack.template_id, pack.template_version))
    sections = sorted(pack.sections, key=lambda s: s.order_index)
    view = pack_view(db, pack)
    blockers = check_guards(view, Event.SIGNOFF)

    return {
        "id": pack.id,
        "period": pack.period,
        "status": pack.status,
        "template_ref": pack.template_ref,
        "template_id": pack.template_id,
        "template_version": pack.template_version,
        "structure_hash": pack.structure_hash,
        "value_digest": pack.value_digest,
        "snapshot_hash": pack.snapshot_hash,
        "model": pack.model,
        "created_at": pack.created_at.isoformat(),
        "cover": {
            "title": template.name,
            "period": pack.period,
            "template_ref": pack.template_ref,
            "section_count": len(sections),
            "gap_count": sum(1 for s in sections if s.gaps_json),
        },
        "sections": [section_to_json(s) for s in sections],
        "gaps": [
            {
                **gap,
                "section_key": s.section_key,
                "title": s.title,
                "required": s.required,
                "waived": s.section_key in view.waived_gap_keys,
            }
            for s in sections
            for gap in (s.gaps_json or [])
        ],
        "blockers": [b.to_json() for b in blockers],
        "can_sign": not blockers and pack.status == Status.IN_REVIEW,
        "approved_count": sum(1 for s in sections if s.approved),
        "signoff": (
            {
                "signer": pack.signoff.signer,
                "at": pack.signoff.at.isoformat(),
                "waivers": pack.signoff.waivers_json,
            }
            if pack.signoff
            else None
        ),
        "archive": (
            {
                "content_hash": pack.archive.content_hash,
                "md_ref": pack.archive.md_ref,
                "pdf_ref": pack.archive.pdf_ref,
                "issued_at": pack.archive.issued_at.isoformat(),
            }
            if pack.archive
            else None
        ),
    }


def section_to_json(section: SectionRow) -> dict[str, Any]:
    ai_text = (section.ai_draft_json or {}).get("text", "")
    current = (section.content_json or {}).get("text", "")
    return {
        "id": section.id,
        "section_key": section.section_key,
        "title": section.title,
        "type": section.type,
        "order_index": section.order_index,
        "required": section.required,
        "binding_status": section.binding_status,
        "approved": section.approved,
        "approved_by": section.approved_by,
        "approved_at": section.approved_at.isoformat() if section.approved_at else None,
        "editable": section.is_editable,
        "content": section.content_json,
        "ai_draft": section.ai_draft_json,
        "gaps": section.gaps_json or [],
        "edit_count": len(section.edits),
        "has_human_edits": bool(section.edits),
        "word_diff": word_diff(ai_text, current) if section.edits and ai_text else [],
        "edits": [
            {
                "id": e.id,
                "editor": e.editor,
                "at": e.at.isoformat(),
                "lines_added": e.diff_json.get("lines_added", 0),
                "lines_removed": e.diff_json.get("lines_removed", 0),
            }
            for e in section.edits
        ],
    }


# -------------------------------------------------------------------- review --


def edit_section(db: Session, section_id: int, text: str, editor: str) -> SectionRow:
    section = db.get(SectionRow, section_id)
    if section is None:
        raise ServiceError(f"no section {section_id}")
    if not section.is_editable:
        raise ServiceError(
            f"{section.title!r} is a {section.type} section and is computed from the data. "
            f"Editing its figures would break the guarantee that the same data and template "
            f"always produce the same output. Change the template instead."
        )
    if section.pack.status in (Status.SIGNED, Status.ISSUED):
        raise ServiceError(f"pack is {section.pack.status}; reopen it before editing")

    before = (section.content_json or {}).get("text", "")
    if before == text:
        return section

    diff = make_diff(before, text)
    section.content_json = {**(section.content_json or {}), "text": text, "edited": True}
    # D-012: editing revokes approval. Otherwise "all sections approved" can be true of
    # text nobody approved — the one case where the claim actually matters.
    section.approved = False
    section.approved_by = None
    section.approved_at = None
    db.add(EditRow(section_id=section.id, diff_json=diff, editor=editor))

    if section.pack.status == Status.DRAFT:
        section.pack.status = Status.IN_REVIEW
    db.commit()
    return section


def approve_section(db: Session, section_id: int, approver: str) -> SectionRow:
    section = db.get(SectionRow, section_id)
    if section is None:
        raise ServiceError(f"no section {section_id}")
    section.approved = True
    section.approved_by = approver
    section.approved_at = datetime.now(UTC)
    if section.pack.status == Status.DRAFT:
        section.pack.status = Status.IN_REVIEW
    db.commit()
    return section


def unapprove_section(db: Session, section_id: int) -> SectionRow:
    section = db.get(SectionRow, section_id)
    if section is None:
        raise ServiceError(f"no section {section_id}")
    section.approved = False
    section.approved_by = None
    section.approved_at = None
    db.commit()
    return section


def submit_for_review(db: Session, pack_id: int) -> PackRow:
    pack = get_pack(db, pack_id)
    pack.status = apply(pack_view(db, pack), Event.SUBMIT)
    db.commit()
    return pack


# ------------------------------------------------------------------ sign-off --


def signoff(
    db: Session,
    pack_id: int,
    signer: str,
    waivers: list[dict[str, str]] | None = None,
) -> PackRow:
    """Sign and issue. Guards run here, server-side, with the UI bypassed.

    One endpoint, two transitions (PLAN.md D-013). Both go through `apply`, so neither
    can be reached without its guards.
    """
    pack = get_pack(db, pack_id)
    if pack.status == Status.DRAFT:
        pack.status = apply(pack_view(db, pack), Event.SUBMIT)

    section_keys = {s.section_key for s in pack.sections}
    gapped_keys = {s.section_key for s in pack.sections if s.gaps_json}
    recorded: list[dict[str, Any]] = []
    for waiver in waivers or []:
        key = waiver.get("section_key", "")
        reason = (waiver.get("reason") or "").strip()
        if key not in section_keys:
            raise ServiceError(f"cannot waive {key!r}: no such section in this pack")
        if key not in gapped_keys:
            raise ServiceError(f"cannot waive {key!r}: that section has no gap")
        if not reason:
            # A waiver with no reason is indistinguishable from nobody having looked,
            # which is exactly what the waiver mechanism exists to rule out.
            raise ServiceError(f"a waiver for {key!r} needs a reason")
        recorded.append(
            {"section_key": key, "reason": reason, "signer": signer,
             "at": datetime.now(UTC).isoformat()}
        )

    # Persist the waivers before the guard runs, because the guard reads them.
    row = SignoffRow(pack_id=pack.id, signer=signer, waivers_json=recorded)
    db.add(row)
    db.flush()
    db.refresh(pack)

    try:
        pack.status = apply(pack_view(db, pack), Event.SIGNOFF)
    except TransitionError:
        db.rollback()
        raise

    snapshot = snapshot_for(db, pack)
    pack_json = pack_to_json(db, pack)
    sections = [
        {
            "section_key": s.section_key,
            "title": s.title,
            "type": s.type,
            "content_json": s.content_json,
            "gaps_json": s.gaps_json,
        }
        for s in sorted(pack.sections, key=lambda s: s.order_index)
    ]

    pack.status = apply(pack_view(db, pack), Event.ISSUE)
    archive_row = write_archive(
        pack.id,
        {**pack_json, "status": Status.ISSUED},
        sections,
        snapshot,
        waivers=recorded,
        signoff={"signer": signer, "at": row.at.isoformat()},
    )
    db.add(
        ArchiveRow(
            pack_id=pack.id,
            md_ref=archive_row["md_ref"],
            pdf_ref=archive_row["pdf_ref"],
            snapshot_ref=archive_row["snapshot_ref"],
            data_snapshot_hash=archive_row["data_snapshot_hash"],
            template_ref=archive_row["template_ref"],
            content_hash=archive_row["content_hash"],
        )
    )
    db.commit()
    # The pack's `archive` relationship was loaded as None earlier in this call, before
    # the row existed. Without the refresh the caller is handed a pack that says it was
    # never archived, moments after archiving it.
    db.refresh(pack)
    return pack


def reopen(db: Session, pack_id: int) -> PackRow:
    pack = get_pack(db, pack_id)
    pack.status = apply(pack_view(db, pack), Event.REOPEN)
    if pack.signoff is not None:
        db.delete(pack.signoff)
    db.commit()
    return pack
