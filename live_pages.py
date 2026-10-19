"""Serve the ORIGINAL GitHub Pages files, backed by the existing Python ledger.

No new database, demo accounts, financial engine or client-side authority.
Run behind TLS/Nginx. Administration uses the same live interface.
"""
import argparse
import base64
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
import hashlib
import hmac
import ipaddress
import json
import logging
import re
from pathlib import Path
import secrets
import threading
import time
import tomllib
from urllib.parse import urlsplit, quote
import uuid

from psycopg2 import sql
from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse
from starlette.routing import Route

import access_control as A
import db
import expense_finance as E
import monthly_finance as F
import records as R
import school_departments as departments
import student_photos
import web_runtime as W

DESIGN_ROOT = Path(__file__).resolve().parent / 'docs'
LIVE_ROOT = Path(__file__).resolve().parent / 'live'
COOKIE = '__Host-kg_session'
MAX_BODY = 8 * 1024 * 1024
ASSETS = {'preview.css','preview.js','access-preview.js','student-profile.js','edit-windows.js',
          'school-logo.jpg','IBMPlexSansArabic-Regular.ttf','IBM_Plex_Sans_Arabic_OFL.txt'}
CONTENT_TYPES = {'.css':'text/css','.js':'text/javascript','.jpg':'image/jpeg','.ttf':'font/ttf','.txt':'text/plain'}


def index_html():
    html = (DESIGN_ROOT/'index.html').read_text(encoding='utf-8')
    html = html.replace('<script src="preview.js">','<script src="/live/runtime.js"></script>\n<script src="preview.js">')
    html=html.replace('</head>','<link rel="stylesheet" href="/live/workspace.css"></head>')
    return html.replace('</body>','<script src="/live/bridge.js"></script>\n<script src="/live/workspace.js"></script>\n</body>')


def json_ready(value):
    if isinstance(value, dict): return {str(k):json_ready(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)): return [json_ready(v) for v in value]
    if isinstance(value, (date,datetime,uuid.UUID)): return str(value)
    if isinstance(value, Decimal): return int(value) if value == value.to_integral_value() else float(value)
    return value


@contextmanager
def connection():
    conn = db.new_transaction_connection()
    try: yield conn
    finally: conn.close()


def require(conn, permission):
    with conn.cursor() as c: return A.require(c,permission,lock=False)


def rows(conn, query, params=()):
    with conn.cursor() as c:
        c.execute(query,params)
        return [dict(row) for row in c.fetchall()]


def text(data, key, maximum=2000, required=False, default=''):
    value=data.get(key,default)
    if not isinstance(value,str) or len(value)>maximum: raise ValueError('قيمة غير صحيحة: '+key)
    value=value.strip()
    if required and not value: raise ValueError('أكمل الحقل المطلوب: '+key)
    return value


def whole_amount(value, *, zero=False):
    if isinstance(value,str) and re.fullmatch(r"[0-9]{1,10}",value):
        value=int(value)
    return F.amount(value,zero=zero)


def request_token(data):
    try: return str(uuid.UUID(data['request_token']))
    except (KeyError,ValueError,TypeError,AttributeError): raise ValueError('رمز طلب الحفظ غير صالح؛ حدّث النموذج.') from None


