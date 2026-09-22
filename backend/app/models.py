"""The six tables spec 13 §6 names, and nothing else.

    templates · packs · sections · edits · signoffs · archives

Two of the columns carry the product's whole governance argument and are worth naming:

``sections.ai_draft_json`` is written **once**, at assembly, and never again. The human's
work lands in ``content_json``. Keeping both means "the AI draft is preserved alongside
the human edits" (spec 13 F5) is a property of the schema rather than a habit — you
cannot lose the draft by editing, because editing does not touch that column.

``archives`` is INSERT-only. No code in ``app/`` issues an UPDATE or DELETE against it,
and a test asserts that by inspection. An archive you can edit is not an archive.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class TemplateRow(Base):
    """A versioned template. ``(template_id, version)`` is immutable once a pack cites it.

    The YAML is stored verbatim rather than as parsed JSON, because the author's
    comments and ordering are part of what they wrote — and a template is a document a
    human maintains, not a config blob the system owns.
    """

    __tablename__ = "templates"
    __table_args__ = (UniqueConstraint("template_id", "version", name="uq_template_version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_id: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(200))
    version: Mapped[int] = mapped_column(Integer)
    yaml: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    packs: Mapped[list[PackRow]] = relationship(back_populates="template")

    @property
    def ref(self) -> str:
        return f"{self.template_id}@v{self.version}"


class PackRow(Base):
    """One period's pack. ``status`` is driven only by app/issue/states.py."""

    __tablename__ = "packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    template_pk: Mapped[int] = mapped_column(ForeignKey("templates.id"))
    template_id: Mapped[str] = mapped_column(String(64), index=True)
    template_version: Mapped[int] = mapped_column(Integer)
    period: Mapped[str] = mapped_column(String(16), index=True)
    status: Mapped[str] = mapped_column(String(16), default="draft", index=True)

    # Two hashes over disjoint inputs, so "same structure, different numbers" is a
    # testable claim rather than an impression (PLAN.md D-016).
    structure_hash: Mapped[str] = mapped_column(String(64), default="")
    value_digest: Mapped[str] = mapped_column(String(64), default="")
    snapshot_hash: Mapped[str] = mapped_column(String(64), default="")

    model: Mapped[str] = mapped_column(String(64), default="mock")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    template: Mapped[TemplateRow] = relationship(back_populates="packs")
    sections: Mapped[list[SectionRow]] = relationship(
        back_populates="pack", cascade="all, delete-orphan", order_by="SectionRow.order_index"
    )
    signoff: Mapped[SignoffRow | None] = relationship(
        back_populates="pack", cascade="all, delete-orphan", uselist=False
    )
    archive: Mapped[ArchiveRow | None] = relationship(
        back_populates="pack", cascade="all, delete-orphan", uselist=False
    )

    @property
    def template_ref(self) -> str:
        return f"{self.template_id}@v{self.template_version}"


class SectionRow(Base):
    """An assembled section.

    ``gaps_json`` is a list, not a nullable object: a section can be bound and still
    carry a warning, and a section can have more than one thing wrong with it. Modelling
    "gap" as a single optional field would have forced the first gap found to win.
    """

    __tablename__ = "sections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"), index=True)
    section_key: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(200))
    type: Mapped[str] = mapped_column(String(16))
    order_index: Mapped[int] = mapped_column(Integer)
    required: Mapped[bool] = mapped_column(Boolean, default=True)

    content_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    # Written once at assembly. Never updated. That is the point.
    ai_draft_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    gaps_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    binding_status: Mapped[str] = mapped_column(String(16), default="bound")

    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(120), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    pack: Mapped[PackRow] = relationship(back_populates="sections")
    edits: Mapped[list[EditRow]] = relationship(
        back_populates="section", cascade="all, delete-orphan", order_by="EditRow.id"
    )

    @property
    def has_gap(self) -> bool:
        return bool(self.gaps_json)

    @property
    def is_editable(self) -> bool:
        """Only narrative sections. A table is a function of (data, template); editing
        its cells would break the golden-file contract and make the archive hash a claim
        about nothing (PLAN.md D-011)."""
        return self.type == "narrative"


class EditRow(Base):
    """One human edit, stored as a diff against what was there before."""

    __tablename__ = "edits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.id"), index=True)
    diff_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    editor: Mapped[str] = mapped_column(String(120))
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    section: Mapped[SectionRow] = relationship(back_populates="edits")


class SignoffRow(Base):
    """The pack-level sign-off, and any waivers it carried.

    ``waivers_json`` holds one entry per waived gap: the section, the gap reason, the
    reason the human gave, and who gave it. A waiver with no reason is rejected — a
    waiver whose reason is unrecorded is indistinguishable from nobody having looked.
    """

    __tablename__ = "signoffs"

    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"), primary_key=True)
    signer: Mapped[str] = mapped_column(String(120))
    waivers_json: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pack: Mapped[PackRow] = relationship(back_populates="signoff")


class ArchiveRow(Base):
    """An issued pack. INSERT-only — see the module docstring."""

    __tablename__ = "archives"

    pack_id: Mapped[int] = mapped_column(ForeignKey("packs.id"), primary_key=True)
    md_ref: Mapped[str] = mapped_column(String(400))
    pdf_ref: Mapped[str | None] = mapped_column(String(400), nullable=True)
    snapshot_ref: Mapped[str] = mapped_column(String(400))
    data_snapshot_hash: Mapped[str] = mapped_column(String(64))
    template_ref: Mapped[str] = mapped_column(String(80))
    # Covers md + pdf + snapshot + template version together. Tampering with any one
    # of the four is detectable, and the verifier says which.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    pack: Mapped[PackRow] = relationship(back_populates="archive")
