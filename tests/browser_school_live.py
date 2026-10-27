"""Actual TLS/PostgreSQL family edit from the modal and period school export."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid

from openpyxl import load_workbook
from playwright.async_api import async_playwright, expect


async def main(origin, username, password):
    out=Path(__file__).resolve().parents[1]/'visual-evidence'/'school-live'
    out.mkdir(parents=True,exist_ok=True);errors=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
        page=await browser.new_page(ignore_https_errors=True,viewport={'width':1360,'height':1000})
        page.on('pageerror',lambda error:errors.append(str(error)))
        try:
            await page.goto(origin,wait_until='networkidle')
            await page.locator('#live-login [name="username"]').fill(username)
            await page.locator('#live-login [name="password"]').fill(password)
            await page.locator('#preview-enter').click()
            await expect(page.locator('#preview-login')).to_be_hidden()
            async def api(op,data=None):
                return await page.evaluate('async({op,data})=>liveCall(op,data===null?undefined:data)',dict(op=op,data=data))
            state=await api('snapshot');today=state['today'];dep=await api('departments.create',dict(name='School QA '+uuid.uuid4().hex[:8]))
            before=await api('reports.finance',dict(start=today,end=today))
            base=dict(department_id=dep['id'],birth='2022-01-01',gender='ذكر',mode='pay',amount='0',registration=False,gilet=False)
            first=await api('students.create',dict(base,name='Family school QA',mother='School mother QA',motherPhone='22334455',request_token=str(uuid.uuid4())))
            state=await api('snapshot');student=next(s for s in state['students'] if s['id']==first['id'])
            second=await api('students.create',dict(base,name='Sibling school QA',existing_parent_id=student['parent_id'],request_token=str(uuid.uuid4())))
            await page.evaluate("async(id)=>{await liveLoad();profileId=id;page='students';render()}",first['id'])
            await page.locator('#open-profile-edit').click()
            await page.locator('#profile-edit-child [name="motherPhone"]').fill('99887766')
            await page.locator('#profile-edit-child .form-end button.primary').click()
            await expect(page.locator('#profile-edit-dialog')).to_be_hidden()
            state=await api('snapshot')
            assert all(next(s for s in state['students'] if s['id']==sid)['motherPhone']=='99887766' for sid in (first['id'],second['id']))
            await api('attendance.save',dict(kind='students',date=today,entries=[
                dict(person=first['id'],status='present',excuse='',revision=0),
                dict(person=second['id'],status='excused',excuse='Medical visit',revision=0)]))
            await page.locator('#nav-reports').click()
            await page.locator('[data-fin-period="today"]').click()
            await expect(page.locator('.school-cards')).to_be_visible()
            await page.locator('[data-report-section=attendance][role=tab]').click()
            data=await page.evaluate('financeData')
            assert data['school']['new_count']==before['school']['new_count']+2
            rows={r['id']:r for r in data['school']['attendance']['items']}
            assert rows[first['id']]['attendance_rate']==100 and rows[second['id']]['absence_rate']==100
            assert data['school']['attendance']['summary']['total']==before['school']['attendance']['summary']['total']+2
            async with page.expect_download() as event:await page.locator('#fin-xlsx').click()
            download=await event.value;await download.save_as(out/'school-real.xlsx')
            book=load_workbook(out/'school-real.xlsx')
            assert any(row[0]=='Sibling school QA' for row in book['حضور الطلاب'].values)
            await page.locator('.school-period').screenshot(path=str(out/'period-live.png'))
            assert not errors,errors
            print('SCHOOL_LIVE_OK: parent modal saved both siblings; actual period report, attendance and XLSX verified.')
        finally:await browser.close()


if __name__=='__main__':
    state=json.loads((Path(os.environ['KG_LIVE_QA_DIR'])/'state.json').read_text())
    from tests.qa_live_pages import guard
    guard(state['dsn'])
    asyncio.run(main(state['origin'],state['username'],state['password']))
