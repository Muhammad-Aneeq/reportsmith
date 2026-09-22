"""The reporting entity and its chart of accounts."""

from __future__ import annotations

from ledgerfab.models import Account, Company
from ledgerfab.profiles import Profile
from ledgerfab.rng import Rng

_COMPANY_NAMES = [
    "Northwind Trading Ltd",
    "Harbourline Logistics Ltd",
    "Beacon & Vale Ltd",
    "Coldharbour Manufacturing Ltd",
    "Stonebridge Services Ltd",
    "Meridian Foods Ltd",
]

# A deliberately small chart — enough to look like books, small enough to reason about.
# Two bank accounts, not one: ``get_bank_transactions(account=...)`` is in spec 02
# F1, and with a single bank account that parameter would be decoration and its
# contract test vacuous (PLAN.md D15).
_ACCOUNTS: list[tuple[str, str, str]] = [
    ("1000", "Cash at bank — current", "asset"),
    ("1010", "Cash at bank — deposit", "asset"),
    ("1100", "Accounts receivable", "asset"),
    ("1200", "Prepayments", "asset"),
    ("2000", "Accounts payable", "liability"),
    ("2100", "Accruals", "liability"),
    ("2200", "VAT control", "liability"),
    ("3000", "Share capital", "equity"),
    ("4000", "Revenue", "income"),
    ("5000", "Cost of sales", "expense"),
    ("6000", "Professional fees", "expense"),
    ("6100", "Software subscriptions", "expense"),
    ("6200", "Rent", "expense"),
    ("6300", "Utilities", "expense"),
]

# Expense accounts a purchase invoice can land in.
EXPENSE_CODES = ["5000", "6000", "6100", "6200", "6300"]

# The bank accounts a payment can leave from. Large payments go out of the
# deposit/treasury account — a deterministic rule, so account assignment costs no
# random draw and cannot shift any other generator's stream.
CURRENT_ACCOUNT = "1000"
DEPOSIT_ACCOUNT = "1010"
BANK_ACCOUNT_CODES = [CURRENT_ACCOUNT, DEPOSIT_ACCOUNT]
DEPOSIT_ACCOUNT_THRESHOLD = 10_000.0

# Accounts payable — the credit side of every purchase accrual.
ACCOUNTS_PAYABLE = "2000"


def bank_account_for(amount: float) -> str:
    """Which bank account a payment of this size would leave from."""
    return DEPOSIT_ACCOUNT if amount >= DEPOSIT_ACCOUNT_THRESHOLD else CURRENT_ACCOUNT


def generate_company(rng: Rng, profile: Profile) -> Company:
    return Company(
        id="CO-001",
        name=rng.choice(_COMPANY_NAMES),
        base_currency="GBP",
        period_start=profile.period_start,
        period_end=profile.period_end,
    )


def generate_accounts() -> list[Account]:
    """The chart is fixed — messiness belongs in the transactions, not the CoA."""
    return [Account(code=c, name=n, type=t) for c, n, t in _ACCOUNTS]
