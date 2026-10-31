"""Complete nonfinancial editing and cancellation without cascading data loss."""
import hashlib
import json
from datetime import date
from decimal import Decimal
import psycopg2
from psycopg2 import sql
import db
import record_history as H

# Only operator input is editable. Generated IDs, request tokens and ledger
# snapshots are intentionally absent. Manually entered teacher/year IDs can change.
FIELDS = {
    'school_departments': ('name',),
    'student_departments': ('department_id',),
    'students': ('full_name','birth_date','gender','birth_place','address','nationality','id_type',
                 'medical_details','allergies','general_notes','authorized_pickups','father_id'),
    'parents': ('father_name','father_mobile','mother_name','mother_mobile','contact_email',
                'father_job','mother_job','mother_work_type','father_id_type','mother_id_type',
                'address','landline','status_refugee','father_work_phone','mother_work_phone',
                'emergency_contact_name','emergency_contact_phone','marital_status','mother_id'),
    'teachers': ('national_id','full_name','salary','mobile','address','hire_date','department_id',
                 'experience_years','degree','specialization'),
    'classes': ('class_type','section','class_name','teacher_id'),
    'academic_years': ('year_id','start_date','end_date','cohort_name'),
    'assets': ('purchase_date','item_name','category','quantity','unit_cost','condition_status','notes'),
    'registrations': ('student_id','class_id','year_id','status','registration_date','annual_tuition'),
}
LABELS = {'monthly_gilet_cancellations':'إلغاء بند الجيليه','gilet_sales':'مبيعات الجيليه','gilet_deliveries':'تسليم الجيليه','account_status_requests':'تأكيدات الإعفاء','student_attendance':'حضور الطلاب','teacher_attendance':'حضور المعلمين','school_departments':'الأقسام','students':'الطلاب','student_photos':'صور الطلاب','parents':'أولياء الأمور',
          'teachers':'المعلمين','classes':'الصفوف السابقة','academic_years':'السنوات الدراسية',
          'assets':'الأصول والمعدات','registrations':'التسجيلات السابقة','expenses':'المصروفات',
          'monthly_receipts':'الدفعات الشهرية','payments':'الدفعات السابقة',
          'teacher_payments':'الرواتب','teacher_advances':'السلف','monthly_tariffs':'الرسوم',
          'student_departments':'توزيع الأطفال','department_transfers':'نقل الأطفال',
          'monthly_accounts':'حساب الطالب','monthly_waivers':'إلغاء الديون'}


def revision(row):
    return hashlib.sha256(json.dumps(dict(row),sort_keys=True,default=str,ensure_ascii=False).encode()).hexdigest()


def migrate(conn):
    with conn.cursor() as c:
        for table in FIELDS:
            c.execute(sql.SQL('ALTER TABLE {} ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ, '
                             'ADD COLUMN IF NOT EXISTS archived_by TEXT').format(sql.Identifier(table)))
        c.execute('ALTER TABLE expenses ADD COLUMN IF NOT EXISTS cancelled_at TIMESTAMPTZ;')
        c.execute('ALTER TABLE monthly_accounts ADD COLUMN IF NOT EXISTS exempt_from DATE;')
        c.execute('ALTER TABLE teacher_payments ADD COLUMN IF NOT EXISTS entry_cancelled_at TIMESTAMPTZ; ALTER TABLE teacher_advances ADD COLUMN IF NOT EXISTS entry_cancelled_at TIMESTAMPTZ;')
        # Editable public identifiers are separate from stable internal keys.
        # No foreign-key policies or historical references are changed.
        c.execute('''ALTER TABLE teachers ADD COLUMN IF NOT EXISTS display_national_id VARCHAR(20);
            ALTER TABLE academic_years ADD COLUMN IF NOT EXISTS display_year_id VARCHAR(20);
            DROP INDEX IF EXISTS teacher_public_identity_unique;
            CREATE UNIQUE INDEX teacher_public_identity_unique
                ON teachers(COALESCE(display_national_id,national_id)) WHERE archived_at IS NULL;
            DROP INDEX IF EXISTS academic_public_identity_unique;
            CREATE UNIQUE INDEX academic_public_identity_unique
                ON academic_years(COALESCE(display_year_id,year_id)) WHERE archived_at IS NULL;
            ALTER TABLE classes DROP CONSTRAINT IF EXISTS classes_class_type_section_key;
            CREATE UNIQUE INDEX IF NOT EXISTS class_active_type_section_unique
                ON classes(class_type,section) WHERE archived_at IS NULL;''')
    H.migrate(conn)


