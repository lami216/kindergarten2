"""Real production entrypoint: manager creates employee, scoped work, revocation."""
import asyncio
import json
import os
from pathlib import Path
import uuid
from urllib.parse import urlparse
from unittest.mock import patch
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright,expect
import access_control as A
import db
import streamlit as st

BASE='http://127.0.0.1:8503'
OUT=Path('visual-evidence/admin-access')
PASSWORD='QA-only-strong-password-2026!'


def connection(): return psycopg2.connect(os.environ['TEST_POSTGRES_DSN'],cursor_factory=RealDictCursor)


async def login(page,name):
    await page.goto(BASE)
    await page.get_by_role('textbox',name='اسم المستخدم',exact=True).fill(name)
    await page.get_by_role('textbox',name='كلمة المرور',exact=True).fill(PASSWORD)
    await page.get_by_role('button',name='تسجيل الدخول',exact=True).click()


async def select(page,key,text):
    picker=page.locator(f'.st-key-{key} input[role="combobox"]')
    await picker.click();await picker.fill(text)
    await page.get_by_role('option').filter(has_text=text).last.click()


async def grant(page,resource,action):
    await page.locator(f'.st-key-admin_new_grants_{resource} input').click()
    await page.get_by_role('option',name=action,exact=True).click()


async def nav(page,key,staff=False):
    button=page.locator(f'.st-key-{"staff_nav_" if staff else "nav_"}{key} button')
    await button.wait_for(state='attached',timeout=30000)
    if not await button.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click()
    await button.click()
    collapse=page.locator('[data-testid="stSidebarCollapseButton"] button').first
    if await collapse.is_visible(): await collapse.click()


