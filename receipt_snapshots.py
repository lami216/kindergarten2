"""Append-only descriptions of allocation targets, independent of billing edits."""


def migrate(cursor):
    # One atomic DDL/backfill batch. Creating the allocation trigger locks out
    # concurrent inserts until the immutable store and legacy backfill exist.
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS monthly_allocation_snapshots (
            allocation_id BIGINT PRIMARY KEY REFERENCES monthly_allocations(allocation_id) ON DELETE RESTRICT,
            fee_kind TEXT, period_no INTEGER, starts DATE, ends DATE,
            stored_fee_price BIGINT NOT NULL,
            source TEXT NOT NULL CHECK(source IN ('issued','account_audit','legacy_at_migration')),
            captured_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK ((fee_kind IS NOT NULL AND period_no IS NULL AND starts IS NULL AND ends IS NULL)
                OR (fee_kind IS NULL AND period_no IS NOT NULL AND starts IS NOT NULL AND ends>starts))
        );
        CREATE OR REPLACE FUNCTION monthly_allocation_snapshot_capture() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.fee_id IS NOT NULL THEN
                INSERT INTO monthly_allocation_snapshots(allocation_id,fee_kind,stored_fee_price,source)
                    SELECT NEW.allocation_id,kind,price,'issued' FROM monthly_fees WHERE fee_id=NEW.fee_id;
            ELSE
                INSERT INTO monthly_allocation_snapshots(allocation_id,period_no,starts,ends,stored_fee_price,source)
                    SELECT NEW.allocation_id,period_no,starts,ends,price,'issued'
                    FROM monthly_periods WHERE period_id=NEW.period_id;
            END IF;
            RETURN NEW;
        END; $$;
        CREATE OR REPLACE FUNCTION monthly_allocation_snapshot_immutable() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Receipt allocation descriptions are immutable'; END; $$;
        DROP TRIGGER IF EXISTS monthly_allocation_snapshot_guard ON monthly_allocation_snapshots;
        CREATE TRIGGER monthly_allocation_snapshot_guard BEFORE UPDATE OR DELETE
            ON monthly_allocation_snapshots FOR EACH ROW EXECUTE FUNCTION monthly_allocation_snapshot_immutable();
        DROP TRIGGER IF EXISTS monthly_allocation_snapshot_write ON monthly_allocations;
        CREATE TRIGGER monthly_allocation_snapshot_write AFTER INSERT ON monthly_allocations
            FOR EACH ROW EXECUTE FUNCTION monthly_allocation_snapshot_capture();

        -- Recover the anchor at issuance from the first later anchor correction.
        -- If that evidence does not exist, freeze the available legacy values
        -- and retain their provenance; do not claim an invented earlier history.
        INSERT INTO monthly_allocation_snapshots
            (allocation_id,fee_kind,period_no,starts,ends,stored_fee_price,source)
        SELECT a.allocation_id,f.kind,p.period_no,
            CASE WHEN h.anchor IS NOT NULL THEN (h.anchor+make_interval(months=>p.period_no))::date ELSE p.starts END,
            CASE WHEN h.anchor IS NOT NULL THEN (h.anchor+make_interval(months=>p.period_no+1))::date ELSE p.ends END,
            COALESCE(f.price,p.price),
            CASE WHEN h.anchor IS NOT NULL THEN 'account_audit' ELSE 'legacy_at_migration' END
        FROM monthly_allocations a JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
        LEFT JOIN monthly_fees f ON f.fee_id=a.fee_id
        LEFT JOIN monthly_periods p ON p.period_id=a.period_id
        LEFT JOIN LATERAL (
            SELECT (audit.before_state->>'start_date')::date AS anchor
            FROM monthly_audit audit WHERE audit.student_id=r.student_id
                AND audit.action='account_input_corrected' AND audit.happened_at>r.created_at
                AND audit.before_state->>'start_date' IS NOT NULL
                AND audit.before_state->>'start_date' IS DISTINCT FROM audit.after_state->>'start_date'
            ORDER BY audit.happened_at,audit.audit_id LIMIT 1
        ) h ON p.period_id IS NOT NULL
        WHERE NOT EXISTS(SELECT 1 FROM monthly_allocation_snapshots s WHERE s.allocation_id=a.allocation_id)
        ON CONFLICT DO NOTHING;
        INSERT INTO finance_schema_versions(version) VALUES(9) ON CONFLICT DO NOTHING;
    """)
