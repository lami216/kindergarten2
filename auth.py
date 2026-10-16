"""Username/password login backed by revocable server sessions."""

import streamlit as st
import ui
import access_control as A


def logout():
    import psycopg2
    try:
        A.revoke_current()
    except psycopg2.Error:
        # The local identity/drafts are erased even during a DB outage.
        pass
    st.rerun()


def check_authentication(conn):
    """Returns True if the manager is logged in. Renders the login screen
    and returns False otherwise (caller should st.stop())."""

    if st.session_state.get('auth_session'):
        try:
            A.refresh(conn)
            return True
        except A.AccessDenied:
            A.clear_state()
            st.info('انتهت الجلسة أو تغيرت صلاحيات الحساب. أعد تسجيل الدخول.')

    # Center column ratio
    _, mid, _ = st.columns([1, 1.2, 1])

    with mid:
        # Single Form Container (Acts as the Card)
        with st.form("login_form", clear_on_submit=False):
            # Render Logo
            ui.render_logo(width=180, center=True, drop_shadow=False)

            # Header HTML inside the form card
            st.markdown("""
            <div class="login-header">
                <h2>روضة أطفال فودي حبيب ساكرا</h2>
                <p class="subtitle-en">Jardin d’enfant FODIYE HABIB SAKERA</p>
                <div class="login-badge-wrapper">
                    <span class="login-badge">تسجيل الدخول 🔐</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            with conn.cursor() as cursor:
                cursor.execute('SELECT EXISTS(SELECT 1 FROM app_users) AS ready')
                ready=cursor.fetchone()['ready']
            if not ready:
                st.warning(
                    'لم يُجهز حساب المدير الأول بعد. يُنشئه مسؤول التشغيل باتباع تعليمات الحسابات في README.'
                )
                return False

            # Inputs
            username = st.text_input("اسم المستخدم", placeholder="أدخل اسم المستخدم")
            password = st.text_input("كلمة المرور", type="password", placeholder="أدخل كلمة المرور")
            
            # Form Submit Button
            submitted = st.form_submit_button("تسجيل الدخول", type="primary", use_container_width=True)

            if submitted:
                token=A.login(username,password)
                if token:
                    A.clear_state()
                    st.session_state['auth_session']=token
                    st.rerun()
                else:
                    st.error('تعذّر الدخول بهذه البيانات. تحقق منها، أو انتظر قليلًا بعد المحاولات المتكررة.')

    return False
