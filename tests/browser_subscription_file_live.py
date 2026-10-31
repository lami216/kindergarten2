"""Actual HTTP/PG intake, in-file date correction, history and receipt dates."""
import asyncio
from datetime import date,timedelta
import json
import os
from pathlib import Path
import sys
import uuid

import psycopg2
from playwright.async_api import async_playwright,expect
from tests.date_entry_helpers import fill_field


async def main(origin,username,password,dsn):
    from tests.qa_live_pages import guard
    guard(dsn)
    out=Path(__file__).resolve().parents[1]/'visual-evidence'/'subscription-file-live';out.mkdir(parents=True,exist_ok=True)
    errors=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
        page=await browser.new_page(ignore_https_errors=True,viewport={'width':1360,'height':1050});page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            await page.goto(origin,wait_until='networkidle')
            await page.locator('#live-login [name=username]').fill(username);await page.locator('#live-login [name=password]').fill(password)
            await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden()
            async def api(op,data=None):return await page.evaluate('async({op,data})=>liveCall(op,data===null?undefined:data)',dict(op=op,data=data))
            state=await api('snapshot');today=date.fromisoformat(state['today']);start=today-timedelta(days=20)
            cash=int(state['prices']['registration'])+6*int(state['prices']['tuition'])
            name='Actual subscription student '+uuid.uuid4().hex[:8]
            dep=await api('departments.create',dict(name='Subscription QA '+uuid.uuid4().hex[:8]))
            await page.evaluate('async()=>{await liveLoad();render()}')
            await page.locator('nav [data-page=students]').click();await page.locator('#add-student').click()
            await page.locator('#student-form [name=name]').fill(name)
            await page.locator('#student-form [data-date-part="day"]').first.fill('12')
            await page.locator('#student-form [data-date-part="month"]').first.select_option('03')
            await page.locator('#student-form [data-date-part="year"]').first.fill('22')
            await page.locator('#student-form [name=mother]').fill('Actual mother');await page.locator('#student-form [name=motherPhone]').fill('22334455')
            await page.locator('#student-form [name=department_id]').select_option(str(dep['id']))
            await fill_field(page.locator('#student-subscription-start'),str(start))
            await page.locator('[data-fee-mode=pay]').click();await page.locator('#student-form [name=gilet]').uncheck()
            await page.locator('#student-form [name=registration]').check()
            await page.locator('#student-form [name=amount]').fill(str(cash))
            await page.locator('#student-form .form-end button.primary').click()
            await page.locator('#student-search').fill(name)
            await expect(page.locator('#student-rows')).to_contain_text(name)
            state=await api('snapshot');s=next(s for s in state['students'] if s['name']==name)
            assert s['start']==s['registered_on']==str(start) and s['account']['full']==6
            assert next(r for r in state['receipts'] if r['student']==s['id'])['date']==str(today)
            await page.locator('[data-profile="'+s['id']+'"]').click()
            await expect(page.locator('.file-account-stats .stat')).to_have_count(4)
            await page.locator('#open-profile-edit').click()
            updated=today-timedelta(days=65)
            await fill_field(page.locator('#profile-registration-start'),str(updated))
            await page.locator('#profile-edit-child .form-end button.primary').click()
            await expect(page.locator('#profile-edit-dialog')).not_to_be_visible()
            state=await api('snapshot');corrected=next(row for row in state['students'] if row['id']==s['id'])
            assert corrected['start']==corrected['registered_on']==str(updated) and corrected['account']['paid']==cash
            with psycopg2.connect(dsn) as conn:
                with conn.cursor() as c:
                    c.execute("SELECT before_state->>'start_date',after_state->>'start_date',actor FROM record_changes WHERE table_name='monthly_accounts' AND record_key=%s ORDER BY change_id DESC LIMIT 1",(s['id'],))
                    assert c.fetchone()==(str(start),str(updated),username)
            rid=next(r['id'] for r in state['receipts'] if r['student']==s['id'] and not r['cancelled'])
            await page.evaluate('(id)=>openReceipt(id)',rid)
            await page.locator('[data-record-type=receipts][data-record-mode=edit]').click()
            await fill_field(page.locator('#record-edit-form [name=date]'),str(today-timedelta(days=2)))
            await page.locator('#record-edit-form [name=reason]').fill('Actual payment date correction')
            await page.locator('#record-edit-form [name=agree]').check();await page.locator('#record-edit-form button.primary').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible()
            state=await api('snapshot');corrected=next(row for row in state['students'] if row['id']==s['id'])
            assert corrected['start']==str(updated) and corrected['account']['full']==6
            active=next(r for r in state['receipts'] if r['student']==s['id'] and not r['cancelled'])
            assert active['date']==str(today-timedelta(days=2)) and active['amount']==cash
            await page.evaluate("(id)=>{page='students';profileId=id;render()}",s['id'])
            await page.locator('.file-account').screenshot(path=str(out/'student-live.png'))
            assert not errors,errors
            print('SUBSCRIPTION_FILE_LIVE_OK: intake, protected in-file date correction, audit history and independent receipt date persisted.')
        finally:await browser.close()


if __name__=='__main__':
    state=json.loads((Path(os.environ['KG_LIVE_QA_DIR'])/'state.json').read_text())
    asyncio.run(main(state['origin'],state['username'],state['password'],state['dsn']))
