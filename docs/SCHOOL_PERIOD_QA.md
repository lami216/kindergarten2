# School period reports and in-file family editing — 25 October 2026

Local review only. Based on main `448a56063df4ea7b2e70f2f6913f5cef461d3689`,
including the dependency/security repairs merged after PR #10. No production
database, deployment or GitHub mutation is part of this change. Schema stays 16.

- Extends the existing period report rather than adding a second report UI.
  Cash calculations remain unchanged. Enrollment and attendance reads share the
  cash report's read-only repeatable-read transaction and export revision.
- New pupils use their explicitly selected intake date for accounts marked by
  the 27 October intake/date-correction workflow. Unmarked legacy accounts use their
  earliest stored registration date, falling back to file creation. Birth and
  payment dates are never substitutes. See SUBSCRIPTION_DATE_CHECK.md.
  Unknown dates are counted separately, not invented. Archived pupils remain in
  historical counts; current file state and current class are explicitly labelled.
- Attendance uses uncancelled student-day records inside inclusive period bounds.
  Present, absent and excused counts are separate. Absence percentage includes
  excused absence. Missing days are excluded, and an empty denominator shows no
  rate, not zero. Global percentages use weighted record counts, not the average
  of child percentages. Duplicate names retain distinct student identifiers.
- Enrollment counts require report access; pupil identities require student view.
  Attendance identities and rates require student attendance view, matching the
  existing attendance service. Restricted sheets are absent from XLSX exports.
- Student and attendance details have literal search, paging, mobile cards,
  Arabic/French labels, RTL/LTR and print-specific full tables. XLSX adds separate
  enrollment and attendance sheets with text-safe cells. School changes invalidate
  an export based on an older report snapshot.
- The official student edit dialog now includes the family's four contact fields
  for users with both student-edit and parent-edit rights. Unchanged parent fields
  are omitted from the payload. Existing server validation, family revision locks,
  atomic rollback and audit apply. Shared-family corrections update siblings;
  unrelated equally named families are never matched. Unsaved edits retain the
  existing explicit discard/stay confirmation.
- Preview family operations mirror revision, permissions, pair validation and
  sibling updates. Preview data remains disposable and never enters production.

Validation: 26 API/report/HTTP/localization tests passed in the combined run;
one old Streamlit cookie compatibility test timed out under concurrent load and
passed when rerun alone unchanged (27 selected checks passed across these runs).
Four bilingual browser journeys cover the new report/modal workflows, layouts,
printing, actual XLSX downloads, shared siblings, unsaved changes and hidden fields.
The existing 12 report browser scenarios still pass. A separate actual TLS and
PostgreSQL browser journey verified in-modal family persistence for both siblings,
period attendance totals and a real XLSX download. Windows socket reset messages
occurred during QA server shutdown after successful assertions; exit status was 0.
The local environment still has the earlier Streamlit/Pillow versions; a fresh
install of main's pinned runtime and complete CI remain required before release.

## Organization revision after local review

- A single period selector governs four permission-aware sections: overview,
  cash movements, new pupils, and attendance. Opening reports loads the default
  period. The overview contains compact indicators rather than detail tables.
  Custom date entry is revealed explicitly; secondary report types remain
  available in the same interface. Search/paging state is separate per list.
- Balance/debt, allocation breakdowns and calculation explanations are disclosed
  on request. Printing names the current section and selected dates and prints
  that section's complete filtered table. Export remains period-wide, with the
  visible cash filter only applied when the cash section is active; a hidden old
  cash query cannot silently restrict an overview/school export.
- Comparison uses the immediately preceding inclusive interval of the same
  duration, including leap-day boundaries. Amount changes are differences, not
  percentage growth from a zero base. Attendance rate differences are percentage
  points and are omitted when either interval has no recorded attendance.
  Prior aggregates share the same repeatable-read snapshot, and a correction
  in the prior interval invalidates an old export. The comparison has its own
  sixth XLSX sheet without disclosing identities.
- Attendance can be filtered to pupils with any absence, unexcused absence or
  excused absence. Filtering changes detail rows, not the period's headline rate.
  The overview's absent-pupil card opens the matching filter. Tabs support arrow,
  Home and End keyboard navigation, preserve the period, and follow RTL/LTR.
- Validation: 13 unique targeted API/report checks passed across the combined
  run and comparison recheck. One new assertion was corrected: an earlier cash
  correction must change opening/closing balances even when current-period
  movements stay unchanged. Four updated bilingual browser journeys pass,
  including section organization, absence filters, hidden-filter export safety,
  keyboard tabs, print dates and stable mobile screenshots after sidebar
  transitions. The existing 12 financial browser scenarios and the actual
  TLS/PostgreSQL school/modal/export journey also pass.
