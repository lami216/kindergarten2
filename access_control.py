"""Server-side identity and granular authorization. Never trust a caller's actor."""
import hashlib
import hmac
import json
import re
import secrets
import uuid
from datetime import datetime, timezone

import streamlit as st
import web_runtime
import db

RESOURCES={
    'students':('الطلاب',('view','create','edit','delete')),
    'parents':('أولياء الأمور',('view','edit','delete')),
    'departments':('الأقسام ونقل الأطفال',('view','create','edit','delete')),
    'payments':('دفعات الطلاب والوصولات',('view','create','edit','delete')),
    'expenses':('المصروفات التشغيلية',('view','create','edit','delete')),
    'assets':('الأصول والتجهيزات',('view','edit','delete')),
    'teachers':('المعلمات',('view','edit','delete')),
    'salaries':('الرواتب والسلف',('view','create','edit','delete')),
    'classes':('سجل الصفوف السابق',('view','edit','delete')),
    'years':('السنوات الدراسية',('view','edit','delete')),
    'accounts':('الاشتراك والإعفاء وإسقاط الدين',('view','edit','delete')),
    'fees':('أسعار الرسوم',('view','edit')),
    'reports':('التقارير والمجاميع المالية الشاملة',('view',)),
    'history':('سجل التغييرات الكامل',('view',)),
}
ACTIONS={'view':'عرض','create':'إضافة','edit':'تعديل','delete':'إلغاء / حذف'}
PERMISSIONS={f'{resource}.{action}' for resource,(_,actions) in RESOURCES.items() for action in actions}
TABLE_RESOURCE={'students':'students','student_photos':'students','parents':'parents','school_departments':'departments',
    'student_departments':'departments','department_transfers':'departments','monthly_receipts':'payments',
    'payments':'payments','expenses':'expenses','assets':'assets','teachers':'teachers',
    'teacher_payments':'salaries','teacher_advances':'salaries','classes':'classes',
    'academic_years':'years','registrations':'accounts','monthly_accounts':'accounts',
    'monthly_waivers':'accounts','monthly_tariffs':'fees'}
ADMIN_LOCK=82416111
PRIVATE_TABLES=set(TABLE_RESOURCE)|{
    'app_users','app_sessions','app_login_attempts','app_access_audit','app_expense_requests',
    'app_schema_migrations','record_changes','department_migrations','finance_schema_versions',
    'monthly_fees','monthly_periods','monthly_allocations','monthly_audit','historical_payment_audit',
    'expense_cash_events','payroll_audit','monthly_waiver_batches','expense_cash_amendments',
    'expense_audit','expense_request_log','monthly_receipt_operations','monthly_allocation_snapshots'}


class AccessDenied(ValueError):
    pass


