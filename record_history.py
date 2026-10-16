"""Append-only history for user records, including writes from the older pages."""
from psycopg2 import sql

TABLES = {
    'students': 'student_id', 'parents': 'father_id', 'teachers': 'national_id',
    'school_departments': 'department_id', 'student_departments': 'student_id',
    'department_transfers': 'transfer_id', 'classes': 'class_id',
    'academic_years': 'year_id', 'registrations': 'registration_id',
    'assets': 'asset_id', 'expenses': 'expense_id', 'payments': 'receipt_number',
    'monthly_receipts': 'receipt_id', 'teacher_payments': 'payment_id',
    'teacher_advances': 'advance_id', 'monthly_tariffs': 'id',
    'monthly_accounts': 'student_id', 'monthly_waivers': 'waiver_id',
}


def context(cursor, actor, reason='', *, local=True):
    # An authenticated operation owns its identity; legacy actor arguments
    # cannot relabel a worker's transaction as the manager.
    cursor.execute("SELECT NULLIF(current_setting('app.audit_user_id',true),'') AS uid")
    uid=cursor.fetchone()['uid']
    if uid:
        cursor.execute('SELECT username FROM app_users WHERE user_id=%s',(uid,))
        user=cursor.fetchone()
        if user: actor=user['username']
    cursor.execute("SELECT set_config('app.audit_actor',%s,%s),set_config('app.audit_reason',%s,%s)",
                   (str(actor or 'النظام')[:100], local, str(reason or ''), local))


def migrate(conn):
    with conn.cursor() as c:
        c.execute("""
            CREATE TABLE IF NOT EXISTS record_changes (
                change_id BIGSERIAL PRIMARY KEY, table_name TEXT NOT NULL,
                record_key TEXT NOT NULL, old_key TEXT, action TEXT NOT NULL,
                actor TEXT NOT NULL, reason TEXT NOT NULL DEFAULT '',
                happened_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                before_state JSONB, after_state JSONB
            );
            CREATE INDEX IF NOT EXISTS record_changes_lookup
                ON record_changes(table_name,record_key,change_id DESC);
            ALTER TABLE record_changes ADD COLUMN IF NOT EXISTS actor_user_id UUID;
            CREATE INDEX IF NOT EXISTS record_changes_user ON record_changes(actor_user_id,change_id);
            CREATE OR REPLACE FUNCTION record_change_capture() RETURNS trigger AS $$
            DECLARE previous JSONB; following JSONB; verb TEXT; who TEXT; why TEXT;
            BEGIN
                IF TG_OP <> 'INSERT' THEN previous=to_jsonb(OLD); END IF;
                IF TG_OP <> 'DELETE' THEN following=to_jsonb(NEW); END IF;
                IF TG_OP='UPDATE' AND previous=following THEN RETURN NEW; END IF;
                verb=CASE TG_OP WHEN 'INSERT' THEN 'created' WHEN 'DELETE' THEN 'deleted' ELSE 'updated' END;
                IF TG_OP='UPDATE' AND (
                    (following->>'archived_at' IS NOT NULL AND previous->>'archived_at' IS NULL)
                    OR (following->>'cancelled_at' IS NOT NULL AND previous->>'cancelled_at' IS NULL)
                    OR (following->>'state'='cancelled' AND previous->>'state'='active')
                    OR (following->>'record_state'='cancelled' AND previous->>'record_state'='active')) THEN
                    verb='cancelled';
                END IF;
                who=COALESCE(NULLIF(current_setting('app.audit_actor',true),''),
                    following->>'actor',following->>'cancelled_by',following->>'archived_by',
                    following->>'created_by',following->>'changed_by','النظام');
                why=COALESCE(NULLIF(current_setting('app.audit_reason',true),''),
                    following->>'cancel_reason',following->>'reason','');
                IF TG_TABLE_NAME='teachers' THEN
                    IF previous IS NOT NULL THEN previous=previous||jsonb_build_object('display_national_id',COALESCE(previous->>'display_national_id',previous->>'national_id')); END IF;
                    IF following IS NOT NULL THEN following=following||jsonb_build_object('display_national_id',COALESCE(following->>'display_national_id',following->>'national_id')); END IF;
                ELSIF TG_TABLE_NAME='academic_years' THEN
                    IF previous IS NOT NULL THEN previous=previous||jsonb_build_object('display_year_id',COALESCE(previous->>'display_year_id',previous->>'year_id')); END IF;
                    IF following IS NOT NULL THEN following=following||jsonb_build_object('display_year_id',COALESCE(following->>'display_year_id',following->>'year_id')); END IF;
                END IF;
                INSERT INTO record_changes(table_name,record_key,old_key,action,actor,reason,before_state,after_state,actor_user_id)
                VALUES(TG_TABLE_NAME,COALESCE(following->>TG_ARGV[0],previous->>TG_ARGV[0]),
                    previous->>TG_ARGV[0],verb,who,why,previous,following,
                    NULLIF(current_setting('app.audit_user_id',true),'')::uuid);
                IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END; $$ LANGUAGE plpgsql;
            CREATE OR REPLACE FUNCTION record_history_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Change history is append-only'; END; $$ LANGUAGE plpgsql;
            DROP TRIGGER IF EXISTS record_history_guard ON record_changes;
            CREATE TRIGGER record_history_guard BEFORE UPDATE OR DELETE ON record_changes
                FOR EACH ROW EXECUTE FUNCTION record_history_immutable();
        """)
        for table, key in TABLES.items():
            c.execute(sql.SQL('DROP TRIGGER IF EXISTS record_change_audit ON {}').format(sql.Identifier(table)))
            c.execute(sql.SQL('CREATE TRIGGER record_change_audit AFTER INSERT OR UPDATE OR DELETE ON {} '
                             'FOR EACH ROW EXECUTE FUNCTION record_change_capture({})').format(sql.Identifier(table),sql.Literal(key)))
