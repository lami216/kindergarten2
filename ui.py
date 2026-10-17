"""
ui.py — Shared mobile-safe UI building blocks.
"""

import base64
from html import escape
import os
import pandas as pd
import streamlit as st

LOGO_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "school-logo.jpg")


def df(conn, sql, params=()):
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        rows = cur.fetchall()
        
        if not rows:
            cur.close()
            return pd.DataFrame()
        
        if isinstance(rows[0], dict):
            data = rows
            cols = list(rows[0].keys())
            cur.close()
            return pd.DataFrame(data, columns=cols)
        else:
            cols = [desc[0] for desc in cur.description] if cur.description else None
            cur.close()
            return pd.DataFrame(rows, columns=cols)
    except Exception as e:
        st.error(f"⚠️ Query error: {e}")
        return pd.DataFrame()


def section_header(icon, title, subtitle=""):
    st.markdown(f"<div class='section-title'>{icon} {title}</div>", unsafe_allow_html=True)
    if subtitle:
        st.markdown(f"<div class='section-sub'>{subtitle}</div>", unsafe_allow_html=True)


def form_section_title(title):
    st.markdown(f'<h3 class="form-section-title">{escape(str(title))}</h3>', unsafe_allow_html=True)


def kpi(col, icon, label, value, bg="#E9F5EC", fg="#219044", hint="", unit=""):
    # Existing currency hints become an inline unit; explanatory hints stay below.
    if hint == "أوقية قديمة" and not unit:
        unit, hint = hint, ""
    unit_html = f'<span class="kpi-unit">{escape(str(unit))}</span>' if unit else ""
    hint_html = f'<div class="kpi-hint">{escape(str(hint))}</div>' if hint else ""
    with col:
        st.markdown(f"""
        <div class="kpi-card" style="--kpi-accent:{fg}; --kpi-tint:{bg};">
            <div class="kpi-heading">
                <span class="kpi-icon" style="background:{bg}; color:{fg};" aria-hidden="true">{escape(str(icon))}</span>
                <span class="kpi-label">{escape(str(label))}</span>
            </div>
            <div class="kpi-number"><strong class="kpi-value">{escape(str(value))}</strong>{unit_html}</div>
            {hint_html}
        </div>
        """, unsafe_allow_html=True)


def navigate(page, **state):
    """Internal shortcuts use the same router as the sidebar."""
    if page=='students':
        st.session_state.pop('student_file_id',None)
        st.session_state.pop('student_select_edit',None)
    st.session_state.update(state)
    st.session_state.current_page = page
    st.rerun()



def open_record_editor(table, ident, label='تعديل كامل / حذف السجل'):
    """Open the same selected record in the complete, audited editor."""
    if st.button(label,key=f'record_manage_{table}_{ident}'):
        st.session_state['records_target']=table
        st.session_state['records_pick_'+table]=ident
        st.session_state.pop('records_open',None)
        st.session_state['current_page']='records'
        st.rerun()


def dataframe(data, **kwargs):
    """Retain native table/export UX; theme cell values without modifying data."""
    if st.session_state.get("night_mode", False) and isinstance(data, pd.DataFrame):
        data = data.style.set_properties(**{
            "background-color": "#202223", "color": "#f0f4f2",
        })
    return st.dataframe(data, **kwargs)


def plotly_chart(figure, **kwargs):
    """Copy presentation only, retaining figure traces and interactions."""
    if st.session_state.get("night_mode", False):
        import plotly.graph_objects as go
        figure = go.Figure(figure)
        figure.update_layout(paper_bgcolor="#202223", plot_bgcolor="#202223",
                             font_color="#f0f4f2")
        figure.update_xaxes(gridcolor="#303636", zerolinecolor="#303636")
        figure.update_yaxes(gridcolor="#303636", zerolinecolor="#303636")
        kwargs["theme"] = None
    return st.plotly_chart(figure, **kwargs)


def empty_state(message):
    st.info(message)


def confirm_delete(key, label="أوافق على الحذف نهائياً"):
    return st.checkbox(f"⚠️ {label}", key=key)


@st.cache_data(show_spinner=False)
def _logo_base64():
    if not os.path.exists(LOGO_PATH):
        return None
    with open(LOGO_PATH, "rb") as f:
        return base64.b64encode(f.read()).decode()


def logo_html(width=46):
    b64 = _logo_base64()
    if not b64:
        return ""
    return (f'<div style="width:{width}px; max-width:100%; aspect-ratio:1; position:relative; '
            'overflow:hidden; border-radius:50%; flex-shrink:0;">'
            f'<img alt="شعار روضة أطفال فودي حبيب ساكرا" src="data:image/jpeg;base64,{b64}" '
            'style="position:absolute; width:100%; max-width:none; height:auto; '
            'top:-64.06%; left:0; border-radius:0;" /></div>')


def render_logo(width=140, center=True, drop_shadow=True):
    logo = logo_html(width)
    if not logo:
        return
    shadow = "box-shadow:0 3px 12px rgba(0,0,0,.12);" if drop_shadow else ""
    align = "display:flex; justify-content:center;" if center else ""
    st.markdown(f"""
    <div style="{align} margin-bottom:6px;">
        <div style="width:{width}px; max-width:100%; border-radius:50%; {shadow}">{logo}</div>
    </div>
    """, unsafe_allow_html=True)


def edit_snapshot(conn, table, ident, *, scope, widget_prefix):
    """Freeze the version paired with displayed widget values, never a submit-time row."""
    import records as R
    from psycopg2 import sql
    import record_history as H
    key='edit_snapshot_'+scope
    if st.button('تحديث بيانات النموذج',key='refresh_'+key):
        st.session_state.pop(key,None)
        for name in list(st.session_state):
            if name.startswith(widget_prefix): del st.session_state[name]
        st.rerun()
    with conn.cursor() as c:
        c.execute(sql.SQL('SELECT * FROM {} WHERE {}=%s').format(sql.Identifier(table),sql.Identifier(H.TABLES[table])),(ident,))
        fresh=dict(c.fetchone())
    if key not in st.session_state: st.session_state[key]=fresh
    old=st.session_state[key]
    if R.revision(old)!=R.revision(fresh):
        st.warning('تغيّرت البيانات بعد فتح النموذج؛ حدّثه وراجع المعلومات الجديدة قبل الحفظ.')
    return old,key
