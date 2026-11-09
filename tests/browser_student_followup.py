"""Collection reminders through real TLS services on private synthetic data."""
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import uuid

import httpx
from playwright.async_api import async_playwright, expect
from tests.qa_live_pages import guard


async def main():
    default = Path(__file__).resolve().parents[2] / 'student-followup-preview' / 'state.json'
    state = json.loads(Path(os.environ.get('KG_FOLLOWUP_STATE', default)).read_text(encoding='utf-8'))
    guard(state['dsn'])
    assert state.get('business_day') == '2026-11-10', 'Use the deterministic reminder fixture'
    out = Path(__file__).resolve().parents[1] / 'visual-evidence' / 'student-followup'
    out.mkdir(parents=True, exist_ok=True)
    results, errors, layouts = [], [], []
    origin = state['origin']
    expected = {'مريم أحمد': 3000, 'زينب محمد': 6000, 'محمد سالم': 3000, 'خديجة علي': 2000, 'أحمد محمود': 3000}

    def passed(name):
        results.append(name)
        (out / 'results.json').write_text(json.dumps({'passed': results, 'javascript_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')

    async def sign_in(page, username=state['username'], password=state['password'], language='ar'):
        await page.goto(origin, wait_until='networkidle')
        if language == 'fr':
            await page.locator('[data-language=fr]').click()
        await page.locator('#live-login [name=username]').fill(username)
        await page.locator('#live-login [name=password]').fill(password)
        await page.locator('#preview-enter').click()
        await expect(page.locator('#preview-login')).to_be_hidden()

    async def open_followup(page):
        if page.viewport_size['width'] < 769 and await page.locator('#menu').get_attribute('aria-expanded') != 'true':
            await page.locator('#menu').click()
        await page.locator('nav [data-page=payments]').click()
        await expect(page.locator('[data-finance=followup]')).to_be_visible()
        await page.locator('[data-finance=followup]').click()
        await expect(page.locator('#followup-search')).to_be_visible()
        await expect(page.locator('#followup-results .followup-card')).to_have_count(5)
        await expect(page.locator('#nav-followup,#home-followup')).to_have_count(0)
        can_create = await page.evaluate("demoCan('receipts','create')")
        await expect(page.locator('[data-finance=payment],[data-finance=receipts],[data-finance=followup]')).to_have_count(3 if can_create else 2)

    with httpx.Client(base_url=origin, verify=False) as api:
        assert api.post('/api/login', json={'username': state['username'], 'password': state['password']}, headers={'Origin': origin}).status_code == 200
        session = api.get('/api/session').json()
        headers = {'Origin': origin, 'X-CSRF-Token': session['csrf']}
        data = api.post('/api/followup.read', json={}, headers=headers).json()
        assert data['settings']['day'] == 10
        by_name = {r['name']: r for r in data['items']}
        assert set(by_name) == set(expected), by_name
        assert sum(r['due_total'] for r in data['items']) == 9000
        for name, amount in expected.items():
            item = by_name[name]
            assert (item['due_total'] if item['status'] == 'due' else item['upcoming']['remaining']) == amount, item
        assert by_name['محمد سالم']['upcoming']['due_date'] == '2026-11-11'
        assert by_name['خديجة علي']['upcoming']['due_date'] == '2026-11-12'
        assert by_name['أحمد محمود']['upcoming']['due_date'] == '2026-11-17'
        original = api.get('/api/snapshot').json()
        original_paid = {r['id']: r['account']['paid'] for r in original['students']}
        readers = []
        for permissions, label in [(['payments.view'], 'money_reader'), (['students.view'], 'student_reader')]:
            username = label + '_' + uuid.uuid4().hex[:8]
            created = api.post('/api/users.save', json=dict(name='قارئ متابعة تجريبي', username=username, password='1234', permissions=permissions, active=True), headers=headers)
            assert created.status_code == 200, created.text
            readers.append(username)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='chrome' if sys.platform == 'win32' else None)
        page = None
        try:
            for language, width in [('ar', 1360), ('ar', 390), ('fr', 390)]:
                context = await browser.new_context(ignore_https_errors=True, viewport={'width': width, 'height': 1000})
                page = await context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                await sign_in(page, language=language)
                await open_followup(page)
                await expect(page.locator('#followup-summary .followup-metric')).to_have_count(2)
                await expect(page.locator('#followup-summary .followup-metric').nth(0).locator('strong')).to_have_text('2')
                await expect(page.locator('#followup-summary .followup-metric').nth(1).locator('strong')).to_contain_text('9\u202f000' if language == 'fr' else '9,000')
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                assert await page.locator('html').get_attribute('dir') == ('ltr' if language == 'fr' else 'rtl')
                portraits = page.locator('.followup-person img')
                await expect(portraits).to_have_count(5)
                await portraits.first.evaluate('(img)=>img.decode()')
                assert await portraits.first.evaluate('(img)=>img.naturalWidth>0')
                names = await page.locator('.followup-person strong').all_text_contents()
                assert set(names) == set(expected), names
                # Keep the routine list short; contacts, section and the
                # financial breakdown are available only on explicit opening.
                await expect(page.locator('.followup-list')).not_to_contain_text('33000000')
                await expect(page.locator('.followup-list')).not_to_contain_text('قسم البراعم')
                await expect(page.locator('[data-followup-details]')).to_have_count(5)
                await expect(page.locator('.followup-list')).not_to_contain_text('آمنة المختار')
                await expect(page.locator('.followup-list')).not_to_contain_text('عمر عبد الله')
                heights = await page.locator('.followup-card').evaluate_all('(rows)=>rows.map(row=>Math.round(row.getBoundingClientRect().height))')
                assert max(heights) <= (85 if width > 768 else 140), heights
                layouts.append(dict(language=language, width=width, row_heights=heights, page_height=await page.evaluate('document.documentElement.scrollHeight')))
                (out / 'layout.json').write_text(json.dumps(layouts, ensure_ascii=False, indent=2), encoding='utf-8')
                await page.screenshot(path=str(out / f'followup-{language}-{width}.png'), full_page=True)
                mary = page.locator('.followup-card').filter(has=page.locator('.followup-person strong', has_text='مريم أحمد'))
                await mary.locator('[data-followup-details]').click()
                detail = page.locator('#record-dialog')
                await expect(detail).to_be_visible()
                await expect(detail).to_contain_text('مريم أحمد')
                await expect(detail).to_contain_text('3\u202f000' if language == 'fr' else '3,000')
                await expect(detail).to_contain_text('33000000')
                await expect(detail).to_contain_text('قسم البراعم')
                await expect(detail).to_contain_text('Inscription' if language == 'fr' else 'التسجيل')
                await page.screenshot(path=str(out / f'followup-details-{language}-{width}.png'), full_page=True)
                await page.locator('#workspace-close').click()
                await expect(detail).not_to_be_visible()
                await expect(page.locator('.discard-box')).to_have_count(0)
                passed(f'{language}-{width}:compact_rows_with_explicit_read_only_amount_details')
                await page.locator('[data-followup-tab=due]').click()
                await expect(page.locator('.followup-card')).to_have_count(2)
                assert set(await page.locator('.followup-person strong').all_text_contents()) == {'مريم أحمد', 'زينب محمد'}
                await page.locator('[data-followup-tab=upcoming]').click()
                await expect(page.locator('.followup-card')).to_have_count(3)
                assert set(await page.locator('.followup-person strong').all_text_contents()) == {'محمد سالم', 'خديجة علي', 'أحمد محمود'}
                await page.locator('[data-followup-tab=all]').click()
                await page.locator('#followup-search').fill('٣٣٠٠٠٠٠٢')
                await expect(page.locator('.followup-card')).to_have_count(1)
                await expect(page.locator('.followup-person strong')).to_have_text('خديجة علي')
                await page.locator('#followup-search').fill('(')
                await expect(page.locator('.followup-card')).to_have_count(0)
                await page.locator('#followup-search').fill('')
                await page.locator('#followup-department').select_option(label='قسم البراعم')
                await expect(page.locator('.followup-card')).to_have_count(2)
                assert set(await page.locator('.followup-person strong').all_text_contents()) == {'مريم أحمد', 'خديجة علي'}
                await page.locator('#followup-department').select_option('')
                passed(f'{language}-{width}:exact_balances_dates_avatars_search_literal_parent_phone_department_tabs_and_direction')
                if language == 'ar' and width == 1360:
                    await page.locator('#followup-settings').click()
                    form = page.locator('#followup-settings-form')
                    await form.locator('[name=day]').fill('8')
                    await page.locator('#workspace-close').click()
                    await expect(page.locator('.discard-box')).to_be_visible()
                    await page.locator('[data-keep]').click()
                    await expect(form.locator('[name=day]')).to_have_value('8')
                    await page.locator('#workspace-close').click()
                    await page.locator('[data-discard]').click()
                    await expect(page.locator('#record-dialog')).not_to_be_visible()
                    await expect(page.locator('.followup-card')).to_have_count(5)
                    passed('unsaved_reminder_day_can_be_kept_or_explicitly_discarded')
                    for day, count in [('8', 4), ('10', 5)]:
                        await page.locator('#followup-settings').click()
                        form = page.locator('#followup-settings-form')
                        await form.locator('[name=day]').fill(day)
                        await form.locator('[name=reason]').fill('اختبار موعد التذكير دون تغيير الحساب')
                        await form.locator('[name=confirmed]').check()
                        await form.locator('button.primary').click()
                        await expect(page.locator('#record-dialog')).not_to_be_visible()
                        await expect(page.locator('.followup-card')).to_have_count(count)
                        if day == '8':
                            await expect(page.locator('.followup-list')).not_to_contain_text('أحمد محمود')
                        else:
                            await expect(page.locator('.followup-list')).to_contain_text('أحمد محمود')
                    passed('audited_settings_shift_only_visibility_and_restore_default')
                    mary = page.locator('.followup-card').filter(has=page.locator('.followup-person strong', has_text='مريم أحمد'))
                    await mary.locator('[data-followup-profile]').click()
                    await expect(page.locator('.file-hero')).to_contain_text('مريم أحمد')
                    await open_followup(page)
                    mary = page.locator('.followup-card').filter(has=page.locator('.followup-person strong', has_text='مريم أحمد'))
                    await mary.locator('[data-followup-pay]').click()
                    await expect(page.locator('#payment-student')).to_have_value(by_name['مريم أحمد']['id'])
                    await expect(page.locator('#payment-body')).to_contain_text('مريم أحمد')
                    await open_followup(page)
                    passed('profile_and_preselected_payment_open_from_current_server_snapshot')
                await page.locator('#theme').click()
                await page.screenshot(path=str(out / f'followup-dark-{language}-{width}.png'), full_page=True)
                assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
                passed(f'{language}-{width}:dark_without_horizontal_overflow')
                await context.close()

            # A synthetic browser clock crosses the business midnight without
            # changing the server clock or creating/correcting any ledger data.
            context = await browser.new_context(ignore_https_errors=True, viewport={'width': 1360, 'height': 1000})
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await page.clock.install(time=datetime(2026, 11, 10, 23, 59, 30, tzinfo=timezone.utc))
            reads = {'count': 0}
            async def next_day_response(route):
                response = await route.fetch()
                body = await response.json()
                reads['count'] += 1
                # Eligibility itself is covered by the backend's real date
                # tests. Here only the new scheduling/refresh is simulated.
                body['today'] = '2026-11-10' if reads['count'] == 1 else '2026-11-11'
                await route.fulfill(response=response, json=body)
            await page.route('**/api/followup.read', next_day_response)
            await sign_in(page)
            await open_followup(page)
            assert reads['count'] == 1
            assert await page.evaluate('followupMidnightTimer!==null')
            await page.clock.fast_forward(61000)
            # Keep the production CSP intact: wait_for_function's string
            # compiler would use unsafe-eval inside the page.
            for _ in range(100):
                if await page.evaluate("followupData?.today==='2026-11-11'"):
                    break
                await asyncio.sleep(.1)
            else:
                raise AssertionError('The open follow-up page did not refresh at business midnight')
            assert reads['count'] == 2, reads
            await page.clock.fast_forward(300000)
            assert reads['count'] == 2, reads
            async def next_snapshot_response(route):
                response = await route.fetch()
                body = await response.json()
                body['today'] = '2026-11-11'
                await route.fulfill(response=response, json=body)
            await page.route('**/api/snapshot', next_snapshot_response)
            await page.locator('.followup-card').filter(has=page.locator('.followup-person strong', has_text='مريم أحمد')).locator('[data-followup-pay]').click()
            await expect(page.locator('#pay-date')).to_have_value('2026-11-11')
            await expect(page.locator('#pay-date')).to_have_attribute('max', '2026-11-11')
            assert await page.evaluate('followupMidnightTimer===null')
            await page.locator('#demo-logout').click()
            await expect(page.locator('#preview-login')).to_be_visible()
            assert await page.evaluate('followupMidnightTimer===null')
            await context.close()
            passed('business_midnight_refreshes_once_without_polling_clears_timer_and_uses_fresh_cash_date')

            context = await browser.new_context(ignore_https_errors=True, viewport={'width': 1360, 'height': 1000})
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await sign_in(page, username=readers[0], password='1234')
            await open_followup(page)
            await expect(page.locator('#followup-settings')).to_have_count(0)
            await expect(page.locator('[data-followup-profile],[data-followup-pay]')).to_have_count(0)
            await expect(page.locator('.followup-contacts,.followup-person img')).to_have_count(0)
            await expect(page.locator('.followup-list')).not_to_contain_text('33000002')
            await page.locator('[data-followup-details]').first.click()
            await expect(page.locator('#record-dialog')).not_to_contain_text('33000005')
            await expect(page.locator('#record-dialog')).not_to_contain_text('والدة زينب')
            await expect(page.locator('#record-dialog .followup-contacts img')).to_have_count(0)
            await page.locator('#workspace-close').click()
            await page.screenshot(path=str(out / 'payment-view-only.png'), full_page=True)
            passed('payments_view_only_cannot_see_contacts_photos_settings_or_mutation_actions')
            await context.close()
            context = await browser.new_context(ignore_https_errors=True, viewport={'width': 390, 'height': 1000})
            page = await context.new_page()
            page.on('pageerror', lambda error: errors.append(str(error)))
            await sign_in(page, username=readers[1], password='1234')
            await expect(page.locator('#nav-followup')).to_have_count(0)
            await expect(page.locator('[data-finance=followup]')).to_have_count(0)
            response = await page.evaluate("async()=>{const r=await fetch('/api/followup.read',{method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':liveSession.csrf},body:'{}'});return r.status;}")
            assert response == 403, response
            passed('students_view_does_not_reveal_financial_followup_ui_or_api')
            await context.close()
        except BaseException:
            if page and not page.is_closed():
                await page.screenshot(path=str(out / 'failure.png'), full_page=True)
            raise
        finally:
            await browser.close()
    with httpx.Client(base_url=origin, verify=False) as api:
        assert api.post('/api/login', json={'username': state['username'], 'password': state['password']}, headers={'Origin': origin}).status_code == 200
        snapshot = api.get('/api/snapshot').json()
        assert {r['id']: r['account']['paid'] for r in snapshot['students']} == original_paid
        session = api.get('/api/session').json()
        data = api.post('/api/followup.read', json={}, headers={'Origin': origin, 'X-CSRF-Token': session['csrf']}).json()
        assert data['settings']['day'] == 10
    passed('reminder_settings_and_navigation_never_change_student_paid_amounts')
    assert not errors, errors
    (out / 'results.json').write_text(json.dumps({'passed': results, 'javascript_errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': results, 'javascript_errors': errors}, ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
