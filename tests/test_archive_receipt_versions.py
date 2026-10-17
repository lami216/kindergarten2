"""Old payment windows and original PDF periods must survive account changes."""
from datetime import timedelta
from io import BytesIO
import uuid

import psycopg2
import pytest
from pypdf import PdfReader
from streamlit.testing.v1 import AppTest

import db
import monthly_finance as F
import records as R
import student_debt as D
import receipt_history as H
import receipt_snapshots
from account_records import change_account
from receipt_pdf import render_receipt_pdf
from tests.test_record_management import ledger, child, row, scalar


def archive(student, route):
    if route=='records': R.cancel('students',student,actor='archive QA',reason='مغادرة')
    elif route=='profile': D.archive_student(student,actor='archive QA')
    else: change_account(student,cancel=True,actor='archive QA',reason='إغلاق الحساب')


@pytest.mark.parametrize('route',['records','profile','account'])
def test_old_500_preview_cannot_add_cash_after_archive_even_without_revision(ledger,route):
    conn,marker=ledger
    student=child(conn,marker,cash=4500)
    preview=F.payment_preview(conn,student,500)
    old_account=row(conn,'monthly_accounts',student)
    old_revision=preview['revision']
    archive(student,route)
    assert F.receipt_revision(conn,student)!=old_revision
    count=scalar(conn,'SELECT COUNT(*) FROM monthly_receipts WHERE student_id=%s',(student,))
    for expected in (old_revision,None):
        with pytest.raises(ValueError,match='مؤرشف'):
            F.take_payment(student,500,actor='stale window',expected_revision=expected)
    # Specific fees and internal callers cannot bypass the transaction guard.
    with pytest.raises(ValueError,match='مؤرشف'):
        D.pay_unpaid_fee(student,'registration',actor='stale fee window')
    transaction=db.new_transaction_connection()
    try:
        with transaction.cursor() as c,pytest.raises(ValueError,match='مؤرشف'):
            F._issue(c,old_account,500,'أهل الطفل','stale internal',str(uuid.uuid4()),'stale')
    finally:
        transaction.rollback(); transaction.close()
    with pytest.raises(ValueError,match='مؤرشف'):
        F.payment_preview(conn,student,500)
    assert scalar(conn,'SELECT COUNT(*) FROM monthly_receipts WHERE student_id=%s',(student,))==count
    assert F.projection(conn,student)['cash_paid']==4500


def test_archive_disables_old_ui_confirmation_and_does_not_report_receipt_success(ledger):
    conn,marker=ledger
    student=child(conn,marker,cash=4500)
    script='''
import os,streamlit as st,psycopg2
from psycopg2.extras import RealDictCursor
from sections.monthly_payments import financial_panel
st.session_state['auth_user']='archive browser QA'
conn=psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)
conn.autocommit=True
financial_panel(conn,st.session_state['child'],scope='stale')
conn.close()
'''
    app=AppTest.from_string(script)
    app.session_state['child']=student
    app.run(timeout=30)
    app.number_input(key=f'monthly_amount_stale_{student}_v0').set_value(500).run(timeout=30)
    next(b for b in app.button if b.key==f'monthly_preview_button_stale_{student}').click().run(timeout=30)
    assert app.session_state[f'monthly_preview_stale_{student}']['amount']==500
    archive(student,'records')
    app.checkbox(key=f'monthly_confirm_stale_{student}_v0').check()
    next(b for b in app.button if b.key==f'monthly_save_stale_{student}_v0').click().run(timeout=30)
    assert not app.exception
    assert any('أُبطلت معاينة' in item.value for item in app.info)
    assert not any('تم تسجيل الدفعة' in item.value for item in app.success)
    assert not any(b.key==f'monthly_save_stale_{student}_v0' for b in app.button)
    assert F.projection(conn,student)['cash_paid']==4500


