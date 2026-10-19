# French interface verification — 19 October 2026

Status: implemented and reviewed locally, based on merged main `c65dedd`.
Local verification is complete; GitHub CI is the merge gate. Production server
rollout is separate and has not been performed from this workspace.
No database migration or currency conversion is introduced.

## Verified behavior

- Arabic remains RTL; French uses LTR navigation, tables, forms and dialogs.
- Language selection is available only on the logged-out login card. The chosen
  language survives reload/logout. Authenticated clicks cannot change it.
- School vocabulary covers students, classes, teachers, attendance, payments,
  receipts, expenses, permissions, history, fees, payroll, reports and exports.
- Stored names, class names, observations and reasons remain unchanged, including
  names identical to a translated system label. Submitted gender/status values
  remain canonical. Exempt profiles also display translated status labels.
- The same authorization checks and Python/PostgreSQL services handle both
  languages. Language is request-local, with concurrent-context coverage.
- Receipt PDF uses French/LTR presentation, old-ouguiya amounts (MRO), the exact
  historical allocation snapshots and cancellation state. Long reasons wrap.
- Excel translates headings and trusted status enums, preserves user data and
  formula-injection protection. Raw backup tables/data remain canonical.

## Results

- Full PostgreSQL suite on a new isolated test schema: **273 passed + 11 subtests**.
- Targeted localization suite after final error-interpolation correction: **6 passed**.
- French browser journey: 13 screen/form captures; desktop/mobile, dark mode,
  attendance approval, unselected defaults, language persistence and data isolation.
- French real-service browser journey: login errors, registration, profile edits,
  payment receipt/PDF, invalid expense correction and recovery, teacher creation,
  salary-net preview/save, report Excel, account creation with `0000`, restricted
  worker attendance, logout and restoration of Arabic/RTL.
- Arabic regression journeys passed: operator actions, record editing/cancellation,
  receipt search, manager accounts, student photos/profiles, teachers, and focused
  attendance with pagination, retries, unsaved changes and manual statuses.
- No JavaScript page errors were reported by the language/people journeys.

The first full suite used a previously populated disposable database. One legacy
family-selection test selected an older fixture with an identical display label.
The complete suite was then repeated on a new schema and passed. Browser-test
assertions were aligned to the actual server wording and explicit role grants;
the final real-service journey passed. Local Windows TLS transport shutdown logs
were observed on browser exit; they did not represent failed application actions.

The public preview uses synthetic data. Production server rollout is separate.
Translation maintenance is described in [localization.md](localization.md).

GitHub CI follow-up: the pinned pypdf 6.1.3 reader dropped Latin text when a
mixed Arabic/French name changed direction inside one PDF text object. French
receipt lines now keep visual positions while emitting separate direction runs;
PDF amounts use a font-supported regular space. The six localization tests pass
with both pypdf 6.1.3 and 6.20.1, including names, period snapshots, cancellation
and complete amount extraction.

The real-service CI journey also exposed a lookup race: a delayed teacher-options
response rebuilt the report form and reset the selected report. Lookup completion
now refreshes only teacher options, preserving report type, dates and selected
teacher. The French browser suite holds and releases this response deliberately
and verifies the selected report still executes.