def snapshot(conn, profile):
    """Only return fields this identity is allowed to see; never return hashes/tokens."""
    result={'students':[], 'receipts':[], 'expenses':[], 'departments':[], 'changes':[],
            'users':[], 'account_events':[], 'metrics':{}, 'overview':None,
            'prices':None, 'families':[], 'today':F.today()}
    can_students = A.can('students.view')
    can_payments = A.can('payments.view')
    if can_payments or A.can('reports.view'):
        F._ensure_all_started(result['today'])
    accounts = F.projections(conn,result['today'],materialize=False) if can_payments else {}
    parents = {}
    photos = {}
    if can_students:
        parents = {p['father_id']:p for p in rows(conn,'SELECT * FROM parents')}
        photos = {p['student_id']:p for p in rows(conn,
            'SELECT student_id,revision,image_data IS NOT NULL AS present FROM student_photos')}
        result['families'] = [dict(id=p['father_id'],father=p['father_name'] or '',
            fatherPhone=p['father_mobile'] or '',mother=p['mother_name'] or '',
            motherPhone=p['mother_mobile'] or '') for p in parents.values() if not p['archived_at']]
    visible = A.can('students.view') or A.can('payments.view') or A.can('departments.view')
    if visible:
        children=rows(conn,'''SELECT s.*,p.father_name,p.father_mobile,p.mother_name,p.mother_mobile,
            d.name AS department_name FROM students s LEFT JOIN parents p USING(father_id)
            LEFT JOIN student_departments sd USING(student_id)
            LEFT JOIN school_departments d ON d.department_id=sd.department_id
            ORDER BY s.student_id''')
        for s in children:
            child={'id':s['student_id'],'name':s['full_name'],
                'parent':s['father_name'] or s['mother_name'] or '',
                'phone':s['father_mobile'] or s['mother_mobile'] or '',
                'fatherName':s['father_name'] or '', 'fatherPhone':s['father_mobile'] or '',
                'motherName':s['mother_name'] or '', 'motherPhone':s['mother_mobile'] or '',
                'class':s['department_name'] or '', 'cancelled':bool(s['archived_at']),
                'registration':0,'gilet':0,'exempt':False,'account':None}
            if A.can('students.view'):
                raw={k:v for k,v in s.items() if k not in ('father_name','father_mobile','mother_name','mother_mobile','department_name')}
                child.update(birth=s['birth_date'],gender=s['gender'],place=s['birth_place'] or '',
                    address=s['address'] or '',health=s['medical_details'] or '',
                    allergy=s['allergies'] or '',notes=s['general_notes'] or '',pickups=s['authorized_pickups'] or [],revision=R.revision(raw))
                parent=parents.get(s['father_id'])
                child['parent_revision']=R.revision(parent) if parent else None
                child['parent_id']=s['father_id']
                photo=photos.get(s['student_id'],{'revision':0,'present':False})
                child['photo']={'revision':photo['revision'],'data':('/api/photo/'+quote(s['student_id'],safe='')+'?v='+str(photo['revision'])) if photo['present'] else None}
            if A.can('payments.view'):
                p=accounts.get(s['student_id'])
                if p:
                    child.update(ledger_revision=0,account_revision=R.revision(p['account']),paused=bool(p['account'].get('departure_on')),exempt=p['exempt'],subscription_status=p['account']['status'],registration=p['fees'].get('registration',{}).get('price',0),
                        gilet=p['fees'].get('gilet',{}).get('price',0),start=p['account']['start_date'])
                    child['account']={'paid':p['cash_paid'],'due':p['due_now'],'full':p['paid_periods'],
                        'monthPaid':sum(x['paid'] for x in p['periods']),
                        'registration_due':max(0,p['fees'].get('registration',{}).get('price',0)-p['fees'].get('registration',{}).get('paid',0)-p['fees'].get('registration',{}).get('waived',0)),
                        'gilet_due':max(0,p['fees'].get('gilet',{}).get('price',0)-p['fees'].get('gilet',{}).get('paid',0)-p['fees'].get('gilet',{}).get('waived',0))}
            result['students'].append(child)
    if A.can('payments.view'):
        result['receipts']=rows(conn,'''SELECT r.receipt_id AS id,r.student_id AS student,r.amount,
             r.received_on AS date,r.state<>'active' AS cancelled,r.payer,r.corrects_id,
             COALESCE(SUM(a.amount) FILTER(WHERE f.kind='registration'),0) AS registration,
             COALESCE(SUM(a.amount) FILTER(WHERE f.kind='gilet'),0) AS gilet,
             COALESCE(SUM(a.amount) FILTER(WHERE a.period_id IS NOT NULL),0) AS monthly
             FROM monthly_receipts r LEFT JOIN monthly_allocations a USING(receipt_id)
             LEFT JOIN monthly_fees f USING(fee_id) GROUP BY r.receipt_id ORDER BY r.receipt_id''')
        revisions={r['student_id']:int(r['revision']) for r in rows(conn,
            'SELECT student_id,MAX(audit_id) AS revision FROM monthly_audit GROUP BY student_id')}
        for r in result['receipts']: r['revision']=revisions.get(r['student'],0)
        for s in result['students']: s['ledger_revision']=revisions.get(s['id'],0)
    if A.can('expenses.view'):
        for e in rows(conn,'SELECT * FROM expenses WHERE teacher_payment_id IS NULL AND teacher_advance_id IS NULL ORDER BY expense_id'):
            result['expenses'].append({'id':e['expense_id'],'category':e['category'],'amount':e['amount'],
                'paid':e['amount_paid'],'payee':e['payee'] or '', 'date':e['expense_date'],
                'notes':e['notes'] or '', 'payment_method':e['payment_method'],
                'cancelled':bool(e['cancelled_at']),'revision':R.revision(e)})
    if A.can('departments.view'):
        result['departments']=[{'id':d['department_id'],'name':d['name'],'cancelled':bool(d['archived_at']),
                                'revision':R.revision(d)} for d in rows(conn,'SELECT * FROM school_departments ORDER BY department_id')]
    if A.can('payments.create') or A.can('students.create') or A.can('fees.view'):
        tariff=rows(conn,'SELECT registration,gilet,tuition FROM monthly_tariffs WHERE id=1')
        result['prices']={k:int(v) for k,v in tariff[0].items()} if tariff else None
    if A.can('reports.view'):
        result['overview']=F.financial_overview(conn,materialize=False)
        counts=rows(conn,'SELECT COUNT(*) FILTER(WHERE archived_at IS NULL) AS active, COUNT(*) FILTER(WHERE archived_at IS NOT NULL) AS archived FROM students')[0]
        result['overview']['students_count']=counts['active']
        result['overview']['archived_students']=counts['archived']
    if A.can('history.view'):
        result['changes']=rows(conn,'''SELECT change_id AS id,table_name AS type,record_key AS key,action,
            before_state AS before,after_state AS after,reason,actor,actor_user_id AS "actorId",happened_at AS time
            FROM record_changes ORDER BY change_id DESC LIMIT 500''')[::-1]
    if profile['is_admin']:
        result['users']=A.list_users(conn)
        result['account_events']=A.access_history(conn)
        for u in result['users']: result['metrics'][str(u['user_id'])]=A.employee_metrics(conn,u['user_id'])
    else: result['metrics'][str(profile['user_id'])]=A.employee_metrics(conn,profile['user_id'])
    import live_tools
    result['tools']=live_tools.catalog()
    result['field_labels']=live_tools.LABELS
    result['resources']={key:dict(title=label,actions=list(actions)) for key,(label,actions) in A.RESOURCES.items()}
    return result