def test_archive_does_not_disable_fresh_historical_correction_or_void(ledger):
    conn,marker=ledger
    student=child(conn,marker,cash=4500)
    receipt=scalar(conn,'SELECT receipt_id FROM monthly_receipts WHERE student_id=%s',(student,))
    archive(student,'records')
    corrected,_=F.correct_receipt(receipt,4000,'تصحيح قبض سابق',actor='archive QA',
        expected_revision=F.receipt_revision(conn,student))
    assert F.projection(conn,student)['cash_paid']==4000
    assert F.cancel_receipt(corrected,'إلغاء قبض سابق',actor='archive QA',
        expected_revision=F.receipt_revision(conn,student))
    assert F.projection(conn,student)['cash_paid']==0
    assert row(conn,'monthly_accounts',student)['archived_at'] is not None


def pdf_text(conn,receipt):
    return '\n'.join(p.extract_text() for p in PdfReader(BytesIO(render_receipt_pdf(conn,receipt))).pages)


@pytest.mark.parametrize('correct_first',[False,True])
def test_original_and_replacement_pdf_periods_do_not_follow_account_anchor(ledger,correct_first):
    conn,marker=ledger
    student=child(conn,marker,cash=4500)
    first=scalar(conn,'SELECT receipt_id FROM monthly_receipts WHERE student_id=%s',(student,))
    ids=[first]
    if correct_first:
        second,_=F.correct_receipt(first,4200,'تصحيح سابق',actor='snapshot QA')
        ids.append(second)
    F.cancel_receipt(ids[-1],'إلغاء القبض',actor='snapshot QA')
    before={ident:(H.receipt_detail(conn,ident)['items'],pdf_text(conn,ident)) for ident in ids}
    anchor=F.anniversary(F.today(),-1).replace(day=10)
    change_account(student,start_date=anchor,status='regular',actor='snapshot QA',reason='تصحيح بداية الاشتراك')
    change_account(student,start_date=anchor-timedelta(days=11),status='regular',actor='snapshot QA',reason='تصحيح آخر')
    for ident in ids:
        items,text=before[ident]
        assert H.receipt_detail(conn,ident)['items']==items
        assert pdf_text(conn,ident)==text
        assert all(item['snapshot_source']=='issued' for item in items)
    with conn.cursor() as c:
        c.execute('SELECT starts FROM monthly_periods WHERE student_id=%s AND period_no=0',(student,))
        assert c.fetchone()['starts']!=before[first][0][-1]['starts']


def test_snapshot_is_immutable_and_legacy_backfill_recovers_audited_anchor(ledger):
    conn,marker=ledger
    student=child(conn,marker,cash=4500)
    receipt=scalar(conn,'SELECT receipt_id FROM monthly_receipts WHERE student_id=%s',(student,))
    originals=H.receipt_detail(conn,receipt)['items']
    F.cancel_receipt(receipt,'إلغاء',actor='snapshot QA')
    change_account(student,start_date=F.anniversary(F.today(),-1).replace(day=10),status='regular',actor='snapshot QA',reason='تصحيح البداية')
    with conn.cursor() as c,pytest.raises(psycopg2.Error,match='immutable'):
        c.execute('UPDATE monthly_allocation_snapshots SET starts=starts-1 WHERE allocation_id=%s',(originals[-1]['allocation_id'],))
    # Simulate a pre-upgrade allocation inside a rollback-only transaction.
    # Production migration never disables the guard or deletes a snapshot.
    legacy=db.new_transaction_connection()
    try:
        with legacy.cursor() as c:
            c.execute('DROP TRIGGER monthly_allocation_snapshot_guard ON monthly_allocation_snapshots')
            c.execute('DELETE FROM monthly_allocation_snapshots WHERE allocation_id=%s',(originals[-1]['allocation_id'],))
            receipt_snapshots.migrate(c)
            c.execute('SELECT * FROM monthly_allocation_snapshots WHERE allocation_id=%s',(originals[-1]['allocation_id'],))
            recovered=c.fetchone()
            assert recovered['source']=='account_audit'
            assert recovered['starts']==originals[-1]['starts'] and recovered['ends']==originals[-1]['ends']
    finally:
        legacy.rollback(); legacy.close()
