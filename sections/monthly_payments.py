"""Simple operator-facing month-based finance panels; one projection for every view."""
import uuid
from datetime import date, timedelta

import streamlit as st
import ui
import monthly_finance as F


def fmt(value):
    return f"{int(value):,} {F.CURRENCY}"


def actor():
    return st.session_state.get("auth_user") or "مديرة الروضة"


def financial_panel(conn, student, *, payment=True):
    result=F.projection(conn,student)
    if not result:
        st.caption("سجل سابق: هذا الطفل ليس ضمن الحسابات الشهرية الجديدة.")
        return
    with st.expander("💵 الرسوم والدفعات الشهرية", expanded=True):
        if result["exempt"]:
            st.write("التسجيل: **معفي** · الجيليه: **معفي** · الشهرية: **معفي**")
            st.caption("الإعفاء يشمل الرسوم الثلاث ولا يعني تسليم الجيليه.")
            st.caption(f"بدأ الحساب: {result['account']['start_date']}")
            return
        fees=result["fees"]
        registration=fees.get("registration",{"price":0,"paid":0})
        garment=fees.get("gilet")
        st.write("التسجيل: " + ("**مدفوع**" if registration["paid"]>=registration["price"]
                  else "**باقي** " + fmt(registration["price"]-registration["paid"])))
        st.write("الجيليه: " + ("**غير مطلوبة**" if garment is None
                 else "**مدفوعة**" if garment["paid"]>=garment["price"]
                 else "**باقي** " + fmt(garment["price"]-garment["paid"])))
        st.write(f"الشهور المدفوعة بالكامل: **{result['paid_periods']}**"
                 + (f" · مدفوع حتى: {result['paid_through']}" if result["paid_through"] else ""))
        st.write(f"**الباقي للدفع الآن: {fmt(result['due_now'])}**")
        if result["future_partial"]:
            st.caption(f"دفعات مقدمة نحو شهر لم يبدأ بعد؛ الباقي حين يبدأ: "
                       f"{fmt(result['future_partial'])}")
        st.caption(f"أول شهر غير مكتمل أو موعد الدفعة القادمة: {result['next_unpaid']}")
        today=F.today()
        rows=[{"الفترة":f"{period['start']} إلى {period['end']-timedelta(days=1)}",
               "المطلوب":fmt(period["price"]),"المدفوع":fmt(period["paid"]),
               "الحالة":("مدفوع مقدماً" if period["paid"]==period["price"] and period["start"]>today
                        else "مدفوع" if period["paid"]==period["price"]
                        else "دفعة مقدمة جزئية" if period["start"]>today and period["paid"]
                        else "باقي" if period["start"]<=today else "لم يبدأ")}
              for period in result["periods"]]
        if rows:
            ui.dataframe(__import__("pandas").DataFrame(rows),hide_index=True,
                         use_container_width=True)
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
    st.caption("حساب الطفل الشهري مستقل عن التسجيل الدراسي القديم. المدفوع بالأوقية القديمة.")
    children=ui.df(conn,"""SELECT a.student_id,s.full_name,a.status
                   FROM monthly_accounts a JOIN students s ON s.student_id=a.student_id
                   ORDER BY s.full_name,a.student_id""")
    if children.empty:
        ui.empty_state("لا توجد حسابات شهرية بعد. أضف طفلاً من صفحة الطلاب.")
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
                    st.success("أُلغي أثر الوصل مع الاحتفاظ بسجل المراجعة.")
                else:
                    F.correct_receipt(chosen[0],int(a),reason,actor=actor(),
                                      token=str(uuid.uuid4()))
                    st.success("تم التصحيح وإعادة توزيع المبلغ في معاملة واحدة.")
                st.rerun()
            except ValueError as exc:
                st.error(str(exc))
            except Exception:
                st.error("تعذّر حفظ التعديل، ولم تتغير الأرصدة.")


def render_report(conn):
    st.markdown("##### المقبوضات الشهرية والتسجيل والجيليه")
    col1,col2=st.columns(2)
    today=F.today()
    start=col1.date_input("من تاريخ",value=date(today.year,today.month,1),
                          key="monthly_report_start")
    end=col2.date_input("إلى تاريخ",value=today,key="monthly_report_end")
    if start>end:
        st.error("تاريخ البداية بعد تاريخ النهاية.")
        return
    try:
        report=F.financial_report(conn,start,end)
        st.caption("كل المبالغ الجديدة بالأوقية القديمة. المقبوضات السنوية القديمة "
                   "تُعرض منفصلة بعملتها الأصلية ولا تُجمع مع الأوقية.")
        a,b,c=st.columns(3)
        a.metric("أطفال سددوا التسجيل",report["registration_children"])
        b.metric("مشتريات جيليه مدفوعة",report["gilet_count"])
        c.metric("الرسوم المستحقة الآن",fmt(report["due_now"]))
        rows=[
          {"البند":"رسوم التسجيل المقبوضة","المبلغ":fmt(report["registration_cash"])},
          {"البند":"الجيليه المقبوض","المبلغ":fmt(report["gilet_cash"])},
          {"البند":"الأشهر المقبوضة","المبلغ":fmt(report["monthly_cash"])},
          {"البند":"منها مبالغ أشهر مقدمة (للتوضيح، لا تجمع مرة أخرى)","المبلغ":fmt(report["prepaid_cash"])},
          {"البند":"مجموع المقبوضات الجديدة","المبلغ":fmt(report["new_cash"])},
        ]
        ui.dataframe(__import__("pandas").DataFrame(rows),hide_index=True,use_container_width=True)
        st.write(f"قبض تاريخي بعملة السجلات القديمة: **{report['historical_cash']}**"
                 " (ليس جزءاً من مجموع الأوقية)")
        st.write(f"مصروفات النظام القديم بعملته المسجلة: **{report['expenses']}**")
        st.caption("لا يجوز طرح المصروفات التاريخية من الأوقية دون توحيد عملة موثّق.")
    except Exception:
        st.error("تعذّر حساب التقرير المالي.")