def pickup_values(value):
    if not isinstance(value,list) or len(value)>12:raise ValueError('أضف حتى 12 شخصًا مخولًا بالاستلام.')
    result=[]
    for item in value:
        if not isinstance(item,dict):raise ValueError('بيانات الاستلام غير صحيحة.')
        name=text(item,'name',100);phone=text(item,'phone',30);relation=text(item,'relation',100)
        if not (name or phone or relation):continue
        if not name or not phone:raise ValueError('كل شخص مخول يحتاج اسمًا ورقم هاتف.')
        result.append(dict(name=name,phone=phone,relation=relation))
    return result


def edit_student(conn, data, actor):
    """Student, family and optional department update share ONE transaction."""
    ident=text(data,'id',20,True)
    values=data.get('values',{})
    if not isinstance(values,dict): raise ValueError('بيانات التعديل غير صالحة.')
    reason=text(data,'reason',2000,True)
    with conn.cursor() as c:
        A.require(c,'students.edit')
        old=R._lock(c,'students',ident,text(data,'revision',64,True))
        if old['archived_at']: raise ValueError('ملف الطالب مؤرشف.')
        import record_history as H
        H.context(c,actor,reason)
        fields={'name':('full_name',100),'birth':('birth_date',10),'gender':('gender',10),
                'place':('birth_place',100),'address':('address',2000),'health':('medical_details',2000),
                'allergy':('allergies',2000),'notes':('general_notes',2000)}
        update={column:text(values,key,limit) for key,(column,limit) in fields.items() if key in values}
        if 'birth_date' in update:
            if not update['birth_date']: update['birth_date']=None
            else: update['birth_date']=date.fromisoformat(update['birth_date'])
        if 'pickups' in values:
            update['authorized_pickups']=pickup_values(values['pickups'])
        R._validate(c,'students',old,update)
        if update:
            c.execute(sql.SQL('UPDATE students SET {} WHERE student_id=%s').format(
                sql.SQL(',').join(sql.SQL('{}=%s').format(sql.Identifier(k)) for k in update)),
                [json.dumps(v,ensure_ascii=False) if k=='authorized_pickups' else v for k,v in update.items()]+[ident])
        parent_fields={'fatherName':'father_name','fatherPhone':'father_mobile','motherName':'mother_name','motherPhone':'mother_mobile'}
        if any(k in values for k in parent_fields):
            A.require(c,'parents.edit')
            parent=R._lock(c,'parents',old['father_id'],text(data,'parent_revision',64,True))
            updates={column:text(values,key,20 if 'Phone' in key else 100) for key,column in parent_fields.items() if key in values}
            R._validate(c,'parents',parent,updates)
            c.execute(sql.SQL('UPDATE parents SET {} WHERE father_id=%s').format(sql.SQL(',').join(
                sql.SQL('{}=%s').format(sql.Identifier(k)) for k in updates)),[*updates.values(),old['father_id']])
        if 'class' in values:
            c.execute('SELECT d.name FROM student_departments sd JOIN school_departments d USING(department_id) WHERE sd.student_id=%s',(ident,))
            before=c.fetchone()
            name=text(values,'class',100)
            if name!=(before['name'] if before else ''):
                raise ValueError('انقل الطفل من نافذة نقل الأطفال في صفحة الأقسام، ثم أعد فتح الملف.')
    conn.commit()
    return {'id':ident}


