"""Real primary UI: siblings, invalid expense recovery and committed readback."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright,expect
from tests.qa_live_pages import guard

async def main():
    root=Path(os.environ['KG_LIVE_QA_DIR']);state=json.loads((root/'state.json').read_text())
    guard(state['dsn']);assert state['origin']=='https://127.0.0.1:8520'
    out=Path(os.environ['KG_LIVE_QA_OUT']);out.mkdir(parents=True,exist_ok=True)
    results=[]
    def passed(case):
        results.append(dict(case=case,passed=True))
        (out/'results.json').write_text(json.dumps(results),encoding='utf-8')
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        context=await browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':900})
        page=await context.new_page()
        try:
            await page.goto(state['origin'])
            await page.locator('#live-login [name="username"]').fill(state['username'])
            await page.locator('#live-login [name="password"]').fill(state['password'])
            await page.locator('#preview-enter').click()
            await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
            async def snapshot():
                r=await context.request.get(state['origin']+'/api/snapshot');assert r.ok
                return await r.json()
            async def nav(target):
                await page.locator('#menu').click()
                await page.locator('nav [data-page="'+target+'"]').click()
            before=await snapshot();family=before['families'][0]
            await nav('students');await page.locator('#add-student').click()
            await page.locator('#student-form [name="name"]').fill('أخت مرتبطة بالأسرة الموجودة')
            await page.locator('#student-form [data-date-part="day"]').first.fill('12')
            await page.locator('#student-form [data-date-part="month"]').first.select_option('03')
            await page.locator('#student-form [data-date-part="year"]').first.fill('22')
            await page.locator('#student-form [name="department_id"]').select_option(index=1)
            picker=page.locator('#student-form [name="existing_parent_id"]')
            await picker.select_option(family['id'])
            for key in ('father','fatherPhone','mother','motherPhone'):
                await expect(page.locator('#student-form [name="'+key+'"]').first).to_be_disabled()
                await expect(page.locator('#student-form [name="'+key+'"]').first).to_have_value(family[key])
            await picker.select_option('')
            await expect(page.locator('#student-form [name="father"]')).to_be_enabled()
            await picker.select_option(family['id'])
            await page.locator('#student-form button.primary[type="submit"], #student-form .form-end button.primary').last.click()
            await expect(page.locator('#student-form')).to_have_count(0,timeout=20000)
            after=await snapshot()
            child=next(s for s in after['students'] if s['name']=='أخت مرتبطة بالأسرة الموجودة')
            assert child['parent_id']==family['id'] and len(after['families'])==len(before['families'])
            assert len(after['students'])==len(before['students'])+1
            assert after['overview']['total_cash']==before['overview']['total_cash']
            passed('mobile_sibling_links_existing_family_without_overwriting_contacts_or_fake_cash')
            await nav('expenses')
            await page.locator('#expense-form [name="category"]').fill('مصروف اختبار تصحيح قابل للتعافي')
            await page.locator('#expense-form [name="amount"]').fill('1200')
            await page.locator('#expense-status').select_option('partial')
            await page.locator('#expense-form [name="paid"]').fill('1000')
            await page.locator('#expense-form button.primary').click()
            await expect(page.locator('#expense-form [name="category"]')).to_have_value('',timeout=20000)
            current=await snapshot();expense=next(e for e in current['expenses'] if e['category']=='مصروف اختبار تصحيح قابل للتعافي')
            await page.locator('[data-record-type="expenses"][data-record-id="'+str(expense['id'])+'"][data-record-mode="edit"]').click()
            await page.locator('#record-edit-form [name="amount"]').fill('800')
            await page.locator('#record-edit-form [name="reason"]').fill('فحص رسالة المدفوع أكبر من الإجمالي')
            await page.locator('#record-edit-form [name="agree"]').check()
            await page.locator('#record-edit-form button.primary').click()
            await expect(page.locator('#record-edit-form .error[role="alert"]')).not_to_be_empty()
            await expect(page.locator('#record-dialog')).to_be_visible()
            await expect(page.locator('#record-edit-form [name="paid"]')).to_have_value('1000')
            unchanged=next(e for e in (await snapshot())['expenses'] if e['id']==expense['id'])
            assert unchanged['amount']==1200 and unchanged['paid']==1000
            await page.locator('#record-edit-form [name="amount"]').fill('1300')
            await page.locator('#record-edit-form button.primary').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            saved=next(e for e in (await snapshot())['expenses'] if e['id']==expense['id'])
            assert saved['amount']==1300 and saved['paid']==1000
            passed('invalid_expense_edit_keeps_fields_and_database_then_accepts_corrected_total')
            await page.screenshot(path=str(out/'mobile-families-expense.png'))
        finally:
            await browser.close()
    print(json.dumps({'passed':len(results),'total':len(results)}))

if __name__=='__main__':asyncio.run(main())
