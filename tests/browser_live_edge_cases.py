"""Regression evidence for independent review findings on synthetic PG only."""
import asyncio,json,os
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright,expect
from tests.qa_live_pages import guard

async def main():
    root=Path(os.environ['KG_LIVE_QA_DIR']);s=json.loads((root/'state.json').read_text());guard(s['dsn'])
    assert s['origin']=='https://127.0.0.1:8520'
    out=Path(os.environ.get('KG_LIVE_QA_OUT',str(root/'edge-browser')));out.mkdir(parents=True,exist_ok=True)
    results=[]
    def record(name):
        results.append({'case':name,'passed':True});(out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    async with async_playwright() as p:
        browser=await p.chromium.launch()
        context=await browser.new_context(ignore_https_errors=True,viewport={'width':1280,'height':900})
        page=await context.new_page()
        async def login(name):
            await page.goto(s['origin']);await expect(page.locator('#live-login')).to_be_visible()
            await page.locator('#live-login [name="username"]').fill(name)
            await page.locator('#live-login [name="password"]').fill(s['password'])
            await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
        async def snapshot():
            r=await context.request.get(s['origin']+'/api/snapshot');assert r.ok,await r.text();return await r.json()
        try:
            await login(s['username'])
            before=await snapshot();cash_before=before['overview']['total_cash']
            await page.locator('nav [data-page="students"]').click();await page.locator('#add-student').click()
            await page.locator('#student-form [name="name"]').fill('طالب إعفاء جزئي للمراجعة')
            await page.locator('#student-form [name="father"]').fill('أب الاختبار')
            await page.locator('#student-form [name="fatherPhone"]').fill('22334455')
            await page.locator('#student-form [name="gilet"]').uncheck()
            await page.locator('#student-form [name="amount"]').fill('0')
            await page.locator('#student-form').get_by_role('button',name='حفظ بيانات الطفل والأهل',exact=True).click()
            await expect(page.locator('#student-form')).to_have_count(0,timeout=20000)
            data=await snapshot();child=next(x for x in data['students'] if x['name']=='طالب إعفاء جزئي للمراجعة');sid=child['id']
            token=next(c['value'] for c in await context.cookies() if c['name']=='__Host-kg_session')
            import web_runtime as W
            import student_debt as D,account_records as AR,records as R,access_control as A
            with W.request_context(s['dsn'],{'auth_session':token}):
                D.waive_debt(sid,'إعفاء اصطناعي موثق',True,actor=s['username'])
                import db
                conn=db.new_transaction_connection()
                with conn.cursor() as c:
                    c.execute('SELECT * FROM monthly_waivers WHERE student_id=%s',(sid,));waiver=dict(c.fetchone())
                conn.close()
                AR.change_waiver(waiver['waiver_id'],actor=s['username'],reason='إعفاء جزئي اصطناعي',new_amount=400,on_date=waiver['effective_on'],expected=R.revision(waiver))
                A.save_user(employee_name='قارئ تقارير للمراجعة',name='qa_reporter',password=s['password'],permissions=['reports.view'])
            await page.reload();await expect(page.locator('#preview-login')).to_be_hidden(timeout=20000)
            await page.locator('nav [data-page="payments"]').click();await page.locator('#payment-student').select_option(sid)
            expected_due=1000-400
            fee=page.locator('[data-collect-fee="registration"]')
            await expect(fee).to_contain_text(str(expected_due))
            await expect(page.locator('#payment-body details p').first).to_have_text('التسجيل: متبقي 600 · الجيليه: لا مبلغ مستحق')
            await fee.click();await expect(page.locator('#fee-collect-form strong')).to_contain_text(str(expected_due))
            await page.locator('#fee-collect-form [name="agree"]').check()
            async with page.expect_request('**/api/fees.collect') as request_event:
                await page.locator('#fee-collect-form button.primary').click()
            request=await request_event.value
            assert request.post_data_json['due']==expected_due
            await expect(page.locator('#record-dialog')).not_to_be_visible(timeout=20000)
            data=await snapshot();paid=next(r for r in data['receipts'] if r['student']==sid and not r['cancelled'])
            assert paid['amount']==expected_due and data['overview']['total_cash']==cash_before+expected_due
            await expect(page.locator('#payment-body details p').first).to_have_text('التسجيل: لا مبلغ مستحق · الجيليه: لا مبلغ مستحق')
            record('partially_waived_fee_button_confirmation_request_receipt_and_cash_agree')
            await page.locator('#demo-logout').click();await expect(page.locator('#live-login')).to_be_visible(timeout=20000)
            await login('qa_reporter');data=await snapshot()
            assert data['students']==[] and data['receipts']==[]
            card=page.locator('.stat').filter(has=page.locator('.stat-label',has_text='الطلاب الحاليون'))
            await expect(card.locator('.stat-value')).to_have_text(str(data['overview']['students_count']))
            assert data['overview']['students_count']>0
            assert await page.locator('#home-student').count()==0
            record('report_only_browser_renders_real_roster_count_without_private_child_payload')
            await page.screenshot(path=str(out/'report-only.png'),full_page=True)
        except Exception as error:
            results.append({'case':'incomplete_edge_flow','passed':False,'error':str(error)[:1800]})
            (out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));raise
        finally:await browser.close()
    print(json.dumps({'passed':sum(x['passed'] for x in results),'total':len(results)}))

if __name__=='__main__':asyncio.run(main())
