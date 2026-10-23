# Period reports — local review, 22 October 2026

This change has not been uploaded, merged or deployed. The local preview uses
disposable synthetic data. The production implementation uses the existing
PostgreSQL ledger, accounts and permissions; no migration is required.

- Reports have a main navigation entry. Useful secondary reports remain on the
  same page; the administration screen no longer duplicates the reports tab.
- Today, last seven days, current month, previous month and manual date range.
  End dates are inclusive; future or reversed ranges are rejected.
- Cash received, cash paid and net period movement come from exactly the same
  rows displayed in the cash detail. Opening/closing are recorded cash balances,
  not a reconstruction of unrecorded initial funds or accounting profit.
- Income allocation categories partition receipts; prepaid money is a subset
  of monthly payments, never added twice. An unallocated legacy remainder has
  an explicit other-income category.
- Operational expenses use corrected cash events and their actual payment
  dates. Invoice date and cumulative amount paid do not define period outflow.
- Payroll uses cash amounts, excludes explicitly linked duplicate expenses,
  retains cash when only a document is voided, and removes erroneous-entry cash.
- Debts use the selected end date and are outside period cash totals. Historical
  reports reflect the currently corrected ledger, not frozen prior publications.
- The production report uses a read-only REPEATABLE READ snapshot. Summary,
  detail and debt cannot straddle a concurrent write. Schedule materialization
  happens before that snapshot, through the existing service.
- Detail search and category filters have an explicitly labelled subtotal;
  headline cards remain the totals for the whole selected period. Both display
  and export use literal text search, not regular expressions.
- Excel contains summary, filtered cash rows and permitted debt details. It
  preserves numbers and protects user-entered text from becoming formulas.
  The server recomputes and checks a snapshot revision before export, requiring
  refresh if the displayed report has changed.
- Report permission is required by the server. Names and source links require
  the corresponding payment/expense/payroll permissions. Login changes clear
  report state and pending old requests cannot populate the new session.
- Mobile cash rows are compact cards; print shows the report and all filtered
  rows, including rows beyond the on-screen page, without navigation/controls.
- Student roster has no irrelevant date/teacher controls. Debts require only
  an end date; payroll alone shows the teacher filter. The invoice report is
  explicitly labelled as invoices/cumulative payments, not period cash flow.

Validation: 20 API/financial checks passed, followed by 13 period/localization
checks (overlapping subsets). Cases include last-month invoice 1,200, prior
payment 1,000, current payment 200; salary/advance cash; void/cancel;
inclusive endpoints, empty periods, decimal amounts; role redaction; safe XLSX;
and a write inserted between ledger and debt reads to verify snapshot isolation.
The real TLS/PostgreSQL browser journey also passed, including downloaded XLSX.
Arabic/French browser coverage includes delayed responses, incomplete dates,
secondary filters, current report revisions, mobile/dark layouts and print.
Existing French and people/attendance preview journeys passed.