def migrate(conn):
    with conn.cursor() as c:
        c.execute('''CREATE TABLE IF NOT EXISTS app_users (
            user_id UUID PRIMARY KEY, employee_name VARCHAR(100) NOT NULL,
            username VARCHAR(64) NOT NULL UNIQUE, password_hash TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT false, active BOOLEAN NOT NULL DEFAULT true,
            permissions JSONB NOT NULL DEFAULT '[]', auth_version INTEGER NOT NULL DEFAULT 1,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(), last_login_at TIMESTAMPTZ);
            CREATE TABLE IF NOT EXISTS app_sessions (
            token_hash TEXT PRIMARY KEY, user_id UUID NOT NULL REFERENCES app_users(user_id),
            auth_version INTEGER NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
            expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '12 hours');
            CREATE INDEX IF NOT EXISTS app_sessions_user ON app_sessions(user_id);
            CREATE TABLE IF NOT EXISTS app_expense_requests (
            request_token UUID PRIMARY KEY, expense_id INTEGER NOT NULL REFERENCES expenses(expense_id),
            request_hash TEXT NOT NULL, user_id UUID NOT NULL REFERENCES app_users(user_id));
            CREATE TABLE IF NOT EXISTS app_login_attempts (
            name_hash TEXT PRIMARY KEY, failures INTEGER NOT NULL DEFAULT 0,
            blocked_until TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now());
            CREATE TABLE IF NOT EXISTS app_access_audit (
            event_id BIGSERIAL PRIMARY KEY, actor_user_id UUID REFERENCES app_users(user_id),
            target_user_id UUID REFERENCES app_users(user_id), action TEXT NOT NULL,
            happened_at TIMESTAMPTZ NOT NULL DEFAULT now(), before_state JSONB, after_state JSONB);
            CREATE OR REPLACE FUNCTION app_access_audit_immutable() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'Access audit is append-only'; END; $$ LANGUAGE plpgsql;
            DROP TRIGGER IF EXISTS app_access_guard ON app_access_audit;
            CREATE TRIGGER app_access_guard BEFORE UPDATE OR DELETE ON app_access_audit
                FOR EACH ROW EXECUTE FUNCTION app_access_audit_immutable();''')
        # Maintenance connections are trusted DB-owner connections. All web
        # session connections are bound below; revocation is checked again at
        # the write even in a legacy manager form using direct SQL.
        c.execute('''CREATE OR REPLACE FUNCTION app_business_access_guard() RETURNS trigger AS $$
        DECLARE actor app_users%ROWTYPE; session_hash TEXT; needed TEXT; action TEXT;
            permitted TEXT; target JSONB;
        BEGIN
            session_hash=NULLIF(current_setting('app.session_hash',true),'');
            IF session_hash IS NULL THEN
                IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            SELECT u.* INTO actor FROM app_users u JOIN app_sessions s ON s.user_id=u.user_id
              WHERE s.token_hash=session_hash AND u.active AND s.auth_version=u.auth_version
              AND s.expires_at>now() AND s.last_seen>now()-interval '30 minutes' FOR SHARE OF u,s;
            IF actor.user_id IS NULL THEN RAISE EXCEPTION 'Session revoked' USING ERRCODE='42501'; END IF;
            PERFORM set_config('app.audit_actor',actor.username,true);
            PERFORM set_config('app.audit_user_id',actor.user_id::text,true);
            IF actor.is_admin THEN IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF; END IF;
            target=CASE WHEN TG_OP='DELETE' THEN to_jsonb(OLD) ELSE to_jsonb(NEW) END;
            action=CASE TG_OP WHEN 'INSERT' THEN 'create' WHEN 'DELETE' THEN 'delete' ELSE 'edit' END;
            IF TG_OP='UPDATE' AND ((target->>'archived_at' IS NOT NULL AND to_jsonb(OLD)->>'archived_at' IS NULL)
                OR (target->>'cancelled_at' IS NOT NULL AND to_jsonb(OLD)->>'cancelled_at' IS NULL)
                OR (target->>'state'='cancelled' AND to_jsonb(OLD)->>'state'='active')) THEN action='delete'; END IF;
            needed=TG_ARGV[0]||'.'||action;
            permitted=NULLIF(current_setting('app.write_permission',true),'');
            IF TG_TABLE_NAME='student_photos' THEN
                needed='students.edit';
                IF TG_OP='INSERT' AND permitted='students.create' THEN needed=permitted; END IF;
            END IF;
            -- One corrected receipt preserves/cancels the original and issues a replacement.
            IF TG_TABLE_NAME='monthly_receipts' AND permitted='payments.edit' THEN needed='payments.edit'; END IF;
            IF TG_TABLE_NAME IN ('student_departments','department_transfers') THEN needed='departments.edit'; END IF;
            IF TG_TABLE_NAME='monthly_tariffs' THEN needed='fees.edit'; END IF;
            IF TG_TABLE_NAME='monthly_waivers' AND permitted='accounts.delete' THEN needed='accounts.delete'; END IF;
            IF TG_TABLE_NAME IN ('teacher_payments','teacher_advances') AND permitted='salaries.delete' THEN needed=permitted; END IF;
            IF TG_TABLE_NAME='parents' AND TG_OP='INSERT' THEN needed='students.create'; END IF;
            IF TG_TABLE_NAME='monthly_accounts' AND TG_OP='INSERT' AND permitted='students.create' THEN
                needed='students.create';
                IF target->>'status'='exempt' AND NOT(actor.permissions ? 'accounts.edit') THEN
                    RAISE EXCEPTION 'Exemption permission required' USING ERRCODE='42501'; END IF;
            END IF;
            IF TG_TABLE_NAME='monthly_accounts' AND permitted='students.delete' THEN needed='students.delete'; END IF;
            IF TG_TABLE_NAME='monthly_accounts' AND TG_OP='INSERT' AND permitted='accounts.edit' THEN needed=permitted; END IF;
            IF TG_TABLE_NAME='expenses' AND (target->>'teacher_payment_id' IS NOT NULL OR target->>'teacher_advance_id' IS NOT NULL)
                THEN needed='salaries.'||action; END IF;
            IF NOT(actor.permissions ? needed) THEN RAISE EXCEPTION 'Permission denied' USING ERRCODE='42501'; END IF;
            IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
        END; $$ LANGUAGE plpgsql;''')
        from psycopg2 import sql
        for table,resource in TABLE_RESOURCE.items():
            c.execute(sql.SQL('DROP TRIGGER IF EXISTS business_access_guard ON {}').format(sql.Identifier(table)))
            c.execute(sql.SQL('CREATE TRIGGER business_access_guard BEFORE INSERT OR UPDATE OR DELETE ON {} '
                'FOR EACH ROW EXECUTE FUNCTION app_business_access_guard({})').format(sql.Identifier(table),sql.Literal(resource)))
        # Streamlit talks to PostgreSQL through a private, table-owning server
        # connection. Neither Supabase client role is an application worker.
        # RLS without public policies denies non-owner rows even if a default
        # grant is accidentally restored later. Unknown/shared tables are untouched.
        c.execute("SELECT rolname FROM pg_roles WHERE rolname IN ('anon','authenticated')")
        client_roles=[r['rolname'] for r in c.fetchall()]
        for table in sorted(PRIVATE_TABLES):
            c.execute('SELECT to_regclass(%s) AS relation',(table,))
            if not c.fetchone()['relation']: continue
            c.execute(sql.SQL('ALTER TABLE {} ENABLE ROW LEVEL SECURITY').format(sql.Identifier(table)))
            c.execute(sql.SQL('REVOKE ALL ON TABLE {} FROM PUBLIC').format(sql.Identifier(table)))
            for role in client_roles:
                c.execute(sql.SQL('REVOKE ALL ON TABLE {} FROM {}').format(sql.Identifier(table),sql.Identifier(role)))


