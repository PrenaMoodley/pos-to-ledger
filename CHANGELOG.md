# Changelog

## [Unreleased]

### Backlog
- Service charge and tips to their own liability accounts.
- Read the POS export directly from the POS reporting API instead of CSV.
- Month-end: reconcile card clearing against the acquirer's settlement report.

## [0.1.0] - 2026-10-13

### Added
- POS export reader (sales by revenue centre and major group, tenders).
- Balanced daily journal with 15% VAT split, rounding allocation and an over/short limit.
- Trial balance, VAT summary and a self-checking Excel workbook.
- Business Central API v2.0 client: OAuth client credentials, idempotent journal lines, optional posting, retries.
- CI on Python 3.11 and 3.13.
