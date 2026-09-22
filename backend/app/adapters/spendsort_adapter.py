"""The SpendSort adapter — against the real export, with the real export's quirks.

The schema is not a reading of spec 11. It is the `COLUMNS` tuple in SpendSort's
`backend/app/services/export.py`, and the fixtures under `fixtures/spendsort/` are files
that SpendSort itself wrote (PLAN.md **D-005**; regenerate with `make fixtures`).

Three things reading the real code surfaced that reading the spec never would. Each is a
line of defensive parsing here and an entry in SIBLING_NOTES:

1. **UTF-8 with a BOM.** SpendSort writes `utf-8-sig` so Excel on Windows renders the
   em-dash in account names. Read as plain UTF-8, the first column name comes back as
   `\\ufeffdate` and every lookup of `date` misses.
2. **Anti-formula-injection apostrophes are in the data.** Text cells beginning `= + - @`
   are prefixed with `'` on export, so a vendor named `-EDF Energy` arrives as
   `'-EDF Energy`. Rendered unstripped, the pack shows a stray apostrophe on exactly the
   vendors whose names are already unusual.
3. **No period column and no schema version.** The export is every transaction SpendSort
   holds, so the period slice happens here, on `date`. And because the file carries no
   version, a schema change upstream is only detectable by the columns going missing —
   which is why every required column is checked explicitly rather than accessed hopefully.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from pathlib import Path

from app.adapters.base import SchemaMismatch
from app.adapters.frame import Frame, Value, frame_from_dicts
from app.money import quantize, to_money
from app.settings import settings

# Exactly the tuple in SpendSort's services/export.py, as of the date in SCHEMA_VERSION.
EXPECTED_COLUMNS = (
    "date",
    "vendor_raw",
    "vendor_norm",
    "amount",
    "currency",
    "account",
    "account_name",
    "confidence",
    "source",
    "reason",
    "status",
    "learned",
    "coa_valid",
    "cost_usd",
    "memo",
)

# SpendSort's own `_DANGEROUS_PREFIXES`; a cell starting with one of these was quoted.
_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r", "\n")

# Rows a human has not finished with. Kept out of the category totals, because a pack
# that counts queued items as coded overstates both the spend and the data quality.
_DECIDED = {"auto", "resolved"}


def strip_injection_guard(value: str) -> str:
    """Undo SpendSort's export-time apostrophe, and only that.

    Deliberately narrow: an apostrophe is only removed when what follows would have
    triggered the guard. A vendor genuinely called `'Round Table Ltd` keeps its quote,
    because that one was not added by the exporter.
    """
    if value.startswith("'") and value[1:2] in _INJECTION_PREFIXES:
        return value[1:]
    return value


class SpendSortAdapter:
    """Reads a real SpendSort export for a period."""

    name = "spendsort"
    SCHEMA_VERSION = "spendsort/v1(services/export.py COLUMNS @2026-09-22)"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self.dir = fixtures_dir or (settings.fixtures_dir / "spendsort")

    def catalog(self) -> tuple[str, ...]:
        return ("categories", "transactions", "review_queue")

    def _path(self, period: str) -> Path:
        path = self.dir / f"{period}.csv"
        if not path.exists():
            available = sorted(p.stem for p in self.dir.glob("*.csv")) if self.dir.exists() else []
            raise FileNotFoundError(
                f"no SpendSort export for {period} at {path}; "
                f"available: {available or 'none'} — run `make fixtures` to regenerate"
            )
        return path

    def _read(self, period: str) -> list[dict[str, Value]]:
        path = self._path(period)
        # utf-8-sig, not utf-8. See quirk 1 in the module docstring.
        with path.open(encoding="utf-8-sig", newline="") as fh:
            reader = csv.DictReader(fh)
            columns = tuple(reader.fieldnames or ())
            missing = [c for c in EXPECTED_COLUMNS if c not in columns]
            if missing:
                raise SchemaMismatch(
                    f"{self.SCHEMA_VERSION} expects column(s) {missing}, absent from "
                    f"{path.name}; found {list(columns)}. SpendSort's export schema has "
                    f"probably changed — regenerate the fixture and re-pin the version."
                )
            raw_rows = list(reader)

        rows: list[dict[str, Value]] = []
        for raw in raw_rows:
            # The export holds every transaction SpendSort knows about, so slice by date.
            # See quirk 3.
            if not (raw.get("date") or "").startswith(period):
                continue
            confidence = raw.get("confidence") or ""
            rows.append(
                {
                    "date": raw["date"],
                    "vendor_raw": strip_injection_guard(raw["vendor_raw"]),
                    "vendor_norm": strip_injection_guard(raw["vendor_norm"]),
                    "amount": to_money(raw["amount"]),
                    "currency": raw["currency"],
                    "account": raw["account"],
                    "account_name": strip_injection_guard(raw["account_name"]) or "(uncategorised)",
                    "confidence": Decimal(confidence) if confidence else None,
                    "source": raw["source"],
                    "reason": strip_injection_guard(raw["reason"]),
                    "status": raw["status"],
                    "learned": raw["learned"] == "yes",
                    "coa_valid": raw["coa_valid"] == "yes",
                    "decided": raw["status"] in _DECIDED,
                }
            )
        return rows

    def _categories(self, period: str) -> Frame:
        """Spend by account, plus the data-quality measures a controller should see.

        ``auto_rate`` travels with the money on purpose. A category total assembled from
        rows a human never confirmed is a different fact from one that was fully reviewed,
        and a pack that shows the first without saying so is overstating its own
        reliability.
        """
        rows = self._read(period)
        groups: dict[str, list[dict[str, Value]]] = {}
        for row in rows:
            groups.setdefault(str(row["account"] or ""), []).append(row)

        out: list[dict[str, Value]] = []
        for account, members in groups.items():
            decided = [m for m in members if m["decided"]]
            # Narrowed explicitly rather than ignored: these columns are built by _read
            # above and are always Decimal, but the Frame value type cannot say so, and
            # an ignore here would also hide a genuine future change to that builder.
            amounts = [m["amount"] for m in decided if isinstance(m["amount"], Decimal)]
            amount = sum(amounts, Decimal(0))
            confidences = [
                m["confidence"] for m in decided if isinstance(m["confidence"], Decimal)
            ]
            out.append(
                {
                    "account": account,
                    "account_name": members[0]["account_name"],
                    "amount": amount,
                    "txn_count": len(decided),
                    "queued_count": len(members) - len(decided),
                    "auto_rate": quantize(Decimal(len(decided)) / Decimal(len(members)) * 100, 4),
                    "avg_confidence": (
                        quantize(sum(confidences, Decimal(0)) / Decimal(len(confidences)), 4)
                        if confidences
                        else None
                    ),
                }
            )
        return frame_from_dicts(
            out,
            columns=(
                "account",
                "account_name",
                "amount",
                "txn_count",
                "queued_count",
                "auto_rate",
                "avg_confidence",
            ),
            source=self.name,
            dataset="categories",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period, "source_file": self._path(period).name},
        )

    def _transactions(self, period: str) -> Frame:
        rows = self._read(period)
        return frame_from_dicts(
            rows,
            source=self.name,
            dataset="transactions",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period},
        )

    def _review_queue(self, period: str) -> Frame:
        """What SpendSort could not decide. A gap in the *data*, surfaced in the pack."""
        rows = [r for r in self._read(period) if not r["decided"]]
        return frame_from_dicts(
            rows,
            columns=(
                "date",
                "vendor_raw",
                "amount",
                "account",
                "account_name",
                "confidence",
                "reason",
                "status",
            ),
            source=self.name,
            dataset="review_queue",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period},
        )

    def fetch(self, dataset: str, period: str) -> Frame:
        if dataset == "categories":
            return self._categories(period)
        if dataset == "transactions":
            return self._transactions(period)
        if dataset == "review_queue":
            return self._review_queue(period)
        raise KeyError(f"spendsort publishes no dataset {dataset!r}")