def _lock(c, table, ident, expected):
    c.execute(sql.SQL('SELECT * FROM {} WHERE {}=%s FOR UPDATE').format(sql.Identifier(table),sql.Identifier(H.TABLES[table])),(ident,))
    row=c.fetchone()
    if not row: raise ValueError('السجل غير موجود؛ حدّث القائمة.')
    if expected is not None and revision(row)!=expected:
        raise ValueError('تغيّر السجل منذ فتحه؛ حدّث الصفحة وراجع البيانات الجديدة قبل الحفظ.')
    return dict(row)


def _validate(c, table, old, updates):
    data={**old,**updates}
    required={'school_departments':('name',),'students':('full_name',),'teachers':('national_id','full_name'),
              'classes':('class_type','section'),'academic_years':('year_id',),'assets':('item_name','category')}
    for key in required.get(table,()):
        if not str(data.get(key) or '').strip(): raise ValueError('أكمل الحقول المطلوبة.')
    if table=='school_departments':
        updates['name']=' '.join(str(data['name']).split())
        if len(updates['name'])>100: raise ValueError('اسم القسم لا يتجاوز 100 حرف.')
    if table=='parents':
        error=db.contact_validation_error(*(str(data.get(k) or '') for k in ('father_name','father_mobile','mother_name','mother_mobile')))
        if error: raise ValueError(error)
    if table=='students':
        if data.get('birth_date') and date.fromisoformat(str(data['birth_date']))>__import__('monthly_finance').today():
            raise ValueError('تاريخ الميلاد لا يكون مستقبليًا.')
        if not isinstance(data.get('authorized_pickups'),list): raise ValueError('المخولون بالاستلام يجب أن يكونوا قائمة.')
        for person in data.get('authorized_pickups',[]):
            if not isinstance(person,dict) or not str(person.get('name','')).strip() or not str(person.get('phone','')).strip():
                raise ValueError('كل شخص مخول يحتاج اسمًا ورقم هاتف.')
        if 'medical_details' in updates:
            updates['has_medical_condition']=int(bool(str(data.get('medical_details') or '').strip()) or
                (not str(old.get('medical_details') or '').strip() and bool(old.get('has_medical_condition'))))
    if table=='academic_years' and data.get('start_date') and data.get('end_date'):
        if str(data['start_date'])>=str(data['end_date']): raise ValueError('نهاية السنة يجب أن تكون بعد بدايتها.')
    for key in ('salary','unit_cost','annual_tuition'):
        if key in data:
            from expense_finance import cash
            updates[key]=cash(data[key],zero=True)
    if table=='teachers' and int(data.get('experience_years') or 0)<0: raise ValueError('سنوات الخبرة لا تكون سالبة.')
    if table=='assets':
        q=Decimal(str(data['quantity']))
        if q!=q.to_integral_value() or q<1 or q>1000000: raise ValueError('الكمية عدد صحيح موجب.')
        updates['quantity']=int(q)
        from expense_finance import cash
        updates['total_cost']=cash(q*Decimal(str(data['unit_cost'])),zero=True)
    # Newly chosen references must still be active when the transaction saves.
    refs={'department_id':('school_departments','department_id'),'father_id':('parents','father_id'),'teacher_id':('teachers','national_id'),
          'student_id':('students','student_id'),'class_id':('classes','class_id'),'year_id':('academic_years','year_id')}
    for key,(target,pk) in refs.items():
        if key in updates and data.get(key) is not None and data.get(key)!=old.get(key) and target!=table:
            c.execute(sql.SQL('SELECT {} FROM {} WHERE {}=%s AND archived_at IS NULL FOR SHARE').format(sql.Identifier(pk),sql.Identifier(target),sql.Identifier(pk)),(data[key],))
            if not c.fetchone(): raise ValueError('السجل المرتبط محذوف أو غير موجود؛ اختر سجلًا آخر.')
    if table=='student_departments' and data.get('department_id') is None:
        raise ValueError('اختر قسمًا؛ لإزالة توزيع الطالب استخدم الحذف.')


