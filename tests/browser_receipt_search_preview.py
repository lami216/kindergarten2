"""One receipt list, literal family search and actions inside the opened source."""
import asyncio
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'visual-evidence'/'receipt-search'


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT/'docs')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    results=[]
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
            for width in (390,1280):
                page=await browser.new_page(viewport={'width':width,'height':900})
                errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(f'http://127.0.0.1:{server.server_port}')
                await page.locator('#preview-enter').click()
                await page.locator('#home-receipts').click()
                await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(5)
                await expect(page.locator('#content [data-record-type="receipts"]')).to_have_count(0)
                search=page.locator('#receipt-search')
                for term in ('مريم أحمد','٠٠٠٠٠٠٠١','0000 1001','١٠١'):
                    await search.fill(term)
                    await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(1)
                    await expect(page.locator('[data-receipt="101"]')).to_be_visible()
                for term in ('[','لا يوجد','"><img src=x>'):
                    await search.fill(term)
                    await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(0)
                    await expect(page.get_by_text('لا توجد وصولات تطابق هذا البحث.',exact=True)).to_be_visible()
                await search.fill('')
                await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(5)
                assert await page.evaluate('changes.length')==0
                # Names can coincide and siblings can share a parent's phone.
                await page.evaluate("students[1].name=students[0].name;students[1].fatherPhone=students[0].fatherPhone")
                await search.fill('مريم أحمد')
                await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(2)
                await search.fill('00000001')
                await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(2)
                await search.fill('101')
                await page.locator('[data-receipt="101"]').click()
                await expect(page.locator('#receipt-content')).to_contain_text('وصل قبض #101')
                await page.screenshot(path=str(OUT/f'opened-{width}.png'),full_page=True)
                await page.locator('#receipt-content [data-record-mode="edit"]').click()
                await page.locator('#record-edit-form [name="amount"]').fill('7000')
                await page.locator('#record-edit-form [name="reason"]').fill('تصحيح القبض من الوصل')
                await page.locator('#record-edit-form [name="agree"]').check()
                await page.locator('#record-edit-form button').first.click()
                await expect(page.locator('#record-dialog')).not_to_be_visible()
                await expect(page.locator('#receipt-content')).to_contain_text('وصل قبض #106')
                await expect(page.locator('#receipt-content')).to_contain_text('7,000')
                await page.locator('#receipt-content [data-record-mode="cancel"]').click()
                await page.locator('#record-edit-form [name="reason"]').fill('إلغاء الإدخال الخاطئ')
                await page.locator('#record-edit-form [name="agree"]').check()
                await page.locator('#record-edit-form button').first.click()
                await expect(page.locator('#receipt-content')).to_contain_text('لا يدخل في المقبوضات')
                await expect(page.locator('#receipt-content [data-record-type]')).to_have_count(0)
                assert await page.evaluate('changes.length')==2
                assert await page.evaluate("account(students[0]).paid")==0
                await page.locator('#receipt-close').click()
                await search.fill('مريم أحمد')
                await expect(page.locator('#receipt-rows .receipt-row')).to_have_count(3)
                # Both original and corrected cancelled documents remain findable.
                await page.locator('[data-receipt="101"]').click()
                await expect(page.locator('#receipt-content')).to_contain_text('6,000')
                await expect(page.locator('#receipt-content [data-record-type]')).to_have_count(0)
                await page.locator('#receipt-close').click()
                await page.locator('#theme').click()
                await page.screenshot(path=str(OUT/f'search-night-{width}.png'),full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert not errors,errors
                results.append({'width':width,'search':'name, both phones, Arabic digits, siblings, literal input, reset','actions':'open/correct/cancel/history retained','errors':errors})
                await page.close()
            await browser.close()
    finally:
        server.shutdown()
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Single receipt list, family search and document actions passed at 390/1280px')


if __name__=='__main__': asyncio.run(run())
