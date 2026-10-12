"""Chromium payroll/advance rapid-submit regression on disposable PostgreSQL."""
import asyncio
import os
import uuid
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright, expect

BASE="http://127.0.0.1:8501"
OUT=Path("visual-evidence")


def sql(text,args=()):
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],
                          cursor_factory=RealDictCursor) as conn:
        with conn.cursor() as c:
            c.execute(text,args)
            return c.fetchall()


async def select_teacher(page, selector, name):
    element=page.locator(selector+" input[role='combobox']").first
    await expect(element).to_be_visible(timeout=20000)
    await element.click()
    await element.fill(name)
    await page.locator("[data-item-hl]").first.click(force=True,timeout=10000)


async def run():
    token=uuid.uuid4().hex
    tid="T"+token[:19]
    name="معلمة كروميوم "+token[:6]
    sql("INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,%s,5000)",(tid,name))
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        ctx=await browser.new_context(viewport={"width":390,"height":850})
        page=await ctx.new_page()
        await page.goto(BASE,wait_until="domcontentloaded")
        nav=page.locator(".st-key-nav_salaries button")
        await nav.wait_for(state="attached",timeout=30000)
        if not await nav.is_visible():
            await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
        await nav.click()
        await page.get_by_role("tab",name="➕ صرف راتب شهري").click()
        await select_teacher(page,".st-key-salary_teacher",name)
        button=page.get_by_role("button",name="🧾 تسجيل الصرف وطباعة قسيمة الراتب")
        await expect(button).to_be_enabled()
        await page.screenshot(path=str(OUT/"payroll_form_390_filled.png"),full_page=True)
        await button.dblclick()
        await expect(page.get_by_text("تم صرف الراتب وحفظ القسيمة",exact=False)).to_be_visible(timeout=20000)
        slips=sql("SELECT payment_id,amount,request_token FROM teacher_payments WHERE national_id=%s",(tid,))
        assert len(slips)==1,slips
        await expect(page.locator(".st-key-salary_month_v1 input")).to_be_visible(timeout=15000)
        # A separate consciously initiated payment is still permitted.
        await page.get_by_role("button",name="🧾 تسجيل الصرف وطباعة قسيمة الراتب").click()
        await expect(page.get_by_text("تم صرف الراتب وحفظ القسيمة",exact=False)).to_be_visible(timeout=20000)
        assert len(sql("SELECT payment_id FROM teacher_payments WHERE national_id=%s",(tid,)))==2

        await page.get_by_role("tab",name="💰 سلف المعلمات").click()
        await select_teacher(page,".st-key-advance_teacher_v0",name)
        await page.locator(".st-key-advance_amount_v0 input").fill("1000")
        await page.get_by_role("button",name="💾 تسجيل السلفة المدفوعة").dblclick()
        await expect(page.get_by_text("تم حفظ صرف السلفة",exact=False)).to_be_visible(timeout=20000)
        advances=sql("SELECT advance_id,amount FROM teacher_advances WHERE national_id=%s",(tid,))
        assert len(advances)==1 and int(advances[0]["amount"])==1000,advances
        await expect(page.locator(".st-key-advance_amount_v1 input")).to_have_value("0.00")
        await page.screenshot(path=str(OUT/"payroll_advance_390_success.png"),full_page=True)
        await ctx.close()
        await browser.close()
    print("Chromium salary double-click created one slip, separate save permitted, advance double-click one.")


if __name__=="__main__":
    asyncio.run(run())
