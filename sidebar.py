"""
sidebar.py — Navigation rail with touch-optimized collapse handling.
"""

import io
import pandas as pd
import streamlit as st
import ui
import auth

NAV_ITEMS = [
    ("dashboard", "📊", "الرئيسية"),
    ("students", "🎒", "الطلاب"),
    ("registration", "🏷️", "الأقسام"),
    ("payments", "💵", "الدفعات المالية"),
    ("expenses", "📦", "المصروفات والأصول"), 
    ("reports", "📈", "التقارير"),
    ("salaries", "💸", "رواتب المعلمات"),
    ("parents", "👨‍👩‍👧", "أولياء الأمور"),
    ("teachers", "👩‍🏫", "المعلمات"),
    ("classes", "📚", "سجل الصفوف"),
    ("years", "📅", "السنوات الدراسية"),
    ("records", "✏️", "إدارة السجلات"),
    ("history", "🕘", "سجل التغييرات"),
    ("admin", "🔐", "لوحة المدير"),
]


@st.dialog("💾 تصدير كامل للبيانات")
def backup_dialog(conn):
    st.write('ملف ZIP يضم جميع جداول البيانات، بما فيها الدفعات الشهرية والتخصيصات والديون وسجلات التغييرات، مع فهرس بعدد السجلات.')
    st.caption('ملفات JSON تحفظ القيم كاملة، وملف Excel لتصفحها. هذا تصدير للبيانات وليس نسخة قاعدة بيانات جاهزة للاستعادة.')
    if st.button("تجهيز ملف التصدير",type="primary",use_container_width=True):
        st.session_state.pop('verified_export',None)
        try:
            from data_export import build_export
            with st.spinner('جاري جمع البيانات والتحقق من اكتمالها...'):
                payload,manifest=build_export()
            st.session_state['verified_export']=(payload,manifest)
        except Exception:
            st.error('تعذّر إكمال التصدير والتحقق منه؛ لم يُجهّز ملف جزئي. حاول مجددًا.')
    if exported:=st.session_state.get('verified_export'):
        payload,manifest=exported
        total=sum(t['rows'] for t in manifest['tables'])
        st.success(f"تم التحقق من {len(manifest['tables'])} جدولًا و{total:,} سجلًا.")
        st.download_button('📥 تحميل البيانات كاملة',data=payload,
            file_name='kindergarten_data_export.zip',mime='application/zip',use_container_width=True)


def _get_scalar(conn, query, params=()):
    try:
        cur = conn.cursor()
        cur.execute(query, params)
        res = cur.fetchone()
        cur.close()
        if res is None:
            return 0
        if isinstance(res, dict):
            val = list(res.values())[0]
        elif isinstance(res, (tuple, list)):
            val = res[0]
        else:
            val = res
        return val if val is not None else 0
    except Exception:
        return 0


def render(conn):
    if "current_page" not in st.session_state:
        st.session_state.current_page = NAV_ITEMS[0][0]

    with st.sidebar:
        ui.render_logo(width=80)

        st.markdown("""
        <div class="brand-box">
            <h2>روضة أطفال فودي حبيب ساكرا</h2>
            <p>نظام الإدارة والمالية</p>
        </div>
        """, unsafe_allow_html=True)

        raw_students = _get_scalar(conn, "SELECT COUNT(*) FROM students WHERE archived_at IS NULL")
        try:
            students_count = int(raw_students)
        except (ValueError, TypeError):
            students_count = 0

        st.markdown(f"""
        <div class="sidebar-stat">🎒 الطلاب الحاليون: <b>{students_count}</b></div>
        """, unsafe_allow_html=True)

        def nav_button(key, icon, label):
            is_active = st.session_state.current_page == key
            if st.button(
                f"{icon}  {label}",
                key=f"nav_{key}",
                use_container_width=True,
                type="primary" if is_active else "secondary"
            ):
                st.session_state.current_page = key
                st.rerun()

        st.caption("الإدارة اليومية")
        for item in NAV_ITEMS[:5]:
            nav_button(*item)
        st.caption("المالية والتقارير")
        for item in NAV_ITEMS[5:7]:
            nav_button(*item)
        with st.expander("ملفات الروضة", expanded=st.session_state.current_page in {x[0] for x in NAV_ITEMS[7:11]}):
            for item in NAV_ITEMS[7:11]:
                nav_button(*item)
        st.caption('المراجعة والتعديل')
        for item in NAV_ITEMS[11:]:
            nav_button(*item)

        st.markdown("<div style='margin-top:16px;'></div>", unsafe_allow_html=True)
        st.markdown("---")

        # زر افتتاحي للنافذة المنبثقة في الشريط الجانبي
        if st.button("💾 تصدير كامل للبيانات", use_container_width=True, key="nav_backup_dialog"):
            backup_dialog(conn)

        st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)
        if st.button("🚪 تسجيل الخروج", use_container_width=True, key="nav_logout"):
            auth.logout()

    return st.session_state.current_page
