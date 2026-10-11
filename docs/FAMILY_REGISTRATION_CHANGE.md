# Child and parent registration - first change

Scope: Only the Students and Parents pages, additive PostgreSQL migration,
and the supplied sidebar/night-mode patch. Annual enrolment and tuition remain
in the existing Registration page.

## Data migration

Run existing db.init_db on startup. The migration drops only the NOT NULL
constraint on parents.father_name and adds:
- parents.contact_email
- students.address, allergies, general_notes, authorized_pickups JSONB, request_token UUID
- UNIQUE index on students.request_token

No legacy identity, employment, contact, registration or payment column is
deleted or backfilled. IDs are generated as 20-character internal keys
(P/S + 19 random hexadecimal characters) and are not identity numbers.

## Atomic write

db.save_child_with_family opens a separate psycopg2 connection with autocommit
disabled, serializes duplicate request tokens with a transaction-scoped
advisory lock, and commits the family+child together. Any failure rolls both
back and the connection is always closed. Cached read connection remains in
its original autocommit mode. Existing family links never overwrite its data.

## Rollback

Revert application commits if needed; added columns, values and historical
data are intentionally left intact. Rolling back the new columns would destroy
newly collected data and is NOT part of this migration.

## Outside this change / current limitations

- Known legacy issues: CURRENT_YEAR_DEFAULT, STATUS_WITHDRAWN and CASCADE deletion
  of linked children/registrations/payments are not fixed here.
- Receipt, finance, attendance, photo upload and translations are unchanged.
- Screenshot and manual responsive checks at 360/390/430/768/1280 in both
  themes remain required before production approval.
- PostgreSQL service integration must pass on the PR workflow before approval.
