"""Real Chromium intake submission and PostgreSQL readback; disposable QA server only."""
import asyncio
import os
import re
import uuid
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright, expect
import monthly_finance as F
import db

BASE="http://127.0.0.1:8501"
OUT=Path("visual-evidence")


def _conn():
    c=psycopg2.connect(os.environ["TEST_POSTGRES_DSN"],cursor_factory=RealDictCursor)
    c.autocommit=False
    return c


def sql(query, args=()):
    with _conn() as c:
        with c.cursor() as cur:
            cur.execute(query,args)
            return cur.fetchall()


async def open_students(page):
    await page.goto(BASE,wait_until="domcontentloaded")
    await page.locator(".st-key-nav_students button").wait_for(state="attached",timeout=30000)
    nav=page.locator(".st-key-nav_students button")
    if not await nav.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await nav.click()
    await expect(page.locator(".section-title")).to_contain_text("إدارة الطلاب",timeout=30000)
    if await nav.is_visible():
        await page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()
    await page.wait_for_timeout(250)


async def fill_family(page, full_name):
    await page.locator(".st-key-kid_name input").fill(full_name)
    await page.locator(".st-key-kid_mother_name input").fill("أم المتصفح")
    await page.locator(".st-key-kid_mother_phone input").fill("0599000015")


async def submit_and_check(page, name, expect_receipt):
    await page.get_by_role("button",name=re.compile("حفظ بيانات الطفل والأهل")).click()
    await expect(page.locator(".st-key-kid_name_v1 input")).to_have_value("",timeout=30000)
    await expect(page.get_by_text("تم حفظ الطفل والأهل",exact=False)).to_be_visible()
    rows=sql("""SELECT s.student_id,a.status,r.receipt_id,r.amount FROM students s
            JOIN monthly_accounts a ON a.student_id=s.student_id
            LEFT JOIN monthly_receipts r ON r.student_id=s.student_id
            WHERE s.full_name=%s""",(name,))
    assert len(rows)==1, (name,rows)
    assert (rows[0]["receipt_id"] is not None)==expect_receipt
    return rows[0]


async def run():
    # Test fixture deliberately sets tariffs via audited service, never production.
    from unittest.mock import patch
    with patch.object(db,"new_transaction_connection",side_effect=_conn):
        F.update_tariffs(1000,2000,3000,"chromium-qa")

    OUT.mkdir(exist_ok=True)
    async with async_playwright() as playwright:
        browser=await playwright.chromium.launch(headless=True)
        context=await browser.new_context(viewport={"width":390,"height":850})
        page=await context.new_page()
        await open_students(page)
        name="طفل دفع "+uuid.uuid4().hex[:8]
        await fill_family(page,name)
        await page.get_by_text("دفع",exact=True).first.click()
        await expect(page.locator(".st-key-kid_initial_registration")).to_be_visible()
        await page.locator(".st-key-kid_initial_registration label").first.click()
        await page.locator(".st-key-kid_initial_gilet label").first.click()
        await page.locator(".st-key-kid_initial_amount input").fill("12000")
        await page.locator(".st-key-kid_initial_amount input").press("Tab")
        await expect(page.get_by_text(re.compile("أشهر مكتملة 3"))).to_be_visible(timeout=20000)
        await page.screenshot(path=str(OUT/"monthly_intake_390_day_filled.png"),
                              full_page=True,animations="disabled")
        record=await submit_and_check(page,name,True)
        sid=record["student_id"]
        assert record["status"]=="regular" and record["amount"]==12000
        allocations=sql("""SELECT CASE WHEN a.fee_id IS NOT NULL THEN f.kind ELSE 'month' END AS kind,
             SUM(a.amount) AS cash FROM monthly_allocations a
             JOIN monthly_receipts r ON r.receipt_id=a.receipt_id
             LEFT JOIN monthly_fees f ON f.fee_id=a.fee_id
             WHERE r.student_id=%s GROUP BY 1""",(sid,))
        assert {x["kind"]:int(x["cash"]) for x in allocations}=={
            "registration":1000,"gilet":2000,"month":9000}
        await page.get_by_role("button",name=re.compile("حفظ بيانات الطفل والأهل")).click()
        await page.wait_for_timeout(300)
        assert len(sql("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s",(sid,)))==1

        # Exempt account: no receipt and no charge.
        await context.close()
        # A browser reload preserves Streamlit session widget generation;
        # use a distinct operator session for the exempt-account scenario.
        context=await browser.new_context(viewport={"width":390,"height":850})
        page=await context.new_page()
        await open_students(page)
        exempt_name="طفل معفى "+uuid.uuid4().hex[:8]
        await fill_family(page,exempt_name)
        await page.get_by_text("معفي",exact=True).first.click()
        await expect(page.get_by_text("يشمل الإعفاء التسجيل",exact=False)).to_be_visible()
        await page.screenshot(path=str(OUT/"monthly_exempt_390_day.png"),
                              full_page=True,animations="disabled")
        result=await submit_and_check(page,exempt_name,False)
        assert result["status"]=="exempt"

        # UI shells in five exact widths, both themes, plus expanded finance rows.
        for width in (360,390,430,768,1280):
            for night in (False,True):
                context2=await browser.new_context(viewport={"width":width,"height":850})
                view=await context2.new_page()
                await open_students(view)
                sw=view.locator(".st-key-night_mode label").last
                toggle=view.locator(".st-key-night_mode [role='switch']")
                if await toggle.is_checked()!=night:
                    await sw.click()
                    await expect(toggle).to_be_checked() if night else await expect(toggle).not_to_be_checked()
                await view.screenshot(path=str(OUT/f"monthly_students_{width}_{'night' if night else 'day'}.png"),
                                       full_page=True,animations="disabled")
                # Inspect the computed color of the actual visible descendant,
                # not the color of a wrapper with an overridden child style.
                for choice in ("دفع","معفي"):
                    await view.get_by_text(choice,exact=True).first.click()
                    for label in ("دفع","معفي"):
                        visible=view.get_by_text(label,exact=True).first
                        details=await visible.evaluate("""el => {
                            const b=el.closest('button');
                            if (!b) return null;
                            const child=b.querySelector('p') || el;
                            return {
                                text:getComputedStyle(child).color,
                                background:getComputedStyle(b).backgroundColor,
                                selected:b.getAttribute('aria-pressed'),
                                disabled:b.disabled
                            };
                        }""")
                        assert details and not details["disabled"],(width,night,choice,label,details)
                        def lum(css):
                            channels=[int(float(v)) for v in re.findall(r"[0-9.]+",css)[:3]]
                            assert len(channels)==3,(width,night,css)
                            def linear(x):
                                x/=255
                                return x/12.92 if x<=0.04045 else ((x+0.055)/1.055)**2.4
                            return sum(w*linear(x) for w,x in zip((0.2126,0.7152,0.0722),channels))
                        t,b=sorted((lum(details["text"]),lum(details["background"])))
                        ratio=(b+0.05)/(t+0.05)
                        assert ratio>=4.5,("actual fee descendant text contrast",width,night,choice,label,details,ratio)
                    await view.screenshot(path=str(OUT/f"monthly_fee_{choice}_{width}_{'night' if night else 'day'}.png"),
                                          full_page=True,animations="disabled")
                horizontal=await view.evaluate("document.documentElement.scrollWidth > innerWidth + 3")
                assert not horizontal, f"Horizontal overflow at {width}"
                await context2.close()
        await context.close()
        await browser.close()
    print("Chromium monthly intake cash split, exempt, reset, readback and 10 screenshots passed")


if __name__=="__main__":
    asyncio.run(run())