def username(value):
    value=str(value or '').strip().casefold()
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]{2,63}',value):
        raise ValueError('اسم المستخدم من 3 إلى 64 حرفًا إنجليزيًا أو رقمًا؛ ويمكن استعمال . و _ و -')
    return value


def password_hash(password):
    if not isinstance(password,str) or not 12<=len(password)<=128:
        raise ValueError('كلمة المرور من 12 إلى 128 حرفًا. يمكن توليد كلمة قوية بدل اختيار رمز قصير.')
    salt=secrets.token_hex(16)
    digest=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),600000).hex()
    return f'pbkdf2_sha256$600000${salt}${digest}'


def verify_password(password,encoded):
    try:
        method,iterations,salt,expected=encoded.split('$')
        if method!='pbkdf2_sha256' or int(iterations)!=600000 or len(password)>128: return False
        actual=hashlib.pbkdf2_hmac('sha256',password.encode('utf-8'),bytes.fromhex(salt),int(iterations)).hex()
        return hmac.compare_digest(actual,expected)
    except (ValueError,TypeError,AttributeError):
        return False


_DUMMY=password_hash(secrets.token_urlsafe(24))


def _public(row):
    return {k:row[k] for k in ('user_id','employee_name','username','is_admin','active','permissions','auth_version')}


def validate_permissions(values):
    values=set(values)
    if values-PERMISSIONS: raise ValueError('توجد صلاحية غير معروفة.')
    for resource in RESOURCES:
        if any(f'{resource}.{a}' in values for a in ('edit','delete')):
            values.add(resource+'.view')
    if 'payments.create' in values: values.add('payments.view')
    if 'salaries.create' in values: values.add('salaries.view')
    if 'accounts.edit' in values or 'accounts.delete' in values: values.add('payments.view')
    return sorted(values)


def current(cursor=None,*,lock=False):
    token=web_runtime.state().get('auth_session')
    if not token: raise AccessDenied('انتهت جلسة الدخول؛ أعد تسجيل الدخول.')
    connection=None
    try:
        if cursor is None:
            connection=db.new_transaction_connection()
            cursor=connection.cursor()
        cursor.execute('''SELECT u.* FROM app_users u JOIN app_sessions s ON s.user_id=u.user_id
            WHERE s.token_hash=%s AND u.active AND s.auth_version=u.auth_version
            AND s.expires_at>now() AND s.last_seen>now()-interval '30 minutes' '''+
            ('FOR SHARE OF u,s' if lock else ''),(hashlib.sha256(token.encode()).hexdigest(),))
        row=cursor.fetchone()
        if not row: raise AccessDenied('انتهت الجلسة أو تغيرت صلاحيات الحساب؛ أعد تسجيل الدخول.')
        return _public(row)
    finally:
        if connection: connection.close()