def mutate(conn, operation, data, profile):
    actor=profile['username']
    if operation=='tools.list':
        import live_tools
        return live_tools.list_rows(conn,data)
    if operation=='tools.change':
        import live_tools
        return live_tools.change(conn,data,profile)
    if operation in ('reports.read','reports.export'):
        import live_tools
        value=live_tools.reports(conn,data)
        if operation=='reports.read':return value
        import pandas as pd
        from sections.reports import _to_excel
        items=value['items'] or [{'البند':key,'القيمة':val} for key,val in value['summary'].items()]
        return _to_excel(pd.DataFrame(items))
    if operation=='fees.save':
        if data.get('confirmed') is not True:raise ValueError('أكد تحديث الرسوم.')
        F.update_tariffs(whole_amount(data.get('registration'),zero=True),whole_amount(data.get('gilet'),zero=True),
            whole_amount(data.get('tuition')),actor,reason=text(data,'reason',2000,True),expected=text(data,'revision',64,True))
        return {'ok':True}
    if operation=='accounts.setup':
        F.initialize_existing_account(text(data,'student',20,True),text(data,'start',10,True),
            text(data,'status',12,True),data.get('confirmed') is True,actor=actor)
        return {'ok':True}
    if operation=='expenses.settle':
        if data.get('confirmed') is not True:raise ValueError('أكد صرف المبلغ الفعلي.')
        E.settle(data.get('id'),data.get('amount'),on_date=text(data,'date',10,True),actor=actor,
            reason=text(data,'reason',2000,True),token=request_token(data),expected=text(data,'revision',64,True))
        return {'ok':True}
    if operation=='payroll.save':
        import payroll_finance as P
        payment_day=date.fromisoformat(text(data,'date',10,True))
        if not date(1990,1,1)<=payment_day<=F.today():raise ValueError('تاريخ الصرف غير صالح أو مستقبلي.')
        if data.get('confirmed') is not True:raise ValueError('أكد الصرف النقدي الفعلي.')
        if data.get('kind')=='advance':
            ident,created=P.save_advance(text(data,'teacher',20,True),text(data,'month',7,True),data.get('amount'),
                notes=text(data,'notes'),actor=actor,token=request_token(data),on_date=date.fromisoformat(text(data,'date',10,True)))
        else:
            ident,created=P.save_salary(text(data,'teacher',20,True),text(data,'month',7,True),data.get('base'),
                data.get('bonus',0),data.get('deductions',0),notes=text(data,'notes'),actor=actor,
                token=request_token(data),on_date=date.fromisoformat(text(data,'date',10,True)))
        return {'id':ident,'created':created}
    if operation=='students.create':
        name=text(data,'name',100,True)
        birthday=date.fromisoformat(text(data,'birth',10,True))
        if birthday>F.today(): raise ValueError('تاريخ الميلاد لا يكون مستقبليًا.')
        gender=text(data,'gender',10,True)
        if gender not in ('ذكر','أنثى'): raise ValueError('الجنس غير صحيح.')
        child=dict(full_name=name,birth_date=birthday,gender=gender,birth_place=text(data,'place',100),
            address=text(data,'address'),medical_details=text(data,'health'),allergies=text(data,'allergy'),
            general_notes=text(data,'notes'),authorized_pickups=[])
        family=dict(father_name=text(data,'father',100),father_mobile=text(data,'fatherPhone',20),
            mother_name=text(data,'mother',100),mother_mobile=text(data,'motherPhone',20),contact_email='')
        mode=text(data,'mode',10,True)
        if mode not in ('pay','none','exempt'): raise ValueError('طريقة الرسوم غير صحيحة.')
        cash=whole_amount(data.get('amount',0),zero=True) if mode=='pay' else 0
        finance=dict(mode='exempt' if mode=='exempt' else 'regular',start_date=str(F.today()),
            charge_registration=bool(data.get('registration')) if mode=='pay' else mode!='exempt',
            due_at_period_end=True,registration=bool(data.get('registration')) if mode=='pay' else False,
            gilet=bool(data.get('gilet')) if mode=='pay' else False,cash=cash,
            payer=family['father_name'] or family['mother_name'])
        photo=decode_photo(data['photo']) if data.get('photo') else None
        existing_parent=text(data,'existing_parent_id',20) or None
        if existing_parent:
            require(conn,'students.view')
            existing=rows(conn,'''SELECT father_name,mother_name FROM parents
                WHERE father_id=%s AND archived_at IS NULL''',(existing_parent,))
            if not existing: raise ValueError('الأسرة المحددة غير متاحة؛ حدّث النموذج.')
            finance['payer']=existing[0]['father_name'] or existing[0]['mother_name'] or ''
        ident,created=db.save_child_with_family(child,family,existing_parent,request_token(data),finance=finance,actor=actor,photo=photo)
        return {'id':ident,'created':created}
    if operation=='students.restore':
        import student_debt as D
        if data.get('confirmed') is not True: raise ValueError('أكد استرجاع الملف للمراجعة.')
        D.restore_student(text(data,'student',20,True),actor=actor,reason=text(data,'reason',2000,True),
            expected=text(data,'revision',64,True),expected_account=data.get('account_revision'))
        return {'ok':True}
    if operation=='students.waive':
        import student_debt as D
        if data.get('confirmed') is not True or type(data.get('revision')) is not int:
            raise ValueError('راجع الدين وأكد إسقاطه دون قبض.')
        due=whole_amount(data.get('due'))
        value,created=D.waive_debt(text(data,'student',20,True),text(data,'reason',2000,True),True,
            actor=actor,token=request_token(data),expected_revision=data['revision'],expected_due=due)
        return {'waived':value,'created':created}
    if operation=='students.edit': return edit_student(conn,data,actor)
    if operation=='departments.create': return {'id':departments.create(text(data,'name',100,True))}
    if operation=='departments.transfer':
        ids=data.get('ids')
        if not isinstance(ids,list) or not ids or len(ids)>1000 or not all(isinstance(x,str) and len(x)<=20 for x in ids): raise ValueError('اختر الأطفال المطلوب نقلهم.')
        return {'changed':departments.transfer(ids,data.get('department_id'),actor=actor)}
    if operation=='payments.preview':
        require(conn,'payments.create')
        return F.payment_preview(conn,text(data,'student',20,True),whole_amount(data.get('amount')))
    if operation=='payments.create':
        if data.get('confirmed') is not True: raise ValueError('أكد قبض المبلغ بعد مراجعة المعاينة.')
        if type(data.get('revision')) is not int or type(data.get('tariff')) is not int: raise ValueError('أعد معاينة توزيع المبلغ.')
        receipt,created=F.take_payment(text(data,'student',20,True),whole_amount(data.get('amount')),payer=text(data,'payer'),
            token=request_token(data),actor=actor,expected_revision=data['revision'],expected_tariff=data['tariff'])
        return {'id':receipt,'created':created}
    if operation=='fees.collect':
        import student_debt as D
        if data.get('confirmed') is not True: raise ValueError('أكد قبض الرسم فعليًا.')
        ident,created=D.pay_unpaid_fee(text(data,'student',20,True),text(data,'kind',20,True),actor=actor,
            token=request_token(data),expected_due=data.get('due'))
        return {'id':ident,'created':created}
    if operation=='expenses.create':
        ident,created=E.create(category=text(data,'category',100,True),amount_total=data.get('amount'),
            amount_paid=data.get('paid'),expense_date=date.fromisoformat(text(data,'date',10,True)),
            payee=text(data,'payee'),notes=text(data,'notes'),token=request_token(data))
        return {'id':ident,'created':created}
    if operation=='records.change':
        kind=text(data,'type',30,True);ident=data.get('id')
        cancel=data.get('mode')=='cancel';reason=text(data,'reason',2000,True)
        if data.get('confirmed') is not True: raise ValueError('أكد التغيير أولًا.')
        values=data.get('values',{})
        if not isinstance(values,dict): raise ValueError('بيانات التعديل غير صالحة.')
        if kind=='receipts':
            revision=data.get('revision')
            if type(revision) is not int: raise ValueError('أعد فتح الوصل.')
            if cancel:
                changed=F.cancel_receipt(ident,reason,actor=actor,token=request_token(data),expected_revision=revision)
                return {'id':int(ident),'cancelled':changed}
            new_id,created=F.correct_receipt(ident,whole_amount(values.get('amount')),reason,actor=actor,token=request_token(data),
                received_on=date.fromisoformat(text(values,'date',10,True)),expected_revision=revision)
            return {'id':new_id,'created':created}
        if kind=='expenses':
            revision=text(data,'revision',64,True)
            if cancel: return {'id':E.cancel(ident,actor=actor,reason=reason,token=request_token(data),expected=revision)}
            existing=rows(conn,'SELECT * FROM expenses WHERE expense_id=%s',(ident,))
            if not existing: raise ValueError('المصروف غير موجود.')
            return {'id':E.correct(ident,amount_total=values.get('amount'),amount_paid=values.get('paid'),
                category=text(values,'category',100,True),expense_date=date.fromisoformat(text(values,'date',10,True)),
                payee=text(values,'payee'),notes=existing[0]['notes'] or '',reason=reason,actor=actor,
                token=request_token(data),expected=revision,payment_method=existing[0]['payment_method'])}
        if kind=='students':
            if cancel:
                R.cancel('students',ident,actor=actor,reason=reason,expected=text(data,'revision',64,True),waive_student_debt=False)
                return {'id':ident}
            return edit_student(conn,{**data,'id':str(ident)},actor)
        if kind=='departments':
            revision=text(data,'revision',64,True)
            if cancel: R.cancel('school_departments',ident,actor=actor,reason=reason,expected=revision,destination=data.get('destination'))
            else: R.edit('school_departments',ident,{'name':text(values,'name',100,True)},actor=actor,reason=reason,expected=revision)
            return {'id':ident}
        raise ValueError('نوع سجل غير مدعوم.')
    if operation=='photos.save':
        expected=data.get('revision')
        if type(expected) is not int: raise ValueError('أعد فتح صورة الطالب.')
        remove=data.get('remove') is True
        if remove and data.get('confirmed') is not True: raise ValueError('أكد حذف الصورة فقط.')
        return {'revision':student_photos.save(text(data,'student',20,True),None if remove else decode_photo(data.get('photo')),
            expected=expected,remove=remove,reason=text(data,'reason',2000,True))}
    if operation=='users.save':
        require(conn,'admin.manage')
        permissions=data.get('permissions',[])
        if not isinstance(permissions,list) or not all(isinstance(p,str) for p in permissions): raise ValueError('صلاحيات غير صحيحة.')
        uid=data.get('id')
        if uid and type(data.get('version')) is not int: raise ValueError('أعد فتح الحساب.')
        password=data.get('password') or None
        return {'id':A.save_user(employee_name=text(data,'name',100,True),name=None if uid else text(data,'username',64,True),
            password=password,is_admin=False,permissions=permissions,active=data.get('active') is not False,
            user_id=uid,expected_version=data.get('version'))}
    raise ValueError('إجراء غير معروف.')


