"""Real Streamlit/Chromium child receipt, correction/cancel, PDF and history QA.

Never runs without the disposable loopback PostgreSQL test DSN.
"""
import asyncio
import json
import os
import re
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright, expect
from pypdf import PdfReader

import db
import monthly_finance as F

BASE="http://127.0.0.1:8501"
OUT=Path("visual-evidence/child-receipt-ui")


def conn():
    c=psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],cursor_factory=RealDictCursor)
    c.autocommit=False
    return c


def query(statement,args=()):
    with conn() as c:
        with c.cursor() as q:
            q.execute(statement,args)
            return [dict(x) for x in q.fetchall()] if q.description else []


def seed():
    token=uuid.uuid4().hex[:19]
    sid,pid="S"+token,"P"+token
    name="طفل وصل "+token[:6]
    phone=str(20000000+int(token,16)%70000000)
    query("INSERT INTO parents(father_id,mother_name,mother_mobile,father_mobile) "
          "VALUES(%s,'أم وصولات',%s,%s)",(pid,phone,'1'+phone))
    query("INSERT INTO students(student_id,full_name,father_id) VALUES(%s,%s,%s)",
          (sid,name,pid))
    query("INSERT INTO monthly_accounts(student_id,status,start_date,created_by) "
          "VALUES(%s,'regular',%s,'Chromium QA')",
          (sid,F.today()-timedelta(days=12)))
    return sid,name,phone


async def goto_students(page):
    await page.goto(BASE,wait_until="domcontentloaded")
    nav=page.locator(".st-key-nav_students button")
    await nav.wait_for(state="attached",timeout=30000)
    if not await nav.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await nav.click()
    await expect(page.get_by_role("tab",name="📋 عرض / تعديل / حذف")).to_be_visible(timeout=30000)
    if await nav.is_visible():
        await page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
    await page.get_by_role("tab",name="📋 عرض / تعديل / حذف").click()


async def open_child(page,name):
    await goto_students(page)
    search=page.get_by_role("textbox",name=re.compile("ابحث باسم الطفل"))
    await search.fill(name)
    # Commit the server-side filter before opening the dropdown. Blurring this
    # field via the dropdown used to replace its options midway through click.
    await search.press("Enter")
    chooser=page.locator(".st-key-student_select_edit input[role='combobox']")
    await expect(chooser).to_be_visible(timeout=30000)
    await chooser.click()
    await chooser.fill(name)
    await page.locator('[role="listbox"]').get_by_text(name,exact=True).last.click(timeout=18000)
    # Student files contain a compact summary; financial intake is explicit.
    await expect(page.get_by_role("spinbutton",name="المبلغ المدفوع")).to_have_count(0)
    await expect(page.get_by_role("button",name="تصدير PDF")).to_have_count(0)
    await page.get_by_role("button",name="💵 تسجيل دفعة",exact=True).click()
    await expect(page.get_by_text("تسجيل دفعة — مبلغ فقط")).to_be_visible(timeout=20000)


async def toggle_theme(page,dark):
    switch=page.locator(".st-key-night_mode [role='switch']").first
    await expect(switch).to_be_visible()
    if await switch.is_checked()!=dark:
        await page.locator(".st-key-night_mode label").last.click()
    if dark: await expect(switch).to_be_checked()
    else: await expect(switch).not_to_be_checked()
    expected="rgb(16, 21, 25)" if dark else "rgb(250, 250, 249)"
    await page.wait_for_function("""expected => {
         const app=document.querySelector('.stApp');
         return app && getComputedStyle(app).backgroundColor===expected;
    }""",arg=expected,timeout=20000)
    return await page.evaluate("""() => {
        const app=document.querySelector('.stApp');
        const get=e=>e?{background:getComputedStyle(e).backgroundColor,
                         foreground:getComputedStyle(e).color}:null;
        return {app:get(app),viewport:innerWidth,
                horizontalOverflow:document.documentElement.scrollWidth>innerWidth+3};
    }""")


async def photo(page,slug,focus=None):
    OUT.mkdir(parents=True,exist_ok=True)
    if focus is not None:
        await focus.scroll_into_view_if_needed(timeout=20000)
    await page.screenshot(path=str(OUT/(slug+".png")),
                          animations="disabled",full_page=True)
    if focus is not None:
        await focus.screenshot(path=str(OUT/(slug+"_detail.png")),
                               animations="disabled")


