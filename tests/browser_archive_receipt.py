"""Actual old Streamlit window: archive externally, then click pending cash save."""
import asyncio
import os
from pathlib import Path
import sys
import uuid
from unittest.mock import patch
from urllib.parse import urlparse

import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright, expect
import db
import monthly_finance as F
import records as R
from tests.test_record_management import child, scalar
from tests.browser_child_receipts import open_child

OUT=Path('visual-evidence/archive-receipt')


def connect():
    dsn=os.environ['TEST_POSTGRES_DSN']
    parsed=urlparse(dsn)
    if parsed.hostname not in ('127.0.0.1','localhost') or parsed.path!='/kindergarten_test':
        raise RuntimeError('Disposable local database required')
    return psycopg2.connect(dsn,cursor_factory=RealDictCursor)


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    conn=connect(); conn.autocommit=True
    try:
        with patch.object(db,'new_transaction_connection',side_effect=connect):
            F.update_tariffs(1000,2000,3000,'archive Chromium QA')
            async with async_playwright() as pw:
                browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
                for width in (390,1280):
                    student=child(conn,uuid.uuid4().hex[:10],cash=4500)
                    name=scalar(conn,'SELECT full_name FROM students WHERE student_id=%s',(student,))
                    context=await browser.new_context(viewport={'width':width,'height':900})
                    page=await context.new_page()
                    await open_child(page,name)
                    amount=page.locator(f'.st-key-monthly_amount_{student}_v0 input')
                    await amount.fill('500'); await amount.press('Tab')
                    await page.get_by_role('button',name='معاينة توزيع المبلغ',exact=True).click()
                    await expect(page.get_by_text('معاينة توزيع 500',exact=False)).to_be_visible()
                    await page.get_by_text('أؤكد قبض المبلغ وتوزيعه كما عُرض',exact=True).click()
                    save=page.get_by_role('button',name='💾 تسجيل دفعة',exact=True)
                    await expect(save).to_be_enabled()
                    # The browser still displays the live old confirmation. A
                    # separate transaction archives through the record manager.
                    R.cancel('students',student,actor='second session',reason='أرشفة من نافذة ثانية')
                    await save.click()
                    await expect(page.get_by_text('حساب مؤرشف:',exact=False)).to_be_visible(timeout=25000)
                    await expect(page.get_by_text('أُبطلت معاينة الدفع',exact=False)).to_be_visible()
                    await expect(page.get_by_role('button',name='💾 تسجيل دفعة',exact=True)).to_have_count(0)
                    await expect(page.get_by_text('تم تسجيل الدفعة',exact=False)).to_have_count(0)
                    assert F.projection(conn,student)['cash_paid']==4500
                    assert scalar(conn,'SELECT COUNT(*) FROM monthly_receipts WHERE student_id=%s',(student,))==1
                    await page.screenshot(path=str(OUT/f'archived_old_preview_{width}.png'),full_page=True)
                    await context.close()
                await browser.close()
    finally:
        conn.close()
    print('Chromium 390/1280: pending 500 rejected after archive; cash remains 4500 and no new receipt')


if __name__=='__main__':
    from tests.qa_auth import install
    install()

if __name__=='__main__':
    asyncio.run(run())
