"""Intake date and a student file that reads financial summaries from their source."""
import asyncio
from datetime import date,timedelta
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

from playwright.async_api import async_playwright,expect
from scripts.build_pages_preview import build
from tests.date_entry_helpers import fill_field


async def main():
    out=Path(__file__).resolve().parents[1]/'visual-evidence'/'subscription-file';out.mkdir(parents=True,exist_ok=True)
    results=[];errors=[]
    with tempfile.TemporaryDirectory() as folder:
        build(Path(folder));server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=folder))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
            try:
                for language in ('ar','fr'):
                    page=await browser.new_page(viewport={'width':1360,'height':1050});page.on('pageerror',lambda e:errors.append(str(e)))
                    await page.goto(f'http://127.0.0.1:{server.server_port}/',wait_until='networkidle')
                    if language=='fr':await page.locator('[data-language="fr"]').click()
                    await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden()
                    await page.evaluate("()=>{page='students';studentMode='add';profileId=null;render()}")
                    await expect(page.locator('#student-subscription-start')).to_have_value(await page.evaluate('today'))
                    await page.locator('#student-form [name=name]').fill('Student subscription QA')
                    await page.locator('#student-form [data-date-part="day"]').first.fill('12')
                    await page.locator('#student-form [data-date-part="month"]').first.select_option('03')
                    await page.locator('#student-form [data-date-part="year"]').first.fill('22')
                    await page.locator('#student-form [name=department_id]').select_option(index=1)
                    await page.locator('#student-form [name=mother]').fill('Mother subscription QA')
                    await page.locator('#student-form [name=motherPhone]').fill('22334455')
                    start=await page.evaluate("(()=>{const d=new Date(today+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-20);return d.toISOString().slice(0,10)})()")
                    await fill_field(page.locator('#student-subscription-start'),start)
                    await page.locator('[data-fee-mode="pay"]').click()
                    await page.locator('#student-form [name=registration]').check();await page.locator('#student-form [name=gilet]').uncheck()
                    await page.locator('#student-form [name=amount]').fill('19000')
                    await page.locator('#student-form .form-end button.primary').click()
                    await expect(page.locator('#student-rows')).to_contain_text('Student subscription QA')
                    sid=await page.evaluate("students.find(s=>s.name==='Student subscription QA').id")
                    await page.locator(f'[data-profile="{sid}"]').click()
                    await expect(page.locator('.file-account-stats .stat')).to_have_count(4)
                    account=await page.evaluate('(id)=>students.find(s=>s.id===id).account',sid)
                    assert account['full']==6 and account['paid']==19000 and account['fee_details']['registration']['paid']==1000
                    assert await page.locator('.subscription-facts,[data-subscription-source],#review-registration-starts').count()==0
                    assert not await page.locator('.file-account-details').evaluate('(el)=>el.open')
                    # One official protected editor, with normal discard and save behavior.
                    await page.locator('#open-profile-edit').click()
                    edited=await page.evaluate("previewAnniversary(today,-2)")
                    await fill_field(page.locator('#profile-registration-start'),edited)
                    await page.locator('#profile-edit-close').click()
                    await expect(page.locator('#profile-edit-dialog .discard-box')).to_be_visible()
                    await page.locator('#profile-edit-dialog [data-discard]').click()
                    await page.locator('#open-profile-edit').click()
                    await expect(page.locator('#profile-registration-start')).to_have_value(start)
                    await fill_field(page.locator('#profile-registration-start'),edited)
                    await page.locator('#profile-edit-child .form-end button.primary').click()
                    await expect(page.locator('#profile-edit-dialog')).not_to_be_visible()
                    assert await page.evaluate('(id)=>students.find(s=>s.id===id).start',sid)==edited
                    assert await page.evaluate("(id)=>previewState.changes.some(c=>c.type==='monthly_accounts'&&c.key===id&&c.after.start_date)",sid)
                    # Payment date stays editable through the existing receipt window.
                    rid=await page.evaluate('(id)=>receipts.find(r=>r.student===id&&!r.cancelled).id',sid)
                    await page.evaluate('(id)=>openReceipt(id)',rid)
                    await page.locator('[data-record-type=receipts][data-record-mode=edit]').click()
                    cash_day=await page.evaluate("(()=>{const d=new Date(today+'T12:00:00Z');d.setUTCDate(d.getUTCDate()-2);return d.toISOString().slice(0,10)})()")
                    await fill_field(page.locator('#record-edit-form [name=date]'),cash_day)
                    await page.locator('#record-edit-form [name=reason]').fill('Correct cash date')
                    await page.locator('#record-edit-form [name=agree]').check()
                    await page.locator('#record-edit-form button.primary').click()
                    await expect(page.locator('#record-dialog')).not_to_be_visible()
                    assert await page.evaluate('(id)=>students.find(s=>s.id===id).start',sid)==edited
                    assert await page.evaluate('receipts.find(r=>r.id===receiptPageId).date')==cash_day
                    assert await page.evaluate('(id)=>receipts.find(r=>r.id===id).cancelled',rid)
                    await page.evaluate("(id)=>{page='students';profileId=id;render()}",sid)
                    await page.locator('.file-account').screenshot(path=str(out/(language+'-desktop.png')))
                    await page.set_viewport_size({'width':390,'height':900})
                    await page.wait_for_function("(()=>{const r=$('#sidebar').getBoundingClientRect();return r.right<=0||r.left>=innerWidth})()")
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                    await page.locator('.file-account').screenshot(path=str(out/(language+'-mobile.png')))
                    await page.locator('#theme').click();await page.locator('.file-account').screenshot(path=str(out/(language+'-dark.png')))
                    results.append(language+': integrated account cards, one protected date editor, discard/save, audited correction and independent receipt date')
                    await page.close()
                assert not errors,errors
            finally:await browser.close();server.shutdown();server.server_close()
    (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':len(results),'results':results},ensure_ascii=False))


if __name__=='__main__':asyncio.run(main())