def allowed(profile,permission):
    return bool(profile and profile.get('active') and
                (profile.get('is_admin') or permission in profile.get('permissions',[])))


def can(permission):
    return allowed(web_runtime.state().get('_access_profile'),permission)


def require(cursor,permission,*,lock=True):
    profile=current(cursor,lock=lock)
    if not allowed(profile,permission): raise AccessDenied('ليس لديك صلاحية لتنفيذ هذا الإجراء.')
    cursor.execute("SELECT set_config('app.audit_user_id',%s,true),set_config('app.audit_actor',%s,true),set_config('app.write_permission',%s,true),set_config('app.session_hash',%s,true)",
                   (str(profile['user_id']),profile['username'],permission,
                    hashlib.sha256(web_runtime.state()['auth_session'].encode()).hexdigest()))
    return profile


def table_permission(table,action):
    resource=TABLE_RESOURCE.get(table)
    if not resource: raise AccessDenied('هذا النوع غير متاح لحساب العامل.')
    return resource+'.'+action


def actor(cursor,permission,legacy_actor=None):
    return require(cursor,permission)['username']


def bind(conn,profile):
    with conn.cursor() as c:
        c.execute("SELECT set_config('app.audit_user_id',%s,false),set_config('app.audit_actor',%s,false),set_config('app.session_hash',%s,false)",
                  (str(profile['user_id']),profile['username'],hashlib.sha256(web_runtime.state()['auth_session'].encode()).hexdigest()))


def login(name,password):
    # Unknown/disabled users receive the same response and hashing work.
    normal=str(name or '').strip().casefold()[:128]
    key=hashlib.sha256(normal.encode()).hexdigest()
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            c.execute('INSERT INTO app_login_attempts(name_hash) VALUES(%s) ON CONFLICT DO NOTHING',(key,))
            c.execute('SELECT *,blocked_until>now() AS blocked FROM app_login_attempts WHERE name_hash=%s FOR UPDATE',(key,))
            attempt=c.fetchone()
            if attempt['blocked']: conn.commit(); return None
            c.execute('SELECT * FROM app_users WHERE username=%s FOR SHARE',(normal,))
            user=c.fetchone()
            valid=verify_password(password,user['password_hash'] if user else _DUMMY)
            if not (valid and user and user['active']):
                c.execute('''UPDATE app_login_attempts SET failures=CASE WHEN updated_at<now()-interval '15 minutes'
                    THEN 1 ELSE failures+1 END,blocked_until=CASE WHEN failures>=4 AND updated_at>=now()-interval '15 minutes'
                    THEN now()+interval '15 minutes' ELSE NULL END,updated_at=now() WHERE name_hash=%s''',(key,))
                conn.commit(); return None
            c.execute('UPDATE app_login_attempts SET failures=0,blocked_until=NULL WHERE name_hash=%s',(key,))
            token=secrets.token_urlsafe(32)
            c.execute('INSERT INTO app_sessions(token_hash,user_id,auth_version) VALUES(%s,%s,%s)',
                (hashlib.sha256(token.encode()).hexdigest(),user['user_id'],user['auth_version']))
            c.execute('UPDATE app_users SET last_login_at=now() WHERE user_id=%s',(user['user_id'],))
        conn.commit(); return token
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def refresh(conn):
    with conn.cursor() as c:
        profile=current(c)
        c.execute('UPDATE app_sessions SET last_seen=now() WHERE token_hash=%s',
                  (hashlib.sha256(web_runtime.state()['auth_session'].encode()).hexdigest(),))
    previous=web_runtime.state().get('_access_profile')
    if previous and (previous['user_id'],previous['auth_version'])!=(profile['user_id'],profile['auth_version']):
        clear_state(keep_token=True)
    web_runtime.state()['_access_profile']=profile
    web_runtime.state()['auth_ok']=True
    web_runtime.state()['auth_user']=profile['username']
    bind(conn,profile)
    return profile


