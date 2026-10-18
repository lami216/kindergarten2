"""Production sections at 390/1280px: no legacy dashboard, current reports."""
import asyncio
import json
import os
from pathlib import Path
import uuid

import psycopg2
import pandas as pd
from openpyxl import load_workbook
from playwright.async_api import async_playwright, expect

OUT=Path('visual-evidence/main-cleanup')


async def navigate(page,section):
    button=page.locator('.st-key-nav_'+section+' button')
    await button.wait_for(state='attached',timeout=30000)
    if not await button.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await button.click()
    await expect(page.locator('.section-title')).to_contain_text(
        'الرئيسية' if section=='dashboard' else 'التقارير والتصدير')
    if await button.is_visible():
        await page.locator('[data-testid="stSidebarCollapseButton"] button').first.click()


async def choose_report(page,label):
    picker=page.locator('.st-key-report_type input[role="combobox"]')
    try:
        await picker.click()
        await picker.fill(label)
        await page.get_by_role('option').filter(has_text=label).last.click()
        # This heading comes from the server-rendered report, not the client picker.
        await expect(page.get_by_role('heading',name=label,exact=True)).to_be_visible()
    except Exception:
        await page.screenshot(path=str(OUT/'report-selection-failure.png'))
        print(await page.locator('.stApp').aria_snapshot(),flush=True)
        raise


async def exported_report(page,path):
    async with page.expect_download() as download:
        await page.get_by_role('button',name='📊 تحميل التقرير كملف Excel',exact=True).click()
    file=await download.value
    await file.save_as(path)
    return pd.read_excel(path)


def assert_literal_workbook(path):
    book=load_workbook(path,data_only=False)
    cells=[cell for sheet in book for row in sheet for cell in row]
    assert any(cell.value=='=1+1' and cell.data_type=='s' for cell in cells)
    assert all(cell.data_type!='f' for cell in cells)
    book.close()


async def top(page):
    await page.evaluate("""() => {
        document.querySelectorAll('*').forEach(e=>{if(e.scrollTop)e.scrollTop=0});
    }""")
    await page.wait_for_timeout(150)


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    prefix=uuid.uuid4().hex[:8]
    child='ملخص حالي '+prefix
    with psycopg2.connect(os.environ['TEST_POSTGRES_DSN']) as conn:
        with conn.cursor() as c:
            c.execute('INSERT INTO school_departments(name) VALUES(%s) RETURNING department_id',
                      ('قسم جديد '+prefix,))
            department=c.fetchone()[0]
            sid='clean'+prefix
            c.execute('INSERT INTO students(student_id,full_name) VALUES(%s,%s)',(sid,child))
            c.execute('INSERT INTO student_departments(student_id,department_id) VALUES(%s,%s)',
                      (sid,department))
            c.execute('INSERT INTO students(student_id,full_name) VALUES(%s,%s)',('form'+prefix,'=1+1'))
            c.execute('INSERT INTO student_departments(student_id,department_id) VALUES(%s,%s)',
                      ('form'+prefix,department))
    results=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch()
        for width in (390,1280):
            context=await browser.new_context(viewport={'width':width,'height':900})
            page=await context.new_page()
            await page.goto('http://127.0.0.1:8501',wait_until='domcontentloaded')
            await expect(page.get_by_text('ملخص الروضة',exact=True)).to_be_visible(timeout=30000)
            await navigate(page,'dashboard')
            for night in (False,True):
                toggle=page.locator('.st-key-night_mode [role="switch"]').first
                if await toggle.is_checked()!=night:
                    await page.locator('.st-key-night_mode label').last.click()
                if night: await expect(toggle).to_be_checked()
                else: await expect(toggle).not_to_be_checked()
                await expect(page.locator('[data-testid="stPlotlyChart"]')).to_have_count(0)
                for text in ('استحقاق الرواتب الشهري','تشغيلية مدفوعة','ديون الموردين',
                             'الأصول والتجهيزات','الرسوم البيانية وآخر التسجيلات'):
                    await expect(page.locator('[data-testid="stMain"]').get_by_text(text,exact=True)).to_have_count(0)
                await top(page)
                await page.screenshot(path=str(OUT/f'dashboard-{width}-{"night" if night else "day"}.png'))
            await page.get_by_role('button',name='عرض الوصولات',exact=True).click()
            await expect(page.locator('.section-title')).to_contain_text('الدفعات المالية')
            await expect(page.get_by_role('tab',name='🧾 الوصولات',exact=True)).to_have_attribute('aria-selected','true')
            await navigate(page,'reports')
            await expect(page.locator('.st-key-reports_legacy input')).not_to_be_checked()
            await choose_report(page,'الطلاب وأولياء الأمور')
            exported=await exported_report(page,OUT/f'students-{width}.xlsx')
            assert_literal_workbook(OUT/f'students-{width}.xlsx')
            row=exported[exported['اسم الطالب']==child]
            assert len(row)==1 and row.iloc[0]['القسم']=='قسم جديد '+prefix
            await expect(page.get_by_text('السنة الدراسية',exact=True)).to_have_count(0)
            await choose_report(page,'كشف الحضور حسب القسم')
            exported=await exported_report(page,OUT/f'attendance-{width}.xlsx')
            assert_literal_workbook(OUT/f'attendance-{width}.xlsx')
            row=exported[exported['اسم الطالب']==child]
            assert len(row)==1 and row.iloc[0]['القسم']=='قسم جديد '+prefix
            assert 'الأحد' in exported.columns and 'الخميس' in exported.columns
            await top(page)
            await page.screenshot(path=str(OUT/f'attendance-{width}.png'))
            assert await page.locator('[data-testid="stException"]').count()==0
            results.append({'width':width,'dashboard_no_charts_or_obligations':True,
                            'current_department_reports_without_legacy_registration':True,
                            'receipt_shortcut':True,'excel_formula_text_literal':True})
            await context.close()
        await browser.close()
    (OUT/'results.json').write_text(json.dumps(results,indent=2),encoding='utf8')
    print(json.dumps(results))


asyncio.run(run())
