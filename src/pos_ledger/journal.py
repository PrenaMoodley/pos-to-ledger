"""Turn one business day of POS data into a balanced, double-entry journal.

    Dr  tender clearing accounts (cash, card, room charge -> guest ledger)
    Cr  sales by revenue centre and major group, excluding VAT
    Cr  VAT output (15% standard rate, prices are VAT-inclusive)
    Dr/Cr  cash over/short for small differences between tenders and sales

Amounts are Decimal and rounded to cents once per line. The journal must
balance to the cent or it is not produced.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .pos_export import SalesLine, TenderLine

CENT = Decimal("0.01")
VAT_FRACTION = Decimal(15) / Decimal(115)  # VAT inside a VAT-inclusive SA price


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class JournalLine:
    posting_date: date
    document_no: str
    account: str
    description: str
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")

    @property
    def amount(self) -> Decimal:
        """Signed amount as most ERPs expect it: debit positive, credit negative."""
        return self.debit - self.credit


@dataclass(frozen=True)
class AccountMap:
    sales: dict[str, str]  # "Revenue centre|Major group" -> GL account
    tenders: dict[str, str]  # tender name -> GL account
    vat_output: str
    over_short: str
    over_short_limit: Decimal  # larger differences stop the journal

    @classmethod
    def load(cls, path: Path) -> AccountMap:
        data = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            sales=data["sales"],
            tenders=data["tenders"],
            vat_output=data["vat_output"],
            over_short=data["over_short"],
            over_short_limit=Decimal(data["over_short_limit"]),
        )


class JournalError(ValueError):
    pass


def build_journal(
    day: date, sales: list[SalesLine], tenders: list[TenderLine], accounts: AccountMap
) -> list[JournalLine]:
    sales = [s for s in sales if s.business_date == day]
    tenders = [t for t in tenders if t.business_date == day]
    if not sales and not tenders:
        raise JournalError(f"No POS data for {day}")
    doc = f"POS-{day:%Y%m%d}"
    lines: list[JournalLine] = []

    # Net sales (after discounts) per GL account, VAT-inclusive.
    net_by_account: dict[str, Decimal] = defaultdict(Decimal)
    unmapped = set()
    for s in sales:
        key = f"{s.revenue_centre}|{s.major_group}"
        account = accounts.sales.get(key)
        if account is None:
            unmapped.add(key)
            continue
        net_by_account[account] += s.gross_incl_vat - s.discounts_incl_vat
    for t in tenders:
        if t.tender not in accounts.tenders:
            unmapped.add(f"tender {t.tender}")
    if unmapped:
        raise JournalError("No GL account mapped for: " + ", ".join(sorted(unmapped)))

    total_incl = sum(net_by_account.values(), Decimal("0"))
    total_vat = cents(total_incl * VAT_FRACTION)

    # Split VAT out of each sales line, then put the rounding remainder on the
    # largest line so the VAT total is exactly 15/115 of total sales.
    excl_by_account = {a: cents(v - v * VAT_FRACTION) for a, v in net_by_account.items()}
    remainder = (total_incl - total_vat) - sum(excl_by_account.values(), Decimal("0"))
    if excl_by_account and remainder:
        largest = max(excl_by_account, key=excl_by_account.get)
        excl_by_account[largest] += remainder

    for account in sorted(excl_by_account):
        lines.append(JournalLine(day, doc, account, "POS sales excl. VAT", credit=excl_by_account[account]))
    lines.append(JournalLine(day, doc, accounts.vat_output, "Output VAT 15%", credit=total_vat))

    tender_totals: dict[str, Decimal] = defaultdict(Decimal)
    for t in tenders:
        tender_totals[accounts.tenders[t.tender]] += t.amount
    for account in sorted(tender_totals):
        lines.append(JournalLine(day, doc, account, "POS tenders", debit=cents(tender_totals[account])))

    debits = sum((l.debit for l in lines), Decimal("0"))
    credits = sum((l.credit for l in lines), Decimal("0"))
    difference = debits - credits  # positive: more tendered than sold (over)
    if abs(difference) > accounts.over_short_limit:
        raise JournalError(
            f"{day}: tenders R{debits} vs sales R{credits} differ by R{difference}, "
            f"more than the R{accounts.over_short_limit} over/short limit. Check the POS close."
        )
    if difference > 0:
        lines.append(JournalLine(day, doc, accounts.over_short, "Cash over", credit=difference))
    elif difference < 0:
        lines.append(JournalLine(day, doc, accounts.over_short, "Cash short", debit=-difference))

    assert_balanced(lines)
    return lines


def assert_balanced(lines: list[JournalLine]) -> None:
    debits = sum((l.debit for l in lines), Decimal("0"))
    credits = sum((l.credit for l in lines), Decimal("0"))
    if debits != credits:
        raise JournalError(f"Journal does not balance: Dr R{debits} / Cr R{credits}")
