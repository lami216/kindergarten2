"""Actual isolated Chromium finance acceptance with scrolled Streamlit regions.

This script never uses production auth or connection data; screenshots are
emulated viewports rather than physical-device inspection.
"""
import asyncio
import json
import os
import re
import uuid
from datetime import date
from pathlib import Path
from urllib.parse import urlparse
from unittest.mock import patch

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright, expect

import db
import monthly_finance as F

BASE="http://127.0.0.1:8501"
OUT=Path("visual-evidence")
WIDTHS=(360,390,430,768,1280)


def connection():
    dsn=os.environ["TEST_POSTGRES_DSN"]
    parsed=urlparse(dsn)
    if parsed.hostname not in ("localhost","127.0.0.1","::1") or (
            parsed.path!="/kindergarten_test"):
        raise RuntimeError("Browser QA refuses all databases except local kindergarten_test")
    return psycopg2.connect(dsn,cursor_factory=RealDictCursor)


def read(sql,params=()):
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql,params)
            return cur.fetchall()


def make_child(name,finance=None):
    child={"full_name":name,"birth_date":date(2022,1,5),"gender":"ذكر",
           "birth_place":"","address":"","medical_details":"","allergies":"",
           "general_notes":"","authorized_pickups":[]}
    family={"father_name":"","father_mobile":"","mother_name":"أم فحص مالي",
            "mother_mobile":"0599001234","contact_email":""}
    with patch.object(db,"new_transaction_connection",side_effect=connection):
        return db.save_child_with_family(child,family,None,str(uuid.uuid4()),
                                         finance=finance,actor="chromium")[0]


async def open_section(page,section):
    await page.goto(BASE,wait_until="domcontentloaded")
    nav=page.locator(f".st-key-nav_{section} button")
    await nav.wait_for(state="attached",timeout=30000)
    if not await nav.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await nav.click()
    heading={"students":"إدارة الطلاب","payments":"الدفعات المالية",
             "reports":"التقارير والتصدير","dashboard":"الرئيسية",
             "expenses":"المصروفات","salaries":"رواتب المعلمات"}[section]
    await expect(page.locator(".section-title")).to_contain_text(heading,timeout=30000)
    if await nav.is_visible():
        await page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
    await page.wait_for_timeout(220)


async def night_theme(page,night):
    toggle=page.locator(".st-key-night_mode [role='switch']").first
    await expect(toggle).to_be_visible()
    if await toggle.is_checked()!=night:
        await page.locator(".st-key-night_mode label").last.click()
        if night:
            await expect(toggle).to_be_checked()
        else:
            await expect(toggle).not_to_be_checked()


async def capture(page,locator,slug,manifest):
    """Scroll the real content scroller; a full-page top capture is not enough."""
    await locator.scroll_into_view_if_needed(timeout=20000)
    await page.wait_for_timeout(220)
    region=await locator.bounding_box()
    metrics=await page.evaluate("""() => ({
        windowWidth:innerWidth,documentWidth:document.documentElement.scrollWidth,
        scrollers:[...document.querySelectorAll('*')].filter(e =>
            e.scrollHeight>e.clientHeight+20 && getComputedStyle(e).overflowY!='visible'
        ).map(e=>({testid:e.getAttribute('data-testid'),scrollTop:e.scrollTop,
                   clientHeight:e.clientHeight,scrollHeight:e.scrollHeight})).slice(0,12)
    })""")
    assert region and region["height"]>0 and region["width"]>0,(slug,region)
    assert metrics["documentWidth"]<=metrics["windowWidth"]+3, (slug,metrics)
    await page.screenshot(path=str(OUT/(slug+".png")),animations="disabled")
    # Element screenshot guarantees the account/controls themselves were captured,
    # not just the top app viewport.
    await locator.screenshot(path=str(OUT/(slug+"_region.png")),animations="disabled")
    manifest.append({"image":slug+".png","region":slug+"_region.png",
                     "geometry":region,"metrics":metrics})


