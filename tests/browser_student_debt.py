"""Chromium student debt-removal choice and non-cash waiver, disposable PG."""
import asyncio
import os
import json
import uuid
from datetime import date

import monthly_finance as F
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
    sql("INSERT INTO monthly_accounts(student_id,status,start_date,created_by) VALUES(%s,'regular',%s,'Chromium QA')",(sid,F.today()))
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
    # Select by the exact visible student label. A transient BaseWeb
    # highlight attribute is not guaranteed on virtualized options.
    await page.get_by_text(name,exact=True).last.click(timeout=15000)
    await expect(page.get_by_role("button",name="🗑️ حذف الطالب")).to_be_visible(timeout=15000)


async def wait_for_real_theme(page, dark, *, form=False):
    """Wait for Streamlit rerun AND computed CSS, not the switch/filename."""
    expected_canvas="rgb(16, 21, 25)" if dark else "rgb(250, 250, 249)"
    expected_form="rgb(32, 34, 35)" if dark else "rgb(255, 255, 255)"
    await page.wait_for_function("""({canvas, form, requireForm}) => {
        const main=document.querySelector('.stApp');
        const waiver=[...document.querySelectorAll('[data-testid="stForm"]')].at(-1);
        if (!main || (requireForm && !waiver)) return false;
        const actual=getComputedStyle(main).backgroundColor;
        const formColor=waiver && getComputedStyle(waiver).backgroundColor;
        return actual===canvas && (!requireForm || formColor===form);
    }""",arg={"canvas":expected_canvas,"form":expected_form,"requireForm":form},timeout=25000)
    # A rerun can briefly expose a correct CSS state before widget hydration.
    await expect(page.locator(".st-key-night_mode [role='switch']")).to_be_visible()
    if form:
        await expect(page.get_by_role("button",name="تأكيد قرار إلغاء الدين")).to_be_visible()
    await page.wait_for_timeout(400)
    colors=await page.evaluate("""() => {
        const main=document.querySelector('.stApp');
        const forms=[...document.querySelectorAll('[data-testid="stForm"]')];
        const form=forms.at(-1);
        const css=e=>e?{background:getComputedStyle(e).backgroundColor,
                         color:getComputedStyle(e).color}:null;
        return {canvas:css(main),form:css(form),url:location.href};
    }""")
    assert colors["canvas"]["background"]==expected_canvas,colors
    if form: assert colors["form"]["background"]==expected_form,colors
    return colors


async def change_theme(page,dark,*,form=False):
    switch=page.locator(".st-key-night_mode [role='switch']").first
    await expect(switch).to_be_visible()
    if await switch.is_checked()!=dark:
        await page.locator(".st-key-night_mode label").last.click()
    if dark: await expect(switch).to_be_checked()
    else: await expect(switch).not_to_be_checked()
    return await wait_for_real_theme(page,dark,form=form)


async def snapshot(page,filename,region=None):
    await page.screenshot(path=str(OUT/filename),full_page=True,animations="disabled")
    if region is not None:
        await region.scroll_into_view_if_needed()
        await region.screenshot(path=str(OUT/filename.replace(".png","_form.png")),
                                animations="disabled")


