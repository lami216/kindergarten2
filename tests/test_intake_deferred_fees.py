"""New intake terms: fee choice, zero cash, monthly anniversary and corrections."""
from datetime import date
from unittest.mock import patch
import os
import uuid
import pytest
import db
import monthly_finance as F
import student_debt as D
import receipt_history as H
from tests.test_monthly_finance import connect

pytestmark=pytest.mark.skipif(not os.getenv('TEST_POSTGRES_DSN'),reason='isolated PostgreSQL required')


@pytest.fixture
def intake():
    conn=connect();conn.autocommit=True
    with patch.object(db,'new_transaction_connection',side_effect=connect):
        F.update_tariffs(1000,2000,3000,'test')
        def create(*,registration=True,gilet=True,cash=0,mode='regular'):
            token=str(uuid.uuid4());name='شروط جديدة '+token[:8]
            child=dict(full_name=name,birth_date=date(2022,1,1),gender='ذكر',
                       birth_place='',address='',medical_details='',allergies='',general_notes='',authorized_pickups=[])
            family=dict(mother_name='أم الاختبار',mother_mobile='22334455',father_name='',father_mobile='',contact_email='')
            options=dict(mode=mode,start_date='2026-01-31',registration=registration,
                charge_registration=registration,gilet=gilet,cash=cash,payer='أم الاختبار',due_at_period_end=True)
            with patch.object(F,'today',return_value=date(2026,1,31)), patch.object(H,'today',return_value=date(2026,1,31)):
                result=db.save_child_with_family(child,family,None,token,finance=options,actor='test')
                assert db.save_child_with_family(child,family,None,token,finance=options,actor='test')==(result[0],False)
            return result[0]
        yield conn,create
    conn.close()


@pytest.mark.parametrize('registration,gilet,fees',[(True,True,3000),(False,True,2000),(True,False,1000),(False,False,0)])
def test_zero_cash_selected_fees_and_completed_months(intake,registration,gilet,fees):
    conn,create=intake
    with patch.object(F,'today',return_value=date(2026,1,31)), patch.object(H,'today',return_value=date(2026,1,31)):
        before=F._total_due(conn,date(2026,1,31))
    sid=create(registration=registration,gilet=gilet)
    for day,monthly in [(date(2026,1,31),0),(date(2026,2,27),0),(date(2026,2,28),3000),(date(2026,3,30),3000),(date(2026,3,31),6000)]:
        with patch.object(F,'today',return_value=day):
            p=F.projection(conn,sid)
            assert p['due_now']==fees+monthly
            assert p['receipts']==[] and p['cash_paid']==0
            with conn.cursor() as c:
                account=F._lock(c,sid,for_payment=False)
                assert sum(max(0,x['remaining']) for x in D.current_debt(c,sid,account))==fees+monthly
    assert bool('registration' in p['fees'])==registration
    assert bool('gilet' in p['fees'])==gilet
    assert F._total_due(conn,date(2026,1,31))-before==fees


def test_paid_allocation_correction_preview_and_exemption(intake):
    conn,create=intake
    sid=create(cash=9000)
    with patch.object(F,'today',return_value=date(2026,1,31)), patch.object(H,'today',return_value=date(2026,1,31)):
        p=F.projection(conn,sid)
        assert p['cash_paid']==9000 and p['due_now']==0
        assert p['fees']['registration']['paid']==1000 and p['fees']['gilet']['paid']==2000
        receipt=p['receipts'][0]['receipt_id']
        impact=H.receipt_impact(conn,receipt,new_amount=4000)
        assert impact['currently_due']==0 and impact['projected_due']==0
        corrected,_=F.correct_receipt(receipt,4000,'تصحيح الاختبار',actor='test',token=str(uuid.uuid4()),expected_revision=impact['revision'])
        assert F.projection(conn,sid)['cash_paid']==4000
    with patch.object(F,'today',return_value=date(2026,2,28)):
        assert F.projection(conn,sid)['due_now']==2000
        F.cancel_receipt(corrected,'إلغاء الاختبار',actor='test',token=str(uuid.uuid4()))
        assert F.projection(conn,sid)['due_now']==6000
    exempt=create(registration=False,gilet=False,mode='exempt')
    with patch.object(F,'today',return_value=date(2026,3,31)):
        p=F.projection(conn,exempt)
        assert p['due_now']==0 and not p['receipts'] and not p['periods']


def test_insufficient_positive_cash_remains_atomic(intake):
    conn,create=intake
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM students');before=c.fetchone()['n']
    with pytest.raises(ValueError,match='يغطي'):
        create(cash=1)
    with conn.cursor() as c:
        c.execute('SELECT COUNT(*) AS n FROM students');assert c.fetchone()['n']==before


def test_zero_intake_freezes_first_month_before_any_file_view(intake):
    conn,create=intake
    sid=create(registration=False,gilet=False)
    with patch.object(F,'today',return_value=date(2026,2,10)):
        F.update_tariffs(1000,2000,5000,'test')
    with patch.object(F,'today',return_value=date(2026,2,28)):
        p=F.projection(conn,sid)
        assert p['periods'][0]['price']==3000 and p['due_now']==3000
        assert p['periods'][1]['price']==5000
    with patch.object(F,'today',return_value=date(2026,3,31)):
        assert F.projection(conn,sid)['due_now']==8000
