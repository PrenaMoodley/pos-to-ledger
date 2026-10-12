"""Read a POS daily export.

The layout is modelled on a hospitality POS "daily sales by revenue centre" and
"tenders" report (Simphony-style), exported as CSV. Column names are configurable
in one place because every site's export template differs slightly.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path


@dataclass(frozen=True)
class SalesLine:
    business_date: date
    revenue_centre: str  # e.g. "Restaurant", "Pool Bar"
    major_group: str  # e.g. "Food", "Beverage"
    gross_incl_vat: Decimal  # before discounts
    discounts_incl_vat: Decimal  # positive number


@dataclass(frozen=True)
class TenderLine:
    business_date: date
    tender: str  # e.g. "Cash", "Card", "Room Charge"
    amount: Decimal


class ExportError(ValueError):
    pass


def _money(raw: str, where: str) -> Decimal:
    try:
        return Decimal(raw.replace(",", "").strip())
    except InvalidOperation as e:
        raise ExportError(f"{where}: '{raw}' is not an amount") from e


def _date(raw: str, where: str) -> date:
    try:
        return date.fromisoformat(raw.strip())
    except ValueError as e:
        raise ExportError(f"{where}: '{raw}' is not a YYYY-MM-DD date") from e


def read_sales(path: Path) -> list[SalesLine]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    lines = []
    for n, row in enumerate(rows, start=2):
        where = f"{path.name} row {n}"
        lines.append(
            SalesLine(
                business_date=_date(row["business_date"], where),
                revenue_centre=row["revenue_centre"].strip(),
                major_group=row["major_group"].strip(),
                gross_incl_vat=_money(row["gross_sales"], where),
                discounts_incl_vat=_money(row.get("discounts") or "0", where),
            )
        )
    return lines


def read_tenders(path: Path) -> list[TenderLine]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    return [
        TenderLine(
            business_date=_date(row["business_date"], f"{path.name} row {n}"),
            tender=row["tender"].strip(),
            amount=_money(row["amount"], f"{path.name} row {n}"),
        )
        for n, row in enumerate(rows, start=2)
    ]