def edit(table, ident, updates, *, actor, reason, expected=None, clear_legacy_medical=False):
    if table not in FIELDS or set(updates)-set(FIELDS[table]): raise ValueError('حقل غير قابل للتعديل من هذا النموذج.')
    if not str(actor or '').strip() or not str(reason or '').strip(): raise ValueError('أدخل سبب التغيير وتأكد من تسجيل الدخول.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,A.table_permission(table,'edit'),actor)
            H.context(c,actor,reason)
            if table in ('school_departments','student_departments','teachers'):
                c.execute("SELECT pg_advisory_xact_lock(hashtextextended('department_mutation',0))")
            old=_lock(c,table,ident,expected)
            if old.get('archived_at'): raise ValueError('السجل محذوف؛ اعرضه في سجل التغييرات.')
            updates={key:(value.strip() or None) if isinstance(value,str) else value for key,value in updates.items()}
            _validate(c,table,old,updates)
            if table=='students' and clear_legacy_medical:
                updates['has_medical_condition']=int(bool(str(updates.get('medical_details',old.get('medical_details')) or '').strip()))
            identity={'teachers':('national_id','display_national_id'),'academic_years':('year_id','display_year_id')}.get(table)
            if identity and identity[0] in updates:
                key,display=identity
                public=str(updates.pop(key)).strip()
                if public!=(old.get(display) or old[key]): updates[display]=public
            changed={k:v for k,v in updates.items() if v!=old.get(k)}
            if not changed:
                conn.commit(); return False
            if table=='student_departments':
                c.execute('INSERT INTO department_transfers(student_id,from_department_id,to_department_id,actor) VALUES(%s,%s,%s,%s)',
                          (ident,old['department_id'],updates['department_id'],actor))
            values=[json.dumps(v,ensure_ascii=False) if k=='authorized_pickups' else v for k,v in changed.items()]
            c.execute(sql.SQL('UPDATE {} SET {} WHERE {}=%s').format(sql.Identifier(table),
                sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in changed),sql.Identifier(H.TABLES[table])),values+[ident])
        conn.commit(); return True
    except (psycopg2.errors.UniqueViolation,psycopg2.errors.StringDataRightTruncation):
        conn.rollback(); raise ValueError('القيمة مكررة أو أطول من المسموح؛ لم تُحفظ التغييرات.') from None
    except Exception:
        conn.rollback(); raise
    finally: conn.close()