def decode_photo(value):
    if not isinstance(value,str) or len(value)>7*1024*1024: raise ValueError('حجم الصورة أكبر من المسموح.')
    try: return base64.b64decode(value,validate=True)
    except (ValueError,TypeError): raise ValueError('ملف الصورة غير صالح.') from None


class LoginAttempts:
    """Bound expensive login attempts per verified peer, not per proxy header.

    Success releases its reservation; failures stay in the five-minute window.
    The persistent account-specific limiter remains authoritative across workers.
    """
    def __init__(self):
        self.attempts = {}
        self.lock = threading.Lock()

    def reserve(self, peer):
        with self.lock:
            now = time.monotonic()
            if len(self.attempts)>4096:
                self.attempts = {k:v for k,v in self.attempts.items() if now-v[0]<=300}
            started,count = self.attempts.get(peer,(now,0))
            if now-started>300: started,count = now,0
            if count>=20: return None
            self.attempts[peer] = (started,count+1)
            return started

    def success(self, peer, started):
        with self.lock:
            current,count = self.attempts.get(peer,(None,0))
            if current==started:
                self.attempts[peer] = (current,max(0,count-1))


def make_app(dsn, public_origin, *, management=False, trusted_proxies=()):
    parsed=urlsplit(public_origin)
    if parsed.scheme!='https' or not parsed.hostname or parsed.path not in ('','/') or parsed.query or parsed.fragment or parsed.username:
        raise ValueError('Public origin must be an exact HTTPS origin.')
    origin=public_origin.rstrip('/')
    csrf_key=secrets.token_bytes(32)
    # Explicit IPs only: never trust '*' or an arbitrary forwarded header.
    proxies=[str(ipaddress.ip_address(ip)) for ip in trusted_proxies]
    attempts=LoginAttempts()
    def csrf(token): return hmac.new(csrf_key,token.encode(),hashlib.sha256).hexdigest()
    def execute(token, operation, data=None):
        with W.request_context(dsn,{'auth_session':token} if token else {}):
            if operation=='login': return A.login(data.get('username'),data.get('password'))
            with connection() as conn:
                profile=A.refresh(conn);conn.commit();conn.autocommit=True
                db.assert_schema_ready(conn)
                if operation=='session': return {'user':profile,'csrf':csrf(token),'management':False}
                if operation=='snapshot': return snapshot(conn,profile)
                if operation=='logout': A.revoke_current();return {'ok':True}
                if operation=='pdf':
                    require(conn,'payments.view')
                    import receipt_pdf
                    return receipt_pdf.render_receipt_pdf(conn,int(data['id']))
                if operation=='photo':
                    p=student_photos.get(conn,data['id'])
                    return bytes(p['image_data']) if p.get('image_data') else None
                if operation=='backup':
                    require(conn,'admin.export')
                    import data_export
                    return data_export.build_export()[0]
                if operation=='fees.read':
                    require(conn,'fees.view')
                    row=rows(conn,'SELECT * FROM monthly_tariffs WHERE id=1')
                    return {'values':{k:int(row[0][k]) if row else 0 for k in ('registration','gilet','tuition')},
                        'revision':R.revision({k:row[0][k] for k in ('registration','gilet','tuition')} if row else {})}
                if operation=='teachers.options':
                    require(conn,'salaries.view')
                    return rows(conn,'''SELECT national_id AS id,full_name AS name,
                        COALESCE(display_national_id,national_id) AS identity,salary,archived_at IS NOT NULL AS archived
                        FROM teachers ORDER BY full_name,national_id''')
                conn.autocommit=False
                return mutate(conn,operation,data,profile)
    async def api(request: Request):
        operation=request.path_params['operation']
        expected_method='GET' if operation in ('session','snapshot','fees.read','teachers.options') else 'POST'
        if request.method!=expected_method: return JSONResponse({'error':'طريقة غير مسموحة.'},405)
        token=request.cookies.get(COOKIE,'')
        if len(token)>256: return JSONResponse({'error':'جلسة غير صالحة.'},401)
        data={}
        if request.method=='POST':
            if request.headers.get('origin')!=origin: return JSONResponse({'error':'مصدر الطلب غير مسموح.'},403)
            if request.headers.get('content-type','').split(';')[0]!='application/json': return JSONResponse({'error':'صيغة الطلب غير مدعومة.'},415)
            if operation!='login' and (not token or not hmac.compare_digest(request.headers.get('x-csrf-token',''),csrf(token))):
                return JSONResponse({'error':'حدّث الصفحة ثم أعد المحاولة.'},403)
            parts=[];size=0
            async for part in request.stream():
                size+=len(part)
                if size>MAX_BODY: return JSONResponse({'error':'الطلب أكبر من المسموح.'},413)
                parts.append(part)
            try:
                data=json.loads(b''.join(parts))
                if not isinstance(data,dict): raise ValueError()
            except (ValueError,UnicodeDecodeError): return JSONResponse({'error':'بيانات الطلب غير صالحة.'},400)
        try:
            if operation=='login':
                if not isinstance(data.get('username'),str) or not isinstance(data.get('password'),str) or not 1<=len(data['password'])<=128 or len(data['username'])>128:
                    return JSONResponse({'error':'تعذّر الدخول بهذه البيانات.'},401)
                peer=request.client.host if request.client else 'unknown'
                reservation=attempts.reserve(peer)
                if reservation is None: return JSONResponse({'error':'محاولات كثيرة؛ انتظر قليلًا.'},429)
                new_token=await run_in_threadpool(execute,None,'login',data)
                if not new_token: return JSONResponse({'error':'تعذّر الدخول بهذه البيانات.'},401)
                attempts.success(peer,reservation)
                response=JSONResponse({'ok':True})
                response.set_cookie(COOKIE,new_token,secure=True,httponly=True,samesite='strict',path='/')
                return response
            if not token: return JSONResponse({'error':'سجّل الدخول أولًا.'},401)
            result=await run_in_threadpool(execute,token,operation,data)
            if operation=='reports.export':
                return Response(result,media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                    headers={'Content-Disposition':'attachment; filename="report.xlsx"'})
            response=JSONResponse(json_ready(result))
            if operation=='logout': response.delete_cookie(COOKIE,path='/',secure=True,httponly=True,samesite='strict')
            return response
        except __import__('schema_migrations').SchemaNotReady:
            return JSONResponse({'error':'التطبيق قيد التحديث؛ أكمل ترحيل قاعدة البيانات أولًا.'},503)
        except A.AccessDenied:
            return JSONResponse({'error':'انتهت الجلسة أو ليس لديك صلاحية لهذا الإجراء.'},403 if token else 401)
        except __import__('psycopg2').errors.StringDataRightTruncation:
            return JSONResponse({'error':'أحد الحقول أطول من المسموح؛ قصّر القيمة وأعد الحفظ.'},422)
        except __import__('psycopg2').errors.UniqueViolation:
            return JSONResponse({'error':'توجد بيانات بالهوية نفسها؛ راجع السجل قبل الإضافة.'},422)
        except (ValueError,TypeError,KeyError) as exc:
            return JSONResponse({'error':str(exc) if isinstance(exc,ValueError) else 'قيمة غير صحيحة في الطلب.'},422)
        except Exception:
            logging.getLogger(__name__).error('Live Pages operation failed; operation=%s incident=%s',operation,uuid.uuid4().hex)
            return JSONResponse({'error':'تعذّر حفظ العملية. لم نعرض بيانات اتصال أو تفاصيل داخلية.'},500)
    async def private_file(request):
        token=request.cookies.get(COOKIE,'')
        if not token or len(token)>256: return JSONResponse({'error':'سجّل الدخول أولًا.'},401)
        kind=request.path_params['kind'];ident=request.path_params['ident']
        if kind not in ('photo','receipt','download'): return Response(status_code=404)
        if len(ident)>20: return Response(status_code=404)
        try:
            if kind=='download' and ident!='backup':return Response(status_code=404)
            value=await run_in_threadpool(execute,token,'backup' if kind=='download' else 'photo' if kind=='photo' else 'pdf',{'id':ident})
            if value is None: return Response(status_code=404)
            headers={'Content-Disposition':'attachment; filename="kindergarten-data.zip"'} if kind=='download' else {'Content-Disposition':f'attachment; filename="receipt-{int(ident)}.pdf"'} if kind=='receipt' else {}
            return Response(value,media_type='application/zip' if kind=='download' else 'image/jpeg' if kind=='photo' else 'application/pdf',headers=headers)
        except __import__('schema_migrations').SchemaNotReady: return Response(status_code=503)
        except A.AccessDenied: return Response(status_code=403)
        except (ValueError,TypeError): return Response(status_code=404)
    async def health(request):
        def ready():
            with W.request_context(dsn),connection() as conn: db.assert_schema_ready(conn)
        try: await run_in_threadpool(ready);return JSONResponse({'status':'ready'})
        except Exception: return JSONResponse({'status':'not_ready'},503)
    async def asset(request):
        filename=request.path_params['filename']
        if filename not in ASSETS: return Response(status_code=404)
        return Response((DESIGN_ROOT/filename).read_bytes(),media_type=CONTENT_TYPES[Path(filename).suffix])
    async def runtime(request):
        return Response('window.LIVE_APP=true;window.LIVE_TODAY='+json.dumps(str(F.today()))+';',media_type='text/javascript')
    async def bridge(request): return Response((LIVE_ROOT/'bridge.js').read_bytes(),media_type='text/javascript')
    async def workspace_asset(request):
        name=request.path_params['name']
        if name not in ('workspace.js','workspace.css'):return Response(status_code=404)
        return Response((LIVE_ROOT/name).read_bytes(),media_type='text/javascript' if name.endswith('.js') else 'text/css')
    async def index(request): return Response(index_html(),media_type='text/html')
    app=Starlette(routes=[Route('/',index),Route('/api/health',health),
        Route('/api/{kind}/{ident}',private_file),
        Route('/api/{operation}',api,methods=['GET','POST']),
        Route('/live/runtime.js',runtime),Route('/live/bridge.js',bridge),Route('/live/{name}',workspace_asset),Route('/{filename}',asset)])
    async def headers(request,call_next):
        if request.headers.get('host')!=parsed.netloc: return Response(status_code=400)
        response=await call_next(request)
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'X-Frame-Options':'DENY','Referrer-Policy':'same-origin',
            'Content-Security-Policy':"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"})
        return response
    app.add_middleware(BaseHTTPMiddleware,dispatch=headers)
    if proxies:
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware
        app.add_middleware(ProxyHeadersMiddleware,trusted_hosts=proxies)
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',required=True)
    parser.add_argument('--origin',required=True)
    parser.add_argument('--host',default='127.0.0.1',choices=('127.0.0.1','::1'))
    parser.add_argument('--port',type=int,default=8520)
    parser.add_argument('--management',action='store_true')
    parser.add_argument('--trusted-proxy',action='append',default=[],
                        help='Explicit reverse-proxy IP; repeat for additional trusted proxies.')
    args=parser.parse_args()
    config=tomllib.loads(Path(args.config).read_text(encoding='utf-8'))
    import uvicorn
    uvicorn.run(make_app(config['postgres']['url'],args.origin,management=args.management,trusted_proxies=args.trusted_proxy),
        host=args.host,port=args.port,proxy_headers=False,access_log=False)


if __name__=='__main__': main()
