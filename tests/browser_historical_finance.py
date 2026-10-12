"""Real Chromium audit flow for legacy receipts, isolated PostgreSQL only."""
import asyncio
import os
import re
import uuid
from decimal import Decimal
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright, expect

BASE="http://127.0.0.1:8501"
OUT=Path("visual-evidence")


def query(sql, params=()):
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],
                          cursor_factory=RealDictCursor) as connection:
        with connection.cursor() as c:
            c.execute(sql,params)
            return c.fetchall()


def seed():
    suffix=uuid.uuid4().hex
    pid="P"+suffix[:19]
    sid="S"+suffix[:19]
    year="Y"+suffix[:18]
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],
                          cursor_factory=RealDictCursor) as con:
        with con.cursor() as c:
            c.execute("INSERT INTO parents(father_id,father_name) VALUES(%s,%s)",
                      (pid,"ولي المتصفح القديم"))
            c.execute("INSERT INTO students(student_id,full_name,father_id) VALUES(%s,%s,%s)",
                      (sid,"طالب وصلة تاريخية "+suffix[:6],pid))
            c.execute("INSERT INTO academic_years(year_id) VALUES(%s)",(year,))
            c.execute("INSERT INTO classes(class_type,section) VALUES(%s,%s) RETURNING class_id",
                      ("QA وصلة "+suffix[:6],suffix[:7]))
            klass=c.fetchone()["class_id"]
            c.execute("""INSERT INTO registrations(student_id,class_id,year_id,status,
                    annual_tuition) VALUES(%s,%s,%s,'مسجل جديد',3500)
                    RETURNING registration_id""",(sid,klass,year))
            registration=c.fetchone()["registration_id"]
            c.execute("""INSERT INTO payments(registration_id,amount,payment_date,
                       payment_for,payer_name) VALUES(%s,120.50,CURRENT_DATE,
                       'رسوم تسجيل','ولي المتصفح القديم') RETURNING receipt_number""",
                      (registration,))
            receipt=c.fetchone()["receipt_number"]
    return receipt


async def test_browser():
    rid=seed()
    OUT.mkdir(exist_ok=True)
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        ctx=await browser.new_context(viewport={"width":390,"height":850})
        page=await ctx.new_page()
        await page.goto(BASE,wait_until="domcontentloaded")
        nav=page.locator(".st-key-nav_payments button")
        await nav.wait_for(state="attached",timeout=30000)
        if not await nav.is_visible():
            await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
        await nav.click()
        await expect(page.locator(".section-title").first).to_contain_text(
            "الدفعات المالية",timeout=20000)
        if await nav.is_visible():
            await page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
        await page.get_by_role("tab",name="📂 الدفعات السنوية القديمة").click()
        await page.get_by_role("tab",name="📋 سجل الدفعات والإعادة").click()
        select=page.locator(".st-key-payment_select_edit")
        await expect(select).to_be_visible(timeout=15000)
        # The whole Streamlit widget container is not the interactive
        # select. Target its native searchable combobox input directly.
        combo = select.locator('input[role="combobox"]').first
        await combo.click()
        await combo.fill(f"وصل #{rid}")
        # A value in the searchable input is not yet a committed selection.
        # Click the matching visible menu item, then wait for Streamlit rerun.
        await page.get_by_text(f"وصل #{rid} —", exact=False).last.click(timeout=10000)
        await expect(combo).to_have_value(re.compile(f"وصل #{rid}"), timeout=15000)
        details=page.get_by_text(f"تصحيح أو إلغاء الوصل #{rid}",exact=False)
        await details.click()
        await page.get_by_role("spinbutton",name="المبلغ",exact=True).fill("90.25")
        await page.get_by_role("textbox",name="سبب التصحيح أو الإلغاء *").fill("تدقيق كروميوم")
        await page.screenshot(path=str(OUT/"legacy_receipt_before_correction_390.png"),
                              full_page=True,animations="disabled")
        await page.get_by_role("button",name="💾 حفظ التصحيح").click()
        await expect(page.get_by_text("حُفظ التصحيح",exact=False)).to_be_visible(timeout=15000)
        r=query("SELECT amount,receipt_state FROM payments WHERE receipt_number=%s",(rid,))[0]
        assert r["amount"]==Decimal("90.25") and r["receipt_state"]=="active",r

        await details.click()
        await page.get_by_role("textbox",name="سبب التصحيح أو الإلغاء *").fill("إلغاء اختبار")
        await page.get_by_role("button",name="إلغاء الوصل مع الاحتفاظ بالسجل").click()
        r=query("SELECT amount,receipt_state,cancel_reason FROM payments WHERE receipt_number=%s",(rid,))[0]
        assert r["amount"]==Decimal("90.25") and r["receipt_state"]=="cancelled",r
        await page.screenshot(path=str(OUT/"legacy_receipt_cancelled_390.png"),
                              full_page=True,animations="disabled")
        logs=query("SELECT action,actor,reason FROM historical_payment_audit WHERE receipt_number=%s ORDER BY audit_id",
                   (rid,))
        assert [x["action"] for x in logs]==["legacy_receipt_corrected","legacy_receipt_cancelled"],logs
        assert all(x["actor"]=="Chromium QA" for x in logs),logs
        await ctx.close()
        await browser.close()
    print("Chromium historical receipt corrected, soft-cancelled, audit logged and retained.")


if __name__=="__main__":
    asyncio.run(test_browser())