async def select_account(page,name,*,has_account=True):
    await page.get_by_role("tab",name=re.compile("حسابات الأطفال")).click()
    select=page.locator(".st-key-monthly_finance_child")
    if await select.count()==0:
        await page.screenshot(path=str(OUT/"debug_missing_account_picker.png"),
                              animations="disabled")
        print("MISSING_ACCOUNT_PICKER_TEXT:",
              (await page.locator(".stApp").inner_text())[-1700:],flush=True)
        raise AssertionError("Accounts selectbox not rendered after selecting finance tab")
    combo=select.get_by_role("combobox").first
    await combo.click()
    await combo.fill(name)
    # BaseWeb's virtualized search options aren't necessarily exposed with
    # role=option at all widths, but their visible label is stable.
    await page.locator('[role="listbox"]').get_by_text(name,exact=True).last.click(timeout=15000)
    if has_account:
        await expect(page.get_by_text("💵 الرسوم والدفعات الشهرية",exact=False)).to_be_visible()
    else:
        await expect(page.get_by_text("تهيئة الحساب الشهري لهذا الطفل")).to_be_visible()


async def run():
    OUT.mkdir(exist_ok=True)
    with patch.object(db,"new_transaction_connection",side_effect=connection):
        F.update_tariffs(1000,2000,3000,"chromium-fixture")
    prefix=uuid.uuid4().hex[:8]
    anchor=F.today()
    regular_name="مالي جزئي "+prefix
    exempt_name="مالي معفى "+prefix
    unfunded_name="مالي قديم "+prefix
    sid=make_child(regular_name,{"mode":"regular","cash":12000,"registration":True,
         "gilet":True,"start_date":anchor.isoformat(),"payer":"أم فحص"})
    first_receipt=read("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s "
                       "ORDER BY receipt_id LIMIT 1",(sid,))[0]["receipt_id"]
    # An ordinary payment fills half of the earliest unpaid period.
    with patch.object(db,"new_transaction_connection",side_effect=connection):
        F.take_payment(sid,1500,actor="chromium")
    exempt_sid=make_child(exempt_name,{"mode":"exempt","cash":0,
                     "registration":False,"gilet":False,"start_date":anchor.isoformat()})
    unfunded_sid=make_child(unfunded_name)
    teacher_id="T"+uuid.uuid4().hex[:19]
    with connection() as qa_conn:
        with qa_conn.cursor() as cur:
            cur.execute("INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,%s,4000)",
                        (teacher_id,"معلمة مالية للمتصفح "+prefix))
    assert read("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(unfunded_sid,))[0]["n"]==0
    manifest=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        # Exact filled region, exemption selection, price/report/dashboard/account
        # in every requested width and theme.
        for width in WIDTHS:
            for night in (False,True):
                context=await browser.new_context(viewport={"width":width,"height":850})
                page=await context.new_page()
                suffix=f"{width}_{'dark' if night else 'light'}"
                await open_section(page,"students")
                await night_theme(page,night)
                await page.locator(".st-key-kid_name input").fill("معاينة جديدة")
                await page.locator(".st-key-kid_mother_name input").fill("أم معاينة")
                await page.locator(".st-key-kid_mother_phone input").fill("0599112233")
                await page.get_by_text("دفع",exact=True).first.click()
                await page.locator(".st-key-kid_initial_registration label").first.click()
                await page.locator(".st-key-kid_initial_gilet label").first.click()
                amount=page.locator(".st-key-kid_initial_amount input")
                await amount.fill("12000")
                await amount.press("Tab")
                await expect(amount).to_have_value("12000")
                await capture(page,amount,f"finance_choice_filled_{suffix}",manifest)
                await amount.fill("2000")
                await amount.press("Tab")
                await capture(page,page.get_by_test_id("stAlertContentWarning")
                    .get_by_text("المبلغ لا يغطي",exact=False).first,
                    f"finance_insufficient_preview_{suffix}",manifest)
                await page.get_by_text("معفي",exact=True).first.click()
                await expect(page.get_by_text("يشمل الإعفاء التسجيل",exact=False)).to_be_visible()
                await capture(page,page.get_by_text("يشمل الإعفاء التسجيل",exact=False),
                              f"finance_exempt_choice_{suffix}",manifest)

                await open_section(page,"payments")
                await night_theme(page,night)
                await select_account(page,regular_name)
                await page.get_by_text("تفاصيل الأشهر والرسوم",exact=True).click()
                await capture(page,page.get_by_text("أول شهر غير مكتمل أو موعد الدفعة القادمة",exact=False),
                              f"finance_account_partial_{suffix}",manifest)
                await select_account(page,exempt_name)
                await capture(page,page.get_by_text("الإعفاء يمنع رسومًا جديدة، ولا يلغي دينًا سابقًا",exact=False),
                              f"finance_exempt_saved_{suffix}",manifest)
                await select_account(page,unfunded_name,has_account=False)
                await capture(page,page.get_by_role("button",name="تأكيد تهيئة حساب الطفل"),
                              f"finance_existing_setup_{suffix}",manifest)
                await page.get_by_role("tab",name=re.compile("إعدادات الرسوم")).click()
                await capture(page,page.get_by_role("button",name="حفظ الأسعار"),
                              f"finance_tariffs_{suffix}",manifest)
                await page.get_by_role("tab",name=re.compile("تقرير النقدية")).click()
                await capture(page,page.get_by_text("الباقي من المداخيل",exact=False).first,
                              f"finance_cash_report_{suffix}",manifest)
                await page.get_by_role("tab",name=re.compile("الوصولات")).click()
                await page.get_by_role("textbox",name="بحث باسم الطفل أو هاتف الأب أو الأم أو رقم الوصل").fill(str(first_receipt))
                await page.get_by_role("textbox",name="بحث باسم الطفل أو هاتف الأب أو الأم أو رقم الوصل").press("Enter")
                specific=page.locator(f".st-key-finance_receipt_open_{first_receipt} button")
                await expect(specific).to_be_visible(timeout=30000)
                await specific.click()
                await expect(page.get_by_role("tabpanel",name="🧾 الوصولات",exact=True)
                             .get_by_text(f"وصل قبض #{first_receipt}",exact=False)).to_be_visible(timeout=30000)
                await page.get_by_role("button",name="تعديل الوصل").click()
                await capture(page,page.get_by_role("button",name="معاينة أثر التصحيح"),
                              f"finance_receipt_edit_{suffix}",manifest)
                await open_section(page,"dashboard")
                await night_theme(page,night)
                await capture(page,page.get_by_text("الباقي من المداخيل",exact=False).first,
                              f"finance_dashboard_{suffix}",manifest)
                await open_section(page,"expenses")
                await night_theme(page,night)
                await capture(page,page.get_by_role("button",name="حفظ المصروف"),
                              f"finance_expense_form_{suffix}",manifest)
                await open_section(page,"salaries")
                await night_theme(page,night)
                await capture(page,page.get_by_role("button",name=re.compile("تسجيل الصرف وطباعة")),
                              f"finance_salary_form_{suffix}",manifest)
                await page.get_by_role("tab",name=re.compile("سلف المعلمات")).click()
                await capture(page,page.get_by_role("button",name="💾 تسجيل السلفة المدفوعة"),
                              f"finance_advance_form_{suffix}",manifest)
                await context.close()

        # Mutable paths: verify browser-visible failure, success, account setup
        # and receipt correction/cancellation against the actual PostgreSQL rows.
        context=await browser.new_context(viewport={"width":390,"height":850})
        page=await context.new_page()
        await open_section(page,"students")
        await page.locator(".st-key-kid_name input").fill("فحص مبلغ ناقص "+prefix)
        await page.locator(".st-key-kid_mother_name input").fill("أم فحص")
        await page.locator(".st-key-kid_mother_phone input").fill("0599112233")
        await page.get_by_text("دفع",exact=True).first.click()
        await page.locator(".st-key-kid_initial_registration label").first.click()
        await page.locator(".st-key-kid_initial_gilet label").first.click()
        await page.locator(".st-key-kid_initial_amount input").fill("2000")
        await page.get_by_role("button",name=re.compile("حفظ بيانات الطفل والأهل")).click()
        error=page.get_by_test_id("stAlertContentError").get_by_text("المبلغ لا يغطي",exact=False).first
        await expect(error).to_be_visible()
        await expect(page.locator(".st-key-kid_name input")).to_have_value("فحص مبلغ ناقص "+prefix)
        assert not read("SELECT 1 FROM students WHERE full_name=%s",("فحص مبلغ ناقص "+prefix,))
        await capture(page,error,"finance_insufficient_390",manifest)

        await open_section(page,"payments")
        await select_account(page,regular_name)
        old_count=read("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(sid,))[0]["n"]
        amt=page.locator(f'.st-key-monthly_amount_{sid}_v0 input')
        await amt.fill("4500")
        await amt.press("Tab")
        await capture(page,amt,"finance_next_before_390",manifest)
        await page.get_by_role("button",name="معاينة توزيع المبلغ").click()
        await expect(page.get_by_text("معاينة توزيع 4,500",exact=False)).to_be_visible()
        await page.get_by_text("أؤكد قبض المبلغ وتوزيعه كما عُرض",exact=False).click()
        await page.get_by_role("button",name="💾 تسجيل دفعة").click()
        await expect(page.get_by_text("تم تسجيل الدفعة",exact=False)).to_be_visible()
        await capture(page,page.get_by_text("تم تسجيل الدفعة",exact=False),
                      "finance_next_after_390",manifest)
        assert read("SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s",(sid,))[0]["n"]==old_count+1
        latest=read("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s ORDER BY receipt_id DESC LIMIT 1",(sid,))[0]["receipt_id"]
        allocations=read("""SELECT p.period_no,a.amount FROM monthly_allocations a
                  JOIN monthly_periods p ON a.period_id=p.period_id
                  WHERE a.receipt_id=%s ORDER BY p.period_no""",(latest,))
        assert [int(x["amount"]) for x in allocations]==[1500,3000],allocations

        await page.get_by_role("tab",name=re.compile("الوصولات")).click()
        await page.get_by_role("textbox",name="بحث باسم الطفل أو هاتف الأب أو الأم أو رقم الوصل").fill(str(latest))
        await page.get_by_role("textbox",name="بحث باسم الطفل أو هاتف الأب أو الأم أو رقم الوصل").press("Enter")
        specific=page.locator(f".st-key-finance_receipt_open_{latest} button")
        await expect(specific).to_be_visible(timeout=30000)
        await specific.click()
        await expect(page.get_by_role("tabpanel",name="🧾 الوصولات",exact=True)
                     .get_by_text(f"وصل قبض #{latest}",exact=False)).to_be_visible(timeout=30000)
        await page.get_by_role("button",name="تعديل الوصل").click()
        reason=page.get_by_role("textbox",name=re.compile("سبب التصحيح"))
        await reason.fill("مراجعة مبلغ")
        await page.get_by_role("spinbutton",name="المبلغ المصحح").fill("3000")
        await page.get_by_role("spinbutton",name="المبلغ المصحح").press("Tab")
        await page.get_by_role("button",name="معاينة أثر التصحيح").click()
        await expect(page.get_by_text("القبض القديم:",exact=False)).to_be_visible()
        await page.get_by_text("أؤكد أثر التصحيح وحفظ الوصل الأصلي في السجل",exact=False).click()
        await page.get_by_role("button",name="تأكيد تصحيح الوصل").click()
        await expect(page.get_by_text("صُحح الوصل",exact=False)).to_be_visible()
        assert read("SELECT state FROM monthly_receipts WHERE receipt_id=%s",(latest,))[0]["state"]=="cancelled"
        new=read("SELECT receipt_id,amount FROM monthly_receipts WHERE corrects_id=%s",(latest,))
        assert len(new)==1 and new[0]["amount"]==3000
        await capture(page,page.get_by_text("صُحح الوصل",exact=False),
                      "finance_receipt_corrected_390",manifest)

        # Child without account: explicit date/status/confirmation and no cash.
        await page.get_by_role("tab",name=re.compile("حسابات الأطفال")).click()
        combo=page.locator(".st-key-monthly_finance_child").get_by_role("combobox").first
        await combo.click()
        await combo.fill(unfunded_name)
        await page.locator('[role="listbox"]').get_by_text(unfunded_name,exact=True).last.click()
        await expect(page.get_by_text("تهيئة الحساب الشهري لهذا الطفل")).to_be_visible()
        await capture(page,page.get_by_text("تهيئة الحساب الشهري لهذا الطفل"),
                      "finance_legacy_setup_before_390",manifest)
        await page.get_by_text("أؤكد التاريخ والحالة",exact=False).click()
        await page.get_by_role("button",name="تأكيد تهيئة حساب الطفل").click()
        await expect(page.get_by_text("تم تهيئة الحساب",exact=False)).to_be_visible()
        assert read("SELECT status FROM monthly_accounts WHERE student_id=%s",(unfunded_sid,))[0]["status"]=="regular"
        assert not read("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s",(unfunded_sid,))
        await capture(page,page.get_by_text("تم تهيئة الحساب",exact=False),
                      "finance_legacy_setup_after_390",manifest)
        await context.close()
        await browser.close()
    (OUT/"single_currency_manifest.json").write_text(
        json.dumps({"candidate":os.environ.get("GITHUB_SHA","local"),
                    "currency":F.CURRENCY,"screenshots":manifest},
                   ensure_ascii=False,indent=2,default=str))
    print(f"Single-currency scrolled finance screenshots: {len(manifest)*2}; "
          "PostgreSQL readback and UI saves verified")


if __name__=="__main__":
    asyncio.run(run())
