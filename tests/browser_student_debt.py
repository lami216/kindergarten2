"""Chromium student debt-removal choice and non-cash waiver, disposable PG."""
import asyncio
import os
import uuid
from datetime import date
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright,expect

BASE="http://127.0.0.1:8501"
OUT=Path("visual-evidence")


def sql(command,args=()):
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],
                          cursor_factory=RealDictCursor) as con:
        with con.cursor() as c:
            c.execute(command,args)
            return c.fetchall() if c.description is not None else []


def seed():
    suffix=uuid.uuid4().hex
    sid="S"+suffix[:19]
    fid="P"+suffix[:19]
    name="طفل دين كروميوم "+suffix[:6]
    sql("INSERT INTO parents(father_id,mother_name,mother_mobile) VALUES(%s,'أم كروميوم','0599112233')",(fid,))
    sql("INSERT INTO students(student_id,full_name,father_id) VALUES(%s,%s,%s)",(sid,name,fid))
    sql("INSERT INTO monthly_accounts(student_id,status,start_date,created_by) VALUES(%s,'regular',%s,'Chromium QA')",(sid,date.today()))
    sql("INSERT INTO monthly_fees(student_id,kind,price) VALUES(%s,'registration',1000)",(sid,))
    return sid,name


async def open_student(page,name):
    await page.goto(BASE,wait_until="domcontentloaded")
    nav=page.locator(".st-key-nav_students button")
    await nav.wait_for(state="attached",timeout=30000)
    if not await nav.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await nav.click()
    await expect(page.get_by_role("tab",name="📋 عرض / تعديل / حذف")).to_be_visible(timeout=20000)
    if await nav.is_visible():
        await page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
    await page.get_by_role("tab",name="📋 عرض / تعديل / حذف").click()
    select=page.locator(".st-key-student_select_edit input[role='combobox']").first
    await expect(select).to_be_visible()
    await select.click()
    await select.fill(name)
    await page.locator("[data-item-hl]").first.click(force=True)
    await expect(page.get_by_role("button",name="🗑️ حذف الطالب")).to_be_visible(timeout=15000)


async def run():
    sid,name=seed()
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        ctx=await browser.new_context(viewport={"width":390,"height":850})
        page=await ctx.new_page()
        await open_student(page,name)
        await page.get_by_role("button",name="🗑️ حذف الطالب").click()
        await expect(page.get_by_text("لا يمكن حذف الطالب؛ عليه مبلغ",exact=False).first).to_be_visible()
        await expect(page.get_by_role("button",name="تسجيل دفعة",exact=True)).to_be_visible()
        await expect(page.get_by_role("button",name="إلغاء الدين")).to_be_visible()
        assert sql("SELECT archived_at FROM students WHERE student_id=%s",(sid,))[0]["archived_at"] is None
        await page.screenshot(path=str(OUT/"student_debt_choices_390_day.png"),full_page=True)
        await page.get_by_role("button",name="إلغاء الدين").click()
        await expect(page.get_by_role("button",name="تأكيد قرار إلغاء الدين")).to_be_visible()
        await page.screenshot(path=str(OUT/"student_debt_waiver_390_day.png"),full_page=True)
        night=page.locator(".st-key-night_mode [role='switch']")
        if not await night.is_checked():
            await page.locator(".st-key-night_mode label").last.click()
            await expect(night).to_be_checked()
        await page.screenshot(path=str(OUT/"student_debt_waiver_390_night.png"),full_page=True)
        await page.get_by_role("textbox",name="سبب إلغاء الدين *").fill("قرار مديرة")
        await page.get_by_text("أؤكد إلغاء الدين دون قبض أي مبلغ",exact=False).click()
        await page.get_by_role("button",name="تأكيد قرار إلغاء الدين").click()
        await expect(page.get_by_text("ألغي الدين",exact=False).first).to_be_visible(timeout=20000)
        assert not sql("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s",(sid,))
        rows=sql("SELECT amount,reason FROM monthly_waivers WHERE student_id=%s",(sid,))
        assert rows and sum(int(x["amount"]) for x in rows)==4000,rows
        await page.get_by_role("button",name="🗑️ حذف الطالب").click()
        # Streamlit button click returns before the server-side transaction
        # necessarily commits; wait for the durable PostgreSQL state.
        for _ in range(60):
            if sql("SELECT archived_at FROM students WHERE student_id=%s",
                   (sid,))[0]["archived_at"] is not None:
                break
            await page.wait_for_timeout(250)
        else:
            raise AssertionError("Archival did not commit after the UI click")
        await ctx.close()
        await browser.close()
    print("Chromium debt refusal, two native choices, dark waiver, no cash, durable archive passed")


if __name__=="__main__":
    asyncio.run(run())
