"""Shared receipt inspector and audit UI, used by child and finance contexts."""
import os
import uuid
from datetime import timedelta

import streamlit as st
import monthly_finance as F
import receipt_history as H


def _authorized():
    # The live app is gated by auth.check_authentication() before routing.
    # Only the isolated, explicitly flagged QA runner bypasses that UI gate.
    from urllib.parse import urlparse
    dsn=os.environ.get("TEST_POSTGRES_DSN","")
    test=urlparse(dsn) if dsn else None
    disposable=(test is not None and test.hostname in ("localhost","127.0.0.1")
                and test.path=="/kindergarten_test")
    if not (st.session_state.get("auth_ok") or disposable):
        raise PermissionError("يلزم تسجيل الدخول للاطلاع على الوثائق المالية.")


def _actor():
    _authorized()
    actor=str(st.session_state.get("auth_user") or "").strip()
    if not actor: raise PermissionError("هوية المستخدم غير متاحة.")
    return actor


def _amount(value):
    return f"{int(value):,} {F.CURRENCY}"


def _stamp(value):
    if value is None: return "غير مسجل"
    from zoneinfo import ZoneInfo
    try:
        return value.astimezone(ZoneInfo("Africa/Nouakchott")).strftime("%Y-%m-%d %H:%M")
    except (AttributeError,ValueError):
        return str(value)


def _state(receipt,data):
    if receipt["state"]!="active":
        return "مصحح (الأصل محفوظ)" if data["replacements"] else "ملغى"
    if receipt["corrects_id"]: return "ساري — نسخة مصححة"
    return "ساري"


def _feedback(scope,message):
    st.session_state[f"{scope}_receipt_feedback"]=message


def render_receipt_list(conn,receipts,*,scope,student_id=None,limit=30):
    """Open the exact cash document from a compact actual-receipt row."""
    _authorized()
    selected=st.session_state.get(f"{scope}_receipt_open")
    for row in receipts[:limit]:
        ident=int(row["receipt_id"])
        cols=st.columns([1.0,1.2,1.1,1.1])
        cols[0].write(f"**#{ident}**")
        cols[1].caption(str(row["received_on"]))
        cols[2].write(_amount(row["amount"]))
        if cols[3].button("فتح الوصل",key=f"{scope}_open_{ident}",
                          use_container_width=True):
            st.session_state[f"{scope}_receipt_open"]=ident
            st.session_state.pop(f"{scope}_receipt_mode",None)
            st.rerun()
        st.caption("ساري" if row["state"]=="active" else "ملغى / مصحح")
        st.divider()
    if len(receipts)>limit:
        st.caption(f"يعرض آخر {limit} من {len(receipts)} وصلاً؛ بقية الوصولات في سجل المالية.")
    if selected:
        render_inspector(conn,selected,scope=scope,student_id=student_id)


