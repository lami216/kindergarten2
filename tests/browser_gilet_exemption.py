"""Actual live UI, TLS and PostgreSQL; synthetic students, Arabic/French, mobile."""
import asyncio
from datetime import date,timedelta
from pathlib import Path
import sys,uuid
from playwright.async_api import async_playwright,expect
from tests.date_entry_helpers import fill_field


async def main(origin,username,password,dsn):
    from tests.qa_live_pages import guard
    guard(dsn)
    output=Path(__file__).resolve().parents[1]/'visual-evidence'/'gilet-exemption';output.mkdir(parents=True,exist_ok=True)
    errors=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
        for lang,width in [('ar',1360),('fr',390),('ar',390),('fr',1360)]:
            context=await browser.new_context(ignore_https_errors=True,viewport=dict(width=width,height=1000))
            page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
            await page.goto(origin,wait_until='networkidle')
            if lang=='fr':
                await page.locator('[data-language=fr]').click();await page.wait_for_load_state('networkidle')
            await page.locator('#live-login [name=username]').fill(username)
            await page.locator('#live-login [name=password]').fill(password)
            await page.locator('#preview-enter').click();await expect(page.locator('body')).not_to_have_class('login-mode')
            async def api(op,data=None):
                return await page.evaluate('''async ([op,data])=>{const r=await liveCall(op,data===null?undefined:data);return r;}''',[op,data])
            state=await api('snapshot');dep=next(d for d in state['departments'] if not d['cancelled'])
            price=int(state['prices']['gilet']);assert price>0
            name='Garment UI '+lang+str(width)+' '+uuid.uuid4().hex[:5]
            created=await api('students.create',dict(department_id=dep['id'],name=name,birth='2022-01-01',gender='ذكر',mother='Synthetic parent',motherPhone='22000000',mode='pay',amount='0',registration=False,gilet=False,start_date=str(date.today()-timedelta(days=40)),request_token=str(uuid.uuid4())))
            sid=created['id'];await page.evaluate('async sid=>{await liveLoad();profileId=sid;page="students";render();}',sid)
            await page.locator('[data-gilet]').click();await expect(page.locator('#gilet-sale-form')).to_be_visible()
            await fill_field(page.locator('#gilet-sale-form [name=date]'),str(date.today()-timedelta(days=1)))
            await page.locator('#gilet-sale-form [name=confirmed]').check()
            await page.screenshot(path=str(output/f'{lang}-{width}-sale.png'),full_page=True)
            await page.locator('#gilet-sale-form button.primary').click()
            await expect(page.locator('#receipt-page')).to_be_visible()
            state=await api('snapshot');r=next(r for r in state['receipts'] if r['student']==sid)
            assert r['gilet']==price and r['monthly']==0 and r['date']==str(date.today()-timedelta(days=1))
            response=await page.request.get(origin+'/api/receipt/'+str(r['id']))
            assert response.status==200 and (await response.body()).startswith(b'%PDF')
            await page.evaluate('sid=>{profileId=sid;page="students";render();}',sid)
            await page.locator('[data-exempt]').click()
            await expect(page.locator('#exemption-form')).to_be_visible()
            await page.locator('#exemption-form [name=reason]').fill('Reviewed exemption by school')
            await page.locator('#exemption-form [name=confirmed]').check()
            await page.screenshot(path=str(output/f'{lang}-{width}-exemption.png'),full_page=True)
            await page.locator('#exemption-form button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible()
            state=await api('snapshot');s=next(s for s in state['students'] if s['id']==sid)
            assert s['exempt'] and s['account']['due']==0 and s['account']['paid']==price
            await page.locator('[data-gilet]').click();await page.locator('#gilet-sale-form [name=confirmed]').check()
            await page.locator('#gilet-sale-form button.primary').click();await expect(page.locator('#receipt-page')).to_be_visible()
            state=await api('snapshot');s=next(s for s in state['students'] if s['id']==sid)
            assert s['exempt'] and s['account']['paid']==2*price
            await page.evaluate('()=>navigate("history")')
            await page.locator('#history-type').select_option('gilet_sales')
            await expect(page.locator('#history-rows')).to_contain_text(name)
            assert await page.locator('html').get_attribute('dir')==('ltr' if lang=='fr' else 'rtl')
            assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')
            await context.close()
        await browser.close()
    assert not errors,errors
    print('GILET_EXEMPTION_LIVE_OK: 4 bilingual desktop/mobile journeys; PDF, cash and exemption persisted')


if __name__=='__main__':
    import json,os
    state=json.loads((Path(os.environ.get('KG_LIVE_QA_DIR','/tmp/kg-original-pages-qa'))/'state.json').read_text())
    asyncio.run(main(state['origin'],state['username'],state['password'],state['dsn']))
