"""Separate, audited daily registers. Unmarked days are never absences."""
from datetime import date
from urllib.parse import quote
from psycopg2 import sql
import access_control as A
import record_history as H
import records as R
import monthly_finance as F

KINDS = {'students': ('student_attendance','students','student_id','student_attendance'),
         'teachers': ('teacher_attendance','teachers','national_id','teacher_attendance')}
STATUSES = {'present','absent','excused'}


def migrate(conn):
    with conn.cursor() as c:
        c.execute('ALTER TABLE teachers ADD COLUMN IF NOT EXISTS department_id INTEGER REFERENCES school_departments(department_id) ON DELETE RESTRICT')
        for table, entity, pk, _ in KINDS.values():
            c.execute(sql.SQL('''CREATE TABLE IF NOT EXISTS {} (
                attendance_id BIGSERIAL PRIMARY KEY, person_id VARCHAR(20) NOT NULL REFERENCES {}({}) ON DELETE RESTRICT,
                on_date DATE NOT NULL, status TEXT NOT NULL CHECK(status IN ('present','absent','excused')),
                excuse TEXT NOT NULL DEFAULT '', department_id INTEGER REFERENCES school_departments(department_id) ON DELETE RESTRICT,
                department_name TEXT NOT NULL DEFAULT '', revision BIGINT NOT NULL DEFAULT 1,
                cancelled_at TIMESTAMPTZ, updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                CHECK(status<>'excused' OR length(btrim(excuse))>0), UNIQUE(person_id,on_date))''').format(
                    sql.Identifier(table),sql.Identifier(entity),sql.Identifier(pk)))
            c.execute(sql.SQL('CREATE INDEX IF NOT EXISTS {} ON {}(on_date) WHERE cancelled_at IS NULL').format(
                sql.Identifier(table+'_date'),sql.Identifier(table)))


def kind_config(kind):
    if kind not in KINDS: raise ValueError('اختر سجل الطلاب أو المعلمين.')
    return KINDS[kind]


def day(value):
    try: value=date.fromisoformat(value)
    except (TypeError,ValueError): raise ValueError('تاريخ الحضور غير صحيح.') from None
    if not date(1990,1,1)<=value<=F.today(): raise ValueError('لا يمكن تسجيل حضور بتاريخ مستقبلي أو غير صالح.')
    return value


def percentages(counts):
    counts={k:int(counts.get(k,0)) for k in ('present','absent','excused')}
    total=sum(counts.values())
    return {**counts,'total':total,'attendance_rate':round(counts['present']*100/total,1) if total else None,
            'absence_rate':round((counts['absent']+counts['excused'])*100/total,1) if total else None}


def summaries(conn,kind,start=None,end=None):
    table,_,_,resource=kind_config(kind)
    if not A.can(resource+'.view'): return {}
    with conn.cursor() as c:
        c.execute(sql.SQL('''SELECT person_id,COUNT(*) FILTER(WHERE status='present') AS present,
            COUNT(*) FILTER(WHERE status='absent') AS absent,COUNT(*) FILTER(WHERE status='excused') AS excused
            FROM {} WHERE cancelled_at IS NULL AND (%s::date IS NULL OR on_date>=%s)
            AND (%s::date IS NULL OR on_date<=%s) GROUP BY person_id''').format(sql.Identifier(table)),(start,start,end,end))
        return {r['person_id']:percentages(r) for r in c.fetchall()}


