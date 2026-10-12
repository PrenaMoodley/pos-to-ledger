"""pos-ledger: POS daily export -> balanced journal -> trial balance, VAT, Business Central.

pos-ledger build 2026-10-11 --xlsx out/2026-10-11.xlsx
pos-ledger post 2026-10-11              # dry run: shows what would be sent
pos-ledger post 2026-10-11 --send       # adds lines to the BC journal batch
pos-ledger post 2026-10-11 --send --post
"""

from __future__ import annotations

import argparse
import os
from datetime import date
from decimal import Decimal
from pathlib import Path

from .business_central import BCConfig, BusinessCentral
from .journal import AccountMap, build_journal
from .pos_export import read_sales, read_tenders
from .reports import load_chart, trial_balance, vat_summary, write_workbook

ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pos-ledger")
    p.add_argument("action", choices=["build", "post"])
    p.add_argument("day", type=date.fromisoformat)
    p.add_argument("--data", type=Path, default=ROOT / "sample_data")
    p.add_argument("--config", type=Path, default=ROOT / "config")
    p.add_argument("--xlsx", type=Path)
    p.add_argument("--send", action="store_true", help="Actually send to Business Central.")
    p.add_argument("--post", action="store_true", help="Also post the journal batch after adding lines.")
    a = p.parse_args(argv)

    accounts = AccountMap.load(a.config / "accounts.json")
    chart = load_chart(a.config / "chart_of_accounts.csv")
    lines = build_journal(
        a.day, read_sales(a.data / "sales.csv"), read_tenders(a.data / "tenders.csv"), accounts
    )

    for l in lines:
        side = f"Dr {l.debit:>10}" if l.debit else f"Cr {l.credit:>10}"
        print(f"{l.document_no}  {l.account}  {chart[l.account].name:<28} {side}")
    total = sum((l.debit for l in lines), Decimal("0"))
    print(f"Balanced: Dr = Cr = R{total}")

    if a.action == "build":
        if a.xlsx:
            tb = trial_balance(lines, chart)
            vat = vat_summary(lines, accounts.vat_output, set(accounts.sales.values()))
            print(f"Workbook: {write_workbook(lines, tb, vat, a.xlsx)}")
        return 0

    if not a.send:
        print("Dry run. Add --send to add these lines to Business Central.")
        return 0
    bc = BusinessCentral(
        BCConfig(
            tenant_id=os.environ["BC_TENANT_ID"],
            client_id=os.environ["BC_CLIENT_ID"],
            client_secret=os.environ["BC_CLIENT_SECRET"],
            environment=os.environ.get("BC_ENVIRONMENT", "Sandbox"),
            company_id=os.environ["BC_COMPANY_ID"],
            journal_name=os.environ.get("BC_JOURNAL", "POS"),
        )
    )
    print(f"Sent {bc.add_lines(lines, post=a.post)} lines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