def cancel(table, ident, *, actor, reason, expected=None, destination=None, waive_student_debt=False):
    if table not in FIELDS: raise ValueError('استخدم إلغاء العملية المالية من صفحتها.')
    if not str(actor or '').strip() or not str(reason or '').strip(): raise ValueError('أدخل سبب الحذف وتأكد من تسجيل الدخول.')
    conn=db.new_transaction_connection()
    try:
        with conn.cursor() as c:
            import access_control as A
            actor=A.actor(c,A.table_permission(table,'delete'),actor)
            if waive_student_debt: A.require(c,'accounts.delete')
            H.context(c,actor,reason)
            # Serializes department edits/deletes/transfers in a consistent order.
            if table in ('school_departments','student_departments'): c.execute("SELECT pg_advisory_xact_lock(hashtextextended('department_mutation',0))")
            old=_lock(c,table,ident,expected)
            if old.get('archived_at'): conn.commit(); return False
            if table=='student_departments':
                c.execute('DELETE FROM student_departments WHERE student_id=%s',(ident,))
                conn.commit(); return True
            if table=='school_departments':
                if destination is not None:
                    if int(destination)==int(ident): raise ValueError('اختر قسمًا مختلفًا.')
                    c.execute('SELECT department_id FROM school_departments WHERE department_id=%s AND archived_at IS NULL FOR UPDATE',(destination,))
                    if not c.fetchone(): raise ValueError('القسم البديل غير موجود.')
                c.execute('SELECT national_id FROM teachers WHERE department_id=%s AND archived_at IS NULL FOR UPDATE',(ident,))
                staff=c.fetchall()
                if staff and destination is None:raise ValueError('القسم مرتبط بمعلمين؛ اختر القسم البديل قبل حذفه.')
                if staff and destination is not None:
                    A.require(c,'teachers.edit')
                    c.execute('UPDATE teachers SET department_id=%s WHERE department_id=%s AND archived_at IS NULL',(destination,ident))
                    A.require(c,'departments.delete')
                c.execute('SELECT student_id FROM student_departments WHERE department_id=%s ORDER BY student_id FOR UPDATE',(ident,))
                for member in c.fetchall():
                    if destination is None:
                        c.execute('DELETE FROM student_departments WHERE student_id=%s',(member['student_id'],))
                    else:
                        c.execute('UPDATE student_departments SET department_id=%s,assigned_at=now() WHERE student_id=%s',(destination,member['student_id']))
                        c.execute('INSERT INTO department_transfers(student_id,from_department_id,to_department_id,actor) VALUES(%s,%s,%s,%s)',(member['student_id'],ident,destination,actor))
            if table=='students':
                import monthly_finance as F
                import student_debt as D
                c.execute('SELECT * FROM monthly_accounts WHERE student_id=%s FOR UPDATE',(ident,))
                account=c.fetchone()
                if account:
                    debts=D.current_debt(c,ident,account)
                    due=sum(max(0,r['remaining']) for r in debts)
                    if due and not waive_student_debt:
                        raise ValueError(f'على الطالب {due:,} أوقية قديمة؛ أكد إسقاط المتبقي إذا أردت إلغاء ملفه.')
                    if due:
                        # Noncash adjustment in the SAME transaction as archiving.
                        import uuid
                        for item in debts:
                            if item['remaining']<=0: continue
                            token=str(uuid.uuid4())
                            c.execute('''INSERT INTO monthly_waivers(student_id,fee_id,period_id,amount,effective_on,
                                request_token,request_hash,actor,reason,before_state,after_state)
                                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'{}','{}')''',
                                (ident,item['ident'],item['period_id'],item['remaining'],F.today(),token,'record-cancellation',actor,reason))
                        F._audit(c,ident,None,'debt_waived_non_cash',actor,{'gross_due':due},{'waived':due,'cash':0},reason)
                if account:
                    c.execute('UPDATE monthly_accounts SET archived_at=now(),archived_by=%s,departure_on=%s WHERE student_id=%s',(actor,min(account.get('departure_on') or F.today(),F.today()),ident))
                    F._audit(c,ident,None,'student_archived',actor,dict(account),{'departed_on':str(F.today()),'cash':0},reason)
                c.execute('DELETE FROM student_departments WHERE student_id=%s',(ident,))
            if table=='registrations':
                # The legacy receipt remains auditable, but leaves annual totals.
                c.execute("UPDATE payments SET receipt_state='cancelled',cancelled_at=now(),cancelled_by=%s,cancel_reason=%s WHERE registration_id=%s AND receipt_state='active'",(actor,reason,ident))
            c.execute(sql.SQL('UPDATE {} SET archived_at=now(),archived_by=%s WHERE {}=%s').format(sql.Identifier(table),sql.Identifier(H.TABLES[table])),(actor,ident))
        conn.commit(); return True
    except Exception:
        conn.rollback(); raise
    finally: conn.close()
