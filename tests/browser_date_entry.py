"""Manual dates: real forms, leap days, filters, unsaved edits, AR/FR and mobile."""
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.async_api import async_playwright, expect
from scripts.build_pages_preview import build
from tests.date_entry_helpers import fill_field


async def main():
    out = Path(__file__).resolve().parents[1] / 'visual-evidence' / 'manual-dates'
    out.mkdir(parents=True, exist_ok=True)
    errors, passed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp))
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=tmp))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, channel='chrome' if sys.platform == 'win32' else None)
            try:
                for language in ('ar', 'fr'):
                    context = await browser.new_context(viewport={'width': 1360, 'height': 960})
                    page = await context.new_page()
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    await page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
                    if language == 'fr':
                        await page.locator('[data-language="fr"]').click()
                    await page.locator('#preview-enter').click()
                    await expect(page.locator('#preview-login')).to_be_hidden()
                    await page.evaluate("navigate('students'); studentMode='add'; render()")
                    birth = page.locator('#student-form [name="birth"]')
                    await expect(birth).to_have_attribute('data-date-canonical', '')
                    group = birth.locator('xpath=preceding-sibling::*[1]')
                    assert await group.locator('select option').count() == 13
                    assert await group.locator('.date-entry-century').inner_text() == '20'
                    await fill_field(birth, '2024-02-29')
                    await expect(birth).to_have_value('2024-02-29')
                    await fill_field(birth, '2025-02-29')
                    assert not await birth.evaluate('(el)=>el.form.checkValidity()')
                    await expect(group.locator('.date-entry-error')).to_be_visible()
                    await fill_field(birth, '2024-04-31')
                    assert not await birth.evaluate('(el)=>el.form.checkValidity()')
                    await fill_field(birth, '2024-04-30')
                    await expect(birth).to_have_value('2024-04-30')
                    await group.locator('[data-date-part="day"]').fill('٢٩')
                    await group.locator('[data-date-part="year"]').fill('٢٤')
                    await group.locator('[data-date-part="year"]').press('Tab')
                    await expect(birth).to_have_value('2024-04-29')
                    await group.locator('[data-date-part="year"]').fill('2')
                    assert not await birth.evaluate('(el)=>el.form.checkValidity()')
                    await fill_field(birth, '2099-01-01')
                    assert not await birth.evaluate('(el)=>el.form.checkValidity()')
                    await fill_field(birth, '2022-01-15')
                    assert await birth.evaluate('(el)=>new FormData(el.form).get("birth")') == '2022-01-15'
                    passed.append(language + ': calendar boundaries, Arabic digits, ISO form data')

                    # Today's expense date remains pre-filled but saves a manually corrected date.
                    await page.evaluate("navigate('expenses')")
                    expense_date = page.locator('#expense-form [name="date"]')
                    await expect(expense_date).to_have_value(await page.evaluate('today'))
                    await fill_field(expense_date, '2026-09-18')
                    await page.locator('#expense-form [name="category"]').fill('Manual date QA')
                    await page.locator('#exp-amount').fill('100')
                    await page.locator('#expense-form button.primary').click()
                    await page.wait_for_function("expenses.some(e=>e.category==='Manual date QA'&&e.date==='2026-09-18')")
                    passed.append(language + ': real expense form stores edited default date')

                    await page.evaluate("navigate('payments')")
                    student = await page.evaluate("students.find(s=>!s.cancelled&&!s.exempt).id")
                    await page.locator('#payment-student').select_option(str(student))
                    payment_date = page.locator('#pay-date')
                    await expect(payment_date).to_have_value(await page.evaluate('today'))
                    await fill_field(payment_date, '2026-09-17')
                    await page.locator('#pay-amount').fill('1000')
                    await page.locator('#payment-preview-button').click()
                    await expect(page.locator('#pay-agree')).to_be_visible()
                    await fill_field(payment_date, '2026-09-18')
                    await expect(page.locator('#pay-agree')).to_have_count(0)
                    await page.locator('#payment-preview-button').click()
                    await page.locator('#pay-agree').check()
                    await page.locator('#pay-save').click()
                    await page.wait_for_function("receipts.some(r=>r.date==='2026-09-18'&&r.amount===1000)")
                    passed.append(language + ': payment date saved and stale preview cleared')

                    # Enhancement itself does not make an untouched protected dialog dirty.
                    await page.evaluate("salaryWindow('salary')")
                    month = page.locator('#payroll-form [name="month"]')
                    await expect(month).to_have_attribute('data-date-canonical', '')
                    await page.locator('#workspace-close').click()
                    await expect(page.locator('#record-dialog')).not_to_be_visible()
                    await page.evaluate("salaryWindow('salary')")
                    await fill_field(month, '2026-09')
                    await expect(month).to_have_value('2026-09')
                    await page.locator('#workspace-close').click()
                    await expect(page.locator('.discard-box')).to_be_visible()
                    await page.locator('[data-discard]').click()
                    passed.append(language + ': monthly salary selector and unsaved-change guard')

                    # Empty optional dates are allowed; partial drafts still prompt on leaving.
                    await page.evaluate('''openProtected('Date QA', '<form id="date-qa"><label>Optional<input type="date" name="optional"></label><label>Historic<input type="date" name="historic" value="1999-12-31"></label><label>Limited<input type="date" name="limited" min="2024-01-01" max="2024-12-31" value="2024-05-06"></label><button type="reset">Reset</button></form>')''')
                    optional = page.locator('[name="optional"]')
                    await expect(optional).to_have_attribute('data-date-canonical', '')
                    assert await optional.evaluate('(el)=>el.form.checkValidity()')
                    historic = page.locator('[name="historic"]')
                    await expect(historic).to_have_value('1999-12-31')
                    await expect(historic.locator('xpath=preceding-sibling::*[1]').locator('.date-entry-century')).to_have_text('19')
                    limited = page.locator('[name="limited"]')
                    await fill_field(limited, '2023-12-31')
                    assert not await limited.evaluate('(el)=>el.form.checkValidity()')
                    await fill_field(limited, '2024-07-08')
                    await page.locator('#date-qa [type="reset"]').click()
                    await expect(limited).to_have_value('2024-05-06')
                    await optional.locator('xpath=preceding-sibling::*[1]').locator('[data-date-part="day"]').fill('1')
                    await page.evaluate("window.invalidDateSubmits=0;document.querySelector('#date-qa').onsubmit=e=>{e.preventDefault();invalidDateSubmits++};document.querySelector('#date-qa').requestSubmit()")
                    assert await page.evaluate('invalidDateSubmits') == 0
                    await page.locator('#workspace-close').click()
                    await expect(page.locator('.discard-box')).to_be_visible()
                    await page.locator('[data-discard]').click()
                    passed.append(language + ': optional, partial draft, legacy year, bounds and reset')

                    # No page reload while moving between the three attendance components.
                    await page.evaluate("navigate('student-attendance')")
                    await expect(page.locator('#attendance-department')).to_be_enabled()
                    attendance_date = page.locator('#attendance-date')
                    await expect(attendance_date).to_have_attribute('data-date-canonical', '')
                    original = await attendance_date.input_value()
                    target = original[:8] + ('01' if original[-2:] != '01' else '02')
                    await fill_field(attendance_date, target)
                    await page.wait_for_function('(target)=>attendanceState.date===target', arg=target)
                    await page.evaluate("navigate('teacher-attendance')")
                    await expect(page.locator('#attendance-date')).to_have_attribute('data-date-canonical', '')
                    passed.append(language + ': student and teacher attendance dates')

                    await page.evaluate("navigate('students');studentMode='add';render()")
                    await page.set_viewport_size({'width': 390, 'height': 844})
                    await page.evaluate("document.querySelector('#sidebar').classList.remove('open')")
                    await page.wait_for_function("(()=>{const r=document.querySelector('#sidebar').getBoundingClientRect();return r.right<=0||r.left>=innerWidth})()")
                    await page.screenshot(path=str(out / (language + '-mobile.png')), full_page=True)
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.locator('#theme').click()
                    await page.screenshot(path=str(out / (language + '-dark.png')), full_page=True)
                    await context.close()
                assert not errors, errors
            finally:
                await browser.close()
                server.shutdown()
    (out / 'results.json').write_text(json.dumps({'passed': passed, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('MANUAL_DATE_BROWSER_OK', len(passed), 'scenarios', errors)


if __name__ == '__main__':
    asyncio.run(main())