async def run():
    parsed=urlparse(os.environ.get('TEST_POSTGRES_DSN',''))
    assert parsed.hostname in ('127.0.0.1','localhost') and parsed.path=='/kindergarten_test'
    OUT.mkdir(parents=True,exist_ok=True)
    with patch.object(db,'new_transaction_connection',side_effect=connection):
        A.bootstrap('مدير فحص المتصفح','qa-owner',PASSWORD)
    results=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True)
        for width in (390,1280):
            marker=uuid.uuid4().hex[:8];name='worker-'+marker
            admin=await browser.new_context(viewport={'width':width,'height':950})
            owner=await admin.new_page();await login(owner,'qa-owner')
            await nav(owner,'admin')
            await expect(owner.locator('.section-title').filter(has_text='لوحة المدير')).to_be_visible(timeout=30000)
            expand=owner.get_by_text('➕ إنشاء حساب عامل',exact=True)
            if not await owner.locator('.st-key-admin_new_name input').is_visible(): await expand.click()
            await owner.locator('.st-key-admin_new_name input').fill('عامل '+marker)
            await owner.locator('.st-key-admin_new_username input').fill(name)
            await owner.locator('.st-key-admin_new_password input').fill(PASSWORD)
            await grant(owner,'students','إضافة')
            await grant(owner,'expenses','إضافة')
            await grant(owner,'expenses','تعديل')
            await grant(owner,'expenses','إلغاء / حذف')
            await owner.get_by_role('button',name='إنشاء الحساب',exact=True).click()
            await expect(owner.get_by_text('تم إنشاء الحساب.',exact=False)).to_be_visible(timeout=30000)
            staff=await browser.new_context(viewport={'width':width,'height':950})
            employee=await staff.new_page();await login(employee,name)
            await expect(employee.locator('.st-key-staff_nav_students button')).to_be_attached(timeout=30000)
            assert await employee.locator('.st-key-nav_admin').count()==0
            assert await employee.locator('.st-key-staff_nav_salaries').count()==0
            assert await employee.locator('.st-key-staff_nav_payments').count()==0
            await nav(employee,'students',staff=True)
            await expect(employee.locator('.st-key-kid_name input')).to_be_visible(timeout=30000)
            await employee.locator('.st-key-kid_name input').fill('طفل عامل '+marker)
            await employee.locator('.st-key-kid_mother_name input').fill('أم عامل '+marker)
            await employee.locator('.st-key-kid_mother_phone input').fill('22223333')
            await employee.locator('.st-key-kid_mother_phone input').press('Tab')
            await expect(employee.get_by_role('button',name='دفع',exact=True)).to_have_count(0)
            await employee.get_by_role('button',name='💾 حفظ بيانات الطفل والأهل',exact=True).click()
            await expect(employee.get_by_text('تم حفظ الطفل والأهل بنجاح.',exact=False)).to_be_visible(timeout=30000)
            await expect(employee.get_by_role('combobox',name='نوع السجل',exact=True)).to_have_count(0)
            await employee.screenshot(path=str(OUT/f'student-only-{width}.png'),full_page=True)
            await nav(employee,'expenses',staff=True)
            await employee.locator('.st-key-staff_expense_0_category input').fill('مصروف عامل '+marker)
            await employee.locator('.st-key-staff_expense_0_total input').fill('1200')
            await employee.locator('.st-key-staff_expense_0_paid input').fill('900')
            await employee.get_by_role('button',name='حفظ المصروف',exact=True).click()
            await expect(employee.get_by_text('حُفظ المصروف باسم حسابك.',exact=True)).to_be_visible(timeout=30000)
            await owner.get_by_role('tab',name='📊 نشاط العاملين',exact=True).click()
            await select(owner,'admin_activity_user',name)
            metric=owner.get_by_test_id('stMetric').filter(has=owner.get_by_text('طلاب سجلهم العامل',exact=True))
            await expect(metric.get_by_test_id('stMetricValue')).to_have_text('1')
            cash=owner.get_by_test_id('stMetric').filter(has=owner.get_by_text('صافي تلك المصروفات حاليًا',exact=True))
            await expect(cash.get_by_test_id('stMetricValue')).to_contain_text('900.00')
            await owner.screenshot(path=str(OUT/f'activity-{width}.png'),full_page=True)
            await owner.get_by_role('tab',name='👥 الحسابات والصلاحيات',exact=True).click()
            await select(owner,'admin_selected_user',name)
            await owner.locator('.st-key-admin_edit_active label').last.click()
            await owner.locator('.st-key-admin_edit_confirm label').last.click()
            await owner.get_by_role('button',name='حفظ الحساب والصلاحيات',exact=True).click()
            await expect(owner.get_by_text('حُفظ الحساب وأُبطلت جلساته القديمة.',exact=True)).to_be_visible(timeout=30000)
            # The worker still has a form rendered before the disable operation.
            await employee.locator('.st-key-staff_expense_1_category input').fill('يجب ألا يحفظ '+marker)
            await employee.get_by_role('button',name='حفظ المصروف',exact=True).click()
            await expect(employee.get_by_role('button',name='تسجيل الدخول',exact=True)).to_be_visible(timeout=30000)
            with connection() as c:
                with c.cursor() as cursor:
                    cursor.execute('SELECT user_id FROM app_users WHERE username=%s',(name,));uid=cursor.fetchone()['user_id']
                    cursor.execute("SELECT COUNT(*) AS n FROM record_changes WHERE actor_user_id=%s AND table_name='students' AND action='created'",(uid,))
                    assert cursor.fetchone()['n']==1
                    cursor.execute("SELECT COUNT(*) AS n FROM expenses WHERE category=%s",('يجب ألا يحفظ '+marker,))
                    assert cursor.fetchone()['n']==0
            await employee.screenshot(path=str(OUT/f'revoked-{width}.png'),full_page=True)
            assert await owner.locator('[data-testid="stException"]').count()==0
            results.append({'width':width,'student_count':1,'expense_cash':900,'scoped_ui':True,'stale_form_rejected':True})
            await staff.close();await admin.close()
        await browser.close()
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Real manager creation, worker login, scoped student/expense intake, usage and revoked form passed 390/1280')


if __name__=='__main__': asyncio.run(run())