def render_inspector(conn,receipt_id,*,scope,student_id=None):
    """Action buttons are native and directly visible on the opened source."""
    _authorized()
    key=f"{scope}_receipt_"
    notice=st.session_state.pop(key+"feedback",None)
    if notice: st.success(notice)
    try:
        data=H.receipt_detail(conn,receipt_id,student_id=student_id)
    except ValueError as error:
        st.error(str(error))
        return
    r=data["receipt"]
    st.markdown(f"##### 🧾 وصل قبض #{int(r['receipt_id'])}")
    st.write(f"**الحالة: {_state(r,data)}**")
    a,b,c=st.columns(3)
    a.metric("المبلغ المثبت",_amount(r["amount"]))
    b.metric("تاريخ القبض",str(r["received_on"]))
    c.metric("الطفل",r["student_name"])
    st.caption(f"الدافع: {r['payer'] or 'غير مسجل'} · رقم الوصل ثابت: #{int(r['receipt_id'])}")
    if r["state"]!="active":
        st.error("هذا الوصل ملغى ولا يدخل في المقبوضات. بياناته الأصلية محفوظة.")
        st.write(f"سبب القرار: **{r['cancel_reason'] or 'غير مسجل'}**")
        st.caption(f"المسؤول: {r['cancelled_by'] or 'غير مسجل'}"
                   f" · وقت القرار بتوقيت نواكشوط: {_stamp(r['cancelled_at'])}")
    if r["corrects_id"]:
        if st.button(f"↩ فتح الوصل الأصلي #{r['corrects_id']}",
                     key=key+"parent_"+str(receipt_id)):
            st.session_state[f"{scope}_receipt_open"]=int(r["corrects_id"])
            st.rerun()
    for replacement in data["replacements"]:
        rid=replacement["receipt_id"]
        if st.button(f"↪ فتح الوصل المصحح #{rid}",
                     key=key+"child_"+str(rid)):
            st.session_state[f"{scope}_receipt_open"]=int(rid)
            st.rerun()
    st.markdown("**توزيع المبلغ الأصلي على الرسوم والأشهر**")
    for item in data["items"]:
        cols=st.columns([2.4,1.1])
        cols[0].write(H.receipt_line(item))
        cols[1].write(_amount(item["amount"]))
        st.caption(f"رسم محفوظ: {_amount(item['stored_fee_price'])} · "
                   +("تخصيص ساري" if item["active"] else "أثر تاريخي مستبعد"))
    st.caption("مجموع التخصيصات: "+_amount(sum(int(x["amount"]) for x in data["items"])))
    # Generate PDF from the exact id and archived original on the SERVER.
    try:
        from receipt_pdf import render_receipt_pdf
        pdf=render_receipt_pdf(conn,receipt_id,student_id=student_id)
    except Exception:
        pdf=None
        st.error("تعذّر تجهيز PDF العربي؛ لم تتغير بيانات الوصل.")
    buttons=st.columns(4)
    if r["state"]=="active":
        if buttons[0].button("تعديل الوصل",key=key+"edit_"+str(receipt_id)):
            st.session_state[key+"mode"]="edit"
            st.session_state.pop(key+"preview",None)
            st.rerun()
        if buttons[1].button("إلغاء الوصل",key=key+"cancel_"+str(receipt_id)):
            st.session_state[key+"mode"]="cancel"
            st.session_state[key+"cancel_revision"]=F.receipt_revision(conn,r["student_id"])
            st.rerun()
    else:
        buttons[0].caption("لا يمكن تعديل أو إلغاء وصل غير ساري.")
    buttons[2].download_button("تصدير PDF",data=pdf or b"",
              file_name=f"kindergarten-receipt-{receipt_id}.pdf",
              mime="application/pdf",disabled=not bool(pdf),
              key=key+"pdf_"+str(receipt_id),use_container_width=True)
    if buttons[3].button("سجل العمليات",key=key+"history_"+str(receipt_id)):
        st.session_state[key+"mode"]="history"
        st.rerun()
    mode=st.session_state.get(key+"mode")
    if mode=="edit" and r["state"]=="active":
        st.markdown("###### تصحيح الوصل — لا يمحو الأصل")
        amount=st.number_input("المبلغ المصحح",min_value=1,max_value=F.MAX_AMOUNT,
                  value=int(r["amount"]),step=1,key=key+str(receipt_id)+"_amount")
        day=st.date_input("تاريخ القبض الصحيح",value=r["received_on"],
                  min_value=__import__("datetime").date(1990,1,1),max_value=F.today(),
                  key=key+str(receipt_id)+"_date")
        payer=st.text_input("الدافع",value=r["payer"] or "",
                  key=key+str(receipt_id)+"_payer")
        reason=st.text_input("سبب التصحيح *",key=key+str(receipt_id)+"_reason")
        left,right=st.columns(2)
        if left.button("معاينة أثر التصحيح",key=key+"preview_button"):
            try:
                preview=H.receipt_impact(conn,receipt_id,
                         new_amount=int(amount),new_date=day,new_payer=payer)
                preview["reason"]=reason.strip()
                st.session_state[key+"preview"]=preview
            except ValueError as error:
                st.error(str(error))
        snapshot=st.session_state.get(key+"preview")
        if snapshot and snapshot["receipt"]["receipt"]["receipt_id"]==receipt_id:
            st.info(f"القبض القديم: {_amount(r['amount'])} · "
                    f"القبض الجديد: {_amount(snapshot['new_amount'])} · "
                    f"الفرق: {_amount(snapshot['cash_delta'])}. "
                    "التخصيص النهائي يعاد حسابه من الرسوم والفترات المحفوظة.")
            st.caption("فترات/رسوم الوصل الأصلي: "+
                       "، ".join(snapshot["affected_periods"]))
            confirmed=st.checkbox("أؤكد أثر التصحيح وحفظ الوصل الأصلي في السجل",
                        key=key+str(receipt_id)+"_edit_confirm")
            if right.button("تأكيد تصحيح الوصل",key=key+"commit_edit",
                             disabled=not confirmed):
                if (int(amount)!=snapshot["new_amount"] or day!=snapshot["new_date"]
                    or payer.strip()!=snapshot["new_payer"]
                    or reason.strip()!=snapshot["reason"] or not reason.strip()):
                    st.error("تغيّرت بيانات التصحيح منذ المعاينة؛ أعد المعاينة.")
                else:
                    try:
                        token_key=key+str(receipt_id)+"_edit_token"
                        st.session_state.setdefault(token_key,str(uuid.uuid4()))
                        new_id,_=F.correct_receipt(receipt_id,int(amount),reason,
                            actor=_actor(),token=st.session_state[token_key],
                            received_on=day,payer=payer,
                            expected_revision=snapshot["revision"])
                        st.session_state[token_key]=str(uuid.uuid4())
                        st.session_state[f"{scope}_receipt_open"]=new_id
                        st.session_state.pop(key+"preview",None)
                        st.session_state.pop(key+"mode",None)
                        _feedback(scope,f"صُحح الوصل وحُفظ الأصل؛ النسخة السارية #{new_id}.")
                        st.rerun()
                    except ValueError as error:
                        st.error(str(error))
                    except Exception:
                        st.error("فشل التصحيح؛ لم تتغير المقبوضات.")
        if st.button("رجوع دون تصحيح",key=key+"back_edit"):
            st.session_state.pop(key+"mode",None)
            st.session_state.pop(key+"preview",None)
            st.rerun()
    elif mode=="cancel" and r["state"]=="active":
        st.warning("الإلغاء يستبعد قبض هذا الوصل من جميع التقارير المصححة، "
                   "ويعيد المتبقي دون تسجيل مصروف أو استرداد وهمي.")
        with st.form(key+"cancel_form_"+str(receipt_id)):
            reason=st.text_area("سبب إلغاء الوصل *")
            confirm=st.checkbox("أؤكد إلغاء هذا الوصل وإبقاء أصله محفوظاً")
            submit=st.form_submit_button("تأكيد إلغاء الوصل",type="primary")
        if submit:
            if not confirm: st.error("يلزم تأكيد الإلغاء صراحةً.")
            else:
                try:
                    token_key=key+str(receipt_id)+"_cancel_token"
                    st.session_state.setdefault(token_key,str(uuid.uuid4()))
                    F.cancel_receipt(receipt_id,reason,actor=_actor(),
                      token=st.session_state[token_key],
                      expected_revision=st.session_state.get(key+"cancel_revision"))
                    st.session_state[token_key]=str(uuid.uuid4())
                    st.session_state.pop(key+"mode",None)
                    _feedback(scope,f"أُلغي الوصل #{receipt_id} دون إنشاء مصروف.")
                    st.rerun()
                except ValueError as error:
                    st.error(str(error))
                except Exception:
                    st.error("تعذّر إلغاء الوصل؛ بقي أثره كما هو.")
        if st.button("رجوع — إبقاء الوصل سارياً",key=key+"back_cancel"):
            st.session_state.pop(key+"mode",None)
            st.rerun()
    elif mode=="history":
        render_history(conn,scope=scope+"_specific_"+str(receipt_id),
                       receipt_id=receipt_id,student_id=student_id,show_open=False)
        if st.button("إغلاق سجل هذا الوصل",key=key+"back_history"):
            st.session_state.pop(key+"mode",None)
            st.rerun()


