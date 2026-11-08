"""Teacher file, monthly instalments and reversible recoveries on real services."""
import asyncio,json,os,sys,uuid
import httpx
from pathlib import Path
from playwright.async_api import async_playwright,expect
from tests.qa_live_pages import guard
from tests.date_entry_helpers import fill_field

async def main():
 state=json.loads(Path(os.environ['KG_TEACHER_PAYROLL_STATE']).read_text());guard(state['dsn'])
 out=Path('visual-evidence/teacher-payroll');out.mkdir(parents=True,exist_ok=True)
 results=[];errors=[]
 async with async_playwright() as pw:
  browser=await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
  for lang,width in [('ar',1360),('ar',390),('fr',390)]:
   ctx=await browser.new_context(ignore_https_errors=True,viewport={'width':width,'height':960});page=await ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   await page.goto(state['origin'],wait_until='networkidle')
   if lang=='fr':await page.locator('[data-language=fr]').click()
   await page.locator('#live-login [name=username]').fill(state['username']);await page.locator('#live-login [name=password]').fill(state['password']);await page.locator('#preview-enter').click();await expect(page.locator('#preview-login')).to_be_hidden()
   if width<769:await page.locator('#menu').click()
   await page.locator('#nav-teachers').click();await page.locator('[data-teacher-profile]').filter(has_text='').first.click()
   await expect(page.locator('.pay-metrics')).to_be_visible();await expect(page.locator('[data-pay-month="2026-10"]')).to_be_visible()
   assert not await page.evaluate('document.documentElement.scrollWidth>innerWidth')
   assert await page.locator('html').get_attribute('dir')==('ltr' if lang=='fr' else 'rtl')
   await page.screenshot(path=str(out/f'file-{lang}-{width}.png'),full_page=True)
   await page.locator('[data-pay-month="2026-10"]').click();await expect(page.locator('.pay-month-detail')).to_be_visible()
   await page.screenshot(path=str(out/f'month-{lang}-{width}.png'),full_page=True)
   await page.locator('#workspace-close').click();assert not await page.locator('.discard-box').count()
   if lang=='ar' and width==1360:
    await page.locator('[data-pay-month="2026-10"]').click();await page.locator('[data-pay-month-salary]').click();f=page.locator('#payroll-form')
    await expect(f.locator('[name=payment_cash]')).to_have_value('500');await f.locator('[name=payment_cash]').fill('600')
    await f.locator('[name=reason]').fill('اختبار رفض التجاوز');await f.locator('[name=confirmed]').check();await f.locator('button.primary').click();await expect(f.locator('.error').last).not_to_be_empty()
    await f.locator('[name=payment_cash]').fill('500');await f.locator('button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible();await expect(page.locator('.pay-metrics')).to_be_visible()
    results.append('partial_month_completed_without_duplicate_or_overpayment')
    await page.locator('[data-teacher-salary=salary]').click();f=page.locator('#payroll-form');await expect(f.locator('[name=payment_cash]')).to_have_value('1400')
    await f.locator('[name=bonus]').fill('500');await expect(f.locator('[name=payment_cash]')).to_have_value('1900')
    await f.locator('[name=deductions]').fill('100');await expect(f.locator('[name=payment_cash]')).to_have_value('1800');await expect(page.locator('#salary-net')).to_contain_text('2,400')
    await f.locator('[name=payment_cash]').fill('400');await f.locator('[name=bonus]').fill('600');await expect(f.locator('[name=payment_cash]')).to_have_value('400')
    await f.locator('[name=bonus]').fill('0');await f.locator('[name=deductions]').fill('0')
    await fill_field(f.locator('[name=month]'),'2026-12');await expect(f).to_have_attribute('data-quote-month','2026-12');await expect(f.locator('[name=payment_cash]')).to_have_value('400')
    await fill_field(f.locator('[name=month]'),'2026-11');await expect(f).to_have_attribute('data-quote-month','2026-11');await expect(f.locator('[name=payment_cash]')).to_have_value('400')
    results.append('salary_preview_updates_and_preserves_explicit_partial_cash')
    await f.locator('[name=reason]').fill('جزئي نوفمبر وتسديد السلفة');await f.locator('[name=confirmed]').check();await page.screenshot(path=str(out/'salary-recovery.png'),full_page=True);await f.locator('button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible();await expect(page.locator('.pay-metrics')).to_be_visible()
    await page.locator('[data-pay-tab=movements]').click();await page.locator('[data-pay-entry=salary]').first.click()
    async with page.expect_download() as download:await page.locator('[data-pay-pdf]').click()
    path=out/'salary-slip-ar.pdf';await (await download.value).save_as(path);assert path.read_bytes().startswith(b'%PDF')
    await page.locator('[data-pay-edit=salary]').click();f=page.locator('#payroll-form');await expect(f.locator('[name=payment_cash]')).to_have_value('400')
    await f.locator('[name=payment_cash]').fill('300');await page.locator('#workspace-close').click();await expect(page.locator('.discard-box')).to_be_visible();await page.locator('[data-keep]').click()
    await f.locator('[name=reason]').fill('تصحيح الدفعة');await f.locator('[name=confirmed]').check();await f.locator('button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible();await expect(page.locator('.pay-metrics')).to_be_visible()
    await page.locator('[data-pay-tab=movements]').click();await page.locator('[data-pay-entry=salary]').first.click();await page.locator('[data-pay-cancel=salary]').click();f=page.locator('#pay-cancel-form');await f.locator('[name=reason]').fill('إلغاء دفعة الاختبار');await f.locator('[name=confirmed]').check();await f.locator('button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible();await expect(page.locator('.pay-metrics')).to_be_visible()
    results.extend(['named_recovery_and_salary_correction','guarded_unsaved_dialog','cash_cancel_reopens_loan','private_salary_pdf_download'])
    await page.locator('#nav-workspace').click();await page.locator('[data-tool-tab=payroll]').click();await page.locator('[data-payroll-records=teacher_payments]').click()
    await page.locator('#tool-rows [data-tool-mode=edit]').last.click();await expect(page.locator('#payroll-form [name=payment_cash]')).to_be_visible()
    assert await page.locator('#tool-edit-form').count()==0
    await page.locator('#workspace-close').click();await expect(page.locator('.discard-box')).to_have_count(0)
    await page.locator('#nav-teachers').click();await page.locator('[data-teacher-profile]').first.click();await expect(page.locator('.pay-metrics')).to_be_visible()
    results.append('generic_records_use_same_safe_payroll_editor')
   await page.locator('[data-pay-tab=advances]').click();await page.screenshot(path=str(out/f'advances-{lang}-{width}.png'),full_page=True)
   if lang=='fr':
    await page.locator('[data-pay-tab=movements]').click();await page.locator('#teacher-finance [data-pay-entry=salary]').last.click()
    if await page.locator('[data-pay-pdf]').count():
     async with page.expect_download() as download:await page.locator('[data-pay-pdf]').click()
     await (await download.value).save_as(out/'salary-slip-fr.pdf')
    await page.locator('#workspace-close').click()
   await page.locator('#theme').click();await page.screenshot(path=str(out/f'dark-{lang}-{width}.png'),full_page=True)
   results.append(f'{lang}-{width}:file_months_loans_direction_and_dark')
   if lang=='fr':
    await page.locator('[data-teacher-archive]').click();f=page.locator('#tool-edit-form');await f.locator('[name=reason]').fill('Archivage de contrôle');await f.locator('[name=confirmed]').check();await f.locator('button.primary').click();await expect(page.locator('#record-dialog')).not_to_be_visible();await expect(page.locator('.pay-metrics')).to_be_visible()
    await expect(page.locator('[data-teacher-salary]')).to_have_count(0)
    await page.locator('[data-pay-tab=movements]').click();await page.locator('#teacher-finance [data-pay-entry=salary]').last.click();await page.locator('[data-pay-edit=salary]').click()
    await expect(page.locator('#payroll-form [name=payment_cash]')).to_be_visible();await expect(page.locator('#payroll-form [name=teacher]')).to_be_disabled()
    await page.locator('#workspace-close').click();assert not await page.locator('.discard-box').count()
    results.append('archived_teacher_historical_editor_available_without_new_disbursement')
   await ctx.close()
  with httpx.Client(base_url=state['origin'],verify=False) as api:
   assert api.post('/api/login',json={'username':state['username'],'password':state['password']},headers={'Origin':state['origin']}).status_code==200
   session=api.get('/api/session').json();username='salary_editor_'+uuid.uuid4().hex[:7]
   r=api.post('/api/users.save',json=dict(name='مراجع الرواتب فقط',username=username,password='1234',permissions=['salaries.edit'],active=True),headers={'Origin':state['origin'],'X-CSRF-Token':session['csrf']});assert r.status_code==200,r.text
   tid=next(t['id'] for t in api.get('/api/teachers.options').json() if t['identity']=='TEACHER-1')
  ctx=await browser.new_context(ignore_https_errors=True,viewport={'width':1360,'height':960});p=await ctx.new_page();p.on('pageerror',lambda e:errors.append(str(e)))
  await p.goto(state['origin'],wait_until='networkidle');await p.locator('#live-login [name=username]').fill(username);await p.locator('#live-login [name=password]').fill('1234');await p.locator('#preview-enter').click();await expect(p.locator('#preview-login')).to_be_hidden()
  await expect(p.locator('#nav-teachers')).to_have_count(0)
  await p.locator('#nav-workspace').click();await p.locator('[data-tool-tab=payroll]').click();await p.locator('[data-pay-pick-month]').click()
  await p.locator('#pay-month-picker [name=teacher]').select_option(tid);await p.locator('#pay-month-picker button').click();f=p.locator('#pay-month-form');await expect(f).to_be_visible()
  await f.locator('[name=bonus]').fill('100');await f.locator('[name=reason]').fill('اختبار تعديل الاستحقاق بصلاحية رواتب فقط');await f.locator('[name=confirmed]').check();await f.locator('button.primary').click();await expect(p.locator('#record-dialog')).not_to_be_visible()
  results.append('salary_editor_without_teacher_view_can_edit_entitlement_without_viewing_private_teacher_file')
  await ctx.close();await browser.close()
 assert not errors,errors
 (out/'results.json').write_text(json.dumps({'passed':results,'javascript_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'passed':results,'javascript_errors':errors},ensure_ascii=False))

if __name__=='__main__':asyncio.run(main())