def read(conn,data):
    table,entity,pk,resource=kind_config(data.get('kind'))
    with conn.cursor() as c:
        A.require(c,resource+'.view')
        person=data.get('person')
        if person:
            if not isinstance(person,str) or len(person)>20:raise ValueError('الملف غير صحيح.')
            c.execute(sql.SQL('SELECT {} FROM {} WHERE {}=%s').format(sql.Identifier(pk),sql.Identifier(entity),sql.Identifier(pk)),(person,))
            if not c.fetchone(): raise ValueError('الملف غير موجود.')
            # Bounded, newest-first history; no truncation of totals.
            try: page=int(data.get('page',1))
            except (ValueError,TypeError):raise ValueError('صفحة غير صحيحة.') from None
            if not 1<=page<=100000: raise ValueError('صفحة غير صحيحة.')
            c.execute(sql.SQL('SELECT COUNT(*) AS n FROM {} WHERE person_id=%s AND cancelled_at IS NULL').format(sql.Identifier(table)),(person,))
            total=c.fetchone()['n']
            c.execute(sql.SQL('SELECT * FROM {} WHERE person_id=%s AND cancelled_at IS NULL ORDER BY on_date DESC LIMIT 30 OFFSET %s').format(sql.Identifier(table)),(person,(page-1)*30))
            return dict(items=[dict(r) for r in c.fetchall()],total=total,page=page,pages=max(1,(total+29)//30),
                        summary=summaries(conn,data['kind']).get(person,percentages({})))
        on=day(data.get('date'))
        c.execute(sql.SQL('SELECT * FROM {} WHERE on_date=%s').format(sql.Identifier(table)),(on,))
        records={r['person_id']:dict(r) for r in c.fetchall()}
        if entity=='students':
            c.execute('''SELECT s.student_id AS id,s.full_name AS name,
                sd.department_id,d.name AS department,p.revision AS photo_revision,p.image_data IS NOT NULL AS photo_present
                FROM students s LEFT JOIN student_photos p USING(student_id) LEFT JOIN student_departments sd USING(student_id)
                LEFT JOIN school_departments d USING(department_id) WHERE s.archived_at IS NULL AND (s.birth_date IS NULL OR s.birth_date<=%s) ORDER BY s.full_name,s.student_id''',(on,))
        else:
            c.execute('''SELECT t.national_id AS id,t.full_name AS name,
                t.department_id,d.name AS department,COALESCE(t.display_national_id,t.national_id) AS identity
                FROM teachers t LEFT JOIN school_departments d USING(department_id) WHERE t.archived_at IS NULL AND (t.hire_date IS NULL OR t.hire_date<=%s) ORDER BY t.full_name,t.national_id''',(on,))
        roster=[{**dict(r),'entry':records.get(r['id'])} for r in c.fetchall()]
        if entity=='students':
            for row in roster:
                present=row.pop('photo_present');revision=row.pop('photo_revision') or 0
                row['photo']={'revision':revision,'data':('/api/attendance-photo/'+quote(row['id'],safe='')+'?v='+str(revision)) if present else None}
        month=on.replace(day=1)
        return dict(date=on,items=roster,summaries=summaries(conn,data['kind'],month,on),period_start=month,period_end=on)


def photo(conn, person):
    """Portrait only for an active student, independently of full file access."""
    with conn.cursor() as c:
        A.require(c,'student_attendance.view',lock=False)
        c.execute('''SELECT p.image_data FROM student_photos p JOIN students s USING(student_id)
            WHERE p.student_id=%s AND s.archived_at IS NULL''',(person,))
        row=c.fetchone()
        return bytes(row['image_data']) if row and row['image_data'] else None


def save(conn,data,profile):
    table,entity,pk,resource=kind_config(data.get('kind')); on=day(data.get('date'))
    entries=data.get('entries')
    if not isinstance(entries,list) or not entries or len(entries)>1000:raise ValueError('حدد من 1 إلى 1000 سجل للحفظ.')
    normalized={}
    for item in entries:
        if not isinstance(item,dict):raise ValueError('بيانات الحضور غير صحيحة.')
        ident=item.get('person');status=item.get('status');excuse=item.get('excuse','')
        if not isinstance(ident,str) or not ident or len(ident)>20 or ident in normalized:raise ValueError('تكرار أو خطأ في اختيار الملف.')
        if status not in STATUSES|{''}:raise ValueError('حالة الحضور غير صحيحة.')
        if not isinstance(excuse,str) or len(excuse)>1000:raise ValueError('العذر حتى 1000 حرف.')
        excuse=excuse.strip() if status=='excused' else ''
        if status=='excused' and not excuse:raise ValueError('اكتب عذر الغياب قبل الحفظ.')
        if type(item.get('revision')) is not int or item['revision']<0:raise ValueError('أعد تحميل سجل الحضور.')
        normalized[ident]=(status,excuse,item['revision'])
    with conn.cursor() as c:
        A.require(c,resource+'.view')
        c.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',('attendance:'+table+':'+str(on),))
        H.context(c,profile['username'],str(data.get('reason') or 'تحديث سجل الحضور اليومي')[:2000])
        for ident,(status,excuse,revision) in sorted(normalized.items()):
            # Entity lock prevents a concurrent archive from accepting new attendance.
            c.execute(sql.SQL('SELECT * FROM {} WHERE {}=%s FOR SHARE').format(sql.Identifier(entity),sql.Identifier(pk)),(ident,))
            person=c.fetchone()
            if not person:raise ValueError('الملف غير موجود؛ حدّث القائمة.')
            c.execute(sql.SQL('SELECT * FROM {} WHERE person_id=%s AND on_date=%s FOR UPDATE').format(sql.Identifier(table)),(ident,on))
            old=c.fetchone();cancelled=not status
            if old and old['revision']!=revision:raise ValueError('تغيّر حضور أحد الأشخاص من جلسة أخرى؛ أعد تحميل اليوم قبل الحفظ.')
            if not old and revision:raise ValueError('تغيّر السجل؛ أعد تحميل اليوم.')
            if not old and cancelled:continue
            action='delete' if cancelled else 'edit' if old else 'create'
            A.require(c,resource+'.'+action)
            if person['archived_at'] and (not old or on>person['archived_at'].date()):raise ValueError('لا يمكن تسجيل حضور جديد لملف مؤرشف.')
            begins=person.get('hire_date') if entity=='teachers' else person.get('birth_date')
            if begins and on<begins:raise ValueError('التاريخ أقدم من تاريخ التوظيف أو ميلاد الطالب.')
            if old:
                if (not old['cancelled_at'] and old['status']==status and old['excuse']==excuse) or (old['cancelled_at'] and cancelled):continue
                c.execute(sql.SQL('''UPDATE {} SET status=CASE WHEN %s='' THEN status ELSE %s END,excuse=CASE WHEN %s='' THEN excuse ELSE %s END,
                    cancelled_at=CASE WHEN %s THEN now() ELSE NULL END,revision=revision+1,updated_at=now() WHERE attendance_id=%s''').format(sql.Identifier(table)),
                    (status,status,status,excuse,cancelled,old['attendance_id']))
            else:
                if entity=='students':
                    c.execute('SELECT d.department_id,d.name FROM student_departments sd JOIN school_departments d USING(department_id) WHERE student_id=%s',(ident,))
                else:c.execute('SELECT department_id,name FROM school_departments WHERE department_id=%s',(person['department_id'],))
                department=c.fetchone() or {}
                c.execute(sql.SQL('INSERT INTO {}(person_id,on_date,status,excuse,department_id,department_name) VALUES(%s,%s,%s,%s,%s,%s)').format(sql.Identifier(table)),
                    (ident,on,status,excuse,department.get('department_id'),department.get('name') or ''))
    conn.commit()
    return {'saved':len(normalized)}
