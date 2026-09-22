"""The archive: four artefacts, one hash, and no way to edit any of it.

Spec 13 F6: *"issued packs immutable: rendered markdown + PDF + data snapshot + template
version + hash."*

**The hash covers all four together.** A hash over the markdown alone would let the data
snapshot be swapped without detection — and the snapshot is the part that says what the
numbers were. `verify_archive` re-computes each component and names which one changed, so a
tamper report is actionable rather than just alarming.

**Immutability is structural.** This module has no UPDATE or DELETE statement, and
`test_archive_immutable.py` greps the whole of `app/` to prove no other module has one
either. Re-issuing raises. Files are written once, to a directory named for the pack.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.assemble.hashes import digest
from app.issue.render_md import render_markdown
from app.issue.render_pdf import render_pdf
from app.settings import settings


class ArchiveError(RuntimeError):
    pass


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def content_hash(
    *, markdown: str, snapshot_hash: str, template_ref: str, pdf_sha: str | None
) -> str:
    """One hash over everything an archive attests to.

    `pdf_sha` may be None — a pack issued without a PDF is a different artefact set from
    one issued with it, and the hash says so rather than quietly matching.
    """
    return digest(
        {
            "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
            "pdf_sha256": pdf_sha,
            "data_snapshot_hash": snapshot_hash,
            "template_ref": template_ref,
        }
    )


def archive_dir(pack_id: int) -> Path:
    return settings.archive_dir / f"pack-{pack_id:05d}"


def write_archive(
    pack_id: int,
    pack: dict[str, Any],
    sections: list[dict[str, Any]],
    snapshot: dict[str, Any],
    *,
    waivers: list[dict[str, Any]] | None = None,
    signoff: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Write the four artefacts and return the row for the `archives` table."""
    out = archive_dir(pack_id)
    if out.exists() and (out / "pack.md").exists():
        raise ArchiveError(f"pack {pack_id} is already archived at {out}; archives are append-only")
    out.mkdir(parents=True, exist_ok=True)

    markdown = render_markdown(pack, sections, waivers=waivers, signoff=signoff)
    md_path = out / "pack.md"
    md_path.write_text(markdown, encoding="utf-8", newline="\n")

    snapshot_path = out / "data_snapshot.json"
    snapshot_path.write_text(
        json.dumps(snapshot, indent=2, sort_keys=True, default=str), encoding="utf-8", newline="\n"
    )

    pdf_path = render_pdf(out / "pack.pdf", pack, sections, waivers=waivers, signoff=signoff)
    pdf_sha = _sha256_file(pdf_path) if pdf_path else None

    combined = content_hash(
        markdown=markdown,
        snapshot_hash=pack.get("snapshot_hash", ""),
        template_ref=pack["template_ref"],
        pdf_sha=pdf_sha,
    )

    # A manifest beside the artefacts, so an archive can be verified by someone who has
    # the directory and not the database. An archive that is only checkable from inside
    # the app that wrote it is not much of an archive.
    manifest = {
        "pack_id": pack_id,
        "period": pack["period"],
        "template_ref": pack["template_ref"],
        "data_snapshot_hash": pack.get("snapshot_hash", ""),
        "structure_hash": pack.get("structure_hash", ""),
        "value_digest": pack.get("value_digest", ""),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "pdf_sha256": pdf_sha,
        "pdf_available": pdf_path is not None,
        "content_hash": combined,
        "issued_at": datetime.now(UTC).isoformat(),
        "signoff": signoff,
        "waivers": waivers or [],
    }
    (out / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8", newline="\n"
    )

    return {
        "pack_id": pack_id,
        "md_ref": str(md_path),
        "pdf_ref": str(pdf_path) if pdf_path else None,
        "snapshot_ref": str(snapshot_path),
        "data_snapshot_hash": pack.get("snapshot_hash", ""),
        "template_ref": pack["template_ref"],
        "content_hash": combined,
        "pdf_available": pdf_path is not None,
    }


def verify_archive(pack_id: int) -> dict[str, Any]:
    """Re-check an archive against its manifest, naming whatever changed."""
    out = archive_dir(pack_id)
    manifest_path = out / "MANIFEST.json"
    if not manifest_path.exists():
        return {"ok": False, "problems": [f"no manifest at {manifest_path}"]}

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    problems: list[str] = []

    md_path = out / "pack.md"
    if not md_path.exists():
        problems.append("pack.md is missing")
    else:
        actual = hashlib.sha256(md_path.read_bytes()).hexdigest()
        if actual != manifest["markdown_sha256"]:
            problems.append("pack.md has been modified since issuance")

    if manifest.get("pdf_available"):
        pdf_path = out / "pack.pdf"
        if not pdf_path.exists():
            problems.append("pack.pdf is missing")
        elif _sha256_file(pdf_path) != manifest["pdf_sha256"]:
            problems.append("pack.pdf has been modified since issuance")

    snapshot_path = out / "data_snapshot.json"
    if not snapshot_path.exists():
        problems.append("data_snapshot.json is missing")
    else:
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        if digest(snapshot) != manifest["data_snapshot_hash"]:
            problems.append("data_snapshot.json no longer matches the hash recorded at issuance")

    return {"ok": not problems, "problems": problems, "manifest": manifest}
