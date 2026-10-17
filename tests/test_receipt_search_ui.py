"""Receipt search across the whole archive and safe single-list navigation."""
import pytest
from streamlit.testing.v1 import AppTest

SOURCE='''
from unittest.mock import patch
import pandas as pd
import streamlit as st
from sections import monthly_payments as M
rows=[dict(receipt_id=i,student_id='S'+str(i),amount=1000,received_on='2026-10-01',
    payer='',state='active' if i%2 else 'cancelled',full_name='طفل '+str(i),
    father_name='',mother_name='',father_mobile=None,mother_mobile=None) for i in range(211,0,-1)]
rows[-1].update(full_name='أحمد سالم',father_mobile='22 33-44 55',mother_mobile='(46) 78-90 12')
rows[-2].update(full_name='أحمد سالم',father_mobile='22 33-44 55',mother_mobile='11111111')
def frame(conn,sql,args):
    assert 'LIMIT 200' not in sql
    return pd.DataFrame([r for r in rows if not args[0] or r['student_id']==args[0]])
def inspector(conn,ident,**kwargs): st.write('DOCUMENT '+str(ident))
with patch.object(M.ui,'df',side_effect=frame),patch.object(M.RI,'render_inspector',side_effect=inspector):
    M.render_receipts(None)
'''


def app():
    a=AppTest.from_string(SOURCE)
    a.session_state['auth_ok']=True
    return a.run(timeout=30)


def opens(a):
    return {int(b.key.rsplit('_',1)[-1]) for b in a.button if b.label=='فتح الوصل'}


@pytest.mark.parametrize('term,expected',[
    ('احمد',{1,2}),('٢٢٣٣٤٤٥٥',{1,2}),('46 78 90 12',{1}),
    ('١١١١١١١١',{2}),('[',set()),('لا يوجد',set())])
def test_literal_name_both_phones_and_empty_results(term,expected):
    a=app()
    a.text_input(key='monthly_receipt_search').set_value(term).run(timeout=30)
    assert not a.exception
    assert opens(a)==expected
    a.text_input(key='monthly_receipt_search').set_value('').run(timeout=30)
    assert not a.exception and len(opens(a))==40


def test_pagination_reaches_old_receipts_and_search_closes_previous_editor():
    a=app()
    assert len(opens(a))==40 and 1 not in opens(a)
    a.selectbox(key='finance_receipt_page').select_index(5).run(timeout=30)
    assert 1 in opens(a)
    a.button(key='finance_receipt_open_1').click().run(timeout=30)
    assert any(x.value=='DOCUMENT 1' for x in a.markdown)
    a.session_state['finance_receipt_receipt_mode']='cancel'
    a.session_state['finance_receipt_receipt_preview']={'old':True}
    a.text_input(key='monthly_receipt_search').set_value('11111111').run(timeout=30)
    assert not a.exception and opens(a)=={2}
    assert not any(x.value.startswith('DOCUMENT ') for x in a.markdown)
    assert 'finance_receipt_receipt_mode' not in a.session_state
    assert 'finance_receipt_receipt_preview' not in a.session_state


def test_child_handoff_and_show_all_clear_search_together():
    a=app()
    a.session_state['payments_receipt_child']='S1'
    a.run(timeout=30)
    assert opens(a)=={1}
    a.text_input(key='monthly_receipt_search').set_value('no match').run(timeout=30)
    assert not opens(a)
    a.button(key='receipts_clear_child').click().run(timeout=30)
    assert not a.exception and len(opens(a))==40
    assert a.text_input(key='monthly_receipt_search').value==''
    assert 'payments_receipt_child' not in a.session_state
