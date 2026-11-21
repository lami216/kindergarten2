"""Native attendance design and saved day/week/month rates on synthetic TLS QA."""
import asyncio
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit

import httpx
from playwright.async_api import async_playwright, expect
from tests.date_entry_helpers import fill_field
from tests.qa_live_pages import guard


async def main():
    state_path=Path(os.environ.get('KG_DAILY_STATE',Path(__file__).resolve().parents[2]/'daily-attendance-preview/state.json'))
    state=json.loads(state_path.read_text(encoding='utf-8'));guard(state['dsn'])
    origin=state['origin'];endpoint=urlsplit(origin)
    assert endpoint.scheme=='https' and endpoint.hostname=='127.0.0.1' and endpoint.port
    assert not endpoint.username and not endpoint.password and endpoint.path in ('','/') and not endpoint.query and not endpoint.fragment
    out=Path(__file__).resolve().parents[1]/'visual-evidence/attendance-design';out.mkdir(parents=True,exist_ok=True)
    passed=[];errors=[]
    def record(name):
        passed.append(name)
        (out/'results.json').write_text(json.dumps({'passed':passed,'javascript_errors':errors},indent=2),encoding='utf-8')
    with httpx.Client(base_url=origin,verify=False,timeout=20) as api:
        response=api.post('/api/login',json={'username':state['username'],'password':state['password']},headers={'Origin':origin})
        assert response.status_code==200
        session=api.get('/api/session').json();headers={'Origin':origin,'X-CSRF-Token':session['csrf']}
        before=api.get('/api/snapshot').json()
        paid={s['id']:s['account']['paid'] for s in before['students']}
        baseline=api.post('/api/attendance.daily',json={},headers=headers).json()
        assert baseline['date']=='2026-11-18'
        for kind,rates in [('students',(50,70,77.8)),('teachers',(66.7,77.8,83.3))]:
            response=api.post('/api/attendance.overview',json={'kind':kind,'date':baseline['date']},headers=headers)
            assert response.status_code==200,response.text
            overview=response.json()
            assert tuple(overview['periods'][p]['summary']['attendance_rate'] for p in ('day','week','month'))==rates
        record('actual_day_week_month_rates_match_seeded_saved_records')

    async def login(page,language):
        await page.goto(origin,wait_until='networkidle')
        if language=='fr':await page.locator('[data-language=fr]').click()
        await page.locator('#live-login [name=username]').fill(state['username'])
        await page.locator('#live-login [name=password]').fill(state['password'])
        await page.locator('#preview-enter').click()
        await expect(page.locator('#preview-login')).to_be_hidden()
        await expect(page.locator('#home-attendance [data-home-attendance-kind]')).to_have_count(2)

    async def no_overflow(page):
        assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth+1')

    async def go(page,target):
        if page.viewport_size['width']<769 and not await page.locator('#sidebar').evaluate("e=>e.classList.contains('open')"):
            await page.locator('#menu').click()
        await page.locator(f'nav [data-page="{target}"]').click()

    async def metric(page,key,value,language):
        text=format(value,'g') if isinstance(value,(int,float)) else str(value)
        if language=='fr':text=text.replace('.',',')
        await expect(page.locator(f'#attendance-overview [data-overview-metric={key}] .stat-value')).to_have_text(text+'%')

    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
        try:
            for language,width in [('ar',1360),('ar',390),('fr',390)]:
                context=await browser.new_context(ignore_https_errors=True,viewport={'width':width,'height':1000})
                page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                await login(page,language)
                assert await page.locator('html').get_attribute('dir')==('ltr' if language=='fr' else 'rtl')
                await no_overflow(page)
                home=page.locator('#home-attendance [data-home-attendance-kind]')
                for card in await home.all():
                    assert 'stat' in (await card.get_attribute('class')).split()
                    await expect(card.locator('.stat-icon')).to_be_visible()
                cards=await home.evaluate_all('els=>els.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,width:e.getBoundingClientRect().width,height:e.getBoundingClientRect().height}))')
                assert len(cards)==2 and abs(cards[0]['y']-cards[1]['y'])<2,'Home uses the same paired counters even on mobile'
                await page.locator('#home-attendance').screenshot(path=str(out/f'home-{language}-{width}.png'))
                record(f'{language}-{width}:native_paired_home_counters')
                calls={'count':0}
                page.on('request',lambda r:calls.update(count=calls['count']+1) if r.url.endswith('/api/attendance.overview') else None)
                await page.locator('#home-attendance [data-person-nav=student-attendance]').click()
                await expect(page.locator('#start-attendance')).to_be_visible()
                await metric(page,'present',50,language)
                await metric(page,'absent',50,language)
                initial_calls=calls['count']
                await page.locator('[data-attendance-period=week]').click()
                await expect(page.locator('[data-attendance-period=week]')).to_have_attribute('aria-pressed','true')
                await metric(page,'present',70,language)
                await page.locator('[data-attendance-period=month]').click()
                await metric(page,'present',77.8,language)
                await metric(page,'absent',22.2,language)
                assert calls['count']==initial_calls,'Switching the saved summary tabs does not refetch or reset the page'
                await expect(page.locator('#attendance-date')).to_have_value('2026-11-18')
                await expect(page.locator('.roll-step-label')).to_have_count(0)
                await no_overflow(page)
                await page.screenshot(path=str(out/f'students-month-{language}-{width}.png'),full_page=True)
                await page.locator('#theme').click();await no_overflow(page)
                await metric(page,'present',77.8,language)
                await page.screenshot(path=str(out/f'students-month-dark-{language}-{width}.png'),full_page=True)
                await page.locator('#theme').click()
                record(f'{language}-{width}:saved_day_week_month_rates_compact_layout_direction_dark_and_instant_tabs')
                if language=='ar' and width==1360:
                    # Date and department operate on the actual API, keeping
                    # the selected period rather than silently resetting it.
                    await fill_field(page.locator('#attendance-date'),'2026-11-17')
                    await metric(page,'present',85.7,language)
                    await expect(page.locator('[data-attendance-period=month]')).to_have_attribute('aria-pressed','true')
                    await fill_field(page.locator('#attendance-date'),'2026-11-18')
                    await metric(page,'present',77.8,language)
                    options=await page.locator('#attendance-department option').evaluate_all('els=>els.map(e=>e.value).filter(Boolean)')
                    assert len(options)==2
                    async with page.expect_response(lambda r:r.url.endswith('/api/attendance.overview') and r.request.method=='POST') as pending:
                        await page.locator('#attendance-department').select_option(options[0])
                    department_data=await (await pending.value).json()
                    assert department_data['department']==int(options[0])
                    expected=department_data['periods']['month']['summary']['attendance_rate']
                    await metric(page,'present',expected,language)
                    await page.locator('#attendance-department').select_option('')
                    await metric(page,'present',77.8,language)
                    record('selected_date_and_department_refresh_actual_saved_summary_without_resetting_period')
                    before_reload=calls['count']
                    async with page.expect_response(lambda r:r.url.endswith('/api/attendance.overview') and r.request.method=='POST') as pending:
                        await page.locator('[data-att-reload]').click()
                    assert (await pending.value).status==200 and calls['count']>before_reload
                    await metric(page,'present',77.8,language)
                    record('explicit_refresh_reads_fresh_summary_for_unchanged_filter')
                    await page.locator('#start-attendance').click()
                    await expect(page.locator('#roll-dialog')).to_be_visible()
                    await page.locator('[data-roll-person][data-roll-status=absent]').first.click()
                    await page.locator('[data-roll-exit]').first.click()
                    await expect(page.locator('#record-dialog')).to_be_visible()
                    await page.locator('#keep-attendance').click()
                    await expect(page.locator('#roll-dialog')).to_be_visible()
                    await page.locator('[data-roll-exit]').first.click()
                    await page.locator('#discard-attendance').click()
                    await expect(page.locator('#roll-dialog')).not_to_be_visible()
                    await metric(page,'present',77.8,language)
                    record('focused_roll_call_and_discard_guard_preserved_without_persisting_changes')
                    async def fail(route):await route.abort('failed')
                    await page.route('**/api/attendance.overview',fail)
                    await page.locator('[data-att-reload]').click()
                    await expect(page.locator('[data-attendance-overview-retry]')).to_be_visible()
                    await page.unroute('**/api/attendance.overview',fail)
                    await page.locator('[data-attendance-overview-retry]').click()
                    await metric(page,'present',77.8,language)
                    record('network_error_keeps_readable_retry_and_recovers_without_fake_zero')
                    await go(page,'teachers')
                    await page.locator('[data-person-nav=teacher-attendance]').click()
                    await page.locator('[data-attendance-period=day]').click()
                    await metric(page,'present',66.7,language)
                    await page.locator('[data-attendance-period=week]').click();await metric(page,'present',77.8,language)
                    await page.locator('[data-attendance-period=month]').click();await metric(page,'present',83.3,language)
                    await page.screenshot(path=str(out/'teachers-month-ar-1360.png'),full_page=True)
                    record('teachers_share_native_design_and_keep_separate_saved_rates')
                await context.close()
        except BaseException:
            if 'page' in locals() and not page.is_closed():await page.screenshot(path=str(out/'failure.png'),full_page=True)
            raise
        finally:await browser.close()

    with httpx.Client(base_url=origin,verify=False,timeout=20) as api:
        api.post('/api/login',json={'username':state['username'],'password':state['password']},headers={'Origin':origin})
        session=api.get('/api/session').json();headers={'Origin':origin,'X-CSRF-Token':session['csrf']}
        after=api.post('/api/attendance.daily',json={},headers=headers).json()
        assert {k:after[k] for k in ('date','students','teachers')}=={k:baseline[k] for k in ('date','students','teachers')}
        assert {s['id']:s['account']['paid'] for s in api.get('/api/snapshot').json()['students']}==paid
    assert not errors,errors
    record('attendance_and_student_financial_amounts_unchanged_no_javascript_errors')
    print(json.dumps({'passed':len(passed),'javascript_errors':errors}))


if __name__=='__main__':asyncio.run(main())
