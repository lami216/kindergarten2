"""Actual unified UI: archives/debt, lists, tools, standalone receipts and scroll."""
import asyncio,json,os
from pathlib import Path
from playwright.async_api import async_playwright,expect
from tests.qa_live_pages import guard

async def main():
    root=Path(os.environ['KG_LIVE_QA_DIR']);state=json.loads((root/'state.json').read_text());guard(state['dsn'])
    assert state['origin']=='https://127.0.0.1:8520'
    out=Path(os.environ['KG_LIVE_QA_OUT']);out.mkdir(parents=True,exist_ok=True);results=[]
    def passed(case):
        results.append(dict(case=case,passed=True));(out/'results.json').write_text(json.dumps(results),encoding='utf-8')
    async with async_playwright() as pw:
        browser=await pw.chromium.launch();context=await browser.new_context(ignore_https_errors=True,viewport={'width':1280,'height':900},accept_downloads=True)
        page=await context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            await page.goto(state['origin']);await page.locator('#live-login [name="username"]').fill(state['username']);await page.locator('#live-login [name="password"]').fill(state['password']);await page.locator('#preview-enter').click()
            await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
            async def snapshot():
                r=await context.request.get(state['origin']+'/api/snapshot');assert r.ok;return await r.json()
            async def api(operation,data):
                return await page.evaluate('async ([op,data])=>liveCall(op,data)',[operation,data])
            async def nav(target):
                b=page.locator('#nav-workspace') if target=='tools' else page.locator('nav [data-page="'+target+'"]')
                if not await b.is_visible():await page.locator('#menu').click()
                await b.click()
            data=await snapshot()
            card=page.locator('.stat[role="button"]').filter(has=page.locator('.stat-label',has_text='إجمالي المقبوضات')).first
            await card.focus();await page.keyboard.press('Enter')
            await expect(page.locator('#record-dialog')).to_be_visible()
            await expect(page.locator('#record-content')).to_contain_text('المقبوض للشهور')
            await page.locator('#workspace-close').click();passed('summary_card_keyboard_opens_real_breakdown')
            # Enough persisted children to exercise two pages and actual scrolling.
            import uuid
            for i in range(24):
                await api('students.create',dict(department_id=data['departments'][0]['id'],name=f'قائمة فعلية {i:02}',birth='2022-01-01',gender='ذكر',mother='أم القائمة',motherPhone='22334455',mode='pay',amount='0',registration=False,gilet=False,request_token=str(uuid.uuid4())))
            debtor=await api('students.create',dict(department_id=data['departments'][0]['id'],name='دين داخل الأرشيف فقط',birth='2022-01-01',gender='أنثى',mother='أم الأرشيف',motherPhone='99887766',mode='pay',amount='0',registration=True,gilet=False,request_token=str(uuid.uuid4())))
            sid=debtor['id'];token=next(c['value'] for c in await context.cookies() if c['name']=='__Host-kg_session')
            import web_runtime as W,access_control as A,db,monthly_finance as F,record_history as H
            with W.request_context(state['dsn'],{'auth_session':token}):
                conn=db.new_transaction_connection();A.refresh(conn);conn.commit()
                with conn.cursor() as c:
                    A.require(c,'students.delete');H.context(c,state['username'],'عينة أرشيف مع دين للمراجعة')
                    c.execute('UPDATE students SET archived_at=now() WHERE student_id=%s',(sid,))
                    A.require(c,'accounts.edit');c.execute('UPDATE monthly_accounts SET archived_at=now(),departure_on=%s WHERE student_id=%s',(F.today(),sid))
                conn.commit();conn.close()
            await page.reload();await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
            await nav('students');assert await page.locator('#student-rows tr:has([data-profile])').count()==15
            await page.locator('#student-rows [data-delta="1"]').click()
            assert await page.locator('#student-rows tr:has([data-profile])').count()>0
            await page.locator('#student-search').fill('دين داخل الأرشيف فقط')
            await expect(page.locator('#student-rows')).to_contain_text('لا توجد نتائج')
            await page.locator('#open-archive').click();await expect(page.locator('#archive-rows')).to_contain_text('دين داخل الأرشيف فقط')
            await page.locator('[data-restore="'+sid+'"]').click();await page.locator('#restore-form [name="reason"]').fill('مراجعة وإسقاط الدين')
            await page.locator('#restore-form [name="confirmed"]').check();await page.locator('#restore-form button.primary').click()
            await expect(page.locator('.file-identity h2')).to_have_text('دين داخل الأرشيف فقط',timeout=20000)
            current=await snapshot();cash=current['overview']['total_cash']
            await page.locator('[data-waiver="'+sid+'"]').click();await page.locator('#waiver-form [name="reason"]').fill('إسقاط الدين دون نقد')
            await page.locator('#waiver-form [name="confirmed"]').check();await page.locator('#waiver-form button.primary').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            after=await snapshot();assert next(s for s in after['students'] if s['id']==sid)['account']['due']==0 and after['overview']['total_cash']==cash
            await page.locator('[data-record-type="students"][data-record-mode="cancel"]').click()
            await page.locator('#record-edit-form [name="reason"]').fill('أرشفة بعد تسوية الدين');await page.locator('#record-edit-form [name="agree"]').check();await page.locator('#record-edit-form button.danger').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            await nav('payments');assert await page.locator('#payment-student option[value="'+sid+'"]').count()==0
            passed('paged_roster_hides_archive_restore_waive_and_rearchive_without_cash')
            await page.locator('[data-finance="receipts"]').click();rid=next(r['id'] for r in (await snapshot())['receipts'] if not r['cancelled'])
            await page.locator('[data-receipt="'+str(rid)+'"]').click()
            await expect(page.locator('#receipt-page')).to_be_visible();assert not await page.locator('#receipt-dialog').is_visible()
            await page.screenshot(path=str(out/'receipt-desktop.png'),full_page=True)
            await page.locator('[data-return-receipts]').click();await nav('students')
            await page.evaluate('window.scrollTo(0,document.body.scrollHeight)');assert await page.evaluate('scrollY')>0
            await nav('expenses');assert await page.evaluate('scrollY')==0
            passed('standalone_receipt_and_navigation_start_at_top')
            await nav('tools');assert await page.locator('a[href="/management/"]').count()==0
            await page.locator('[data-tool-tab="fees"]').click();await expect(page.locator('#edit-fees')).to_be_visible(timeout=20000)
            await page.locator('#edit-fees').click();await page.locator('#fees-edit-form [name="tuition"]').fill('4500')
            await page.locator('#fees-edit-form [name="reason"]').fill('رسوم اختبار للفترات الجديدة');await page.locator('#fees-edit-form [name="confirmed"]').check();await page.locator('#fees-edit-form button.primary').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000);await expect(page.locator('#fees-view')).to_contain_text('4,500')
            await nav('teachers');await page.locator('#add-teacher').click()
            await page.locator('#teacher-form [name="full_name"]').fill('معلمة من الواجهة الموحدة');await page.locator('#teacher-form [name="national_id"]').fill('QA-1901')
            await page.locator('#teacher-form [name="salary"]').fill('2000');await page.locator('#teacher-form [name="department_id"]').select_option(index=1)
            await page.locator('#teacher-form [name="reason"]').fill('إضافة للتجربة');await page.locator('#teacher-form [name="confirmed"]').check();await page.locator('#teacher-form button.primary').click()
            await expect(page.locator('#teacher-roster')).to_contain_text('معلمة من الواجهة الموحدة',timeout=20000)
            await nav('tools')
            await page.locator('[data-tool-tab="payroll"]').click();await page.locator('#new-salary').click()
            await page.locator('#payroll-form [name="teacher"]').select_option(label='معلمة من الواجهة الموحدة · QA-1901')
            await page.locator('#payroll-form [name="bonus"]').fill('500');await page.locator('#payroll-form [name="deductions"]').fill('100')
            await expect(page.locator('#salary-net')).to_contain_text('2,400')
            await page.locator('#payroll-form [name="reason"]').fill('صرف حقيقي في قاعدة اختبار');await page.locator('#payroll-form [name="confirmed"]').check();await page.locator('#payroll-form button.primary').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            passed('fees_teacher_and_live_salary_preview_saved_in_unified_tools')
            await nav('reports');await page.locator('[data-report-mode="other"]').click();await page.locator('#report-form button').click();await expect(page.locator('#report-output .panel')).to_be_visible(timeout=20000)
            async with page.expect_download() as dl:await page.locator('#report-xlsx').click()
            download=await dl.value;await download.save_as(out/'financial-report.xlsx')
            await page.set_viewport_size({'width':390,'height':900});await page.wait_for_timeout(300)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            await page.screenshot(path=str(out/'tools-mobile-day.png'),full_page=True)
            await page.locator('#theme').click();await page.screenshot(path=str(out/'tools-mobile-night.png'),full_page=True)
            passed('reports_export_and_unified_tools_mobile_day_night')
            assert not errors,errors
        except Exception as error:
            results.append(dict(case='failed',passed=False,error=str(error)[:1800],javascript_errors=errors));(out/'results.json').write_text(json.dumps(results),encoding='utf-8')
            await page.screenshot(path=str(out/'failure.png'),full_page=True);raise
        finally:await browser.close()
    print(json.dumps({'passed':len(results),'total':len(results)}))

if __name__=='__main__':asyncio.run(main())
