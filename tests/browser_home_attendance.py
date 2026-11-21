"""Daily home attendance through real TLS on the private synthetic preview.

Run: KG_DAILY_STATE=/private/preview/state.json python -m tests.browser_home_attendance
Only the guarded kindergarten_test fixture is accepted. Network failures and
empty/no-mark presentation states are injected at the browser boundary; real
aggregates, permissions and roll-call writes use the actual services. The one
teacher status changed by the write scenario is restored, including on failure.
"""
import asyncio
from datetime import date, datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import uuid

import httpx
from playwright.async_api import async_playwright, expect
from tests.qa_live_pages import guard


async def main():
    default = Path(__file__).resolve().parents[2] / 'daily-attendance-preview' / 'state.json'
    state = json.loads(Path(os.environ.get('KG_DAILY_STATE', default)).read_text(encoding='utf-8'))
    guard(state['dsn'])
    origin = state['origin']
    assert origin.startswith('https://127.0.0.1:'), 'Use only the private loopback TLS preview'
    out = Path(__file__).resolve().parents[1] / 'visual-evidence' / 'daily-home'
    out.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    restore_teacher = None

    def passed(name):
        results.append(name)
        (out/'results.json').write_text(json.dumps({'passed':results,'javascript_errors':errors}, ensure_ascii=False, indent=2), encoding='utf-8')

    def connect_api():
        api = httpx.Client(base_url=origin, verify=False)
        response = api.post('/api/login', json={'username':state['username'],'password':state['password']}, headers={'Origin':origin})
        assert response.status_code == 200, 'Private QA owner login failed'
        session = api.get('/api/session').json()
        return api, {'Origin':origin,'X-CSRF-Token':session['csrf']}

    api, headers = connect_api()
    baseline = api.post('/api/attendance.daily', json={}, headers=headers).json()
    business_day = date.fromisoformat(baseline['date'])
    assert type(baseline['refresh_after_ms']) is int and 1000<=baseline['refresh_after_ms']<=86401000
    assert {k:baseline['students'][k] for k in ('present','absent','excused','total','roster_total','unmarked','complete')} == dict(present=3,absent=2,excused=1,total=6,roster_total=7,unmarked=1,complete=False)
    assert (baseline['students']['attendance_rate'],baseline['students']['absence_rate']) == (50,50)
    assert {k:baseline['teachers'][k] for k in ('present','absent','excused','total','roster_total','unmarked','complete')} == dict(present=2,absent=0,excused=1,total=3,roster_total=3,unmarked=0,complete=True)
    assert (baseline['teachers']['attendance_rate'],baseline['teachers']['absence_rate']) == (66.7,33.3)
    readers=[]
    for permissions,label in [(['student_attendance.view'],'student_attendance_reader'),(['teacher_attendance.view'],'teacher_attendance_reader'),(['students.view'],'student_file_reader')]:
        username=label+'_'+uuid.uuid4().hex[:8]
        response=api.post('/api/users.save', json=dict(name='قارئ حضور تجريبي',username=username,password='1234',permissions=permissions,active=True), headers=headers)
        assert response.status_code==200, 'Synthetic attendance reader creation failed'
        readers.append(username)
    original_paid={row['id']:row['account']['paid'] for row in api.get('/api/snapshot').json()['students']}
    api.close()
    passed('real_daily_endpoint_weighted_counts_separate_kinds_and_unmarked_denominator')

    async def sign_in(page,language='ar',username=state['username'],password=state['password']):
        await page.goto(origin,wait_until='networkidle')
        if language=='fr':
            await page.locator('[data-language=fr]').click()
        await page.locator('#live-login [name=username]').fill(username)
        await page.locator('#live-login [name=password]').fill(password)
        await page.locator('#preview-enter').click()
        await expect(page.locator('#preview-login')).to_be_hidden()

    async def go(page,target):
        if page.viewport_size['width']<769 and not await page.locator('#sidebar').evaluate("e=>e.classList.contains('open')"):
            await page.locator('#menu').click()
        await page.locator(f'nav [data-page="{target}"]').click()

    async def ready(page):
        await expect(page.locator('.home-attendance-card')).to_have_count(2)
        await expect(page.locator('#home-attendance time')).to_have_attribute('datetime',baseline['date'])

    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
        page=None
        try:
            for language,width in [('ar',1360),('ar',390),('fr',390)]:
                context=await browser.new_context(ignore_https_errors=True,viewport={'width':width,'height':1000})
                page=await context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                await page.clock.install(time=datetime.combine(business_day,time(12),timezone.utc))
                # The synthetic browser clock is independent of the real
                # server clock. Keep its next midnight one day away here;
                # dedicated cases below exercise the actual relative timer.
                async def stable_day(route):
                    response=await route.fetch();body=await response.json()
                    body['refresh_after_ms']=86400000
                    await route.fulfill(response=response,json=body)
                await page.route('**/api/attendance.daily',stable_day)
                requests={'count':0}
                def count_request(request):
                    if request.url.endswith('/api/attendance.daily'):requests['count']+=1
                page.on('request',count_request)
                await sign_in(page,language)
                await ready(page)
                children=page.locator('[data-home-attendance-kind=students]')
                teachers=page.locator('[data-home-attendance-kind=teachers]')
                await expect(children.locator('.present strong')).to_have_text('50%')
                await expect(children.locator('.absent strong')).to_have_text('50%')
                await expect(children.locator('.present .stat-unit')).to_contain_text('3')
                await expect(children.locator('.absent>span')).to_contain_text('3')
                assert '1' in await children.locator('.absent').get_attribute('title')
                await expect(children.locator('.home-attendance-state')).to_have_class('home-attendance-state incomplete')
                await expect(children.locator('.home-attendance-progress')).to_contain_text('6')
                await expect(children.locator('.home-attendance-progress')).to_contain_text('7')
                await expect(children.locator('.home-attendance-progress>span')).to_contain_text('1')
                await expect(teachers.locator('.present strong')).to_have_text('66,7%' if language=='fr' else '66.7%')
                await expect(teachers.locator('.absent strong')).to_have_text('33,3%' if language=='fr' else '33.3%')
                await expect(teachers.locator('.home-attendance-state')).to_have_class('home-attendance-state complete')
                assert await page.locator('html').get_attribute('dir')==('ltr' if language=='fr' else 'rtl')
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                ordering=await page.evaluate("""()=>{const w=document.querySelector('#home-attendance'),f=document.querySelector('#content details'),r=document.querySelector('#content .two-col');return {afterFinance:!!(f.compareDocumentPosition(w)&Node.DOCUMENT_POSITION_FOLLOWING),beforeRecent:!!(w.compareDocumentPosition(r)&Node.DOCUMENT_POSITION_FOLLOWING)};}""")
                assert ordering==dict(afterFinance=True,beforeRecent=True),ordering
                boxes=await page.locator('.home-attendance-card').evaluate_all('(cards)=>cards.map(e=>({x:e.getBoundingClientRect().x,y:e.getBoundingClientRect().y,height:e.getBoundingClientRect().height}))')
                assert max(box['height'] for box in boxes)<280,boxes
                assert abs(boxes[0]['y']-boxes[1]['y'])<2,boxes
                await page.locator('#home-attendance').screenshot(path=str(out/f'home-attendance-{language}-{width}.png'))
                if language=='ar' and width==1360:
                    await page.screenshot(path=str(out/'home-attendance-page-ar-1360.png'),full_page=True)
                await page.locator('#theme').click()
                assert await page.locator('body').evaluate("e=>e.classList.contains('dark')")
                await ready(page)
                await page.locator('#home-attendance').screenshot(path=str(out/f'home-attendance-dark-{language}-{width}.png'))
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                before=requests['count']
                await page.clock.fast_forward(2*60*60*1000)
                assert requests['count']==before,'Daily home must not poll'
                await teachers.click()
                await expect(page.locator('#start-attendance')).to_be_visible()
                await expect(page.locator('#roll-dialog[open]')).to_have_count(0)
                assert not await page.evaluate('homeAttendanceTimer!==null')
                before=requests['count']
                await page.clock.fast_forward(2*60*60*1000)
                assert requests['count']==before,'Away from home must not fetch daily attendance'
                await go(page,'dashboard')
                await ready(page)
                assert requests['count']==before+1,'Returning home reads the fresh aggregate once'
                passed(f'{language}-{width}:real_rates_counts_order_compact_layout_direction_dark_no_polling_and_view_only_navigation')
                await context.close()

            # Browser-boundary contract cases cannot alter the saved attendance.
            context=await browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':1000})
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            await page.clock.install(time=datetime.combine(business_day,time(12),timezone.utc))
            mode={'value':'error'}
            async def presentation(route):
                if mode['value']=='error':
                    await route.fulfill(status=503,json={'error':'Test network failure','language':'ar'})
                    return
                response=await route.fetch()
                body=await response.json()
                body['refresh_after_ms']=86400000
                if mode['value'] in ('unmarked','empty'):
                    for kind in ('students','teachers'):
                        if body[kind] is not None:
                            roster=body[kind]['roster_total'] if mode['value']=='unmarked' else 0
                            body[kind]=dict(present=0,absent=0,excused=0,total=0,attendance_rate=None,absence_rate=None,roster_total=roster,unmarked=roster,complete=roster==0)
                await route.fulfill(response=response,json=body)
            await page.route('**/api/attendance.daily',presentation)
            await sign_in(page)
            await expect(page.locator('[data-home-attendance-retry]')).to_be_visible()
            await expect(page.locator('.home-attendance-card')).to_have_count(0)
            await page.locator('#home-attendance').screenshot(path=str(out/'home-attendance-error-ar-390.png'))
            mode['value']='real'
            await page.locator('[data-home-attendance-retry]').click();await ready(page)
            passed('network_failure_shows_retry_not_stale_zero_and_recovers_real_counts')
            for value,state_class in [('unmarked','notRecorded'),('empty','empty')]:
                mode['value']=value
                await page.evaluate("window.dispatchEvent(new Event('focus'))")
                await expect(page.locator('.home-attendance-state')).to_have_class(['home-attendance-state '+state_class]*2)
                await expect(page.locator('.home-attendance-stat strong')).to_have_text(['—']*4)
                await expect(page.locator('.home-attendance-state.complete')).to_have_count(0)
                await page.locator('#home-attendance').screenshot(path=str(out/f'home-attendance-{value}-ar-390.png'))
            passed('no_marks_and_empty_roster_show_null_rates_without_claiming_absence_or_completion')
            await context.close()

            # A real correction through the existing focused attendance flow.
            context=await browser.new_context(ignore_https_errors=True,viewport={'width':1360,'height':1000})
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            await page.clock.install(time=datetime.combine(business_day,time(12),timezone.utc))
            await sign_in(page);await ready(page)
            await page.locator('[data-home-attendance-kind=teachers][data-person-nav]').click()
            await expect(page.locator('#start-attendance')).to_be_visible()
            teacher=await page.evaluate("attendanceState.items.find(r=>r.entry&&!r.entry.cancelled_at&&r.entry.status==='present')")
            restore_teacher={'person':teacher['id'],'status':teacher['entry']['status'],'excuse':teacher['entry']['excuse'],'date':baseline['date']}
            await page.locator('#start-attendance').click()
            await page.locator(f'[data-roll-person="{teacher["id"]}"][data-roll-status=absent]').click()
            await page.evaluate("document.querySelector('#theme').click()")
            await expect(page.locator('#roll-dialog')).to_be_visible()
            await expect(page.locator(f'[data-roll-person="{teacher["id"]}"][data-roll-status=absent]')).to_have_attribute('aria-pressed','true')
            await page.locator('#roll-review').click();await page.locator('#roll-save').click()
            await expect(page.locator('#roll-dialog[open]')).to_have_count(0)
            await go(page,'dashboard');await ready(page)
            await expect(page.locator('[data-home-attendance-kind=teachers] .present strong')).to_have_text('33.3%')
            await expect(page.locator('[data-home-attendance-kind=teachers] .absent strong')).to_have_text('66.7%')
            await page.locator('[data-home-attendance-kind=teachers][data-person-nav]').click()
            await expect(page.locator('#start-attendance')).to_be_visible();await page.locator('#start-attendance').click()
            await page.locator(f'[data-roll-person="{teacher["id"]}"][data-roll-status=present]').click()
            await page.locator('#roll-review').click();await page.locator('#roll-save').click()
            await expect(page.locator('#roll-dialog[open]')).to_have_count(0)
            await go(page,'dashboard');await ready(page)
            await expect(page.locator('[data-home-attendance-kind=teachers] .present strong')).to_have_text('66.7%')
            restore_teacher=None
            passed('real_attendance_correction_and_restoration_refresh_home_and_theme_preserves_unsaved_roll_draft')
            await context.close()

            for index,kind in [(0,'students'),(1,'teachers'),(2,None)]:
                context=await browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':1000})
                page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
                await page.clock.install(time=datetime.combine(business_day,time(12),timezone.utc))
                calls={'count':0}
                page.on('request',lambda request: calls.update(count=calls['count']+1) if request.url.endswith('/api/attendance.daily') else None)
                await sign_in(page,username=readers[index],password='1234')
                if kind:
                    await expect(page.locator('.home-attendance-card')).to_have_count(1)
                    await expect(page.locator(f'[data-home-attendance-kind={kind}]')).to_be_visible()
                    await expect(page.locator('#content .stat:not(.home-attendance-card),#content #home-receipts,#content #home-student')).to_have_count(0)
                    response=await page.evaluate("async()=>{const r=await fetch('/api/attendance.daily',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf},body:'{}'});return {status:r.status,body:await r.json()};}")
                    assert response['status']==200
                    assert response['body']['teachers' if kind=='students' else 'students'] is None
                    await expect(page.locator('[data-home-attendance-kind][data-person-nav]')).to_have_count(1)
                    await page.locator('#home-attendance').screenshot(path=str(out/f'home-attendance-permission-{kind}.png'))
                else:
                    await expect(page.locator('#home-attendance')).to_have_count(0)
                    assert calls['count']==0,'No attendance view permission must not request daily data'
                    status=await page.evaluate("async()=>{const r=await fetch('/api/attendance.daily',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf},body:'{}'});return r.status;}")
                    assert status==403
                passed(f'permission_{kind or "none"}:only_authorized_kind_in_home_and_actual_server_response')
                await context.close()

            # The UTC midnight refresh is a one-shot, not a repeating poll.
            context=await browser.new_context(ignore_https_errors=True,viewport={'width':1360,'height':1000})
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            await page.clock.install(time=datetime.combine(business_day,time(23,59,30),timezone.utc))
            calls={'count':0}
            async def midnight(route):
                calls['count']+=1;response=await route.fetch();body=await response.json()
                body['refresh_after_ms']=31000 if calls['count']==1 else 86400000
                if calls['count']>1:body['date']=(business_day+timedelta(days=1)).isoformat()
                await route.fulfill(response=response,json=body)
            await page.route('**/api/attendance.daily',midnight)
            await sign_in(page);await ready(page)
            assert calls['count']==1
            await page.clock.fast_forward(32000)
            await expect(page.locator('#home-attendance time')).to_have_attribute('datetime',(business_day+timedelta(days=1)).isoformat())
            assert calls['count']==2
            await page.clock.fast_forward(2*60*60*1000)
            assert calls['count']==2
            passed('single_utc_midnight_read_uses_new_server_date_without_polling_or_page_reload')
            await context.close()

            # Deliberately wrong client calendar: only the server's relative
            # deadline may advance the widget and the two register routes.
            context=await browser.new_context(ignore_https_errors=True,viewport={'width':1360,'height':1000})
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            await page.clock.install(time=datetime.combine(business_day+timedelta(days=2),time(12),timezone.utc))
            skew_calls={'count':0};register_dates=[]
            tomorrow=(business_day+timedelta(days=1)).isoformat()
            async def skew_day(route):
                skew_calls['count']+=1;response=await route.fetch();body=await response.json()
                body['refresh_after_ms']=10000 if skew_calls['count']==1 else 86400000
                if skew_calls['count']>1:body['date']=tomorrow
                await route.fulfill(response=response,json=body)
            async def future_register(route):
                payload=route.request.post_data_json
                register_dates.append((payload['kind'],payload['date']))
                # The preview's server business day is frozen. Preserve real
                # roster data, while serving the simulated next-day response.
                response=await route.fetch(post_data=json.dumps({**payload,'date':baseline['date']}))
                body=await response.json();body['date']=payload['date'];body['period_end']=payload['date']
                await route.fulfill(response=response,json=body)
            await page.route('**/api/attendance.daily',skew_day)
            await page.route('**/api/attendance.read',future_register)
            await sign_in(page);await ready(page)
            assert skew_calls['count']==1
            await page.clock.fast_forward(8000);assert skew_calls['count']==1
            await page.clock.fast_forward(3000)
            await expect(page.locator('#home-attendance time')).to_have_attribute('datetime',tomorrow)
            assert skew_calls['count']==2
            await page.clock.fast_forward(60*60*1000);assert skew_calls['count']==2
            for kind in ('teachers','students'):
                await page.locator(f'[data-home-attendance-kind={kind}][data-person-nav]').click()
                await expect(page.locator('#start-attendance')).to_be_visible()
                await expect(page.locator('#attendance-date')).to_have_value(tomorrow)
                await expect(page.locator('#attendance-date')).to_have_attribute('max',tomorrow)
                assert register_dates[-1]==(kind,tomorrow)
                if kind=='teachers':
                    await page.locator('#start-attendance').click()
                    row=await page.evaluate("attendanceState.items.find(r=>r.entry&&!r.entry.cancelled_at&&r.entry.status==='present')")
                    await page.locator(f'[data-roll-person="{row["id"]}"][data-roll-status=absent]').click()
                    draft=await page.evaluate('({date:attendanceState.date,drafts:[...attendanceState.drafts.values()]})')
                    before=skew_calls['count']
                    await page.evaluate("window.dispatchEvent(new Event('focus'))")
                    await page.clock.fast_forward(2*60*60*1000)
                    assert skew_calls['count']==before
                    assert await page.evaluate('({date:attendanceState.date,drafts:[...attendanceState.drafts.values()]})')==draft
                    await expect(page.locator('#roll-dialog')).to_be_visible()
                    await page.locator('[data-roll-exit]').click()
                    await page.locator('#discard-attendance').click()
                    await expect(page.locator('#roll-dialog[open]')).to_have_count(0)
                await go(page,'dashboard')
                await expect(page.locator('#home-attendance time')).to_have_attribute('datetime',tomorrow)
            passed('ahead_client_clock_uses_server_deadline_and_both_registers_keep_server_day_max_and_unsaved_drafts')
            await context.close()

            # If the business date advances slightly before midnight's timer,
            # a short same-day read must still re-arm the following midnight.
            context=await browser.new_context(ignore_https_errors=True,viewport={'width':1360,'height':1000})
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            await page.clock.install(time=datetime.combine(business_day,time(12),timezone.utc))
            rearm={'count':0}
            async def same_day_then_next(route):
                rearm['count']+=1;response=await route.fetch();body=await response.json()
                body['refresh_after_ms']=1000 if rearm['count']==1 else 86400000
                if rearm['count']>2:body['date']=tomorrow
                await route.fulfill(response=response,json=body)
            await page.route('**/api/attendance.daily',same_day_then_next)
            await sign_in(page);await ready(page)
            await page.clock.fast_forward(1500)
            await expect(page.locator('#home-attendance time')).to_have_attribute('datetime',baseline['date'])
            await page.wait_for_function('homeAttendanceData&&homeAttendanceData.refresh_after_ms===86400000')
            assert rearm['count']==2
            await page.clock.fast_forward(86401000)
            await expect(page.locator('#home-attendance time')).to_have_attribute('datetime',tomorrow)
            assert rearm['count']==3
            passed('short_same_day_boundary_read_rearms_the_following_midnight')
            await context.close()

            context=await browser.new_context(ignore_https_errors=True,viewport={'width':390,'height':1000})
            page=await context.new_page();page.on('pageerror',lambda error:errors.append(str(error)))
            started,release,finished=asyncio.Event(),asyncio.Event(),asyncio.Event()
            async def held_response(route):
                started.set();await release.wait()
                response=await route.fetch();await route.fulfill(response=response)
                finished.set()
            await page.route('**/api/attendance.daily',held_response)
            await sign_in(page);await started.wait()
            await page.evaluate('liveLoginScreen()')
            release.set();await finished.wait()
            await page.wait_for_timeout(100)
            await expect(page.locator('#preview-login')).to_be_visible()
            await expect(page.locator('#home-attendance')).to_have_count(0)
            assert await page.evaluate('liveSession===null&&homeAttendanceData===null&&homeAttendanceTimer===null')
            passed('late_daily_response_after_logout_cannot_restore_data_or_timer')
            await context.close()
        except BaseException:
            (out/'failure-errors.json').write_text(json.dumps({'javascript_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
            if page and not page.is_closed():await page.screenshot(path=str(out/'failure.png'),full_page=True)
            raise
        finally:
            await browser.close()
            if restore_teacher:
                api,headers=connect_api()
                roster=api.post('/api/attendance.read',json={'kind':'teachers','date':restore_teacher['date']},headers=headers).json()
                teacher=next(row for row in roster['items'] if row['id']==restore_teacher['person'])
                entry={k:restore_teacher[k] for k in ('person','status','excuse')}
                entry['revision']=teacher['entry']['revision']
                response=api.post('/api/attendance.save',json={'kind':'teachers','date':restore_teacher['date'],'entries':[entry],'reason':'إعادة حالة اختبار حضور تجريبي'},headers=headers)
                assert response.status_code==200,'Restore the disposable teacher test status'
                api.close()

    api,headers=connect_api()
    final=api.post('/api/attendance.daily',json={},headers=headers).json()
    assert {key:final[key] for key in ('date','students','teachers')}=={key:baseline[key] for key in ('date','students','teachers')},'The synthetic attendance fixture must retain its original counts'
    assert {row['id']:row['account']['paid'] for row in api.get('/api/snapshot').json()['students']}==original_paid
    api.close()
    passed('attendance_fixture_restored_and_student_financial_amounts_unchanged')
    assert not errors,errors
    print(json.dumps({'passed':results,'javascript_errors':errors},ensure_ascii=False))


if __name__=='__main__':
    asyncio.run(main())
