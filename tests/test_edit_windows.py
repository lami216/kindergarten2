"""User-visible save/discard paths in Streamlit's actual dialog renderer."""
from streamlit.testing.v1 import AppTest

APP = '''
import streamlit as st
import ui
st.session_state.setdefault('saved', {'name':'الاسم الأصلي','amount':1200})
st.write(st.session_state['saved'])
def editor(form):
    name=form.text_input('الاسم',value=st.session_state['saved']['name'],key='draft_name')
    amount=form.number_input('الإجمالي',value=st.session_state['saved']['amount'],key='draft_amount')
    if form.form_submit_button('حفظ'):
        if amount<1000:
            st.error('المدفوع أكبر من الإجمالي؛ صحح المبلغ.')
        else:
            st.session_state['saved']={'name':name,'amount':amount}
            ui.finish_edit()
            st.rerun()
ui.edit_window('تعديل السجل','example',editor)
'''


def button(app, label):
    return next(b for b in app.button if b.label == label)


def test_live_modal_discard_keep_save_and_recoverable_error():
    app=AppTest.from_string(APP,default_timeout=30).run()
    button(app,'تعديل السجل').click().run()
    assert not app.exception
    app.text_input(key='draft_name').set_value('مسودة غير محفوظة').run()
    app.number_input(key='draft_amount').set_value(800).run()
    button(app,'حفظ').click().run()
    assert not app.exception and app.error
    assert app.session_state['saved']['name']=='الاسم الأصلي'
    button(app,'إغلاق دون حفظ').click().run()
    assert any('تغييرات غير محفوظة' in w.value for w in app.warning)
    button(app,'متابعة التعديل').click().run()
    assert app.text_input(key='draft_name').value=='مسودة غير محفوظة'
    button(app,'إغلاق دون حفظ').click().run()
    button(app,'تجاهل التغييرات والخروج').click().run()
    button(app,'تعديل السجل').click().run()
    assert not app.exception
    assert app.text_input(key='draft_name').value=='الاسم الأصلي'
    assert app.number_input(key='draft_amount').value==1200
    app.text_input(key='draft_name').set_value('اسم محفوظ').run()
    button(app,'حفظ').click().run()
    assert not app.exception
    assert app.session_state['saved']=={'name':'اسم محفوظ','amount':1200}
    button(app,'تعديل السجل').click().run()
    assert app.text_input(key='draft_name').value=='اسم محفوظ'
    button(app,'إغلاق دون حفظ').click().run()
    assert not app.warning and not app.exception
