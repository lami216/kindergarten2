"""Serve only public synthetic build; exercise it under the GitHub project prefix."""
import asyncio,json,sys,tempfile,threading
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright,expect
from tests.date_entry_helpers import fill_field
from scripts.build_pages_preview import build

async def main():
    root=Path(__file__).resolve().parents[1];out=root/'visual-evidence'/'unified-pages-preview';out.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='pages-public-') as folder:
        public=Path(folder);build(public/'kindergarten2')
        server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(public)))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        results=[]
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
            page=await browser.new_page(viewport={'width':1280,'height':900});errors=[];requests=[]
            page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda r:requests.append(r.url))
            try:
                await page.goto('http://127.0.0.1:'+str(server.server_port)+'/kindergarten2/')
                await expect(page.locator('#pages-scope')).to_contain_text('لا تدخل بيانات')
                await expect(page.locator('#live-login [name="password"]')).to_be_hidden()
                await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden()
                async def nav(p):
                    b=page.locator('#nav-workspace') if p=='tools' else page.locator('nav [data-page="'+p+'"]')
                    if not await b.is_visible():await page.locator('#menu').click()
                    await b.click()
                card=page.locator('.stat[role="button"]').filter(has=page.locator('.stat-label',has_text='إجمالي المقبوضات')).first
                await card.click();await expect(page.locator('#record-content')).to_contain_text('المقبوض للشهور');await page.locator('#workspace-close').click()
                results.append('interactive_summary')
                await nav('students');await page.locator('#student-search').fill('طالب مؤرشف للمراجعة');await expect(page.locator('#student-rows')).to_contain_text('لا توجد نتائج')
                await page.locator('#open-archive').click();await page.locator('#archive-search').fill('00000999');await expect(page.locator('#archive-rows')).to_contain_text('طالب مؤرشف للمراجعة')
                await page.locator('[data-restore="archived-1"]').click();await page.locator('#restore-form [name="reason"]').fill('مراجعة الدين');await page.locator('#restore-form [name="confirmed"]').check();await page.locator('#restore-form button.primary').click()
                await expect(page.locator('.file-identity h2')).to_have_text('طالب مؤرشف للمراجعة')
                cash=await page.evaluate('liveData.overview.total_cash')
                await page.locator('[data-waiver="archived-1"]').click();await page.locator('#waiver-form [name="reason"]').fill('إسقاط الدين');await page.locator('#waiver-form [name="confirmed"]').check();await page.locator('#waiver-form button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible()
                assert await page.evaluate('liveData.students.find(s=>s.id==="archived-1").account.due')==0
                assert await page.evaluate('liveData.overview.total_cash')==cash
                await page.locator('[data-record-type="students"][data-record-mode="cancel"]').click();await page.locator('#record-edit-form [name="reason"]').fill('أرشفة');await page.locator('#record-edit-form [name="agree"]').check();await page.locator('#record-edit-form button.danger').click();await expect(page.locator('#record-dialog')).not_to_be_visible()
                results.append('archive_restore_waive_rearchive')
                await nav('payments');assert await page.locator('#payment-student option[value="archived-1"]').count()==0
                await page.locator('[data-finance="receipts"]').click();await page.locator('[data-receipt="101"]').click();await expect(page.locator('#receipt-page')).to_be_visible();assert not await page.locator('#receipt-dialog').is_visible()
                await page.screenshot(path=str(out/'receipt-desktop.png'),full_page=True);results.append('standalone_receipt')
                await nav('teachers');await page.locator('#add-teacher').click()
                await page.locator('#teacher-form [name="national_id"]').fill('DEMO-01');await page.locator('#teacher-form [name="full_name"]').fill('معلمة المعاينة');await page.locator('#teacher-form [name="salary"]').fill('2000');await page.locator('#teacher-form [name="department_id"]').select_option(index=1);await page.locator('#teacher-form [name="reason"]').fill('إضافة للتجربة');await page.locator('#teacher-form [name="confirmed"]').check();await page.locator('#teacher-form button.primary').click();await expect(page.locator('#teacher-roster')).to_contain_text('معلمة المعاينة')
                await nav('tools');assert await page.locator('a[href="/management/"]').count()==0
                await page.locator('[data-tool-tab="payroll"]').click();await page.locator('#new-salary').click();await page.locator('#payroll-form [name="teacher"]').select_option(label='معلمة المعاينة · DEMO-01');await page.locator('#payroll-form [name="bonus"]').fill('500');await page.locator('#payroll-form [name="deductions"]').fill('100');await expect(page.locator('#salary-net')).to_contain_text('2,400');await page.locator('#payroll-form [name="reason"]').fill('معاينة');await page.locator('#payroll-form [name="confirmed"]').check();await page.locator('#payroll-form button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible()
                results.append('unified_tools_and_salary_preview')
                await nav('students');await page.locator('#add-student').click();await page.locator('#student-form [name="name"]').fill('طفل أضيف في المعاينة');await page.locator('#student-form [name="department_id"]').select_option(index=1);await fill_field(page.locator('#student-form [name="birth"]'), '2022-01-01');await page.locator('#student-form [name="mother"]').fill('أم الطفل');await page.locator('#student-form [name="motherPhone"]').fill('00000888');await page.locator('#student-form .form-end button.primary').click();await expect(page.locator('#student-rows')).to_contain_text('طفل أضيف في المعاينة');await expect(page.locator('#toast')).to_have_text('تم الحفظ في المعاينة.');assert await page.evaluate('scrollY')==0;results.append('student_intake_and_success_notice')
                await nav('admin');await page.locator('#demo-user-create [name="name"]').fill('عامل المعاينة');await page.locator('#demo-user-create [name="username"]').fill('pages_worker');await page.locator('#demo-user-create [name="password"]').fill('123');assert not await page.locator('#demo-user-create').evaluate('(f)=>f.checkValidity()');await page.locator('#demo-user-create [name="password"]').fill('1234');await page.locator('#demo-user-create [value="students.create"]').check();await page.locator('#demo-user-create button.primary').click();await expect(page.locator('#content')).to_contain_text('pages_worker')
                await page.locator('#demo-logout').click();await expect(page.locator('#preview-login')).to_be_visible();await page.locator('#pages-worker').click();await page.locator('#live-login [name="username"]').fill('pages_worker');await page.locator('#live-login [name="password"]').fill('1234');await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden();await nav('students');await expect(page.locator('#student-form')).to_be_visible();assert await page.locator('#nav-workspace').count()==0;results.append('temporary_worker_permissions_and_login')
                await page.locator('#demo-logout').click();await expect(page.locator('#preview-login')).to_be_visible();await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden();await nav('tools')
                await page.set_viewport_size({'width':390,'height':900});await page.wait_for_timeout(300)
                await page.locator('[data-tool-tab="reports"]').click();await page.locator('#report-form button').click();await expect(page.locator('#report-output .panel')).to_be_visible();await expect(page.locator('#report-output')).not_to_contain_text('students_count')
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                await page.screenshot(path=str(out/'mobile-day.png'),full_page=True);await page.locator('#theme').click();await page.screenshot(path=str(out/'mobile-night.png'),full_page=True);results.append('mobile_day_night')
                assert not errors,errors
                assert not any('/api/' in url for url in requests),requests
                await page.reload();await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden()
                assert await page.evaluate('liveData.students.find(s=>s.id==="archived-1").account.due')>0
                results.append('isolated_temporary_data_and_no_api_network')
            except Exception:
                await page.screenshot(path=str(out/'failure.png'),full_page=True);raise
            finally:
                (out/'results.json').write_text(json.dumps({'passed':results,'javascript_errors':errors},ensure_ascii=False),encoding='utf-8')
                await browser.close();server.shutdown()
        print(json.dumps({'passed':len(results),'cases':results}))

if __name__=='__main__':asyncio.run(main())
