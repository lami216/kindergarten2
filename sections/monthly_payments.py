"""Simple operator-facing month-based finance panels; one projection for every view."""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import streamlit as st
import ui
import monthly_finance as F


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
        # A historical, timezone-naive timestamp may already have been stored
        # as tomorrow by an older Berlin session; do not offer a future date.
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
        st.write(f"الشهور المدفوعة بالكامل: **{result['paid_periods']}**"
                 + (f" · مدفوع حتى: {result['paid_through']}" if result["paid_through"] else ""))
        st.write(f"**الباقي للدفع الآن: {fmt(result['due_now'])}**")
        if result["account"].get("archived_at"):
            st.warning("حساب مؤرشف: لم تُمحَ الرسوم أو الوصولات، ولن تُصدر شهور جديدة.")
        if result["future_partial"]:
            st.caption(f"دفعات مقدمة نحو شهر لم يبدأ بعد؛ الباقي حين يبدأ: "
                       f"{fmt(result['future_partial'])}")
        st.caption(f"أول شهر غير مكتمل أو موعد الدفعة القادمة: {result['next_unpaid']}")
        today=F.today()
        rows=[{"الفترة":f"{period['start']} إلى {period['end']-timedelta(days=1)}",
               "المطلوب":fmt(period["price"]),"المدفوع":fmt(period["paid"]),"الملغى":fmt(period.get("waived",0)),
               "الحالة":("ألغي الدين" if period.get("waived",0) and not period["paid"]
                        else "مدفوع جزئياً والباقي ملغى" if period.get("waived",0)
                        else "مدفوع مقدماً" if period["paid"]==period["price"] and period["start"]>today
                        else "مدفوع" if period["paid"]==period["price"]
                        else "دفعة مقدمة جزئية" if period["start"]>today and period["paid"]
                        else "باقي" if period["start"]<=today else "لم يبدأ")}
              for period in result["periods"]]
        if rows:
            ui.dataframe(__import__("pandas").DataFrame(rows),hide_index=True,
                         use_container_width=True)
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
        if receipts:
            st.markdown("##### 🧾 آخر الدفعات")
            ui.dataframe(__import__("pandas").DataFrame([
                {"رقم الوصل":r["receipt_id"],"التاريخ":r["received_on"],
                 "المبلغ":fmt(r["amount"]),"الدافع":r["payer"],
                 "الحالة":"ساري" if r["state"]=="active" else "ملغى"}
                for r in receipts[:20]]),hide_index=True,use_container_width=True)
        if payment:
            # No default 3000: the next visible form must never implicitly
            # create a second receipt after the successful-save rerun.
            token_key=f"monthly_pay_token_{student}"
            version_key=f"monthly_pay_version_{student}"
            version=st.session_state.get(version_key,0)
            if token_key not in st.session_state:
                st.session_state[token_key]=str(uuid.uuid4())
            with st.form(f"monthly_simple_pay_{student}_v{version}"):
                paid=st.number_input("المبلغ المدفوع",min_value=0,max_value=F.MAX_AMOUNT,
                           value=0,step=1,key=f"monthly_amount_{student}_v{version}")
                submit=st.form_submit_button("💾 تسجيل دفعة",type="primary",
                                               use_container_width=True)
            if submit:
                try:
                    rid,new=F.take_payment(student,int(paid),actor=actor(),
                                             token=st.session_state[token_key])
                    st.session_state[token_key]=str(uuid.uuid4())
                    st.session_state[version_key]=version+1
                    st.session_state["monthly_payment_success"]=(
                        f"تم تسجيل الدفعة — وصل #{rid}" if new
                        else f"هذه الدفعة محفوظة بالفعل — وصل #{rid}")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                except Exception:
                    st.error("تعذّر تسجيل الدفعة؛ لم يُخصم المبلغ. حاول مجدداً.")
            message=st.session_state.pop("monthly_payment_success",None)
            if message:
                st.success(message)


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
    last=st.session_state.pop("monthly_receipt_feedback",None)
    if last:
        st.success(last)
    receipts=ui.df(conn,"""SELECT r.student_id, r.receipt_id AS "الوصل",s.full_name AS "الطفل",
       r.amount AS "المبلغ",r.received_on AS "التاريخ",
       r.payer AS "الدافع",r.state AS "الحالة"
       FROM monthly_receipts r JOIN students s ON s.student_id=r.student_id
       ORDER BY r.receipt_id DESC""")
    if receipts.empty:
        ui.empty_state("لا توجد وصولات شهرية.")
        return
    display=receipts.copy()
    display["الحالة"]=display["الحالة"].replace({"active":"ساري","cancelled":"ملغى"})
    ui.dataframe(display.drop(columns=["student_id"]),hide_index=True,use_container_width=True)
    choices=[(int(r["الوصل"]),str(r["الطفل"])) for _,r in receipts.iterrows()]
    chosen=st.selectbox("اختر الوصل",choices,index=None,
                        format_func=lambda x:f"وصل #{x[0]} — {x[1]}")
    if not chosen:
        return
    row=receipts[receipts["الوصل"]==chosen[0]].iloc[0]
    if st.button("🖨️ عرض / طباعة الوصل"):
        import receipt
        status=F.projection(conn,row["student_id"],materialize=True)
        receipt.render_receipt(
            receipt_id=chosen[0],date=str(row["التاريخ"]),student_name=row["الطفل"],
            payer=row["الدافع"],amount=f"{int(row['المبلغ']):,}",
            reason="رسوم الروضة الشهرية" if row["الحالة"]=="active" else "وصل ملغى",
            remaining=f"{status['due_now']:,}",
            currency=F.CURRENCY,remaining_label="المتبقي المستحق الآن",
        )
    if row["الحالة"]!="active":
        st.warning("وصل ملغى؛ محفوظ في سجل المراجعة ولا يضاف إلى المقبوضات.")
        return
    with st.expander("تصحيح أو إلغاء الوصل"):
        with st.form(f"monthly_receipt_modify_{chosen[0]}"):
            a=st.number_input("المبلغ الصحيح",min_value=1,max_value=F.MAX_AMOUNT,
                              step=1,value=int(row["المبلغ"]))
            reason=st.text_input("سبب التصحيح أو الإلغاء *")
            left,right=st.columns(2)
            fix=left.form_submit_button("حفظ التصحيح")
            void=right.form_submit_button("إلغاء الوصل")
        if fix or void:
            try:
                if void:
                    F.cancel_receipt(chosen[0],reason,actor=actor())
                    st.session_state["monthly_receipt_feedback"]="أُلغي أثر الوصل مع الاحتفاظ بسجل المراجعة."
                else:
                    F.correct_receipt(chosen[0],int(a),reason,actor=actor(),
                                      token=str(uuid.uuid4()))
                    st.session_state["monthly_receipt_feedback"]="تم التصحيح وإعادة توزيع المبلغ في معاملة واحدة."
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("تعذّر حفظ التعديل، ولم تتغير الأرصدة.")


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
