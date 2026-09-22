"""The ledgerfab adapter — statements from the emitter, operational detail from the engine.

Two upstream halves, one adapter, because a controller does not think of them as two
things. The emitter gives the *reported position* (P&L, balance sheet, cash flow, all
derived from one trial balance). The base engine gives the *operational detail* behind
the payables line — the invoices and the exceptions somebody has to chase.

Every dataset here carries its prior-period comparative alongside the current figure,
because every table and KPI in the default pack wants one and computing it twice, in
two places, is how the table and the narrative end up disagreeing.
"""

from __future__ import annotations

from decimal import Decimal

from app.adapters.frame import Frame, Value, frame_from_dicts
from app.money import pct_change, quantize, to_money
from app.periods import period_ref, statements_for, world_for
from app.settings import settings

# The exception taxonomy carries no severity of its own — it is a cause, not a rank.
# A pack has to sort exceptions somehow, and "by how much a controller should care"
# beats alphabetical. Mapped here rather than in the template so the ranking is one
# reviewable table instead of a magic number in YAML.
_EXCEPTION_SEVERITY: dict[str, tuple[str, int]] = {
    "duplicate": ("high", 3),  # real money out of the door twice
    "dispute": ("high", 3),  # a counterparty is contesting; it will not self-resolve
    "partial_payment": ("medium", 2),
    "missing_reference": ("medium", 2),
    "fx_rounding": ("low", 1),
    "timing": ("low", 1),
    "unknown": ("medium", 2),  # unknown is not low: it means nobody has looked yet
}

# The P&L and balance sheet lines the pack summarises. Not every line the emitter
# produces — a management pack is a summary, and a 23-row balance sheet is a trial
# balance with ambitions.
_PNL_LINES = (
    "revenue",
    "cogs",
    "gross_profit",
    "operating_expenses",
    "operating_profit",
    "interest_expense",
    "tax_expense",
    "net_income",
)
_BS_LINES = (
    "cash",
    "accounts_receivable",
    "inventory",
    "total_current_assets",
    "ppe_net",
    "total_assets",
    "accounts_payable",
    "total_current_liabilities",
    "long_term_debt",
    "total_liabilities",
    "total_equity",
)
_CF_LINES = (
    "cf_net_income",
    "cf_depreciation",
    "cf_change_receivables",
    "cf_change_inventory",
    "cf_change_payables",
    "cf_operating",
    "cf_capex",
    "cf_investing",
    "cf_financing",
    "cf_net_change_in_cash",
    "cf_cash_close",
)


