"""Generate the SpendSort export fixtures — by running SpendSort, not by imitating it.

The brief offers two branches: *"fixture-test against real sample exports you generate
from them if runnable, else from their documented schemas."* SpendSort **is** runnable, so
this takes the first branch (PLAN.md **D-005**).

What this script does:

1. Builds an intake CSV from **this pack's own ledgerfab period** — the same GL expense
   lines the pack reports on. So the SpendSort category total must reconcile to the pack's
   expense total to the cent, and `test_fixture_reconciliation.py` asserts exactly that
   (PLAN.md **D-006**). A hand-written fixture could only prove the parser runs.
2. Drives SpendSort's real `parse_csv` → `categorize_pending` → `export_csv`, in mock-LLM
   mode, so it costs nothing and is deterministic.
3. Writes the result under `fixtures/spendsort/<period>.csv`, committed, so the repo stays
   self-contained and neither CI nor a fresh clone ever reaches into a sibling
   (PLAN.md **D-017**).

This is a **build-time** script. Nothing in `backend/app/` imports SpendSort; the product
reads the committed CSV. Run it with `make fixtures`.

    python fixtures/gen_fixtures.py [--periods 2024-07 2024-08]
"""

from __future__ import annotations

import argparse
import csv
import io
import os
import shutil
import subprocess
import sys
import tempfile
import json

import yaml
from decimal import Decimal
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SPENDSORT = REPO.parent / "spendsort"
OUT_DIR = REPO / "fixtures" / "spendsort"

sys.path.insert(0, str(REPO / "backend"))


class SpendSortUnavailable(RuntimeError):
    """SpendSort is not on disk, so a real export cannot be generated here.

    Not fatal to the product: the committed fixtures are what ship. This only stops
    *regeneration*, and the message says so rather than implying the pack is broken.
    """


def _require_spendsort() -> Path:
    backend = SPENDSORT / "backend"
    if not (backend / "app" / "services" / "export.py").exists():
        raise SpendSortUnavailable(
            f"SpendSort not found at {SPENDSORT}. The committed fixtures under "
            f"{OUT_DIR.relative_to(REPO)} still work; only regeneration needs the sibling."
        )
    return backend


def build_payload(period: str) -> tuple[dict[str, object], Decimal]:
    """Everything SpendSort needs to categorise this period the way a trained instance would.

    Three parts, and the second two are why this works at all:

    **The intake CSV** — this period's GL expense lines in SpendSort's intake shape
    (`date, amount, currency, vendor, memo`, per its `examples/README.md`).

    **A chart of accounts** built from the same ledgerfab world. SpendSort ships its own
    CoA in which `6000` is *Advertising & Marketing*, while the shared engine's `6000` is
    *Professional fees* — the same code meaning two different things (SIBLING_NOTES).
    Categorising against the wrong chart would put real money under wrong headings, so the
    chart travels with the data.

    **A pre-seeded vendor memory.** SpendSort's `MockCategorizer` recognises a fixed table
    of consumer and SaaS descriptors — Amazon, Uber, Zoom — and cannot categorise the
    shared engine's B2B counterparties at all; every row comes back blank and queued. But
    SpendSort's *signature* design is memory-first: a mapping a human has confirmed
    bypasses the model entirely (its spec 11 F4). The GL already records which account
    each counterparty's invoices were booked to, so those mappings are exactly what a
    trained SpendSort instance would hold after a month of review. Seeding them uses the
    product as designed rather than working around it — and it means this fixture is
    generated with **zero LLM calls**, which is also why it is deterministic.
    """
    from app.periods import world_for  # noqa: PLC0415 — build-time import, after sys.path

    world = world_for(period)
    accounts = {a.code: a for a in world.accounts}
    invoice_by_id = {inv.id: inv for inv in world.invoices}
    counterparty_by_id = {c.id: c for c in world.counterparties}

    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(["date", "amount", "currency", "vendor", "memo"])

    total = Decimal(0)
    # vendor name → the account its invoices were actually booked to, straight from the GL.
    learned: dict[str, str] = {}

    for entry in world.gl_entries:
        account = accounts.get(entry.account_code)
        if account is None or account.type != "expense":
            continue
        invoice = invoice_by_id.get(entry.invoice_id or "")
        counterparty = counterparty_by_id.get(invoice.counterparty_id) if invoice else None
        vendor = counterparty.canonical_name if counterparty else "Unknown vendor"
        amount = Decimal(str(entry.amount)).quantize(Decimal("0.01"))
        total += amount
        learned.setdefault(vendor, entry.account_code)
        writer.writerow(
            [entry.date.isoformat(), f"{amount:.2f}", world.company.base_currency, vendor, entry.memo]
        )

    coa = {
        "accounts": [
            {
                "code": a.code,
                "name": a.name,
                "kind": a.type,
                "description": f"{a.name} ({a.type})",
            }
            for a in world.accounts
            if a.type == "expense"
        ]
    }

    return {"intake": buffer.getvalue(), "coa": coa, "learned": learned}, total


