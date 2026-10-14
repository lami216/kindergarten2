import pandas as pd
from student_search import filter_children
from streamlit.testing.v1 import AppTest


def test_names_both_parent_phones_and_empty_search():
    rows=pd.DataFrame([
        dict(student_id='S1',full_name='أحمد سالم',father_name='سالم',mother_name='ليلى',father_mobile='+222 12-34-56-78',mother_mobile='87654321'),
        dict(student_id='S2',full_name='مريم محمد',father_name=None,mother_name='أم مريم',father_mobile=None,mother_mobile='22334455'),
    ])
    assert len(filter_children(rows,''))==2
    for query in ('احمد','سالم','١٢٣٤٥٦٧٨','۸۷۶۵۴۳۲۱'):
        assert list(filter_children(rows,query).student_id)==['S1']
    assert list(filter_children(rows,'22334455').student_id)==['S2']
    assert filter_children(rows,'.*').empty


def test_payment_search_clears_a_child_outside_the_results():
    app=AppTest.from_string('''
from unittest.mock import patch
import pandas as pd
import streamlit as st
import ui
from sections import monthly_payments as M
children=pd.DataFrame([
 {'student_id':'S1','full_name':'أحمد سالم','father_mobile':'12345678','mother_mobile':'87654321'},
 {'student_id':'S2','full_name':'مريم محمد','mother_mobile':'22334455'},
])
with patch.object(ui,'df',return_value=children), patch.object(M,'financial_panel',side_effect=lambda c,s:st.caption('حساب '+s)):
 M.render_accounts(None)
''').run(timeout=20)
    assert not app.exception
    assert len(app.selectbox(key='monthly_finance_child').options)==2
    app.selectbox(key='monthly_finance_child').set_value(('S1','أحمد سالم')).run()
    assert any(x.value=='حساب S1' for x in app.caption)
    app.text_input(key='monthly_finance_search').set_value('22334455').run()
    assert not app.exception
    assert app.selectbox(key='monthly_finance_child').options==['مريم محمد']
    assert app.selectbox(key='monthly_finance_child').value is None
    assert not any(x.value=='حساب S1' for x in app.caption)
    app.text_input(key='monthly_finance_search').set_value('').run()
    assert len(app.selectbox(key='monthly_finance_child').options)==2
