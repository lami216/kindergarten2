"""Fresh-install server: 3 sessions, real ZIP download, dark datepicker contrast."""
import asyncio
import json
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import patch
import zipfile

from playwright.async_api import async_playwright, expect
import db
import monthly_finance as F
from data_export import verify_export
from tests.browser_archive_receipt import connect
from tests.test_record_management import child, scalar

BASE='http://127.0.0.1:8501'
OUT=Path('visual-evidence/runtime')


async def nav(page,key):
    button=page.locator(f'.st-key-nav_{key} button')
    await button.wait_for(state='attached',timeout=30000)
    if not await button.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await button.click()


async def calendar(page,width):
    await nav(page,'students')
    await expect(page.get_by_role('tab',name='➕ إضافة طالب جديد')).to_be_visible(timeout=30000)
    collapse=page.locator('[data-testid="stSidebarCollapseButton"] button').first
    if await collapse.is_visible(): await collapse.click()
    await page.get_by_role('tab',name='➕ إضافة طالب جديد').click()
    draft=page.get_by_role('textbox',name='اسم الطفل *',exact=True)
    await expect(draft).to_be_visible()
    await draft.fill('مسودة اختبار التقويم'); await draft.press('Tab')
    toggle=page.locator('.st-key-night_mode [role="switch"]')
    if not await toggle.is_checked():
        await page.locator('.st-key-night_mode').click()
    await page.wait_for_function("getComputedStyle(document.querySelector('.stApp')).backgroundColor==='rgb(16, 21, 25)'")
    await expect(draft).to_have_value('مسودة اختبار التقويم')
    field=page.get_by_label('تاريخ الميلاد *',exact=True)
    if not await field.count(): field=page.locator('[data-testid="stDateInput"] input').first
    # Current month includes selected, ordinary and future/disabled days.
    await field.fill(F.today().strftime('%Y/%m/%d'))
    await field.press('Enter')
    await expect(field).to_have_value(F.today().strftime('%Y/%m/%d'))
    samples=[]
    for attempt in range(2):
        await field.click()
        popup=page.locator('[data-baseweb="calendar"]')
        await expect(popup).to_be_visible()
        probe=await popup.evaluate('''root=>{
          const rgb=s=>(s.match(/[\\d.]+/g)||[]).map(Number);
          const luminance=c=>c.slice(0,3).map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4})
             .reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
          const cells=[...root.querySelectorAll('[role="gridcell"][aria-label]')];
          return {root:getComputedStyle(root).backgroundColor,cells:cells.map(cell=>{
            const number=cell.querySelector('div')||cell;
            const style=getComputedStyle(number); let node=number,bg;
            while(node){bg=rgb(getComputedStyle(node).backgroundColor);if(bg.length===3||bg[3]===1)break;node=node.parentElement;}
            const fg=rgb(style.color); const a=luminance(fg),b=luminance(bg||[0,0,0]);
            return {label:cell.getAttribute('aria-label'),text:number.textContent,color:style.color,
                    background:bg,contrast:(Math.max(a,b)+.05)/(Math.min(a,b)+.05)};
          })};
        }''')
        (OUT/f'calendar-probe-{width}-{attempt}.json').write_text(json.dumps(probe,indent=2))
        await page.screenshot(path=str(OUT/f'calendar-night-{width}-{attempt}.png'),full_page=True)
        assert probe['root']=='rgb(32, 34, 35)',probe
        assert len(probe['cells'])>=28,probe
        assert all(c['contrast']>=4.5 for c in probe['cells']),probe
        samples.append(probe)
        await page.keyboard.press('Escape')
        await expect(popup).to_be_hidden()
    # Actual selection works, then daylight remains readable and draft survives.
    await field.click()
    cell=page.locator('[data-baseweb="calendar"] [role="gridcell"][aria-label^="Choose"]').first
    if not await cell.count():
        cell=page.locator('[data-baseweb="calendar"] [role="gridcell"][aria-label^="Selected"]').first
    await cell.click()
    await expect(page.locator('[data-baseweb="calendar"]')).to_be_hidden()
    await page.locator('.st-key-night_mode').click()
    await page.wait_for_function("getComputedStyle(document.querySelector('.stApp')).backgroundColor==='rgb(250, 250, 249)'")
    await expect(draft).to_have_value('مسودة اختبار التقويم')
    assert await page.locator('[data-testid="stException"]').count()==0
    return {'width':width,'opens':2,'minimum_contrast':min(c['contrast'] for s in samples for c in s['cells'])}


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    conn=connect();conn.autocommit=True
    try:
        with patch.object(db,'new_transaction_connection',side_effect=connect):
            F.update_tariffs(1000,2000,3000,'runtime browser QA')
            student=child(conn,uuid.uuid4().hex[:10],cash=12000)
        receipt=scalar(conn,'SELECT receipt_id FROM monthly_receipts WHERE student_id=%s',(student,))
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
            contexts=[await browser.new_context(viewport={'width':1280,'height':900}) for _ in range(3)]
            pages=[await c.new_page() for c in contexts]
            async def open_page(page):
                await page.goto(BASE,wait_until='domcontentloaded')
                await expect(page.get_by_text('ملخص الروضة',exact=True)).to_be_visible(timeout=45000)
                assert await page.locator('[data-testid="stException"]').count()==0
            await asyncio.gather(*(open_page(p) for p in pages))
            pids=[await p.locator('#qa-session').get_attribute('data-backend') for p in pages]
            assert len(set(pids))==3,pids
            page=pages[0]
            await page.locator('.st-key-nav_backup_dialog button').click()
            await page.get_by_role('button',name='تجهيز ملف التصدير',exact=True).click()
            download=page.get_by_role('button',name='📥 تحميل البيانات كاملة',exact=True)
            await expect(download).to_be_visible(timeout=45000)
            async with page.expect_download(timeout=30000) as event:
                await download.click()
            result=await event.value
            assert await result.failure() is None
            target=OUT/'downloaded-data.zip'
            await result.save_as(target)
            manifest=verify_export(target.read_bytes())
            with zipfile.ZipFile(target) as z:
                receipts=json.loads(z.read('data/monthly_receipts.json'))
                assert any(r['receipt_id']==receipt and r['amount']==12000 for r in receipts)
                assert 'data/record_changes.json' in z.namelist()
            print(json.dumps({'concurrent_sessions':3,'distinct_connections':len(set(pids)),
                'real_zip_download_bytes':target.stat().st_size,'verified_tables':len(manifest['tables']),
                'receipt_12000_verified':True}))
            for context in contexts: await context.close()
            calendars=[]
            for width in (390,1280):
                context=await browser.new_context(viewport={'width':width,'height':900})
                page=await context.new_page();await page.goto(BASE,wait_until='domcontentloaded')
                try:
                    calendars.append(await calendar(page,width))
                except Exception:
                    await page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
                    (OUT/f'failure-{width}.html').write_text(await page.content(),encoding='utf8')
                    raise
                await context.close()
            await browser.close()
        report={'concurrent_sessions':3,'distinct_connections':len(set(pids)),
                'download_bytes':target.stat().st_size,'verified_tables':len(manifest['tables']),
                'receipt_12000_verified':True,'calendars':calendars}
        (OUT/'results.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:
        conn.close()


if __name__=='__main__': asyncio.run(run())
