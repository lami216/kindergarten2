"""The actual shared people UI against real Python/PostgreSQL services."""
import asyncio,json,sys,io
from PIL import Image
from pathlib import Path
from playwright.async_api import async_playwright,expect
from tests.date_entry_helpers import fill_field

async def main(origin,username,password):
    out=Path(__file__).resolve().parents[1]/'visual-evidence'/'people-live';out.mkdir(parents=True,exist_ok=True)
    results=[];errors=[]
    async with async_playwright() as pw:
        browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
        context=await browser.new_context(ignore_https_errors=True,viewport={'width':1280,'height':960})
        page=await context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        try:
            await page.goto(origin)
            await page.locator('#live-login [name="username"]').fill(username)
            await page.locator('#live-login [name="password"]').fill(password)
            await page.locator('#preview-enter').click()
            await expect(page.locator('#preview-login')).to_be_hidden()
            baseline=await page.evaluate('liveCall("snapshot")')
            await page.locator('#nav-teachers').click();await page.locator('#add-teacher').click()
            for key,value in {'full_name':'معلم من الواجهة الفعلية','national_id':'LIVE-1','salary':'5000'}.items():await page.locator('#teacher-form [name="'+key+'"]').fill(value)
            await page.locator('#teacher-section').select_option('new')
            await page.locator('#teacher-form [name="new_department"]').fill('قسم الواجهة الفعلية')
            await page.locator('#teacher-form [name="reason"]').fill('تسجيل فعلي في قاعدة اختبار')
            await page.locator('#teacher-form [name="confirmed"]').check();await page.locator('#teacher-form button.primary').click()
            await expect(page.locator('#teacher-roster')).to_contain_text('معلم من الواجهة الفعلية')
            data=await page.evaluate('liveCall("snapshot")');teacher=next(t for t in data['teachers'] if t['name']=='معلم من الواجهة الفعلية')['id'];section=next(d for d in data['departments'] if d['name']=='قسم الواجهة الفعلية')['id']
            results.append('actual_teacher_and_department_atomic_registration')
            await page.locator('nav [data-page="students"]').click();await page.locator('#add-student').click()
            for key,value in {'name':'طالب الحضور الفعلي','birth':'2022-01-01','mother':'أم الطالب','motherPhone':'22334455'}.items():await fill_field(page.locator('#student-form [name="'+key+'"]'), value)
            portrait=io.BytesIO();Image.new('RGB',(48,48),'teal').save(portrait,format='PNG')
            await page.locator('#student-form [name="photo"]').set_input_files(dict(name='synthetic-portrait.png',mimeType='image/png',buffer=portrait.getvalue()))
            await page.locator('#student-form [name="department_id"]').select_option(str(section))
            await page.locator('#student-form .form-end button.primary').click()
            await page.locator('#student-search').fill('طالب الحضور الفعلي')
            await expect(page.locator('#student-rows')).to_contain_text('طالب الحضور الفعلي')
            data=await page.evaluate('liveCall("snapshot")');child=next(s for s in data['students'] if s['name']=='طالب الحضور الفعلي')['id']
            assert next(s for s in data['students'] if s['id']==child)['class']=='قسم الواجهة الفعلية'
            await page.locator('#open-student-attendance').click()
            await expect(page.locator('#start-attendance')).to_be_enabled()
            await page.locator('#attendance-department').select_option(str(section))
            await page.locator('#start-attendance').click()
            image=page.locator('[data-roll-row="'+child+'"] .roll-avatar img')
            await expect(image).to_be_visible()
            await image.evaluate('(img)=>img.decode()')
            assert await image.evaluate('(img)=>img.naturalWidth>0')
            await page.locator('[data-roll-person="'+child+'"][data-roll-status="excused"]').click()
            await page.locator('[data-roll-excuse="'+child+'"]').fill('موعد طبي')
            await page.locator('#roll-review').click();await page.locator('#roll-save').click();await expect(page.locator('#toast')).to_contain_text('تم اعتماد وحفظ')
            await page.locator('[data-person-nav="students"]').click();await page.locator('#student-search').fill('طالب الحضور الفعلي');await page.locator('[data-profile="'+child+'"]').first.click()
            await expect(page.locator('.person-attendance')).to_contain_text('1')
            await page.locator('[data-att-history="students"]').click();await expect(page.locator('#record-dialog')).to_contain_text('موعد طبي')
            await page.locator('[data-att-correct]').first.click()
            await page.locator('#attendance-correction [name="status"]').select_option('present')
            await page.locator('#attendance-correction [name="reason"]').fill('تصحيح بعد التواصل')
            await page.locator('#attendance-correction [name="confirmed"]').check();await page.locator('#attendance-correction button.primary').click()
            await expect(page.locator('#toast')).to_contain_text('تم تصحيح')
            results.append('actual_student_placement_attendance_and_profile_correction')
            await page.locator('#nav-teachers').click();await page.locator('[data-person-nav="teacher-attendance"]').click()
            await expect(page.locator('#start-attendance')).to_be_enabled()
            await page.locator('#attendance-department').select_option(str(section))
            await page.locator('#start-attendance').click();await page.locator('[data-roll-person="'+teacher+'"][data-roll-status="present"]').click();await page.locator('#roll-review').click();await page.locator('#roll-save').click()
            await expect(page.locator('#toast')).to_contain_text('تم اعتماد وحفظ')
            await expect(page.locator('#start-attendance')).to_contain_text('تعديل الحضور')
            await page.locator('[data-person-nav="teachers"]').click();await page.locator('#teacher-search').fill('معلم من الواجهة الفعلية');await page.locator('[data-teacher-profile="'+teacher+'"]').click()
            await expect(page.locator('#teacher-finance')).to_contain_text('لا توجد سجلات')
            await page.locator('[data-teacher-salary="salary"]').click()
            await page.locator('#payroll-form [name="bonus"]').fill('500');await page.locator('#payroll-form [name="deductions"]').fill('100')
            await expect(page.locator('#salary-net')).to_contain_text('5,400')
            await page.locator('#payroll-form [name="reason"]').fill('صرف اختباري')
            await page.locator('#payroll-form [name="confirmed"]').check();await page.locator('#payroll-form button.primary').click()
            await expect(page.locator('#teacher-finance')).to_contain_text('5,400')
            await page.locator('[data-teacher-salary="advance"]').click()
            await page.locator('#payroll-form [name="amount"]').fill('500')
            await page.locator('#payroll-form [name="reason"]').fill('سلفة اختبارية')
            await page.locator('#payroll-form [name="confirmed"]').check();await page.locator('#payroll-form button.primary').click()
            await expect(page.locator('#teacher-finance')).to_contain_text('500')
            await page.locator('[data-teacher-cash="teacher_payments"]').first.click()
            await page.locator('[data-person-cash-mode="edit"]').click()
            await page.locator('#tool-edit-form [name="bonus"]').fill('600')
            await page.locator('#tool-edit-form [name="reason"]').fill('تصحيح مكافأة')
            await page.locator('#tool-edit-form [name="confirmed"]').check();await page.locator('#tool-edit-form button.primary').click()
            await expect(page.locator('#teacher-finance')).to_contain_text('5,500')
            await page.locator('[data-teacher-cash="teacher_payments"]').first.click()
            await page.locator('[data-person-cash-mode="void_document"]').click()
            await page.locator('#tool-edit-form [name="reason"]').fill('إلغاء المستند مع بقاء النقد')
            await page.locator('#tool-edit-form [name="confirmed"]').check();await page.locator('#tool-edit-form button.primary').click()
            await expect(page.locator('#teacher-finance')).to_contain_text('المستند ملغى')
            await page.locator('[data-teacher-cash="teacher_advances"]').first.click()
            await page.locator('[data-person-cash-mode="cancel"]').click()
            await page.locator('#tool-edit-form [name="reason"]').fill('إلغاء إدخال السلفة')
            await page.locator('#tool-edit-form [name="confirmed"]').check();await page.locator('#tool-edit-form button.primary').click()
            await expect(page.locator('#teacher-finance')).to_contain_text('إدخال ملغى')
            results.append('teacher_file_retains_cash_correction_and_both_cancellation_meanings')
            await page.screenshot(path=str(out/'teacher-profile-real.png'),full_page=True)
            data=await page.evaluate('liveCall("snapshot")')
            assert data['attendance']['students'][child]['present']==1 and data['attendance']['teachers'][teacher]['present']==1
            assert data['overview']['salary_cash']==baseline['overview']['salary_cash']+5500 and data['overview']['advance_cash']==baseline['overview']['advance_cash']
            results.append('actual_teacher_register_salary_and_advance_share_existing_ledger')
            await page.reload();await expect(page.locator('#preview-login')).to_be_hidden()
            data=await page.evaluate('liveCall("snapshot")')
            assert data['attendance']['students'][child]['present']==1
            assert any(c['type']=='student_attendance' and c['after']['full_name']=='طالب الحضور الفعلي' for c in data['changes'])
            results.append('persisted_after_reload_and_readable_audit')
            await page.locator('nav [data-page="students"]').click();await page.locator('#open-student-attendance').click()
            await expect(page.locator('#start-attendance')).to_be_enabled()
            await page.locator('#attendance-department').select_option(str(section))
            await page.locator('#start-attendance').click();await page.locator('[data-roll-clear="'+child+'"]').click()
            await page.locator('#roll-review').click()
            await expect(page.locator('.roll-review-screen')).to_contain_text('إلغاء تسجيل اليوم (1)')
            await page.locator('#roll-save').click();await expect(page.locator('#roll-dialog')).not_to_be_visible()
            data=await page.evaluate('liveCall("snapshot")')
            assert data['attendance']['students'].get(child,{}).get('total',0)==0
            assert data['attendance']['teachers'][teacher]['present']==1
            assert any(c['type']=='student_attendance' and c['action']=='cancelled' for c in data['changes'])
            results.append('focused_cancellation_updates_actual_summary_and_audit_without_affecting_teachers')
            assert not errors,errors
        except Exception:
            await page.screenshot(path=str(out/'failure.png'),full_page=True);raise
        finally:
            (out/'results.json').write_text(json.dumps({'passed':results,'javascript_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
            await browser.close()
    print(json.dumps({'passed':results,'javascript_errors':errors},ensure_ascii=False))

if __name__=='__main__':
    import os
    state=json.loads(Path(os.environ['KG_LIVE_QA_DIR'],'state.json').read_text())
    asyncio.run(main(state['origin'],state['username'],state['password']))