# The driver that runs *inside* SpendSort's own interpreter. Kept here rather than as a
# file in the sibling, because this repo must not write into a sibling repo to work.
_DRIVER = '''
import json, sys
from app.db import SessionLocal, init_db
from app.models import Transaction, VendorMemory
from app.normalize import normalize_vendor
from app.services.export import export_csv
from app.services.ingest import parse_csv
from app.services.runner import categorize_pending

payload = json.loads(sys.stdin.read())
init_db()
report = parse_csv(payload["intake"].encode("utf-8"), max_bytes=50_000_000, max_rows=100_000)

with SessionLocal() as db:
    # Seed the learned mappings first, so every row takes the memory path and the model
    # is never called. `source="human"` is accurate: these came from the general ledger,
    # which is a person's posting decision, not a guess.
    for vendor_raw, account_code in payload["learned"].items():
        db.add(VendorMemory(
            vendor_norm=normalize_vendor(vendor_raw),
            account_code=account_code,
            source="human",
            hit_count=0,
            example_vendor_raw=vendor_raw,
        ))
    for row in report.rows:
        db.add(Transaction(
            date=row.date, amount=row.amount, currency=row.currency,
            vendor_raw=row.vendor_raw, vendor_norm=row.vendor_norm, memo=row.memo,
        ))
    db.commit()
    run = categorize_pending(db)
    out = export_csv(db)
    sys.stderr.write(
        "rows=%d auto_rate=%.3f memory_hit_rate=%.3f cost=$%.4f llm=%s\\n"
        % (len(report.rows), run.auto_rate, run.memory_hit_rate, run.cost_usd, run.llm_mode)
    )
sys.stdout.write(out)
'''


def generate(period: str) -> Path:
    """Run real SpendSort over this period, in its own interpreter, and keep its export.

    A **subprocess**, not an import. Both repos name their package `app`, so importing
    SpendSort into this process permanently shadows ReportSmith's own `app` — and the
    failure surfaces three layers away from the cause. A subprocess also means SpendSort
    runs against *its own* installed dependencies rather than whatever happens to be in
    this venv, which is what "we ran the real thing" has to mean to be worth claiming.
    """
    backend = _require_spendsort()
    payload, expected_total = build_payload(period)

    python = SPENDSORT / ".venv" / "Scripts" / "python.exe"
    if not python.exists():
        python = SPENDSORT / ".venv" / "bin" / "python"
    if not python.exists():
        raise SpendSortUnavailable(
            f"SpendSort has no virtualenv at {SPENDSORT / '.venv'}; run `make install` there first"
        )

    tmpdir = Path(tempfile.mkdtemp(prefix=f"spendsort-{period}-"))
    # The chart of accounts travels with the data — see build_payload. Written to the temp
    # dir rather than into the sibling, because generating a fixture must never modify
    # SpendSort's working tree.
    coa_path = tmpdir / "coa.yaml"
    coa_path.write_text(yaml.safe_dump(payload["coa"], sort_keys=False), encoding="utf-8")

    env = {
        **os.environ,
        "SPENDSORT_COA_PATH": str(coa_path),
        "SPENDSORT_DATABASE_URL": f"sqlite:///{tmpdir / 'gen.db'}",
        "SPENDSORT_MOCK_LLM": "true",  # deterministic, and costs nothing
        "PYTHONPATH": str(backend),
        # Without this, the child's stdout defaults to the Windows console codepage and
        # the em-dash in account names like "Travel — Airfare" comes back as a lone 0x97.
        # SpendSort's own export module calls that out as the reason it writes utf-8-sig;
        # the same character bites one layer up, in the pipe.
        "PYTHONIOENCODING": "utf-8",
    }
    env.pop("OPENAI_API_KEY", None)

    try:
        proc = subprocess.run(
            [str(python), "-c", _DRIVER],
            input=json.dumps(payload).encode("utf-8"),
            capture_output=True,
            env=env,
            cwd=str(backend),
            check=False,
        )
        if proc.returncode != 0:
            raise SpendSortUnavailable(
                f"SpendSort failed to run for {period}:\n{proc.stderr.decode('utf-8', 'replace')}"
            )
        exported = proc.stdout.decode("utf-8")
        note = proc.stderr.decode("utf-8", "replace").strip()
        print(f"  {period}: {note} | £{expected_total:,.2f} expense total")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / f"{period}.csv"
    # utf-8-sig, matching what SpendSort's own `export_bytes` writes, so the fixture is
    # byte-faithful to the real thing — including the BOM the adapter has to handle.
    out.write_text(exported, encoding="utf-8-sig", newline="")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--periods", nargs="*", default=None)
    args = parser.parse_args()

    from app.periods import default_period, next_period  # noqa: PLC0415

    periods = args.periods or [default_period().id, next_period(default_period().id).id]

    print(f"Generating SpendSort export fixtures for {', '.join(periods)}")
    try:
        for period in periods:
            path = generate(period)
            print(f"  -> {path.relative_to(REPO)}")
    except SpendSortUnavailable as exc:
        print(f"SKIPPED: {exc}")
        return 0
    print("Done. These are real SpendSort exports, not imitations of the schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