class LedgerfabAdapter:
    """Reads the vendored engine and its statement emitter. No I/O, no network."""

    name = "ledgerfab"
    # Vendored in-process, so the "schema" is the package version itself — there is no
    # file format in between that could drift.
    SCHEMA_VERSION = "ledgerfab/0.1.0+statements(vendored 2026-09-22)"

    def __init__(self, profile: str | None = None, seed: int | None = None) -> None:
        self.profile = profile or settings.profile
        self.seed = seed if seed is not None else settings.seed

    def catalog(self) -> tuple[str, ...]:
        return (
            "pnl_lines",
            "bs_lines",
            "cf_lines",
            "period_metrics",
            "exceptions",
            "invoices",
            "gl_expense_lines",
        )

    # -- statements ---------------------------------------------------------

    def _statement_frame(self, statement: str, codes: tuple[str, ...], period: str) -> Frame:
        st = statements_for(self.profile, self.seed)
        ref = period_ref(period)
        prior = ref.prior_id

        by_code = {line.line_code: line for line in st.lines if line.period_id == period}
        rows: list[dict[str, Value]] = []
        for code in codes:
            line = by_code.get(code)
            if line is None:
                continue
            amount = to_money(line.amount)
            prior_amount = to_money(st.amount(prior, code)) if prior and st.amount(prior, code) is not None else None
            rows.append(
                {
                    "line_code": code,
                    "label": line.label,
                    "statement": statement,
                    "amount": amount,
                    "prior_amount": prior_amount,
                    "delta": (amount - prior_amount) if prior_amount is not None else None,
                    "delta_pct": pct_change(amount, prior_amount),
                    "is_subtotal": bool(getattr(line, "is_subtotal", False)),
                }
            )
        return frame_from_dicts(
            rows,
            source=self.name,
            dataset=f"{statement}_lines",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period, "prior_period": prior, "entity": st.entity_name},
        )

    # -- metrics ------------------------------------------------------------

    def _metrics(self, period: str) -> Frame:
        """One row per metric, not one row of many columns.

        Long rather than wide because a KPI grid selects metrics *by name*: with one row
        per metric, adding a KPI to a template is a lookup, and a template naming a
        metric that does not exist produces a clean "unknown metric" rather than a
        silently absent column.
        """
        st = statements_for(self.profile, self.seed)
        ref = period_ref(period)
        prior = ref.prior_id

        def figure(code: str, which: str | None) -> Decimal | None:
            if which is None:
                return None
            raw = st.amount(which, code)
            return to_money(raw) if raw is not None else None

        def margin(period_id: str | None) -> Decimal | None:
            revenue = figure("revenue", period_id)
            gross = figure("gross_profit", period_id)
            if revenue is None or gross is None or revenue == 0:
                return None
            return quantize(gross / revenue * Decimal(100), 4)

        def days_in(period_id: str) -> Decimal:
            """The period's real length, not an assumed 30.

            A monthly pack computing receivable days on a hard-coded 30 makes February
            look 10% better than January for no reason a reader could ever find. The
            emitter carries real start/end dates; use them.
            """
            p = next(p for p in st.periods if p.id == period_id)
            return Decimal((p.end - p.start).days + 1)

        def receivable_days(period_id: str | None) -> Decimal | None:
            if period_id is None:
                return None
            revenue = figure("revenue", period_id)
            ar = figure("accounts_receivable", period_id)
            if revenue is None or ar is None or revenue == 0:
                return None
            return quantize(ar / revenue * days_in(period_id), 2)

        world = world_for(period, seed=self.seed)
        prior_world = world_for(prior, seed=self.seed) if prior else None

        metrics: list[tuple[str, str, Decimal | None, Decimal | None]] = [
            ("revenue", "Revenue", figure("revenue", period), figure("revenue", prior)),
            ("gross_profit", "Gross profit", figure("gross_profit", period), figure("gross_profit", prior)),
            ("gross_margin_pct", "Gross margin", margin(period), margin(prior)),
            ("operating_profit", "Operating profit", figure("operating_profit", period), figure("operating_profit", prior)),
            ("net_income", "Net income", figure("net_income", period), figure("net_income", prior)),
            ("cash", "Cash", figure("cash", period), figure("cash", prior)),
            ("accounts_receivable", "Accounts receivable", figure("accounts_receivable", period), figure("accounts_receivable", prior)),
            ("accounts_payable", "Accounts payable", figure("accounts_payable", period), figure("accounts_payable", prior)),
            ("total_assets", "Total assets", figure("total_assets", period), figure("total_assets", prior)),
            ("total_equity", "Total equity", figure("total_equity", period), figure("total_equity", prior)),
            ("receivable_days", "Receivable days", receivable_days(period), receivable_days(prior)),
            (
                "exception_count",
                "Payables exceptions",
                Decimal(len(world.ground_truth.exceptions)),
                Decimal(len(prior_world.ground_truth.exceptions)) if prior_world else None,
            ),
        ]

        rows: list[dict[str, Value]] = [
            {
                "metric": key,
                "label": label,
                "value": value,
                "prior_value": prior_value,
                "delta": (value - prior_value) if value is not None and prior_value is not None else None,
                "delta_pct": pct_change(value, prior_value),
            }
            for key, label, value, prior_value in metrics
        ]
        return frame_from_dicts(
            rows,
            source=self.name,
            dataset="period_metrics",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period, "prior_period": prior},
        )

    # -- operational detail --------------------------------------------------

    def _exceptions(self, period: str) -> Frame:
        world = world_for(period, seed=self.seed)
        txn_by_id = {t.id: t for t in world.transactions}
        rows: list[dict[str, Value]] = []
        for exc in world.ground_truth.exceptions:
            severity, rank = _EXCEPTION_SEVERITY.get(str(exc.root_cause_type), ("medium", 2))
            txn = txn_by_id.get(exc.txn_id)
            rows.append(
                {
                    "txn_id": exc.txn_id,
                    "rule_id": str(exc.root_cause_type),
                    "label": str(exc.root_cause_type).replace("_", " ").capitalize(),
                    "message": exc.explanation,
                    "severity": severity,
                    "severity_rank": rank,
                    "amount": to_money(txn.amount) if txn else None,
                    "counterparty": txn.counterparty_raw if txn else None,
                    "evidence": ", ".join(exc.evidence_ids) or None,
                }
            )
        return frame_from_dicts(
            rows,
            columns=(
                "txn_id", "rule_id", "label", "message", "severity",
                "severity_rank", "amount", "counterparty", "evidence",
            ),
            source=self.name,
            dataset="exceptions",
            schema_version=self.SCHEMA_VERSION,
            meta={"period": period},
        )

    def _invoices(self, period: str) -> Frame:
        world = world_for(period, seed=self.seed)
        cp = {c.id: c for c in world.counterparties}
        rows: list[dict[str, Value]] = [
            {
                "invoice_id": inv.id,
                "number": inv.number,
                "counterparty": cp[inv.counterparty_id].canonical_name,
                "issue_date": inv.issue_date.isoformat(),
                "due_date": inv.due_date.isoformat(),
                "amount": to_money(inv.amount),
                "currency": inv.currency,
                "status": str(inv.status),
            }
            for inv in world.invoices
        ]
        return frame_from_dicts(
            rows, source=self.name, dataset="invoices",
            schema_version=self.SCHEMA_VERSION, meta={"period": period},
        )

    def _gl_expense_lines(self, period: str) -> Frame:
        world = world_for(period, seed=self.seed)
        accounts = {a.code: a for a in world.accounts}
        rows: list[dict[str, Value]] = []
        for entry in world.gl_entries:
            account = accounts.get(entry.account_code)
            if account is None or account.type != "expense":
                continue
            rows.append(
                {
                    "account_code": entry.account_code,
                    "account_name": account.name,
                    "date": entry.date.isoformat(),
                    "amount": to_money(entry.amount),
                    "invoice_id": entry.invoice_id,
                    "memo": entry.memo,
                }
            )
        return frame_from_dicts(
            rows,
            columns=("account_code", "account_name", "date", "amount", "invoice_id", "memo"),
            source=self.name, dataset="gl_expense_lines",
            schema_version=self.SCHEMA_VERSION, meta={"period": period},
        )

    # -- dispatch ------------------------------------------------------------

    def fetch(self, dataset: str, period: str) -> Frame:
        if dataset == "pnl_lines":
            return self._statement_frame("pnl", _PNL_LINES, period)
        if dataset == "bs_lines":
            return self._statement_frame("bs", _BS_LINES, period)
        if dataset == "cf_lines":
            return self._statement_frame("cf", _CF_LINES, period)
        if dataset == "period_metrics":
            return self._metrics(period)
        if dataset == "exceptions":
            return self._exceptions(period)
        if dataset == "invoices":
            return self._invoices(period)
        if dataset == "gl_expense_lines":
            return self._gl_expense_lines(period)
        raise KeyError(f"ledgerfab publishes no dataset {dataset!r}")