def clear_state(*,keep_token=False):
    # Reuse this tab's connection slot. Its revoked session hash stays fail-
    # closed until the next successful refresh binds the new identity.
    keep={k:web_runtime.state()[k] for k in ('night_mode','_db_session_key','auth_session') if k in web_runtime.state() and (k!='auth_session' or keep_token)}
    web_runtime.state().clear()
    web_runtime.state().update(keep)


def revoke_current():
    token=web_runtime.state().get('auth_session')
    try:
        if token:
            conn=db.new_transaction_connection()
            try:
                with conn.cursor() as c:
                    c.execute('DELETE FROM app_sessions WHERE token_hash=%s',(hashlib.sha256(token.encode()).hexdigest(),))
                conn.commit()
            finally: conn.close()
    finally:
        clear_state()


def _audit(c,actor,target,action,before,after):
    c.execute('INSERT INTO app_access_audit(actor_user_id,target_user_id,action,before_state,after_state) VALUES(%s,%s,%s,%s,%s)',
        (actor,target,action,json.dumps(before,default=str,ensure_ascii=False),json.dumps(after,default=str,ensure_ascii=False)))


def bootstrap(employee_name,name,password):
    name=username(name); hashed=password_hash(password)
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)',(ADMIN_LOCK,))
            c.execute('SELECT COUNT(*) AS n FROM app_users')
            if c.fetchone()['n']: raise ValueError('حسابات الدخول مهيأة بالفعل؛ استخدم لوحة المدير.')
            uid=str(uuid.uuid4())
            c.execute('INSERT INTO app_users(user_id,employee_name,username,password_hash,is_admin) VALUES(%s,%s,%s,%s,true)',
                      (uid,employee_name.strip()[:100] or 'مدير الروضة',name,hashed))
            _audit(c,None,uid,'owner_bootstrap',{}, {'username':name,'employee_name':employee_name,'is_admin':True})
        conn.commit(); return uid
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def save_user(*,employee_name,name=None,password=None,is_admin=False,permissions=(),active=True,user_id=None,expected_version=None):
    employee_name=employee_name.strip()
    if not employee_name or len(employee_name)>100: raise ValueError('اسم العامل مطلوب، حتى 100 حرف.')
    perms=validate_permissions(permissions)
    hashed=password_hash(password) if password else None
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            c.execute('SELECT pg_advisory_xact_lock(%s)',(ADMIN_LOCK,))
            actor=require(c,'admin.manage')
            if user_id:
                c.execute('SELECT * FROM app_users WHERE user_id=%s FOR UPDATE',(str(user_id),))
                old=c.fetchone()
                if not old: raise ValueError('الحساب غير موجود.')
                if expected_version!=old['auth_version']: raise ValueError('تغير الحساب؛ حدّث بياناته قبل الحفظ.')
                if old['is_admin'] and old['active'] and (not active or not is_admin):
                    c.execute('SELECT COUNT(*) AS n FROM app_users WHERE is_admin AND active')
                    if c.fetchone()['n']<=1: raise ValueError('لا يمكن تعطيل آخر مدير أو إزالة صلاحية الإدارة منه.')
                uid=str(user_id)
                c.execute('''UPDATE app_users SET employee_name=%s,is_admin=%s,permissions=%s,active=%s,
                    password_hash=COALESCE(%s,password_hash),auth_version=auth_version+1 WHERE user_id=%s''',
                    (employee_name,is_admin,json.dumps(perms),active,hashed,uid))
                c.execute('DELETE FROM app_sessions WHERE user_id=%s',(uid,))
                if hashed or (active and not old['active']):
                    c.execute('DELETE FROM app_login_attempts WHERE name_hash=%s',
                        (hashlib.sha256(old['username'].encode()).hexdigest(),))
            else:
                if not hashed: raise ValueError('أدخل كلمة مرور للحساب الجديد.')
                uid=str(uuid.uuid4()); old=None
                c.execute('INSERT INTO app_users(user_id,employee_name,username,password_hash,is_admin,permissions,active) VALUES(%s,%s,%s,%s,%s,%s,%s)',
                    (uid,employee_name,username(name),hashed,is_admin,json.dumps(perms),active))
            c.execute('SELECT * FROM app_users WHERE user_id=%s',(uid,))
            following=_public(c.fetchone()); following['password_changed']=bool(hashed)
            _audit(c,actor['user_id'],uid,'account_updated' if old else 'account_created',_public(old) if old else {},following)
        conn.commit(); return uid
    except __import__('psycopg2').errors.UniqueViolation:
        conn.rollback(); raise ValueError('اسم المستخدم مستخدم؛ اختر اسمًا آخر.') from None
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def list_users(conn):
    with conn.cursor() as c:
        require(c,'admin.manage')
        c.execute('SELECT user_id,employee_name,username,is_admin,active,permissions,auth_version,created_at,last_login_at FROM app_users ORDER BY created_at')
        return [dict(r) for r in c.fetchall()]


