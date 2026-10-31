"""Real user journeys for the UX audit fixes, against disposable TLS/PostgreSQL."""
import asyncio,hashlib,json,os,re,sys,uuid
from pathlib import Path
import psycopg2
from psycopg2.extras import RealDictCursor
from playwright.async_api import async_playwright,expect
from tests.date_entry_helpers import fill_field
from tests.qa_live_pages import guard


async def main(state):
    guard(state['dsn']);origin=state['origin'];out=Path(__file__).resolve().parents[1]/'visual-evidence'/'ux-fixes';out.mkdir(parents=True,exist_ok=True)
    results=[];errors=[]
    def passed(case):results.append(case)
    def query(sql,args=()):
        with psycopg2.connect(state['dsn'],cursor_factory=RealDictCursor) as conn:
            with conn.cursor() as c:
                c.execute(sql,args)
                return c.fetchall() if c.description else []
    async def expire(context):
        cookie=next(c for c in await context.cookies() if c['name']=='__Host-kg_session')
        query("UPDATE app_sessions SET last_seen=now()-interval '31 minutes' WHERE token_hash=%s",(hashlib.sha256(cookie['value'].encode()).hexdigest(),))
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
        try:
            for lang,width in [('ar',1360),('fr',390)]:
                context=await browser.new_context(ignore_https_errors=True,viewport=dict(width=width,height=960))
                page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
                async def login_page(p,username=state['username'],password=state['password']):
                    await p.goto(origin,wait_until='networkidle')
                    if lang=='fr' and await p.locator('html').get_attribute('lang')!='fr':
                        await p.locator('[data-language=fr]').click();await p.wait_for_load_state('networkidle')
                    await p.locator('#live-login [name=username]').fill(username)
                    await p.locator('#live-login [name=password]').fill(password)
                    await p.locator('#preview-enter').click();await expect(p.locator('#preview-login')).to_be_hidden()
                async def nav(name,p=page):
                    if p.viewport_size['width']<769 and await p.locator('#menu').get_attribute('aria-expanded')!='true':await p.locator('#menu').click()
                    await p.locator('nav [data-page="'+name+'"]').click()
                async def data(p=page):return await p.evaluate('liveCall("snapshot")')
                await login_page(page)
                assert await page.locator('html').get_attribute('dir')==('ltr' if lang=='fr' else 'rtl')
                await nav('students');await page.locator('#add-student').click()
                form=page.locator('#student-form');name='UX '+lang+' '+uuid.uuid4().hex[:5]
                await expect(form.locator('[name=birth]')).to_have_value('')
                family_text=await form.locator('[name=existing_parent_id]').inner_text()
                assert not re.search(r'P[a-f0-9]{19}',family_text)
                await form.locator('[name=name]').fill(name)
                await form.locator('[name=department_id]').select_option(index=1)
                await form.locator('[name=mother]').fill('Parent UX')
                await form.locator('[name=motherPhone]').fill('22556677')
                await form.locator('button.primary').last.click()
                await expect(form).to_be_visible()
                assert not any(s['name']==name for s in (await data())['students'])
                passed(lang+':required_birth_has_no_invented_default')
                # Incomplete compound date, checkboxes, and draft must survive keep/theme.
                date_group=form.locator('[name=birth]').locator('xpath=preceding-sibling::*[1]')
                await date_group.locator('[data-date-part=day]').fill('12')
                await form.locator('[name=gilet]').uncheck()
                await nav('expenses')
                await expect(page.locator('#draft-navigation-dialog')).to_be_visible()
                await page.locator('[data-draft-keep]').click()
                await expect(form.locator('[name=name]')).to_have_value(name)
                await expect(date_group.locator('[data-date-part=day]')).to_have_value('12')
                assert not await form.locator('[name=gilet]').is_checked()
                if width<769 and await page.locator('#menu').get_attribute('aria-expanded')=='true':await page.locator('#menu').click()
                await page.locator('#theme').click()
                await expect(form.locator('[name=name]')).to_have_value(name)
                passed(lang+':draft_keep_partial_date_checkbox_and_theme')
                await nav('expenses');await page.locator('[data-draft-discard]').click()
                await expect(page.locator('#expense-form')).to_be_visible()
                assert not any(s['name']==name for s in (await data())['students'])
                # Expenses use the same protection, without saving on navigation.
                await page.locator('#expense-form [name=category]').fill('Unsaved expense')
                await nav('students');await expect(page.locator('#draft-navigation-dialog')).to_be_visible()
                await page.locator('[data-draft-discard]').click();await page.locator('#add-student').click()
                form=page.locator('#student-form')
                await expect(form.locator('[name=name]')).to_have_value('')
                await form.locator('[name=name]').fill(name)
                await form.locator('[name=department_id]').select_option(index=1)
                await form.locator('[name=mother]').fill('Parent UX')
                await form.locator('[name=motherPhone]').fill('22556677')
                await fill_field(form.locator('[name=birth]'),'2022-03-12')
                await form.locator('button.primary').last.click();await expect(form).to_have_count(0)
                sid=next(s['id'] for s in (await data())['students'] if s['name']==name)
                passed(lang+':explicit_discard_and_valid_registration')
                await page.locator('[data-profile="'+sid+'"]').click()
                await expect(page.locator('.file-info')).to_contain_text('12/03/2022' if lang=='fr' else '2022-03-12')
                await page.locator('#open-profile-edit').click()
                edit=page.locator('#profile-edit-child');await edit.locator('[name=address]').fill('Draft after expiry')
                await expire(context);await edit.locator('button.primary').click()
                renewal=page.locator('#session-recovery-dialog');await expect(renewal).to_be_visible()
                await expect(edit.locator('[name=address]')).to_have_value('Draft after expiry')
                await expect(renewal.locator('[name=username]')).to_have_attribute('readonly','')
                await renewal.locator('[name=password]').fill('wrong-password')
                await renewal.locator('button.primary').click();await expect(renewal.locator('.error')).not_to_be_empty()
                await renewal.screenshot(path=str(out/(lang+'-renew-session.png')))
                await renewal.locator('[name=password]').fill(state['password'])
                await renewal.locator('button.primary').click();await expect(renewal).to_have_count(0)
                await expect(edit.locator('[name=address]')).to_have_value('Draft after expiry')
                assert next(s for s in (await data())['students'] if s['id']==sid)['address']!='Draft after expiry'
                await edit.locator('button.primary').click();await expect(page.locator('#profile-edit-dialog')).not_to_be_visible()
                assert next(s for s in (await data())['students'] if s['id']==sid)['address']=='Draft after expiry'
                passed(lang+':reauth_keeps_form_wrong_password_recoverable_no_auto_save')
                # A coworker's new health note must survive a resumed old editor.
                await page.locator('#open-profile-edit').click();await page.locator('#profile-edit-child [name=address]').fill('Old editor address')
                await expire(context);await page.locator('#profile-edit-child button.primary').click();await expect(renewal).to_be_visible()
                other_context=await browser.new_context(ignore_https_errors=True,viewport=dict(width=1360,height=960))
                other=await other_context.new_page();await login_page(other)
                await other.locator('nav [data-page=students]').click();await other.locator('[data-profile="'+sid+'"]').click();await other.locator('#open-profile-edit').click()
                await other.locator('#profile-edit-child [name=health]').fill('Newer health note')
                await other.locator('#profile-edit-child button.primary').click();await expect(other.locator('#profile-edit-dialog')).not_to_be_visible()
                await renewal.locator('[name=password]').fill(state['password']);await renewal.locator('button.primary').click();await expect(renewal).to_have_count(0)
                await page.locator('#profile-edit-child button.primary').click();await expect(page.locator('#profile-edit-error')).not_to_be_empty()
                current=next(s for s in (await data())['students'] if s['id']==sid)
                assert current['health']=='Newer health note' and current['address']=='Draft after expiry'
                await page.locator('#profile-edit-close').click();await page.locator('#profile-edit-dialog [data-discard]').click()
                await other_context.close();passed(lang+':renewal_does_not_refresh_stale_editor_revision')
                await nav('teachers');teacher=(await data())['teachers'][0]
                await page.locator('[data-teacher-profile="'+teacher['id']+'"]').click();await page.locator('[data-teacher-salary=salary]').click()
                reason='UX salary '+lang
                await page.locator('#payroll-form [name=base]').fill('2000');await page.locator('#payroll-form [name=bonus]').fill('500');await page.locator('#payroll-form [name=deductions]').fill('100')
                await expect(page.locator('#salary-net')).to_contain_text('2'+('\u202f' if lang=='fr' else ',')+'400')
                await page.locator('#payroll-form [name=reason]').fill(reason);await page.locator('#payroll-form [name=confirmed]').check();await page.locator('#payroll-form button.primary').click()
                await expect(page.locator('#record-dialog')).not_to_be_visible()
                await page.locator('[data-teacher-salary=advance]').click();await page.locator('#payroll-form [name=amount]').fill('500')
                await page.locator('#payroll-form [name=reason]').fill('UX advance '+lang);await page.locator('#payroll-form [name=confirmed]').check();await page.locator('#payroll-form button.primary').click()
                await expect(page.locator('#record-dialog')).not_to_be_visible()
                rows=query("SELECT reason FROM payroll_audit WHERE reason IN (%s,%s)",(reason,'UX advance '+lang))
                assert {r['reason'] for r in rows}=={reason,'UX advance '+lang}
                await nav('history');await page.locator('#history-search').fill(reason)
                entry=page.locator('.history-entry').first;await expect(entry.locator('summary').first).to_contain_text(teacher['name'])
                await entry.locator('summary').first.click();await expect(entry).to_contain_text(reason)
                assert 'cash_amount' not in await entry.inner_text() and 'record_state' not in await entry.inner_text()
                await page.screenshot(path=str(out/(lang+'-friendly-history.png')),full_page=True)
                passed(lang+':salary_and_advance_reason_human_history')
                await nav('payments');await page.locator('#payment-student').select_option(sid)
                text=await page.locator('#payment-form').inner_text()
                assert ('Date d’encaissement' if lang=='fr' else 'تاريخ القبض') in text
                await page.screenshot(path=str(out/(lang+'-payment-caption.png')),full_page=True)
                passed(lang+':incoming_cash_date_caption')
                await nav('reports');await expect(page.locator('#fin-xlsx')).to_be_enabled()
                await expire(context);await page.locator('#fin-xlsx').click()
                await expect(page.locator('#session-recovery-dialog')).to_be_visible()
                await page.locator('#session-renew-form [name=password]').fill(state['password'])
                await page.locator('#session-renew-form button.primary').click();await expect(page.locator('#session-recovery-dialog')).to_have_count(0)
                async with page.expect_download() as export:
                    await page.locator('#fin-xlsx').click()
                await (await export.value).save_as(out/(lang+'-renewed-report.xlsx'))
                passed(lang+':expired_report_export_renews_in_place_and_downloads')
                await nav('dashboard');await page.locator('#home-receipts').click();await page.locator('[data-receipt]').first.click()
                await expire(context);await page.locator('#receipt-page a').click()
                await expect(page.locator('#session-recovery-dialog')).to_be_visible()
                assert await page.locator('#receipt-page').is_visible()
                await page.locator('#session-renew-form [name=password]').fill(state['password'])
                await page.locator('#session-renew-form button.primary').click();await expect(page.locator('#session-recovery-dialog')).to_have_count(0)
                async with page.expect_download() as pdf:
                    await page.locator('#receipt-page a').click()
                pdf_path=out/(lang+'-renewed-receipt.pdf');await (await pdf.value).save_as(pdf_path)
                assert pdf_path.read_bytes().startswith(b'%PDF')
                passed(lang+':expired_private_receipt_renews_without_blank_error_page')
                await context.close()
            # A changed role must not inherit the old editing UI after renewal.
            owner_context=await browser.new_context(ignore_https_errors=True,viewport=dict(width=1360,height=960))
            owner_page=await owner_context.new_page();await login_page(owner_page)
            username='ux_worker_'+uuid.uuid4().hex[:8]
            user=await owner_page.evaluate('v=>liveCall("users.save",v)',dict(name='UX worker',username=username,password='1234',permissions=['students.view','students.edit'],active=True))
            worker_context=await browser.new_context(ignore_https_errors=True,viewport=dict(width=390,height=960))
            worker_page=await worker_context.new_page();await login_page(worker_page,username,'1234')
            await worker_page.locator('#menu').click();await worker_page.locator('nav [data-page=students]').click()
            await worker_page.locator('[data-profile]').first.click();await worker_page.locator('#open-profile-edit').click()
            await worker_page.locator('#profile-edit-child [name=address]').fill('Must not survive revoked edit permission')
            await expire(worker_context);await worker_page.locator('#profile-edit-child button.primary').click()
            await expect(worker_page.locator('#session-recovery-dialog')).to_be_visible()
            await owner_page.evaluate('v=>liveCall("users.save",v)',dict(id=user['id'],version=1,name='UX worker',permissions=['students.view'],active=True))
            await worker_page.locator('#session-renew-form [name=password]').fill('1234')
            await worker_page.locator('#session-renew-form button.primary').click()
            await expect(worker_page.locator('#session-recovery-dialog')).to_have_count(0)
            await expect(worker_page.locator('#profile-edit-child')).to_have_count(0)
            await expect(worker_page.locator('#preview-login')).to_be_hidden()
            profile=await worker_page.evaluate('liveSession.user')
            assert profile['permissions']==['students.view'] and profile['auth_version']==2
            assert not query("SELECT student_id FROM students WHERE address=%s",('Must not survive revoked edit permission',))
            passed('renewal_honors_revoked_permissions_and_discards_old_edit_context')
            await worker_context.close();await owner_context.close()
            assert not errors,errors
        except Exception:
            if 'page' in locals() and not page.is_closed():await page.screenshot(path=str(out/'failure.png'),full_page=True)
            raise
        finally:
            (out/'results.json').write_text(json.dumps(dict(passed=results,errors=errors),ensure_ascii=False,indent=2),encoding='utf-8')
            await browser.close()
    print(json.dumps(dict(passed=results,errors=errors),ensure_ascii=False))


if __name__=='__main__':
    path=Path(os.environ['KG_UX_STATE']) if os.getenv('KG_UX_STATE') else Path(os.environ['KG_LIVE_QA_DIR'])/'state.json'
    state=json.loads(path.read_text(encoding='utf-8'))
    asyncio.run(main(state))
