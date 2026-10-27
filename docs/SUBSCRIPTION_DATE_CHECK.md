# Enrollment, subscription and payment dates — 27 October 2026

The monthly engine anchors each period to `monthly_accounts.start_date`.
`received_on` records cash and determines the reporting/filter period; it never
moves subscription months. Selected intake dates default to today and can be
back-entered through the existing bilingual manual date control. Invalid dates
are rejected before any child, family, account or receipt is created.

## One official student editor

The student file's existing protected edit window includes the enrollment/start
date for identities with students.edit and accounts.edit. It uses the same save,
discard warning, success notice and navigation as other student fields. The
previous bulk-adoption proposal and its API/UI were removed. No batch matching,
extra review screen, special source-navigation button or startup rewrite remains.
Legacy pupils are corrected individually when necessary; opening a file does not
rewrite its dates or debt.

The server locks the student and account in the student-edit transaction, checks
both the account revision and its financial audit revision, then corrects the
anchor and period schedule. Existing period numbers, IDs, stored prices, cash,
receipt dates and frozen receipt distributions remain intact. Unissued due months
use the current tariff, as in the existing engine. The same helper is used by the
existing account source editor so a funded account no longer requires cancelling
valid receipts merely to correct its start date. Accounts closed by archive cannot
be edited here; a paused account cannot start after its departure date.

The start-date correction shares one transaction with any student/family edits.
Invalid dates, stale student/account/payment state or missing permissions roll the
whole change back. A monthly audit entry invalidates earlier payment previews.
The existing change log records old/new values, operator, reason and timestamp;
there is no new change-log screen. Receipt PDFs retain their original frozen
period descriptions. No new schema column or migration is required.

The date control becomes a hidden canonical input when enhanced, so the editor
stores its original value in form metadata rather than relying on defaultValue.
An unchanged start is omitted from ordinary student edits. This permits normal
student/parent edits without unnecessary account permissions or financial writes.

## Integrated student account view

The existing account panel has four cards in the site's original two-column style:
total paid, current balance, fully paid months and uninterrupted paid-through date.
The old standalone facts grid, explanatory caption and extra management button
were removed. A closed-by-default details section contains the first incomplete
month/due date, partial payment remainder and registration/gilet settlements.
Remissions are separate from cash. The ordinary receipt and payment actions remain
in the same panel. The enrollment date appears among the normal child details.
Account data remains behind payments.view, using actual stored-period projections.

Marked intake/correction dates are used for enrollment-period reporting. Unmarked
legacy files retain their earliest stored registration/file creation source until
corrected explicitly. The derived date is excluded from the raw student revision,
so it does not invalidate unrelated student/family edits by itself.

## Receipt dates and verification

Opening a receipt exposes its existing protected edit window, including collection
date, amount, reason and confirmation. A correction produces a linked receipt
version and an audit trail; the prior version is retained. Tests cover a date-only
receipt correction after correcting enrollment: same total cash, same subscription
anchor, same stored month schedule, new collection/report date, and rejection of a
stale original receipt window. A date-only correction for the same amount also
remains available after exemption or archive, without receiving new money or
changing that status. Amount changes on exempt accounts retain their existing
restriction. This task did not change the receipt allocation
algorithm or replace its audit/versioning service.

The original engine checks cover 10 August enrollment with six monthly fees paid
on 15 August or 15 November, month-end clamping from 31 January in a leap year,
and independent teacher hire, salary-month and disbursement dates. Teacher hire
is not a promise of automatic daily pro-rating. The disposable Pages adapter
uses simplified current tariffs and is not a substitute for stored-price finance.

Current validation includes PostgreSQL/HTTP checks for atomic intake/date edits,
revision guards, permission boundaries, preserved receipts/prices/snapshots,
period report dates, student/family edits and stale payment previews. Two updated
Arabic/French browser journeys passed for the integrated cards, official editor,
discard/save, receipt date correction, mobile layout and dark mode. A real
TLS/PostgreSQL browser journey passed for persisted enrollment edits, change-log
old/new values and receipt date correction. Translation completeness is checked.
These are targeted checks; a fresh pinned dependency install and full release CI
remain required before publication. Local Streamlit/Pillow versions differ from
the pinned release set.

All changes are local. No production data access, GitHub upload, merge or deployment.