async def run_variant(browser,width,dark):
    sid,name,phone=seed()
    ctx=await browser.new_context(viewport={"width":width,"height":850},accept_downloads=True)
    page=await ctx.new_page()
    await open_child(page,name)
    colors=await toggle_theme(page,dark)
    assert not colors["horizontalOverflow"],colors
    suffix=f"{width}_{'night' if dark else 'day'}"
    await photo(page,"child_open_"+suffix,
                page.get_by_text("تسجيل دفعة — مبلغ فقط"))
    await page.get_by_role("spinbutton",name="المبلغ المدفوع").fill("6000")
    await page.get_by_role("spinbutton",name="المبلغ المدفوع").press("Tab")
    await page.get_by_role("button",name="معاينة توزيع المبلغ").click()
    await expect(page.get_by_text("معاينة توزيع 6,000",exact=False)).to_be_visible()
    await page.get_by_text("أؤكد قبض المبلغ وتوزيعه كما عُرض",exact=False).click()
    await photo(page,"payment_preview_"+suffix)
    await page.get_by_role("button",name="💾 تسجيل دفعة").click()
    await expect(page.get_by_text("تم تسجيل الدفعة — وصل #",exact=False)).to_be_visible(timeout=30000)
    with_receipt=query("SELECT receipt_id,state,amount FROM monthly_receipts WHERE student_id=%s",(sid,))
    assert len(with_receipt)==1 and with_receipt[0]["amount"]==6000,with_receipt
    original=with_receipt[0]["receipt_id"]
    # Saving a payment does not open its document. Open it deliberately.
    await expect(page.get_by_text(f"وصل قبض #{original}")).not_to_be_visible()
    await page.get_by_role("tab",name="🧾 الوصولات",exact=True).click()
    search=page.get_by_role("textbox",name="بحث باسم الطفل أو هاتف الأب أو الأم أو رقم الوصل")
    for term in (name,phone,'1'+phone,phone.translate(str.maketrans('0123456789','٠١٢٣٤٥٦٧٨٩'))):
        await search.fill(term)
        await search.press("Enter")
        await expect(page.locator(f".st-key-finance_receipt_open_{original} button")).to_be_visible()
    await search.fill("[not a match")
    await search.press("Enter")
    await expect(page.get_by_text("لا توجد وصولات تطابق هذا البحث.",exact=True)).to_be_visible()
    await search.fill("")
    await search.press("Enter")
    await expect(page.get_by_text("لا توجد وصولات تطابق هذا البحث.",exact=True)).not_to_be_visible()
    await search.fill(str(original))
    await search.press("Enter")
    await page.locator(f".st-key-finance_receipt_open_{original} button").click()
    await expect(page.get_by_text(f"وصل قبض #{original}")).to_be_visible(timeout=20000)
    for title in ("تعديل الوصل","إلغاء الوصل","تصدير PDF","سجل العمليات"):
        await expect(page.get_by_role("button",name=title)).to_be_visible()
    await photo(page,"receipt_active_"+suffix,
                page.get_by_text(f"وصل قبض #{original}"))
    async with page.expect_download() as download_info:
        await page.get_by_role("button",name="تصدير PDF").click()
    download=await download_info.value
    assert str(original) in download.suggested_filename
    path=OUT/("pdf_"+suffix+".pdf")
    await download.save_as(str(path))
    exported=path.read_bytes()
    assert exported.startswith(b"%PDF-")
    assert len(PdfReader(BytesIO(exported)).pages)>=1

    await page.get_by_role("button",name="تعديل الوصل").click()
    await expect(page.get_by_role("spinbutton",name="المبلغ المصحح")).to_be_visible()
    await page.get_by_role("spinbutton",name="المبلغ المصحح").fill("4500")
    await page.get_by_role("spinbutton",name="المبلغ المصحح").press("Tab")
    await page.get_by_role("textbox",name="سبب التصحيح *").fill("تصحيح موثق للمتصفح")
    await page.get_by_role("button",name="معاينة أثر التصحيح").click()
    await expect(page.get_by_text("القبض القديم:",exact=False)).to_be_visible()
    await page.get_by_text("أؤكد أثر التصحيح وحفظ الوصل الأصلي في السجل",exact=False).click()
    await photo(page,"receipt_edit_confirm_"+suffix,
                page.get_by_role("button",name="تأكيد تصحيح الوصل"))
    await page.get_by_role("button",name="تأكيد تصحيح الوصل").click()
    await expect(page.get_by_text("صُحح الوصل وحُفظ الأصل",exact=False)).to_be_visible(timeout=25000)
    rows=query("SELECT receipt_id,state,amount,corrects_id FROM monthly_receipts "
               "WHERE student_id=%s ORDER BY receipt_id",(sid,))
    assert len(rows)==2 and rows[0]["state"]=="cancelled" and rows[1]["state"]=="active",rows
    corrected=rows[1]["receipt_id"]
    assert rows[1]["amount"]==4500 and rows[1]["corrects_id"]==original
    await photo(page,"receipt_corrected_"+suffix,
                page.get_by_text(f"وصل قبض #{corrected}"))

    await page.get_by_role("button",name="إلغاء الوصل").click()
    await expect(page.get_by_role("button",name="تأكيد إلغاء الوصل")).to_be_visible()
    await page.get_by_role("textbox",name="سبب إلغاء الوصل *").fill("إلغاء قبض غير صحيح")
    await page.get_by_text("أؤكد إلغاء هذا الوصل وإبقاء أصله محفوظاً",exact=False).click()
    await photo(page,"receipt_cancel_confirm_"+suffix,
                page.get_by_role("button",name="تأكيد إلغاء الوصل"))
    await page.get_by_role("button",name="تأكيد إلغاء الوصل").click()
    await expect(page.get_by_text("أُلغي الوصل #",exact=False)).to_be_visible(timeout=25000)
    assert all(r["state"]=="cancelled" for r in query(
        "SELECT state FROM monthly_receipts WHERE student_id=%s",(sid,)))
    assert query("SELECT COALESCE(SUM(a.amount),0) AS n FROM monthly_allocations a "
                 "JOIN monthly_receipts r ON r.receipt_id=a.receipt_id "
                 "WHERE r.student_id=%s AND a.active",(sid,))[0]["n"]==0
    await expect(page.get_by_text("هذا الوصل ملغى",exact=False)).to_be_visible()
    await photo(page,"receipt_cancelled_"+suffix,
                page.get_by_text(f"وصل قبض #{corrected}"))

    await page.get_by_role("button",name="سجل العمليات").click()
    # The collapsed child-history expander is also mounted in Streamlit's
    # DOM. Inspect the visible receipt-specific history, not that hidden copy.
    history_heading=page.get_by_text("سجل العمليات المالية",exact=True).filter(visible=True)
    await expect(history_heading).to_have_count(1)
    await expect(history_heading).to_be_visible()
    await photo(page,"receipt_history_"+suffix,history_heading)
    # Actual CSS must match the chosen state *after* the form and reruns.
    post=await toggle_theme(page,dark)
    assert post["app"]["background"]==colors["app"]["background"] and not post["horizontalOverflow"]
    await ctx.close()
    return {"student":sid,"original":original,"corrected":corrected,
            "theme":colors,"post":post,"pdf_bytes":len(exported)}


async def run():
    from urllib.parse import urlparse
    parsed=urlparse(os.environ.get("TEST_POSTGRES_DSN",""))
    assert parsed.hostname in ("localhost","127.0.0.1") and parsed.path=="/kindergarten_test"
    with patch.object(db,"new_transaction_connection",side_effect=conn):
        F.update_tariffs(0,0,3000,"Chromium QA")
    OUT.mkdir(parents=True,exist_ok=True)
    results={}
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(headless=True)
        for width in (390,1280):
            for dark in (False,True):
                results[f"{width}_{dark}"]=await run_variant(browser,width,dark)
        await browser.close()
    (OUT/"browser_results.json").write_text(json.dumps(results,ensure_ascii=False,
        indent=2,default=str),encoding="utf-8")
    print("Real child payment, original/corrected/void receipt, PDF, history & "
          "computed day/night CSS passed at 390 and 1280px")


if __name__=='__main__':
    from tests.qa_auth import install
    install()

if __name__=="__main__":
    asyncio.run(run())