def employee_metrics(conn,user_id):
    with conn.cursor() as c:
        profile=current(c)
        if not profile['is_admin'] and str(profile['user_id'])!=str(user_id):
            raise AccessDenied('لا يمكنك عرض نشاط حساب آخر.')
        c.execute('''SELECT table_name,action,COUNT(*) AS events,COUNT(DISTINCT record_key) AS records
            FROM record_changes WHERE actor_user_id=%s GROUP BY table_name,action ORDER BY table_name,action''',(str(user_id),))
        activity=[dict(r) for r in c.fetchall()]
        c.execute('''SELECT COUNT(*) AS count,COALESCE(SUM((rc.after_state->>'amount_paid')::numeric),0) AS original_cash,
            COALESCE(SUM(CASE WHEN e.cancelled_at IS NULL THEN e.amount_paid ELSE 0 END),0) AS current_cash
            FROM record_changes rc JOIN expenses e ON e.expense_id::text=rc.record_key
            WHERE rc.actor_user_id=%s AND rc.table_name='expenses' AND rc.action='created'
              AND e.teacher_payment_id IS NULL AND e.teacher_advance_id IS NULL''',(str(user_id),))
        expenses=dict(c.fetchone())
        c.execute('''SELECT COUNT(*) AS count,COALESCE(SUM(r.amount),0) AS original_cash,
            COALESCE(SUM(CASE WHEN latest.state='active' THEN latest.amount ELSE 0 END),0) AS current_cash
            FROM record_changes rc JOIN monthly_receipts r ON r.receipt_id::text=rc.record_key
            JOIN LATERAL (
              WITH RECURSIVE chain AS (
                SELECT receipt_id,amount,state FROM monthly_receipts WHERE receipt_id=r.receipt_id
                UNION ALL SELECT child.receipt_id,child.amount,child.state FROM monthly_receipts child
                  JOIN chain parent ON child.corrects_id=parent.receipt_id)
              SELECT * FROM chain ORDER BY receipt_id DESC LIMIT 1
            ) latest ON true
            WHERE rc.actor_user_id=%s AND rc.table_name='monthly_receipts' AND rc.action='created'
              AND r.corrects_id IS NULL''',(str(user_id),))
        payments=dict(c.fetchone())
    students=sum(int(r['records']) for r in activity if r['table_name']=='students' and r['action']=='created')
    if not profile['is_admin']:
        def visible(resource):
            return allowed(profile,resource+'.view') or allowed(profile,resource+'.create')
        if not visible('expenses'): expenses=dict(count=0,original_cash=0,current_cash=0)
        if not visible('payments'): payments=dict(count=0,original_cash=0,current_cash=0)
        if not visible('students'): students=0
        activity=[r for r in activity if visible(TABLE_RESOURCE.get(r['table_name'],''))]
    return {'activity':activity,'expenses':expenses,'payments':payments,'students':students}


def access_history(conn):
    with conn.cursor() as c:
        require(c,'admin.manage')
        c.execute('''SELECT a.event_id,a.action,a.happened_at,u.employee_name AS target_name,u.username,
            actor.username AS responsible,a.before_state,a.after_state FROM app_access_audit a
            LEFT JOIN app_users u ON u.user_id=a.target_user_id
            LEFT JOIN app_users actor ON actor.user_id=a.actor_user_id ORDER BY a.event_id DESC LIMIT 300''')
        return [dict(r) for r in c.fetchall()]


if __name__=='__main__':
    # Deployment-only bootstrap. Never creates an account on page navigation.
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('command',choices=['bootstrap'])
    parser.parse_args()
    bootstrap('مدير الروضة',st.secrets['auth']['username'],st.secrets['auth']['password'])
    print('تم إنشاء حساب المدير الأول. يمكن إدارة بقية الحسابات من لوحة المدير.')
