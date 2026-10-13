"""Simple operator-facing month-based finance panels; one projection for every view."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import streamlit as st
import ui
import monthly_finance as F
from sections import receipt_inspector as RI


def money_number(value):
    """Keep actual fractional cash; never silently truncate payroll/expenses."""
    exact=Decimal(str(value))
    return f"{exact:,.0f}" if exact == exact.to_integral_value() else f"{exact:,.2f}"


def fmt(value):
    return f"{money_number(value)} {F.CURRENCY}"


def actor():
    return st.session_state.get("auth_user") or "مديرة الروضة"


def financial_panel(conn, student, *, payment=True):
    result=F.projection(conn,student)
    if not result:
        info=F.account_setup_suggestion(conn,student)
        with st.expander("تهيئة الحساب الشهري لهذا الطفل",expanded=True):
            st.caption("هذه تهيئة لحساب طفل موجود دون وصل نقدي أو دين سنوي جديد. "
                       "راجع تاريخ التسجيل وقم بتصحيحه إن لزم.")
            if info["legacy_funded"]:
                st.error("لهذا الطفل وصولات مالية تاريخية. لا يجوز افتراض عملتها أو "
                         "تهيئة حساب جديد قبل المراجعة المالية.")
                return
            suggested=info["registered_on"] or info["created_on"] or F.today()
            # A historical naive timestamp could be tomorrow in Berlin.
            # Never suggest a business date later than today.
            suggested=min(suggested,F.today())
            label=("تاريخ تسجيل معروف" if info["registered_on"] else
                   "تاريخ إنشاء ملف الطفل؛ تاريخ مقترح قابل للتعديل")
            st.caption(label)
            with st.form(f"monthly_existing_setup_{student}"):
                anchor=st.date_input("بداية حساب الطفل",value=suggested,
                                     min_value=date(1990,1,1),max_value=F.today(),
                                     key=f"existing_month_start_{student}")
                kind=st.radio("حالة الرسوم",["عادي","معفي"],horizontal=True,
                              key=f"existing_month_mode_{student}")
                agree=st.checkbox("أؤكد التاريخ والحالة، ولا توجد دفعات سابقة غير مسجلة",
                                  key=f"existing_month_confirm_{student}")
                submit=st.form_submit_button("تأكيد تهيئة حساب الطفل",type="primary")
            if submit:
                try:
                    F.initialize_existing_account(student,anchor,
                      "exempt" if kind=="معفي" else "regular",agree,actor=actor())
                    st.session_state[f"existing_month_saved_{student}"]=(
                        "تم تهيئة الحساب دون إنشاء أي إيصال نقدي.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                except Exception:
                    st.error("تعذرت التهيئة؛ لم تُغيّر بيانات الطفل.")
        return
    success=st.session_state.pop(f"existing_month_saved_{student}",None)
    if success:
        st.success(success)
    with st.expander("💵 الرسوم والدفعات الشهرية", expanded=True):
        if result["exempt"]:
            st.write("التسجيل: **معفي** · الجيليه: **معفي** · الشهرية: **معفي**")
            st.caption("الإعفاء يشمل الرسوم الثلاث ولا يعني تسليم الجيليه.")
            st.caption(f"بدأ الحساب: {result['account']['start_date']}")
            return
        fees=result["fees"]
        registration=fees.get("registration",{"price":0,"paid":0})
        garment=fees.get("gilet")
        def item_state(fee):
            if fee is None:
                return "**غير مطلوبة**"
            if fee.get("waived",0):
                return ("**ألغي الدين**" if not fee["paid"] else
                    "**مدفوع جزئياً والباقي ملغى**")
            if fee["paid"] >= fee["price"]:
                return "**مدفوع بالكامل**"
            return "**باقي** " + fmt(max(0,fee["price"]-fee["paid"]-fee.get("waived",0)))
        st.write("التسجيل: " + item_state(registration))
        st.write("الجيليه: " + item_state(garment))
        st.caption("الحالة: "+("مؤرشف" if result["account"].get("archived_at") else "عادي")
                   +" · بداية الاشتراك: "+str(result["account"]["start_date"]))
        st.write(f"**مجموع القبض الصحيح: {fmt(result['cash_paid'])}**")
        st.write(f"شهور مدفوعة فعليًا: **{result['paid_periods']}**"
                 + (f" · تغطية متصلة مدفوعة حتى: {result['paid_through']}" if result["paid_through"] else
                    " · لا توجد تغطية مدفوعة متصلة حتى الآن"))
        st.write(f"**الباقي للدفع الآن: {fmt(result['due_now'])}**")
        if result["account"].get("archived_at"):
            st.warning("حساب مؤرشف: لم تُمحَ الرسوم أو الوصولات، ولن تُصدر شهور جديدة.")
        if result["future_partial"]:
            st.caption(f"فترات مستقبلية غير مستحقة بعد: {fmt(result['future_partial'])}"
                       f" · المدفوع مقدماً: {fmt(result['prepaid_paid'])}")
        st.caption(f"أول شهر غير مكتمل أو موعد الدفعة القادمة: {result['next_unpaid']}")
        today=F.today()
        def period_state(p):
            remaining=max(0,p["price"]-p["paid"]-p.get("waived",0))
            if p.get("waived",0) and remaining==0:
                return "ألغي الدين — ليس قبضاً" if not p["paid"] else "مدفوع جزئياً ودينه ملغى"
            if p["paid"]==p["price"]:
                return "مدفوع بالكامل (مقدّم)" if p["start"]>today else "مدفوع بالكامل"
            if p["paid"]>0:
                return "مدفوع جزئياً — لم يستحق" if p["start"]>today else "مدفوع جزئياً — مستحق"
            return "غير مدفوع — لم يستحق" if p["start"]>today else "غير مدفوع — مستحق"
        rows=[{"الفترة":f"{period['start']} إلى {period['end']-timedelta(days=1)}",
               "المستحق":fmt(period["price"]),"المدفوع فعلياً":fmt(period["paid"]),
               "دين ملغى":fmt(period.get("waived",0)),
               "الباقي":fmt(max(0,period["price"]-period["paid"]-period.get("waived",0))),
               "الحالة":period_state(period)}
              for period in result["periods"]]
        if rows:
            ui.dataframe(__import__("pandas").DataFrame(rows),hide_index=True,
                         use_container_width=True)
        if result["periods"]:
            with st.expander("فتح مصادر تمويل فترة شهرية — الوصولات الفعلية"):
                periods=result["periods"]
                selected_period=st.selectbox("اختر الفترة",list(range(len(periods))),
                     format_func=lambda index:
                        f"الشهر {periods[index]['no']+1} · "
                        f"{periods[index]['start']} إلى "
                        f"{periods[index]['end']-timedelta(days=1)}",
                     key=f"child_month_sources_{student}")
                period=periods[selected_period]
                with conn.cursor() as cur:
                    cur.execute("""SELECT r.receipt_id,r.state,r.received_on,
                          a.amount AS period_amount,a.active AS allocation_active
                          FROM monthly_periods p
                          JOIN monthly_allocations a ON a.period_id=p.period_id
                          JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
                          WHERE p.student_id=%s AND p.period_no=%s
                          ORDER BY r.receipt_id DESC""",
                          (student,period["no"]))
                    original_sources=[dict(x) for x in cur.fetchall()]
                if not original_sources:
                    st.caption("لا توجد وصولات لهذا الشهر؛ لا يُنشأ وصل من مجموع الفترة.")
                for source in original_sources:
                    rid=int(source["receipt_id"])
                    label=("ساري" if source["state"]=="active"
                           and source["allocation_active"] else "ملغى / مصحح")
                    left,right=st.columns([3,1])
                    left.write(f"وصل #{rid} · {source['received_on']}"
                               f" · {fmt(source['period_amount'])} · {label}")
                    if right.button("فتح الوصل",key=f"month_source_{student}_{period['no']}_{rid}"):
                        st.session_state[f"child_receipt_{student}_receipt_open"]=rid
                        st.rerun()
        with conn.cursor() as cur:
            cur.execute("""SELECT w.waiver_id,w.effective_on,w.amount,w.actor,w.reason,
                    COALESCE(f.kind, 'month ' || p.period_no::text) AS item
                    FROM monthly_waivers w
                    LEFT JOIN monthly_fees f ON f.fee_id=w.fee_id
                    LEFT JOIN monthly_periods p ON p.period_id=w.period_id
                    WHERE w.student_id=%s ORDER BY w.waiver_id DESC""",(student,))
            waivers=[dict(x) for x in cur.fetchall()]
        if waivers:
            st.markdown("##### قرارات إلغاء الدين (بدون قبض)")
            ui.dataframe(__import__("pandas").DataFrame([
                {"البند":r["item"],"أُلغي من الدين":fmt(r["amount"]),
                 "تاريخ القرار":r["effective_on"],"المسؤول":r["actor"],
                 "السبب":r["reason"]} for r in waivers
            ]),hide_index=True,use_container_width=True)
            st.caption("الرسوم الأصلية محفوظة؛ هذه القرارات ليست إيصالات ولا مبالغ مدفوعة.")
        receipts=result["receipts"]
        if payment:
            token_key=f"monthly_pay_token_{student}"
            version_key=f"monthly_pay_version_{student}"
            version=st.session_state.get(version_key,0)
            st.session_state.setdefault(token_key,str(uuid.uuid4()))
            st.markdown("##### تسجيل دفعة — مبلغ فقط")
            paid=st.number_input("المبلغ المدفوع",min_value=0,max_value=F.MAX_AMOUNT,
                       value=0,step=1,key=f"monthly_amount_{student}_v{version}")
            left,right=st.columns(2)
            if left.button("معاينة توزيع المبلغ",key=f"monthly_preview_button_{student}"):
                try:
                    st.session_state[f"monthly_preview_{student}"]=F.payment_preview(
                        conn,student,int(paid))
                except ValueError as error:
                    st.error(str(error))
            preview=st.session_state.get(f"monthly_preview_{student}")
            if preview:
                st.caption(f"معاينة توزيع {fmt(preview['amount'])} — "
                           "لا يتم إنشاء وصل إلا بعد التأكيد.")
                for item in preview["months"][:20]:
                    st.write(f"{item['start']} إلى {item['end']-timedelta(days=1)}"
                             f" · تخصيص {fmt(item['allocating'])}"
                             f" · مدفوع سابقاً {fmt(item['previously_paid'])}")
                if len(preview["months"])>20:
                    st.caption(f"وفترات إضافية عددها {len(preview['months'])-20}")
                agree=st.checkbox("أؤكد قبض المبلغ وتوزيعه كما عُرض",
                             key=f"monthly_confirm_{student}_v{version}")
                if right.button("💾 تسجيل دفعة",type="primary",
                                 disabled=not agree,
                                 key=f"monthly_save_{student}_v{version}"):
                    if int(paid)!=preview["amount"]:
                        st.error("تغيّر المبلغ بعد المعاينة؛ أعد المعاينة.")
                    else:
                        try:
                            rid,new=F.take_payment(student,int(paid),actor=actor(),
                              token=st.session_state[token_key],
                              expected_revision=preview["revision"],
                              expected_tariff=preview["tariff"])
                            st.session_state[token_key]=str(uuid.uuid4())
                            st.session_state[version_key]=version+1
                            st.session_state.pop(f"monthly_preview_{student}",None)
                            st.session_state[f"child_receipt_{student}_receipt_open"]=rid
                            st.session_state[f"monthly_payment_success_{student}"]=(
                                f"تم تسجيل الدفعة — وصل #{rid}" if new
                                else f"هذه الدفعة محفوظة بالفعل — وصل #{rid}")
                            st.rerun()
                        except ValueError as error:
                            st.error(str(error))
                        except Exception:
                            st.error("تعذّر تسجيل الدفعة؛ لم تُنشأ حركة نقدية.")
            message=st.session_state.pop(f"monthly_payment_success_{student}",None)
            if message: st.success(message)
        if receipts:
            st.markdown("##### 🧾 الوصولات الحقيقية وعملياتها")
            RI.render_receipt_list(conn,receipts,scope="child_receipt_"+student,
                                   student_id=student,limit=20)
        with st.expander("سجل العمليات الخاصة بهذا الطفل",expanded=False):
            RI.render_history(conn,scope="child_receipt_"+student+"_history",
                              student_id=student)


def render_accounts(conn):
    st.caption("الدفعات والأرصدة بالأوقية القديمة، ويمكن تهيئة الحساب للأطفال الموجودين.")
    children=ui.df(conn,"""SELECT s.student_id,s.full_name,a.status
                   FROM students s LEFT JOIN monthly_accounts a ON a.student_id=s.student_id
                   ORDER BY s.full_name,s.student_id""")
    if children.empty:
        ui.empty_state("لا يوجد أطفال بعد. أضف طفلاً من صفحة الطلاب.")
        return
    choices=[(r["student_id"],r["full_name"]) for _,r in children.iterrows()]
    chosen=st.selectbox("اختر الطفل",choices,format_func=lambda x:x[1],
                       index=None,placeholder="اختر طفلاً...",key="monthly_finance_child")
    if chosen:
        financial_panel(conn,chosen[0])


def render_settings(conn):
    st.caption("أسعار الأوقية القديمة تُضبط هنا فقط. لا تغير الفواتير السابقة.")
    current=F.prices(conn)
    with st.form("monthly_price_settings"):
        a,b,c=st.columns(3)
        reg=a.number_input("رسوم التسجيل",min_value=0,max_value=F.MAX_AMOUNT,
            step=1,value=int(current["registration"]) if current else 0)
        gilet=b.number_input("الجيليه",min_value=0,max_value=F.MAX_AMOUNT,
            step=1,value=int(current["gilet"]) if current else 0)
        month=c.number_input("رسوم الشهر",min_value=1,max_value=F.MAX_AMOUNT,
            step=1,value=int(current["tuition"]) if current else 1)
        save=st.form_submit_button("حفظ الأسعار",type="primary")
    if save:
        try:
            F.update_tariffs(int(reg),int(gilet),int(month),actor())
            st.success("حُفظت الأسعار؛ لن تتغير رسوم الشهور الصادرة أو الدفعات القديمة.")
            st.rerun()
        except ValueError as exc:
            st.error(str(exc))
        except Exception:
            st.error("تعذّر حفظ الأسعار.")


def render_receipts(conn):
    st.caption("الوصولات الأصلية والمصححة والملغاة محفوظة. افتح الوثيقة الفعلية لإجراءاتها.")
    receipts=ui.df(conn,"""SELECT r.receipt_id,r.student_id,r.amount,r.received_on,
        r.payer,r.state,s.full_name
        FROM monthly_receipts r JOIN students s ON s.student_id=r.student_id
        ORDER BY r.receipt_id DESC LIMIT 200""")
    if receipts.empty:
        ui.empty_state("لا توجد وصولات شهرية.")
        return
    term=st.text_input("بحث بالطفل أو رقم الوصل",key="monthly_receipt_search").strip()
    if term:
        receipts=receipts[receipts["full_name"].str.contains(term,case=False,
              regex=False,na=False)|receipts["receipt_id"].astype(str).str.contains(
              term,regex=False)]
    RI.render_receipt_list(conn,receipts.to_dict("records"),scope="finance_receipt",
                           limit=40)


def render_history(conn):
    RI.render_history(conn,scope="finance_receipt_history")
    selected=st.session_state.get("finance_receipt_receipt_open")
    if selected:
        RI.render_inspector(conn,selected,scope="finance_receipt")
    child=st.session_state.get("finance_receipt_history_child")
    if child:
        st.markdown("##### ملف الطفل المرتبط بالعملية")
        with conn.cursor() as cur:
            cur.execute("SELECT full_name FROM students WHERE student_id=%s",(child,))
            row=cur.fetchone()
        if row:
            st.caption(f"{row['full_name']} — السجل محفوظ حتى عند الأرشفة")
            financial_panel(conn,child,payment=False)
        else:
            st.error("لا يوجد ملف طفل لهذا الأثر؛ يتطلب مراجعة قاعدة البيانات.")


def render_report(conn):
    """Date-bounded cash view shared by finance, dashboard and reports."""
    st.markdown("##### حركة المقبوضات والمصروفات بالأوقية القديمة")
    st.caption("جميع الأرقام في هذه الصفحة بالأوقية القديمة؛ القيم النقدية تظهر دون اقتطاع كسور فعلية.")
    a,b=st.columns(2)
    current=F.today()
    start=a.date_input("من تاريخ",value=date(current.year,current.month,1),
                       key="monthly_report_start")
    end=b.date_input("إلى تاريخ",value=current,key="monthly_report_end")
    if start>end:
        st.error("تاريخ البداية بعد تاريخ النهاية.")
        return
    try:
        report=F.financial_report(conn,start,end)
        a,b,c=st.columns(3)
        a.metric("أطفال سددوا التسجيل",report["registration_children"])
        b.metric("جيليه مدفوعة",report["gilet_count"])
        c.metric("الباقي على الطلاب",money_number(report["due_now"]))
        a,b,c=st.columns(3)
        a.metric("إجمالي المقبوضات",money_number(report["total_cash"]))
        b.metric("إجمالي المصروفات",money_number(report["expenses"]))
        c.metric("الباقي من المداخيل",money_number(report["remaining_cash"]))
        rows=[
            {"البند":"قبض رسوم التسجيل","القيمة":fmt(report["registration_cash"])},
            {"البند":"قبض الجيليه","القيمة":fmt(report["gilet_cash"])},
            {"البند":"قبض الأقساط الشهرية","القيمة":fmt(report["monthly_cash"])},
            {"البند":"منها أشهر مدفوعة مقدماً (ضمن القبض الشهري)","القيمة":fmt(report["prepaid_cash"])},
            {"البند":"المصروفات التشغيلية النقدية","القيمة":fmt(report["operational_cash"])},
            {"البند":"صافي الرواتب المدفوعة نقداً","القيمة":fmt(report["salary_cash"])},
            {"البند":"السلف المدفوعة نقداً","القيمة":fmt(report["advance_cash"])},
        ]
        ui.dataframe(__import__("pandas").DataFrame(rows),
                     hide_index=True,use_container_width=True)
        st.caption("الباقي على الطلاب هو استحقاق مستقل ولا يُخصم من المقبوضات. "
                   "السلف المصروفة تُحسب مرة عند صرفها، والخصم من الراتب ليس صرفاً جديداً.")
    except Exception:
        st.error("تعذّر حساب حركة المالية.")
