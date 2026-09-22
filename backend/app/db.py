"""Session handling and first-run seeding."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.models import Base, TemplateRow
from app.settings import settings
from app.template.store import dump_template, load_default_templates

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if settings.database_url.startswith("sqlite") else {},
    future=True,
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False, future=True)


def init_db() -> None:
    """Create tables and install the shipped templates.

    Seeding is idempotent and keyed on ``(template_id, version)``: re-running never
    duplicates, and never overwrites a version some pack already cites. A shipped
    template that changes needs a new version number, exactly like a user's does.
    """
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for template in load_default_templates():
            exists = db.scalar(
                select(TemplateRow).where(
                    TemplateRow.template_id == template.id,
                    TemplateRow.version == template.version,
                )
            )
            if exists:
                continue
            db.add(
                TemplateRow(
                    template_id=template.id,
                    name=template.name,
                    version=template.version,
                    yaml=dump_template(template),
                )
            )
        db.commit()


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    with SessionLocal() as db:
        yield db


@contextmanager
def session_scope() -> Iterator[Session]:
    """For the CLI and tests, where there is no request to hang a dependency on."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
