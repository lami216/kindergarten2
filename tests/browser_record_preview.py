"""Actual Chromium: mutations, invalid inputs, audit, totals and phone layout."""
import asyncio
import sys
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading
from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'visual-evidence'/'record-management'


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT/'docs')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
            for width in (390,768,1280):
                page=await browser.new_page(viewport={'width':width,'height':900})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(f'http://127.0.0.1:{server.server_port}')
                await page.locator('#preview-enter').click()
                async def nav(key):
                    if width<=768: await page.locator('#menu').click()
                    await page.locator(f'nav [data-page="{key}"]').click()
                async def manager(kind):
                    await nav('records'); await page.locator('#record-type').select_option(kind)
                async def confirm(reason):
                    await page.locator('#record-edit-form [name="reason"]').fill(reason)
                    await page.locator('#record-edit-form [name="agree"]').check()
                    await page.locator('#record-edit-form button').first.click()
                await nav('registration')
                # Occupied department rename updates its members and cannot duplicate.
                await page.locator('[data-record-type="departments"][data-record-id="تمهيدي · أ"][data-record-mode="edit"]').click()
                await page.locator('#record-edit-form [name="name"]').fill('تحضيري · أ')
                await confirm('محاولة اسم مكرر')
                await expect(page.locator('#record-error')).to_contain_text('يتكرر')
                await page.locator('#record-edit-form [name="name"]').fill('قسم الورود')
                await confirm('تصحيح اسم القسم')
                await expect(page.locator('#record-dialog')).not_to_be_visible()
                await expect(page.locator('td').filter(has_text='قسم الورود').first).to_be_visible()
                await page.screenshot(path=str(OUT/f'departments_{width}.png'),full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                await page.locator('[data-record-type="departments"][data-record-id="قسم الورود"][data-record-mode="cancel"]').click()
                await page.locator('[name="destination"]').select_option('تحضيري · أ')
                await confirm('دمج القسم في التحضيري')
                await expect(page.locator('[data-record-id="قسم الورود"]')).to_have_count(0)
                await manager('expenses')
                await page.locator('[data-record-type="expenses"][data-record-id="2"][data-record-mode="edit"]').click()
                await page.locator('[name="amount"]').fill('800')
                await page.locator('[name="paid"]').fill('900')
                await confirm('مدفوع أكبر من الإجمالي')
                await expect(page.locator('#record-error')).to_contain_text('بين صفر')
                await page.locator('[name="paid"]').fill('500')
                await page.locator('[name="category"]').fill('تنظيف مصحح')
                await confirm('تصحيح مبلغ المصروف')
                await page.locator('[data-record-type="expenses"][data-record-id="1"][data-record-mode="cancel"]').click()
                await confirm('مصروف مكرر')
                await nav('dashboard')
                expense=page.locator('.stat').filter(has=page.locator('.stat-label',has_text='إجمالي المصروفات'))
                await expect(expense.locator('.stat-value')).to_have_text('500')
                await manager('receipts')
                await page.locator('[data-record-type="receipts"][data-record-id="101"][data-record-mode="edit"]').click()
                await page.locator('[name="amount"]').fill('1000')
                await confirm('مبلغ لا يغطي الرسوم')
                await expect(page.locator('#record-error')).to_contain_text('يغطي الرسوم')
                await page.locator('[name="amount"]').fill('7000')
                await confirm('تصحيح القبض')
                await page.locator('[data-record-type="receipts"][data-record-id="106"][data-record-mode="cancel"]').click()
                await confirm('إلغاء الدفعة الخاطئة')
                await nav('dashboard')
                cash=page.locator('.stat').filter(has=page.locator('.stat-label',has_text='إجمالي المقبوضات'))
                await expect(cash.locator('.stat-value')).to_have_text('16,500')
                await manager('students')
                await page.locator('[data-record-type="students"][data-record-id="1"][data-record-mode="cancel"]').click()
                await confirm('إلغاء ملف مكرر')
                await nav('dashboard')
                count=page.locator('.stat').filter(has=page.locator('.stat-label',has_text='الطلاب الحاليون'))
                await expect(count.locator('.stat-value')).to_have_text('5')
                await nav('history')
                await expect(page.locator('.history-entry')).to_have_count(9)
                await page.locator('#history-action').select_option('cancelled')
                await expect(page.locator('.history-entry')).to_have_count(4)
                await page.locator('.history-entry summary').first.click()
                await page.screenshot(path=str(OUT/f'history_{width}.png'),full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert not errors,errors
                await page.close()
            await browser.close()
    finally: server.shutdown()


if __name__=='__main__': asyncio.run(run())
