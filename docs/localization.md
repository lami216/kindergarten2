# Arabic and French

The production UI and portable Pages preview use the same renderers and the same
`locales/messages.json` catalog. No translation service, JavaScript package install,
database migration or duplicated French application is required.

Add future text under a meaningful key, for example:

```json
"student.save": {"ar": "حفظ الطالب", "fr": "Enregistrer l’élève"}
```

Use `I18N.tr('student.save')` in JavaScript. For an interpolated message use the
same placeholders in both languages and pass an object as the second argument.
Escape user-supplied parameters with the existing `esc()` helper when inserting
the message into HTML. Use `textContent` for plain DOM text. Static HTML can use
`data-i18n` or `data-i18n-placeholder`, `data-i18n-alt`, `data-i18n-aria-label`.

Legacy system metadata and validation messages are matched to their Arabic source
via `sourceLabel()` / Python `localization.label()` and `message()`. Add both
translations to the catalog for every new server label or error. New features
should prefer semantic keys. Unknown server errors have a safe French fallback.

Never translate names, class names, notes, reasons, identifiers, submitted option
values or raw backup records. Use `enumLabel()` only for trusted system enums.
Canonical values remain unchanged in storage. Amounts remain in old ouguiyas
(MRO); localization does not perform a currency conversion.

The language selector belongs only to the logged-out login card. The preference
is stored on this browser, applied on page load, and retained after logout. A
selection reloads the login page before credentials are entered. No authenticated
language-switch control exists. Local-storage denial falls back to Arabic.

`html[lang]` and `html[dir]` control the layout; use logical CSS properties
(`margin-inline-start`, `text-align:start`) for new features. Do not mirror images.
The API receives the selected language through a header or same-origin cookie.
The Python context is request-local, including PDF/Excel generation, never a
mutable global shared between users. Backups keep their canonical schema/data.

After editing the catalog, regenerate its public bundle with
`python scripts/check_translations.py --write`. The generated
`docs/locales/messages.js` supports the raw source preview; edit only the JSON
source. CI rejects a stale generated bundle.

Run `python scripts/check_translations.py`, `pytest tests/test_localization.py`
and `python -m tests.browser_french`. CI also runs the Arabic regression journeys
and the French real-service browser journey against a disposable database.

Date fields share `docs/date-entry.js` and `docs/date-entry.css`. Render new fields
as `input type="date"` (or `month` for a salary month), with their normal name,
ISO value, required flag and min/max bounds. The shared component supplies the
localized day, month list and year suffix automatically, including in dialogs.
Keep reading/writing the original input's ISO value; do not store translated
month names or a two-digit year. Its input event invalidates stale drafts;
change commits after focus leaves the complete group, so attendance filters
cannot reload between typing the day and the year. Existing historical years
retain their century. Only dates that the user actually changes are rewritten.
`tests.date_entry_helpers.fill_field` enters these fields through their visible
controls; `python -m tests.browser_date_entry` covers the shared behavior.