async def run():
    sid,name=seed()
    OUT.mkdir(exist_ok=True)
    metrics={}
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        ctx=await browser.new_context(viewport={"width":390,"height":850})
        page=await ctx.new_page()
        await open_student(page,name)
        await change_theme(page,False)
        await page.get_by_role("button",name="🗑️ حذف الطالب").click()
        await expect(page.get_by_text("لا يمكن حذف الطالب؛ عليه مبلغ",exact=False).first).to_be_visible()
        await expect(page.get_by_role("button",name="تسجيل دفعة",exact=True)).to_be_visible()
        await expect(page.get_by_role("button",name="إلغاء الدين",exact=True)).to_be_visible()
        assert sql("SELECT archived_at FROM students WHERE student_id=%s",(sid,))[0]["archived_at"] is None
        metrics["choices_light"]=await wait_for_real_theme(page,False)
        await snapshot(page,"student_debt_choices_390_day.png")

        await page.get_by_role("button",name="إلغاء الدين",exact=True).click()
        await expect(page.get_by_role("button",name="تأكيد قرار إلغاء الدين")).to_be_visible()
        metrics["waiver_empty_light"]=await wait_for_real_theme(page,False,form=True)
        await snapshot(page,"student_debt_waiver_390_day.png",
                       page.locator('[data-testid="stForm"]').last)
        reason=page.get_by_role("textbox",name="سبب إلغاء الدين *")
        await reason.fill("قرار مديرة موثق دون قبض نقدي")
        checkbox=page.get_by_role("checkbox",name="أؤكد إلغاء الدين دون قبض أي مبلغ")
        if not await checkbox.is_checked():
            await checkbox.click()
        await expect(checkbox).to_be_checked()
        await expect(reason).to_have_value("قرار مديرة موثق دون قبض نقدي")
        await snapshot(page,"student_debt_confirm_390_day.png",
                       page.locator('[data-testid="stForm"]').last)

        # Switching a Streamlit theme reruns the form: re-enter form values,
        # because unsubmitted form inputs are not part of server session state.
        metrics["waiver_dark"]=await change_theme(page,True,form=True)
        await expect(page.get_by_role("button",name="إلغاء الدين",exact=True)).to_be_visible()
        await snapshot(page,"student_debt_choices_390_night.png")
        await reason.fill("قرار مديرة موثق دون قبض نقدي")
        checkbox=page.get_by_role("checkbox",name="أؤكد إلغاء الدين دون قبض أي مبلغ")
        if not await checkbox.is_checked():
            await checkbox.click()
        await expect(checkbox).to_be_checked()
        await expect(reason).to_have_value("قرار مديرة موثق دون قبض نقدي")
        metrics["confirm_dark"]=await wait_for_real_theme(page,True,form=True)
        await snapshot(page,"student_debt_waiver_390_night.png",
                       page.locator('[data-testid="stForm"]').last)

        await page.get_by_role("button",name="تأكيد قرار إلغاء الدين").click()
        await expect(page.get_by_text("أُلغي دين",exact=False).first).to_be_visible(timeout=20000)
        metrics["outcome_dark"]=await wait_for_real_theme(page,True)
        await snapshot(page,"student_debt_outcome_390_night.png")
        assert not sql("SELECT receipt_id FROM monthly_receipts WHERE student_id=%s",(sid,))
        rows=sql("SELECT amount,reason FROM monthly_waivers WHERE student_id=%s",(sid,))
        assert rows and sum(int(x["amount"]) for x in rows)==4000,rows
        assert sql("""SELECT COUNT(*) AS n FROM monthly_receipts WHERE student_id=%s""",(sid,))[0]["n"]==0

        metrics["outcome_light"]=await change_theme(page,False)
        await expect(page.get_by_text("أُلغي دين",exact=False).first).to_be_visible()
        await snapshot(page,"student_debt_outcome_390_day.png")
        await page.get_by_role("button",name="🗑️ حذف الطالب").click()
        # Streamlit may return before server-side archive commits.
        for _ in range(60):
            if sql("SELECT archived_at FROM students WHERE student_id=%s",
                   (sid,))[0]["archived_at"] is not None:
                break
            await page.wait_for_timeout(250)
        else:
            raise AssertionError("Archival did not commit after the UI click")
        await expect(page.get_by_text("الطالب مؤرشف",exact=False).first).to_be_visible(timeout=20000)
        metrics["history_light"]=await wait_for_real_theme(page,False)
        await snapshot(page,"student_debt_history_390_day.png")
        metrics["history_dark"]=await change_theme(page,True)
        await expect(page.get_by_text("الطالب مؤرشف",exact=False).first).to_be_visible()
        await snapshot(page,"student_debt_history_390_night.png")
        (OUT/"student_debt_theme_metrics.json").write_text(
            json.dumps(metrics,ensure_ascii=False,indent=2),encoding="utf-8")
        await ctx.close()
        await browser.close()
    print("Chromium debt refused, light/dark computed canvas & form verified; "
          "waiver reason, confirmation, archived history and zero-cash passed")


if __name__=="__main__":
    asyncio.run(run())