def _change_summary(row):
    old=row.get("before_state") or {}
    new=row.get("after_state") or {}
    pieces=[]
    if "amount" in old or "amount" in new:
        pieces.append(f"المبلغ {old.get('amount','—')} ← {new.get('amount','—')}")
    if "receipt_id" in old and "receipt_id" in new:
        pieces.append(f"الأصل #{old['receipt_id']} ← الجديد #{new['receipt_id']}")
    if "gross_due" in old or "waived" in new:
        pieces.append(f"إلغاء دين {new.get('waived','—')} دون قبض")
    if row["action"]=="student_archived": pieces.append("احتفاظ بالأرشيف المالي")
    return " · ".join(pieces) or "تفاصيل موثقة في سجل التدقيق"


def render_history(conn,*,scope,student_id=None,receipt_id=None,show_open=True):
    """A single history query/UI for global, child and source-receipt contexts."""
    _authorized()
    st.markdown("##### سجل العمليات المالية")
    a,b=st.columns([2,1])
    search=a.text_input("بحث بالطفل / رقم الوصل / المسبب",key=scope+"_q")
    action=b.selectbox("نوع العملية",["الكل"]+list(H.ACTION_LABELS),
               format_func=lambda k:H.ACTION_LABELS.get(k,"الكل"),
               key=scope+"_action")
    dates=st.checkbox("تصفية بتاريخ القرار",key=scope+"_dates")
    start=end=None
    if dates:
        a,b=st.columns(2)
        start=a.date_input("من تاريخ القرار",value=F.today()-timedelta(days=30),
                           key=scope+"_from")
        end=b.date_input("إلى تاريخ القرار",value=F.today(),key=scope+"_to")
    page=st.number_input("صفحة السجل",min_value=1,max_value=1000000,step=1,
                         key=scope+"_page")
    try:
        result=H.history(conn,student_id=student_id,receipt_id=receipt_id,
                 action=None if action=="الكل" else action,query=search,
                 start=start,end=end,page=int(page),page_size=12)
    except ValueError as error:
        st.error(str(error))
        return
    st.caption(f"النتائج المطابقة: {result['total']} · الصفحة {page} من "
               f"{max(1,result['pages'])} · الترتيب بالأحدث")
    for row in result["rows"]:
        rid=row["receipt_id"]
        title=H.ACTION_LABELS.get(row["action"],row["action"])
        st.write(f"**{title}** · {_stamp(row['happened_at'])} · "
                 f"{row['student_name'] or row['student_id'] or 'غير محدد'}")
        st.caption(f"الوصل: {('#'+str(rid)) if rid else '—'} · "
                   f"المسؤول: {row['actor'] or 'غير مسجل'} · "
                   f"السبب: {row['reason'] or 'لم يسجل سبب'}")
        st.caption(_change_summary(row))
        if show_open and rid:
            if st.button(f"فتح مصدر العملية — وصل #{rid}",
                         key=scope+"_source_"+str(row["audit_id"])):
                target_scope=scope.split("_history")[0] if "_history" in scope else scope
                st.session_state[f"{target_scope}_receipt_open"]=int(rid)
                st.rerun()
        with st.expander("تفاصيل قبل / بعد",expanded=False):
            before=row.get("before_state") or {}
            after=row.get("after_state") or {}
            for label,entry in [("قبل",before),("بعد",after)]:
                amount=entry.get("amount",entry.get("gross_due",entry.get("waived","—")))
                number=entry.get("receipt_id",entry.get("old_receipt","—"))
                date=entry.get("received_on","—")
                allocations=entry.get("allocations")
                st.write(f"{label}: المبلغ {amount} · الوصل {number} · تاريخ القبض {date}")
                if isinstance(allocations,list):
                    st.caption(f"التخصيصات المحفوظة: {len(allocations)}")
        st.divider()
    if result["total"] and page>result["pages"]:
        st.warning("الصفحة المطلوبة بعد آخر نتيجة. اختر صفحة أقل.")
