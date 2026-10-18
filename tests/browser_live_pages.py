"""Exercise the ORIGINAL Pages UI against real HTTP auth and disposable PostgreSQL.

Credentials live only in a private generated fixture, never in source or stdout.
No production target or bypass is accepted. Run via python -m tests.browser_live_pages.
"""
import asyncio,json,os
from pathlib import Path
from urllib.parse import urlsplit
import psycopg2
from psycopg2.extensions import parse_dsn
from playwright.async_api import async_playwright,expect

async def main():
    root=Path(os.environ['KG_LIVE_QA_DIR'])
    state=json.loads((root/'state.json').read_text())
    u=urlsplit(state['origin']);dsn=parse_dsn(state['dsn'])
    assert u.hostname=='127.0.0.1' and u.port==8520 and dsn['dbname']=='kindergarten_test' and dsn.get('host') in ('127.0.0.1','localhost')
    out=Path(os.getenv('KG_LIVE_QA_OUT',str(root/'browser')));out.mkdir(parents=True,exist_ok=True)
    results=[]
    def passed(name):
        results.append({'case':name,'passed':True});(out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    async with async_playwright() as p:
        browser=await p.chromium.launch(headless=True)
        context=await browser.new_context(ignore_https_errors=True,viewport={'width':1280,'height':900},accept_downloads=True)
        page=await context.new_page();errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        async def nav(name):
            await page.locator('nav [data-page="'+name+'"]').click()
        async def data():
            response=await context.request.get(state['origin']+'/api/snapshot')
            assert response.ok,await response.text()
            return await response.json()
        async def settle():
            await expect(page.locator('#toast')).to_have_text('تم الحفظ في السجل الحقيقي.',timeout=20000)
        try:
            await page.goto(state['origin']);await expect(page.locator('#live-login')).to_be_visible()
            assert await page.evaluate('students.length')==0
            assert not await page.locator('.demo-scope-note').count()
            passed('original_login_no_demo_identity_or_students')
            await page.locator('#live-login [name="username"]').fill(state['username'])
            await page.locator('#live-login [name="password"]').fill(state['password'])
            await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
            await expect(page.locator('#content h1')).to_have_text('الرئيسية')
            assert (await data())['students']==[]
            cookies=await context.cookies();cookie=next(c for c in cookies if c['name']=='__Host-kg_session')
            assert cookie['secure'] and cookie['httpOnly'] and cookie['sameSite']=='Strict'
            passed('real_password_login_and_secure_session_cookie')
            await nav('students');await page.locator('#add-student').click()
            await page.locator('#student-form [name="name"]').fill('طفل من صفحات Pages الأصلية')
            await page.locator('#student-form [name="father"]').fill('أب الطفل')
            await page.locator('#student-form [name="fatherPhone"]').fill('22334455')
            await page.locator('#student-form [name="amount"]').fill('6000')
            await page.locator('#student-form [name="photo"]').set_input_files(root/'portrait.png')
            await page.locator('#student-form').get_by_role('button',name='حفظ بيانات الطفل والأهل',exact=True).click()
            await expect(page.locator('#student-form')).to_have_count(0,timeout=20000)
            saved=await data();assert len(saved['students'])==1 and len(saved['receipts'])==1
            sid=saved['students'][0]['id'];assert sid.startswith('S') and saved['overview']['total_cash']==6000
            passed('original_intake_form_commits_family_photo_and_cash_once')
            await page.locator('[data-profile="'+sid+'"]').click()
            await expect(page.locator('.file-identity h2')).to_have_text('طفل من صفحات Pages الأصلية')
            await expect(page.locator('img.file-portrait')).to_be_visible()
            await page.locator('#open-profile-edit').click()
            await page.locator('#profile-edit-child [name="health"]').fill('ملاحظة صحية محفوظة بالخادم')
            await page.locator('#profile-edit-child button.primary').click()
            await expect(page.locator('#profile-edit-dialog')).not_to_be_visible(timeout=20000)
            assert (await data())['students'][0]['health']=='ملاحظة صحية محفوظة بالخادم'
            passed('original_profile_and_edit_window_save_real_medical_notes')
            await page.locator('#open-profile-photo').click()
            await page.locator('#profile-photo-form [name="reason"]').fill('تحديث صورة الاختبار')
            await page.locator('#profile-photo-file').set_input_files(root/'portrait.png')
            await page.locator('#profile-photo-save').click()
            await expect(page.locator('#profile-photo-dialog')).not_to_be_visible(timeout=20000)
            passed('original_photo_window_uses_authorized_private_media')
            await nav('registration')
            await page.locator('#department-form [name="name"]').fill('قسم الزهور الحقيقي')
            await page.locator('#department-form button').click()
            await expect(page.locator('table')).to_contain_text('قسم الزهور الحقيقي',timeout=20000)
            await page.locator('#open-transfer').click()
            await page.locator('#transfer-children [value="'+sid+'"]').check()
            await page.locator('#department-destination').select_option(label='قسم الزهور الحقيقي')
            await page.locator('#transfer-form button.primary').click()
            await expect(page.locator('#transfer-dialog')).not_to_be_visible(timeout=20000)
            assert (await data())['students'][0]['class']=='قسم الزهور الحقيقي'
            passed('original_department_and_transfer_windows_commit_assignments')
            await nav('payments');await page.locator('#payment-student').select_option(sid)
            await page.locator('#pay-amount').fill('1000');await page.locator('#payment-preview-button').click()
            await expect(page.locator('#pay-agree')).to_be_visible(timeout=20000)
            await page.locator('#pay-agree').check();await page.locator('#pay-save').click()
            await expect(page.locator('#payment-student')).to_be_visible()
            for _ in range(80):
                saved=await data()
                if len(saved['receipts'])==2:break
                await page.wait_for_timeout(100)
            assert saved['overview']['total_cash']==7000
            passed('original_payment_preview_confirmation_and_durable_receipt')
            await page.locator('[data-finance="receipts"]').click()
            rid=saved['receipts'][-1]['id']
            await page.locator('[data-receipt="'+str(rid)+'"]').click()
            async with page.expect_download() as download_event:
                await page.locator('#receipt-content a').click()
            download=await download_event.value;await download.save_as(out/'real-receipt.pdf')
            assert (out/'real-receipt.pdf').read_bytes().startswith(b'%PDF-')
            passed('real_browser_pdf_download_from_original_receipt_dialog')
            await page.locator('#receipt-content [data-record-mode="edit"]').click()
            await page.locator('#record-edit-form [name="amount"]').fill('2000')
            await page.locator('#record-edit-form [name="reason"]').fill('تصحيح المبلغ')
            await page.locator('#record-edit-form [name="agree"]').check()
            await page.locator('#record-edit-form button.primary').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            saved=await data();assert saved['overview']['total_cash']==8000
            replacement=next(r for r in saved['receipts'] if r['corrects_id']==rid)
            await page.locator('[data-receipt="'+str(replacement['id'])+'"]').click()
            await page.locator('#receipt-content [data-record-mode="cancel"]').click()
            await page.locator('#record-edit-form [name="reason"]').fill('إلغاء إدخال خاطئ')
            await page.locator('#record-edit-form [name="agree"]').check()
            await page.locator('#record-edit-form button.danger').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            assert (await data())['overview']['total_cash']==6000
            passed('original_receipt_edit_and_cancel_preserve_cash_and_audit_semantics')
            await nav('expenses')
            await page.locator('#expense-form [name="category"]').fill('مستلزمات فعلية')
            await page.locator('#exp-amount').fill('100')
            await page.locator('#expense-status').select_option('partial')
            await page.locator('#exp-paid').fill('40')
            await page.locator('#expense-form details summary').click()
            await page.locator('#expense-form [name="notes"]').fill('ملاحظة يجب حفظها')
            await page.locator('#expense-form button.primary').click()
            await expect(page.locator('table')).to_contain_text('مستلزمات فعلية',timeout=20000)
            saved=await data();assert saved['overview']['expenses']==40 and saved['overview']['remaining_cash']==5960
            passed('original_partial_expense_form_uses_real_cash_projection')
            await nav('records');await expect(page.locator('#content h1')).to_have_text('إدارة السجلات')
            await nav('history');await expect(page.locator('#history-rows')).to_contain_text('تصحيح المبلغ')
            passed('original_record_manager_and_server_audit_history')
            await nav('admin');await expect(page.locator('#demo-user-create')).to_be_visible()
            assert 'داخل التبويب' not in await page.locator('#content').inner_text()
            await page.locator('#demo-user-create [name="name"]').fill('عامل اختبار فعلي')
            await page.locator('#demo-user-create [name="username"]').fill('qa_worker')
            await page.locator('#demo-user-create [name="password"]').fill(state['password'])
            await page.locator('#demo-user-create [value="students.create"]').check()
            await page.locator('#demo-user-create button.primary').click()
            await expect(page.locator('#content')).to_contain_text('qa_worker',timeout=20000)
            assert any(u['username']=='qa_worker' for u in (await data())['users'])
            passed('original_admin_form_creates_real_database_worker_account')
            await nav('dashboard')
            await expect(page.locator('#toast')).not_to_have_class('show',timeout=7000)
            await page.screenshot(path=str(out/'desktop-day.png'),full_page=True)
            await page.locator('#theme').click();await page.screenshot(path=str(out/'desktop-night.png'),full_page=True)
            await page.set_viewport_size({'width':390,'height':900})
            await page.screenshot(path=str(out/'mobile-night.png'),full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            await page.locator('#menu').click();await expect(page.locator('#sidebar')).to_have_class('open')
            await page.locator('nav [data-page="students"]').click()
            await expect(page.locator('#sidebar')).not_to_have_class('open')
            passed('original_css_day_night_mobile_and_drawer_without_restyling')
            await page.reload();await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
            assert len((await data())['students'])==1
            passed('fresh_page_reuses_real_session_and_persisted_database_records')
            extra=None
            if os.getenv('KG_LIVE_MANAGEMENT')=='1':
                await page.locator('#menu').click()
                await page.locator('#live-extra-nav summary').click()
                assert await page.locator('#live-extra-nav a').get_attribute('href')=='/management/'
                await page.mouse.click(5,450)
                extra=await context.new_page()
                await extra.goto(state['origin']+'/management/')
                await expect(extra.locator('.st-key-nav_salaries button')).to_be_visible(timeout=45000)
                assert await extra.locator('input[type="password"]').count()==0
                assert await extra.locator('[data-testid="stException"]').count()==0
                await extra.locator('.st-key-nav_salaries button').click()
                await expect(extra.get_by_role('tab',name='➕ صرف راتب شهري',exact=True)).to_be_visible(timeout=30000)
                assert await extra.locator('[data-testid="stException"]').count()==0
                passed('actual_nginx_websocket_and_supplementary_payroll_use_same_httponly_session')
            await page.locator('#menu').click();await page.locator('#demo-logout').click()
            await expect(page.locator('#live-login')).to_be_visible(timeout=20000)
            assert (await context.request.get(state['origin']+'/api/snapshot')).status==401
            assert not errors,errors
            passed('logout_revokes_session_and_no_javascript_errors')
            if extra is not None:
                await extra.reload()
                await expect(extra.locator('input[type="password"]')).to_be_visible(timeout=30000)
                passed('primary_logout_also_revokes_supplementary_streamlit_access')
            conn=psycopg2.connect(state['dsn'])
            with conn.cursor() as c:
                c.execute('SELECT COUNT(*) FROM students');assert c.fetchone()[0]==1
                c.execute('SELECT SUM(amount) FROM monthly_receipts WHERE state=%s',('active',));assert c.fetchone()[0]==6000
                c.execute('SELECT COUNT(*) FROM record_changes');assert c.fetchone()[0]>0
            conn.close();passed('independent_postgresql_readback_matches_ui_cash_and_roster')
        except Exception as error:
            results.append({'case':'incomplete_flow','passed':False,'error':str(error)[:2000],'javascript_errors':errors})
            (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
            await page.screenshot(path=str(out/'failure.png'),full_page=True)
            raise
        finally: await browser.close()
    print(json.dumps({'passed':sum(r['passed'] for r in results),'total':len(results),'output':str(out)}))

if __name__=='__main__':asyncio.run(main())
