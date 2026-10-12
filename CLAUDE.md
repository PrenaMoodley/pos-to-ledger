# pos-to-ledger

POS daily export -> balanced journal -> trial balance, VAT summary, Excel, and
Business Central journal lines.

## Commands

- Install: `pip install -e ".[dev]"`
- Test: `python -m pytest -q` (Business Central is mocked; no credentials needed)
- Lint: `python -m ruff check . && python -m ruff format --check .`
- Try it: `pos-ledger build 2026-10-11`

## Rules

- Money is `Decimal`, rounded to cents once per journal line. Never `float`,
  except at the moment a value is serialised for the BC API.
- A journal that doesn't balance to the cent must raise, never be "fixed" with a plug.
- VAT is 15/115 of VAT-inclusive totals. Calculate on the total, then allocate.
- Unmapped outlets or tenders raise with the exact names, so finance can map them.
- `post` is a dry run unless `--send` is given. Tests must never call a real tenant.
- Posting must stay idempotent: check the document number before adding lines.
- Chart of accounts, mapping and sample data are fictional.
