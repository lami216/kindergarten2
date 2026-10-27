"""Preview dates follow the student's anchor, not the editable cash date."""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

from playwright.async_api import async_playwright, expect
from scripts.build_pages_preview import build
from tests.date_entry_helpers import fill_field


async def main():
    out=Path(__file__).resolve().parents[1]/'visual-evidence'/'subscription-anchor'
    out.mkdir(parents=True,exist_ok=True);errors=[];results=[]
    with tempfile.TemporaryDirectory() as folder:
        build(Path(folder))
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=folder))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
            try:
                for language in ('ar','fr'):
                    page=await browser.new_page(viewport={'width':1360,'height':1000})
                    page.on('pageerror',lambda error:errors.append(str(error)))
                    await page.goto(f'http://127.0.0.1:{server.server_port}/',wait_until='networkidle')
                    if language=='fr':await page.locator('[data-language="fr"]').click()
                    await page.locator('#preview-enter').click()
                    await expect(page.locator('#preview-login')).to_be_hidden()
                    sid=await page.evaluate('''async()=>{
                        const created=await liveCall('students.create',{name:'Anchor QA',birth:'2022-01-01',gender:'ذكر',department_id:1,
                            mother:'Anchor mother',motherPhone:'22334455',mode:'pay',amount:'1000',registration:true,gilet:false,request_token:crypto.randomUUID()});
                        const student=previewState.students.find(s=>s.id===created.id);student.start='2026-08-10';
                        previewState.receipts.find(r=>r.student===created.id).date='2026-08-10';
                        await liveLoad();receiptChild=created.id;page='payments';financeTab='payment';render();return created.id;
                    }''')
                    await expect(page.locator('.subscription-anchor-note')).to_contain_text(await page.evaluate("I18N.date('2026-08-10')"))
                    await fill_field(page.locator('#pay-date'),'2026-08-15')
                    await page.locator('#pay-amount').fill('18000')
                    await page.locator('#payment-preview-button').click()
                    await expect(page.locator('.payment-preview')).to_be_visible()
                    expected=['2026-08-10','2026-09-10','2026-10-10','2026-11-10','2026-12-10','2027-01-10']
                    assert await page.evaluate('livePreview.months.map(m=>m.start)')==expected
                    assert await page.evaluate('livePreview.months.at(-1).end')=='2027-02-10'
                    # Changing only the cash date invalidates confirmation, not the month anchor.
                    await fill_field(page.locator('#pay-date'),'2026-08-16')
                    await expect(page.locator('#pay-save')).to_have_count(0)
                    await page.locator('#payment-preview-button').click()
                    await expect(page.locator('.payment-preview')).to_be_visible()
                    assert await page.evaluate('livePreview.months.map(m=>m.start)')==expected
                    await page.locator('#pay-agree').check()
                    await page.locator('#pay-save').click()
                    await expect(page.locator('.payment-preview')).to_have_count(0)
                    record=await page.evaluate('(id)=>({start:previewState.students.find(s=>s.id===id).start,receipt:previewState.receipts.filter(r=>r.student===id).at(-1)})',sid)
                    assert record['start']=='2026-08-10' and record['receipt']['date']=='2026-08-16'
                    assert record['receipt']['monthly']==18000
                    await page.screenshot(path=str(out/(language+'-payment.png')),full_page=True)
                    # A partial month must be completed before advancing to the next one.
                    months=await page.evaluate('''async()=>{
                        const s=previewState.students.find(s=>s.id===receiptChild);
                        previewState.receipts.push({id:9999,student:s.id,amount:1500,monthly:1500,registration:0,gilet:0,date:today,cancelled:false});
                        return (await liveCall('payments.preview',{student:s.id,amount:'4500',date:today})).months;
                    }''')
                    assert [row['allocating'] for row in months]==[1500,3000]
                    assert [row['start'] for row in months]==['2027-02-10','2027-03-10']
                    leap=await page.evaluate("[0,1,2].map(i=>previewAnniversary('2024-01-31',i))")
                    assert leap==['2024-01-31','2024-02-29','2024-03-31']
                    results.append(language+': fixed enrollment anchor, distinct cash date, six months, partial balance and leap day')
                    await page.close()
                assert not errors,errors
            finally:await browser.close();server.shutdown();server.server_close()
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(results),'results':results},ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
