"""The API — spec 13 §7's surface, and nothing beyond it.

    CRUD /api/templates · POST /api/packs · GET /api/packs/{id}
    POST /api/sections/{id}/edit · POST /api/sections/{id}/approve
    POST /api/packs/{id}/signoff · GET /api/packs/{id}/export · GET /api/archive

Guards live in `app/issue/states.py` and are reached only through `app/service.py`, so no
route can get a pack into a state another route would refuse.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import service
from app.db import get_db, init_db
from app.issue.archive import verify_archive
from app.issue.states import TransitionError
from app.models import ArchiveRow, PackRow, SectionRow, TemplateRow
from app.periods import all_periods, default_period, next_period
from app.settings import settings
from app.template.store import TemplateError

app = FastAPI(
    title="ReportSmith",
    version="0.1.0",
    description="Define the pack once. Review forever after.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    init_db()


def _handle(exc: Exception) -> HTTPException:
    """Service refusals are 400s whose message is meant to be read by a person."""
    if isinstance(exc, TemplateError | service.ServiceError):
        return HTTPException(status_code=400, detail=str(exc))
    if isinstance(exc, TransitionError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


# ------------------------------------------------------------------ schemas --


class TemplateIn(BaseModel):
    yaml: str = Field(min_length=1)


class PackIn(BaseModel):
    template: str = "monthly_management_pack"
    period: str | None = None
    version: int | None = None


class EditIn(BaseModel):
    text: str
    editor: str = "reviewer"


class ApproveIn(BaseModel):
    approver: str = "reviewer"


class WaiverIn(BaseModel):
    section_key: str
    reason: str


class SignoffIn(BaseModel):
    signer: str | None = None
    waivers: list[WaiverIn] = Field(default_factory=list)


# ---------------------------------------------------------------- meta/system --


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "ok": True,
        "llm": "live" if settings.live_llm else "mock",
        "model": settings.model if settings.live_llm else "mock",
        "synthetic_data": True,
    }


@app.get("/api/periods")
def periods() -> dict[str, Any]:
    return {
        "periods": [{"id": p.id, "label": p.label, "index": p.index} for p in all_periods()],
        "default": default_period().id,
        "next": next_period(default_period().id).id,
    }


# ----------------------------------------------------------------- templates --


@app.get("/api/templates")
def list_templates(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(TemplateRow).order_by(TemplateRow.template_id, TemplateRow.version.desc())
    ).all()
    return [
        {
            "id": r.id,
            "template_id": r.template_id,
            "name": r.name,
            "version": r.version,
            "ref": r.ref,
            "locked": service.template_is_locked(db, r),
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


@app.get("/api/templates/{template_id}")
def get_template(
    template_id: str, version: int | None = None, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        row = service.get_template_row(db, template_id, version)
        template = service.load_template(row)
    except Exception as exc:
        raise _handle(exc) from exc
    return {
        "template_id": row.template_id,
        "name": row.name,
        "version": row.version,
        "ref": row.ref,
        "yaml": row.yaml,
        "locked": service.template_is_locked(db, row),
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "type": s.type,
                "required": s.required,
                "source": s.binding.source,
                "select": s.binding.select,
            }
            for s in template.sections
        ],
    }


@app.post("/api/templates")
def create_template(body: TemplateIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        row = service.save_template(db, body.yaml)
    except Exception as exc:
        raise _handle(exc) from exc
    return {"template_id": row.template_id, "version": row.version, "ref": row.ref}


@app.post("/api/templates/validate")
def validate_template(body: TemplateIn) -> dict[str, Any]:
    """Validate without saving — what the editor calls as you type."""
    from app.template.store import parse_template

    try:
        template = parse_template(body.yaml, source="editor")
    except TemplateError as exc:
        return {"valid": False, "error": str(exc)}
    return {
        "valid": True,
        "ref": template.ref,
        "sections": [
            {
                "id": s.id,
                "title": s.title,
                "type": s.type,
                "required": s.required,
                "source": s.binding.source,
                "select": s.binding.select,
            }
            for s in template.sections
        ],
    }


# --------------------------------------------------------------------- packs --


@app.post("/api/packs")
def create_pack(body: PackIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    period = body.period or default_period().id
    try:
        pack = service.create_pack(db, body.template, period, version=body.version)
        return service.pack_to_json(db, pack)
    except Exception as exc:
        raise _handle(exc) from exc


@app.get("/api/packs")
def list_packs(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(PackRow).order_by(PackRow.id.desc())).all()
    return [
        {
            "id": p.id,
            "period": p.period,
            "status": p.status,
            "template_ref": p.template_ref,
            "created_at": p.created_at.isoformat(),
            "gap_count": sum(1 for s in p.sections if s.gaps_json),
            "section_count": len(p.sections),
            "approved_count": sum(1 for s in p.sections if s.approved),
            "issued": p.archive is not None,
        }
        for p in rows
    ]


@app.get("/api/packs/diff")
def diff_packs(
    a: int = Query(...), b: int = Query(...), db: Session = Depends(get_db)
) -> dict[str, Any]:
    """The month-diff view (spec 13 F7): identical structure, changed numbers."""
    try:
        pack_a, pack_b = service.get_pack(db, a), service.get_pack(db, b)
    except Exception as exc:
        raise _handle(exc) from exc

    sections_a = {s.section_key: s for s in pack_a.sections}
    sections_b = {s.section_key: s for s in pack_b.sections}

    rows: list[dict[str, Any]] = []

    def _order(key: str) -> int:
        # A section present in only one pack still needs a position, so the diff renders in
        # template order rather than alphabetically.
        section = sections_a.get(key) or sections_b[key]
        return section.order_index

    for key in sorted(set(sections_a) | set(sections_b), key=_order):
        left, right = sections_a.get(key), sections_b.get(key)
        # One of the two always exists — `key` came from the union of their keys.
        either = left or right
        assert either is not None
        rows.append(
            {
                "section_key": key,
                "title": either.title,
                "type": either.type,
                "in_a": left is not None,
                "in_b": right is not None,
                "structure_same": left is not None
                and right is not None
                and left.type == right.type,
                "values_changed": _values_changed(left, right),
                "a": _diff_side(left),
                "b": _diff_side(right),
            }
        )

    return {
        "a": {
            "id": pack_a.id,
            "period": pack_a.period,
            "template_ref": pack_a.template_ref,
            "structure_hash": pack_a.structure_hash,
            "value_digest": pack_a.value_digest,
        },
        "b": {
            "id": pack_b.id,
            "period": pack_b.period,
            "template_ref": pack_b.template_ref,
            "structure_hash": pack_b.structure_hash,
            "value_digest": pack_b.value_digest,
        },
        "structure_identical": pack_a.structure_hash == pack_b.structure_hash,
        "values_differ": pack_a.value_digest != pack_b.value_digest,
        "sections": rows,
    }


def _values_changed(a: SectionRow | None, b: SectionRow | None) -> bool:
    if a is None or b is None:
        return True
    from app.assemble.hashes import value_digest

    return value_digest([_row(a)]) != value_digest([_row(b)])


def _row(section: SectionRow) -> dict[str, Any]:
    return {
        "section_key": section.section_key,
        "type": section.type,
        "order_index": section.order_index,
        "content_json": section.content_json,
    }


def _diff_side(section: SectionRow | None) -> dict[str, Any] | None:
    if section is None:
        return None
    content = section.content_json or {}
    summary: list[dict[str, str]] = []
    if section.type == "kpi_grid":
        summary = [
            {"label": k["label"], "display": k.get("display", "")}
            for k in content.get("kpis", [])
            if not k.get("missing")
        ]
    elif section.type == "table":
        columns = content.get("columns", [])
        if columns:
            first, last = columns[0]["field"], columns[-1]["field"]
            summary = [
                {
                    "label": str(r.get(first, {}).get("display", "")),
                    "display": str(r.get(last, {}).get("display", "")),
                }
                for r in content.get("rows", [])[:6]
            ]
    elif section.type == "flags":
        summary = [
            {"label": i["label"], "display": i["severity"]} for i in content.get("items", [])
        ]
    elif section.type == "narrative":
        summary = [{"label": "text", "display": (content.get("text") or "")[:400]}]
    return {"gap": bool(section.gaps_json), "summary": summary}


@app.get("/api/packs/{pack_id}")
def get_pack(pack_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return service.pack_to_json(db, service.get_pack(db, pack_id))
    except Exception as exc:
        raise _handle(exc) from exc


@app.post("/api/packs/{pack_id}/signoff")
def signoff(pack_id: int, body: SignoffIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        pack = service.signoff(
            db,
            pack_id,
            body.signer or settings.signer_name,
            [w.model_dump() for w in body.waivers],
        )
        return service.pack_to_json(db, pack)
    except Exception as exc:
        raise _handle(exc) from exc


@app.post("/api/packs/{pack_id}/reopen")
def reopen(pack_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return service.pack_to_json(db, service.reopen(db, pack_id))
    except Exception as exc:
        raise _handle(exc) from exc


@app.get("/api/packs/{pack_id}/export", response_class=PlainTextResponse)
def export_pack(pack_id: int, db: Session = Depends(get_db)) -> str:
    from app.issue.render_md import render_markdown

    try:
        pack = service.get_pack(db, pack_id)
    except Exception as exc:
        raise _handle(exc) from exc

    pack_json = service.pack_to_json(db, pack)
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
    waivers = pack.signoff.waivers_json if pack.signoff else []
    signoff_info = (
        {"signer": pack.signoff.signer, "at": pack.signoff.at.isoformat()} if pack.signoff else None
    )
    return render_markdown(pack_json, sections, waivers=waivers, signoff=signoff_info)


# ------------------------------------------------------------------ sections --


@app.post("/api/sections/{section_id}/edit")
def edit_section(section_id: int, body: EditIn, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return service.section_to_json(service.edit_section(db, section_id, body.text, body.editor))
    except Exception as exc:
        raise _handle(exc) from exc


@app.post("/api/sections/{section_id}/approve")
def approve_section(
    section_id: int, body: ApproveIn, db: Session = Depends(get_db)
) -> dict[str, Any]:
    try:
        return service.section_to_json(service.approve_section(db, section_id, body.approver))
    except Exception as exc:
        raise _handle(exc) from exc


@app.post("/api/sections/{section_id}/unapprove")
def unapprove_section(section_id: int, db: Session = Depends(get_db)) -> dict[str, Any]:
    try:
        return service.section_to_json(service.unapprove_section(db, section_id))
    except Exception as exc:
        raise _handle(exc) from exc


# ------------------------------------------------------------------- archive --


@app.get("/api/archive")
def archive(db: Session = Depends(get_db)) -> list[dict[str, Any]]:
    rows = db.scalars(select(ArchiveRow).order_by(ArchiveRow.issued_at.desc())).all()
    return [
        {
            "pack_id": r.pack_id,
            "period": r.pack.period,
            "template_ref": r.template_ref,
            "content_hash": r.content_hash,
            "data_snapshot_hash": r.data_snapshot_hash,
            "md_ref": r.md_ref,
            "pdf_ref": r.pdf_ref,
            "pdf_available": bool(r.pdf_ref),
            "issued_at": r.issued_at.isoformat(),
            "verified": verify_archive(r.pack_id)["ok"],
        }
        for r in rows
    ]


@app.get("/api/archive/{pack_id}/verify")
def verify(pack_id: int) -> dict[str, Any]:
    return verify_archive(pack_id)
