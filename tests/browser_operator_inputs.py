"""Real Chromium ordinary inputs at 390/1280, with PostgreSQL cash readback."""
import asyncio
from decimal import Decimal
import json
from pathlib import Path
import re
import sys
import uuid
from tests.sidebar_helpers import collapse_sidebar, sidebar_collapsed
from playwright.async_api import async_playwright,expect
from tests.browser_payroll_review import sql,select_teacher
from tests.browser_runtime_readiness import nav
import monthly_finance as F

OUT=Path('visual-evidence/operator-inputs')


async def section(page,key,tab):
    await nav(page,key)
    await expect(page.get_by_role('tab',name=tab,exact=True)).to_be_visible(timeout=30000)
    collapse=page.get_by_role('button', name='Collapse sidebar', exact=True)
    if await collapse.is_visible(): await collapse.click()
    await page.get_by_role('tab',name=tab,exact=True).click()


async def fill_amount(page,selector,value):
    field=page.locator(selector+' input')
    await field.fill(str(value));await field.press('Tab')


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    results=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
        for width in (390,1280):
            marker=uuid.uuid4().hex[:8];tid='T'+uuid.uuid4().hex[:19]
            name=f'معلمة تجربة {marker} ([أ])+ .'
            sql('INSERT INTO teachers(national_id,full_name,salary) VALUES(%s,%s,2000)',(tid,name))
            ident=sql("""INSERT INTO expenses(expense_date,category,amount,amount_paid,payment_status)
                VALUES(%s,%s,1200,1000,'مدفوع جزئياً') RETURNING expense_id""",(F.today(),'فاتورة تجربة '+marker))[0]['expense_id']
            ctx=await browser.new_context(viewport={'width':width,'height':950})
            page=await ctx.new_page()
            try:
                await page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded')
                await section(page,'salaries','➕ صرف راتب شهري')
                await select_teacher(page,'.st-key-salary_teacher',name)
                await fill_amount(page,'.st-key-salary_bonus_v0',500)
                await fill_amount(page,'.st-key-salary_deductions_v0',100)
                await expect(page.get_by_text(re.compile('صافي الراتب المستحق للصرف:.*2,400.00'))).to_be_visible(timeout=20000)
                assert not sql('SELECT payment_id FROM teacher_payments WHERE national_id=%s',(tid,))
                await page.screenshot(path=str(OUT/f'salary-preview-{width}.png'),full_page=True)
                await page.locator('.st-key-salary_save_v0 button').click()
                await expect(page.get_by_text('تم صرف الراتب وحفظ القسيمة',exact=False)).to_be_visible(timeout=20000)
                rows=sql('SELECT base_salary,bonus,deductions,cash_amount FROM teacher_payments WHERE national_id=%s',(tid,))
                assert len(rows)==1 and rows[0]=={'base_salary':Decimal(2000),'bonus':Decimal(500),
                    'deductions':Decimal(100),'cash_amount':Decimal(2400)},rows
                await page.get_by_role('tab',name='📋 سجل الرواتب والإعادة',exact=True).click()
                for term in ('(',')','[',']','+','.','\\','معلمة','2026-10','لا نتائج '+marker,''):
                    search=page.locator('.st-key-salary_log_search input')
                    await search.fill(term);await search.press('Enter')
                    total=sql("""SELECT COALESCE(SUM(p.cash_amount),0) AS n
                        FROM teacher_payments p JOIN teachers t USING(national_id)
                        WHERE position(%s in t.full_name)>0 OR position(%s in p.salary_month)>0""",(term,term))[0]['n']
                    await expect(page.locator('[data-testid="stMetricValue"]')).to_have_text(f'{total:,.2f} أوقية قديمة',timeout=15000)
                    await expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                await page.screenshot(path=str(OUT/f'salary-literal-search-{width}.png'),full_page=True)
                await section(page,'expenses','⚙️ إدارة المصروفات والديون')
                chooser=page.locator('.st-key-expense_manage_select input[role="combobox"]')
                await chooser.click();await chooser.fill('فاتورة تجربة '+marker)
                await page.get_by_role('option').filter(has_text=marker).click()
                open_editor=page.locator(f'.st-key-open_dialog_expense_{ident} button')
                await expect(open_editor).to_be_visible(timeout=30000)
                await open_editor.click()
                await expect(page.get_by_role('dialog')).to_be_visible(timeout=30000)
                form=page.get_by_role('dialog')
                total_input=form.get_by_role('spinbutton',name='إجمالي الفاتورة',exact=True)
                paid_input=form.get_by_role('spinbutton',name='المبلغ المدفوع فعلياً',exact=True)
                await expect(form.get_by_role('textbox',name='المورد',exact=True)).to_have_value('')
                await expect(form.get_by_role('textbox',name='ملاحظات',exact=True)).to_have_value('')
                await expect(total_input).to_have_value('1200.00',timeout=20000)
                await total_input.fill('800')
                await form.get_by_role('textbox',name='سبب تصحيح القيد *',exact=True).fill('تصحيح الفاتورة')
                await form.get_by_role('button',name='حفظ تصحيح القيد',exact=True).click()
                await expect(page.get_by_text('المدفوع أكبر من قيمة الفاتورة.',exact=True)).to_be_visible(timeout=15000)
                await expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                await expect(paid_input).to_have_value('1000.00')
                assert sql('SELECT amount,amount_paid FROM expenses WHERE expense_id=%s',(ident,))[0]=={'amount':Decimal(1200),'amount_paid':Decimal(1000)}
                await page.screenshot(path=str(OUT/f'expense-validation-{width}.png'),full_page=True)
                await total_input.fill('1400')
                await form.get_by_role('button',name='حفظ تصحيح القيد',exact=True).click()
                for _ in range(40):
                    saved=sql('SELECT amount,amount_paid FROM expenses WHERE expense_id=%s',(ident,))[0]
                    if saved['amount']==1400: break
                    await page.wait_for_timeout(200)
                assert saved=={'amount':Decimal(1400),'amount_paid':Decimal(1000)},saved
                await expect(page.locator('[data-testid="stDialog"] [role="dialog"]')).to_have_count(0,timeout=30000)
                await open_editor.click()
                await expect(form).to_be_visible(timeout=30000)
                await expect(total_input).to_have_value('1400.00')
                await expect(paid_input).to_have_value('1000.00')
                await expect(page.locator('[data-testid="stException"]')).to_have_count(0)
                await page.screenshot(path=str(OUT/f'expense-recovered-{width}.png'),full_page=True)
                results.append({'width':width,'salary_preview_and_cash':2400,'literal_search_terms':11,
                    'expense_invalid_preserved':[1200,1000],'expense_recovered':[1400,1000]})
            except Exception:
                await page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
                (OUT/f'failure-{width}.html').write_text(await page.content(),encoding='utf8')
                raise
            finally:
                await ctx.close()
        await browser.close()
    (OUT/'results.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results))


if __name__=='__main__':
    from tests.qa_auth import install
    install()
    asyncio.run(run())
