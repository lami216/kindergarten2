"""Actual app photo intake, replacement/removal, private viewer and mobile file."""
import asyncio
import io
import json
import os
import re
from pathlib import Path
import uuid
from unittest.mock import patch
from PIL import Image
import streamlit as st
from playwright.async_api import async_playwright,expect
import access_control as A
import db
import student_photos as P
from tests.browser_admin_access import connection,login,nav,select,PASSWORD
from tests.browser_child_receipts import toggle_theme

BASE='http://127.0.0.1:8503'
OUT=Path('visual-evidence/student-profile')


def query(sql,args=()):
    with connection() as conn:
        with conn.cursor() as c:
            c.execute(sql,args);return c.fetchall() if c.description else []


async def run():
    from urllib.parse import urlparse
    parsed=urlparse(os.environ.get('TEST_POSTGRES_DSN',''))
    assert parsed.hostname in ('127.0.0.1','localhost') and parsed.path=='/kindergarten_test'
    OUT.mkdir(parents=True,exist_ok=True)
    first=OUT/'first.png';second=OUT/'second.png';bad=OUT/'invalid.png'
    Image.new('RGB',(900,700),'#80c5b1').save(first)
    Image.new('RGB',(700,900),'#3a86b8').save(second)
    bad.write_bytes(b'Not an image, despite its extension')
    results=[]
    with patch.object(db,'new_transaction_connection',side_effect=connection):
        st.session_state['auth_session']=A.login('qa-owner',PASSWORD)
        viewer='photo-viewer-'+uuid.uuid4().hex[:8]
        A.save_user(employee_name='مشاهدة الملف فقط',name=viewer,password=PASSWORD,permissions=['students.view'])
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        for width in (390,1280):
            page=await browser.new_page(viewport={'width':width,'height':1000})
            try:
                name='طفل ملف '+uuid.uuid4().hex[:8]
                await login(page,'qa-owner');await nav(page,'students')
                await page.get_by_role('tab',name='➕ إضافة طالب جديد',exact=True).click()
                await page.locator('.st-key-kid_name input').fill(name)
                await select(page,'kid_gender','ذكر' if width==1280 else 'أنثى')
                await page.locator('.st-key-kid_mother_name input').fill('أم الملف')
                await page.locator('.st-key-kid_mother_phone input').fill('22334455')
                await page.locator('.st-key-kid_mother_phone input').press('Tab')
                await page.get_by_text('📷 صورة الطالب (اختياري)',exact=True).click()
                await page.locator('.st-key-kid_photo input[type="file"]').set_input_files(first)
                await expect(page.locator('.st-key-kid_photo').get_by_text(first.name,exact=True)).to_be_visible(timeout=30000)
                await page.get_by_text('تفاصيل اختيارية',exact=True).click()
                await page.locator('.st-key-kid_health textarea').fill('تحتاج مراجعة الأسرة قبل تقديم الحليب <b>معلومة</b>')
                await page.locator('.st-key-kid_health textarea').press('Tab')
                await page.get_by_role('button',name='💾 حفظ بيانات الطفل والأهل',exact=True).click()
                await expect(page.get_by_text('تم حفظ الطفل والأهل بنجاح.',exact=False)).to_be_visible(timeout=30000)
                sid=query('SELECT student_id FROM students WHERE full_name=%s',(name,))[0]['student_id']
                stored=query('SELECT * FROM student_photos WHERE student_id=%s',(sid,))[0]
                assert bytes(stored['image_data'])==P.normalize(first.read_bytes())['image_data']
                await page.get_by_role('tab',name='📋 عرض / تعديل / حذف',exact=True).click()
                search=page.get_by_role('textbox',name='🔍 ابحث باسم الطفل أو ولي الأمر أو رقم الهاتف',exact=True)
                await search.fill(name);await search.press('Enter')
                picker=page.locator('.st-key-student_select_edit input[role="combobox"]')
                await picker.click();await picker.fill(name)
                await page.get_by_role('option').filter(has_text=name).last.click()
                await expect(page.locator('.student-file-hero')).to_be_visible(timeout=30000)
                assert await page.locator(f'.st-key-open_dialog_student_photo_{sid} button').evaluate('(e)=>e.getBoundingClientRect().width')<200
                await expect(page.get_by_role('img',name='صورة '+name,exact=True)).to_be_visible()
                await expect(page.get_by_role('img',name='صورة '+name,exact=True)).to_have_attribute('src',re.compile(r'^data:image/jpeg;base64,'))
                await expect(page.locator('.student-file-details').get_by_text('تحتاج مراجعة الأسرة قبل تقديم الحليب <b>معلومة</b>',exact=True)).to_be_visible()
                assert await page.locator('.student-file-details b').count()==0
                await expect(page.locator('.student-file-badges .boy' if width==1280 else '.student-file-badges .girl')).to_be_visible()
                await page.get_by_role('button',name='تعديل بيانات الطالب',exact=True).click()
                await expect(page.get_by_role('dialog')).to_be_visible()
                await page.locator(f'.st-key-edit_{sid}_address input').fill('مسودة عنوان')
                await page.get_by_role('button',name='إغلاق دون حفظ',exact=True).click()
                await expect(page.get_by_text('لديك تغييرات غير محفوظة.',exact=False)).to_be_visible()
                await page.get_by_role('button',name='متابعة التعديل',exact=True).click()
                await expect(page.locator(f'.st-key-edit_{sid}_address input')).to_have_value('مسودة عنوان')
                await page.get_by_role('button',name='إغلاق دون حفظ',exact=True).click()
                await page.get_by_role('button',name='تجاهل التغييرات والخروج',exact=True).click()
                await expect(page.get_by_role('dialog')).to_have_count(0,timeout=30000)
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                assert query('SELECT address FROM students WHERE student_id=%s',(sid,))[0]['address'] in ('',None)
                await page.get_by_role('button',name='تعديل بيانات الطالب',exact=True).click()
                await expect(page.locator(f'.st-key-edit_{sid}_address input')).to_have_value('')
                await page.get_by_role('button',name='إغلاق دون حفظ',exact=True).click()
                # React Aria retains closed dialog nodes; no visible modal may remain.
                await expect(page.get_by_role('dialog')).to_have_count(0,timeout=30000)
                await page.screenshot(path=str(OUT/f'file-{width}-day.png'),full_page=True)
                await page.locator(f'.st-key-open_dialog_student_photo_{sid} button').click()
                uploader=page.locator(f'.st-key-student_photo_{sid}_upload_1 input[type="file"]')
                await uploader.set_input_files(bad)
                await expect(page.get_by_text('تعذّر قراءة الصورة.',exact=False)).to_be_visible(timeout=15000)
                assert await page.get_by_test_id('stException').count()==0
                await uploader.set_input_files(second)
                await expect(page.get_by_text('الصورة الجديدة قبل الحفظ',exact=True)).to_be_visible(timeout=30000)
                await expect(page.get_by_role('img',name='معاينة الصورة الجديدة',exact=True)).to_have_attribute('src',re.compile(r'^data:image/jpeg;base64,'))
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                await toggle_theme(page,True)
                await expect(page.get_by_role('img',name='معاينة الصورة الجديدة',exact=True)).to_have_attribute('src',re.compile(r'^data:image/jpeg;base64,'))
                await toggle_theme(page,False)
                await expect(page.get_by_text('الصورة الجديدة قبل الحفظ',exact=True)).to_be_visible()
                await page.locator(f'.st-key-student_photo_{sid}_reason_1 input').fill('تحديث صورة الطفل')
                await page.locator(f'.st-key-student_photo_{sid}_save_1 button').click()
                await expect(page.get_by_text('حُفظت صورة الطالب.',exact=True)).to_be_visible(timeout=30000)
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                assert query('SELECT revision FROM student_photos WHERE student_id=%s',(sid,))[0]['revision']==2
                await expect(page.locator(f'.st-key-student_photo_{sid}_reason_1 input')).to_have_count(0,timeout=30000)
                reason=page.locator(f'.st-key-student_photo_{sid}_reason_2 input')
                if not await reason.is_visible(): await page.locator(f'.st-key-open_dialog_student_photo_{sid} button').click()
                await reason.fill('طلب الأسرة إزالة الصورة')
                await page.get_by_text('أؤكد حذف صورة الطالب فقط، مع بقاء ملفه',exact=True).click()
                await page.locator(f'.st-key-student_photo_{sid}_remove_2 button').click()
                await expect(page.get_by_text('حُذفت الصورة؛ بقي ملف الطالب محفوظًا.',exact=True)).to_be_visible(timeout=30000)
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                assert query('SELECT image_data FROM student_photos WHERE student_id=%s',(sid,))[0]['image_data'] is None
                assert query('SELECT archived_at FROM students WHERE student_id=%s',(sid,))[0]['archived_at'] is None
                await expect(page.get_by_role('img',name='لم تضف صورة للطالب',exact=True)).to_be_visible()
                # A new upload after deletion receives a new version; no stale reuse.
                await expect(page.locator(f'.st-key-student_photo_{sid}_reason_2 input')).to_have_count(0,timeout=30000)
                if not await page.locator(f'.st-key-student_photo_{sid}_reason_3 input').is_visible():
                    await page.locator(f'.st-key-open_dialog_student_photo_{sid} button').click()
                await page.locator(f'.st-key-student_photo_{sid}_upload_3 input[type="file"]').set_input_files(second)
                await expect(page.get_by_text('الصورة الجديدة قبل الحفظ',exact=True)).to_be_visible(timeout=30000)
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                await page.locator(f'.st-key-student_photo_{sid}_reason_3 input').fill('الصورة المختارة الجديدة')
                await page.locator(f'.st-key-student_photo_{sid}_save_3 button').click()
                await expect(page.get_by_text('حُفظت صورة الطالب.',exact=True)).to_be_visible(timeout=30000)
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                await toggle_theme(page,True)
                await expect(page.locator('.student-file-hero')).to_have_css('background-color','rgb(32, 34, 35)')
                await expect(page.locator('[data-stale="true"]')).to_have_count(0,timeout=30000)
                await page.get_by_role('button',name='العودة للطلاب',exact=True).scroll_into_view_if_needed()
                await expect(page.locator('.stApp')).to_have_css('background-color','rgb(16, 21, 25)')
                await page.screenshot(path=str(OUT/f'file-{width}-night.png'),full_page=True)
                events=query("SELECT action,before_state,after_state FROM record_changes WHERE table_name='student_photos' AND record_key=%s ORDER BY change_id",(sid,))
                assert [e['action'] for e in events]==['created','updated','deleted','created']
                assert all('image_data' not in (e['before_state'] or {}) and 'image_data' not in (e['after_state'] or {}) for e in events)
                assert not query('SELECT receipt_id FROM monthly_receipts WHERE student_id=%s',(sid,))
                await page.get_by_role('button',name='💵 تسجيل دفعة',exact=True).click()
                await page.get_by_role('button',name=re.compile('^تسديد رسوم التسجيل')).click()
                await page.get_by_text('أؤكد قبض مبلغ الرسم الموضح فعليًا',exact=True).click()
                await expect(page.get_by_role('checkbox',name='أؤكد قبض مبلغ الرسم الموضح فعليًا',exact=True)).to_be_checked()
                await page.get_by_role('button',name='تأكيد قبض الرسم وإصدار وصل',exact=True).click()
                await expect(page.get_by_text('تم تسديد رسوم التسجيل',exact=False)).to_be_visible(timeout=30000)
                paid_fee=query("SELECT amount FROM monthly_receipts WHERE student_id=%s AND state='active'",(sid,))
                assert len(paid_fee)==1 and paid_fee[0]['amount']==1000
                assert query('SELECT COALESCE(SUM(a.amount),0) AS amount FROM monthly_allocations a JOIN monthly_receipts r USING(receipt_id) WHERE r.student_id=%s AND a.period_id IS NOT NULL AND a.active',(sid,))[0]['amount']==0
                await page.close()
                # The same file is visible without financial or mutation controls.
                page=await browser.new_page(viewport={'width':width,'height':1000});await login(page,viewer)
                await nav(page,'students',staff=True)
                await search_worker(page,name)
                await expect(page.get_by_role('img',name='صورة '+name,exact=True)).to_be_visible()
                await expect(page.get_by_text('💵 الحساب المالي',exact=True)).to_have_count(0)
                await expect(page.get_by_text('📷 صورة الطالب',exact=True)).to_have_count(0)
                await expect(page.get_by_role('button',name='💾 حفظ التعديلات',exact=True)).to_have_count(0)
                assert await page.get_by_test_id('stException').count()==0
                await page.screenshot(path=str(OUT/f'viewer-{width}.png'),full_page=True)
                results.append(dict(width=width,intake_with_photo=True,invalid_recoverable=True,replaced=True,
                    removed_without_archiving=True,audit_metadata_only=True,view_only_no_finance=True))
                await page.close()
            except Exception:
                await page.screenshot(path=str(OUT/f'failure-{width}.png'),full_page=True)
                print((await page.locator('body').aria_snapshot())[:14000])
                raise
        await browser.close()
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real photo intake, invalid recovery, replacement, removal, private viewer and file day/night passed 390/1280')


async def search_worker(page,name):
    search=page.get_by_role('textbox',name='🔍 ابحث باسم الطفل أو ولي الأمر أو رقم الهاتف',exact=True)
    await search.fill(name);await search.press('Enter')
    picker=page.locator('.st-key-student_select_edit input[role="combobox"]')
    await picker.click();await picker.fill(name)
    await page.get_by_role('option').filter(has_text=name).last.click()
    await expect(page.locator('.student-file-hero')).to_be_visible(timeout=30000)


if __name__=='__main__': asyncio.run(run())
