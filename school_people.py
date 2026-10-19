"""Department selection inside an atomic student/teacher registration."""
import access_control as A


def department(cursor, value, new_name=''):
    if not isinstance(new_name,str):raise ValueError('اسم القسم غير صحيح.')
    cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended('department_mutation',0))")
    if new_name:
        if value:raise ValueError('اختر قسمًا موجودًا أو أنشئ قسمًا جديدًا، وليس الاثنين.')
        name=' '.join(str(new_name).split())
        if not name or len(name)>100:raise ValueError('اسم القسم مطلوب، حتى 100 حرف.')
        A.require(cursor,'departments.create')
        cursor.execute('SELECT department_id FROM school_departments WHERE lower(name)=lower(%s) AND archived_at IS NULL',(name,))
        if cursor.fetchone():raise ValueError('القسم موجود بالفعل؛ اختره من القائمة.')
        cursor.execute('INSERT INTO school_departments(name) VALUES(%s) RETURNING department_id',(name,))
        return cursor.fetchone()['department_id']
    if type(value) not in (int,str) or (isinstance(value,str) and not value.isascii()) or (isinstance(value,str) and not value.isdecimal()):raise ValueError('اختر القسم.')
    try: ident=int(value)
    except (TypeError,ValueError):raise ValueError('اختر القسم قبل التسجيل.') from None
    cursor.execute('SELECT department_id FROM school_departments WHERE department_id=%s AND archived_at IS NULL FOR SHARE',(ident,))
    if not cursor.fetchone():raise ValueError('القسم غير موجود أو مؤرشف؛ حدّث القائمة.')
    return ident


def teachers(conn):
    if not A.can('teachers.view'):return []
    import records as R
    with conn.cursor() as c:
        c.execute('SELECT * FROM teachers ORDER BY full_name,national_id')
        return [dict(id=r['national_id'],name=r['full_name'],identity=r['display_national_id'] or r['national_id'],
            salary=r['salary'],phone=r['mobile'] or '',department_id=r['department_id'],hire_date=r['hire_date'],
            cancelled=bool(r['archived_at']),revision=R.revision(r),values={k:r.get(k) for k in R.FIELDS['teachers']}) for r in c.fetchall()]


def teacher_finance(conn,data):
    import records as R
    from live_pages import text
    from psycopg2 import sql
    with conn.cursor() as c:A.require(c,'salaries.view')
    ident=text(data,'teacher',20,True)
    page=data.get('page',1)
    if type(page) is not int or not 1<=page<=100000:raise ValueError('صفحة غير صحيحة.')
    result={'page':page,'pages':1}
    for table,key,title in (('teacher_payments','payment_id','salaries'),('teacher_advances','advance_id','advances')):
        with conn.cursor() as c:
            c.execute(sql.SQL('SELECT COUNT(*) AS n FROM {} WHERE national_id=%s').format(sql.Identifier(table)),(ident,))
            result['pages']=max(result['pages'],(c.fetchone()['n']+19)//20)
            c.execute(sql.SQL('SELECT * FROM {} WHERE national_id=%s ORDER BY {} DESC LIMIT 20 OFFSET %s').format(sql.Identifier(table),sql.Identifier(key)),(ident,(page-1)*20))
            result[title]=[dict(**r,id=r[key],revision=R.revision(r)) for r in c.fetchall()]
    return result
