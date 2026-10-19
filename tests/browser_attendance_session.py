"""Focused attendance session, density, pagination, discard and atomic approval."""
import asyncio
import json
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright, expect
from scripts.build_pages_preview import build


async def mark_visible_present(page):
    for ident in await page.locator('.roll-person.unmarked [data-roll-status="present"]:enabled').evaluate_all('(els)=>els.map(el=>el.dataset.rollPerson)'):
        await page.locator('[data-roll-person="'+ident+'"][data-roll-status="present"]').click()


async def main():
    out = Path(__file__).resolve().parents[1] / 'visual-evidence' / 'attendance-session'
    out.mkdir(parents=True, exist_ok=True)
    passed, errors = [], []
    with tempfile.TemporaryDirectory(prefix='attendance-session-') as temporary:
        public = Path(temporary)
        build(public / 'kindergarten2')
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=str(public)))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, channel='chrome' if sys.platform == 'win32' else None)
            page = await browser.new_page(viewport={'width': 1440, 'height': 1000})
            page.on('pageerror', lambda error: errors.append(str(error)))
            try:
                await page.goto(f'http://127.0.0.1:{server.server_port}/kindergarten2/', wait_until='networkidle')
                await page.locator('#preview-enter').click()
                await expect(page.locator('#preview-login')).to_be_hidden()
                await page.evaluate('''async()=>{
                    const sample=previewClone(previewState.students.find(s=>!s.cancelled));
                    previewState.students.push(...Array.from({length:60-previewState.students.filter(s=>!s.cancelled).length},(_,i)=>({...previewClone(sample),id:String(1000+i),name:'طالب القائمة '+String(i+1).padStart(2,'0')}))); 
                    const canvas=document.createElement('canvas');canvas.width=canvas.height=64;
                    const ctx=canvas.getContext('2d');ctx.fillStyle='#d2e9f5';ctx.fillRect(0,0,64,64);ctx.fillStyle='#275d7e';ctx.font='36px sans-serif';ctx.fillText('م',17,44);
                    previewState.students.find(s=>s.id==='1').photo={revision:1,data:canvas.toDataURL()};
                    previewState.students.find(s=>s.id==='2').photo={revision:1,data:'data:image/png;base64,aW52YWxpZA=='};
                    window.rollAttempts=0;window.rollFail=false;
                    const original=previewOperation;
                    previewOperation=async(op,data)=>{
                        if(op==='attendance.save'){
                            window.rollAttempts++;
                            await new Promise(resolve=>setTimeout(resolve,150));
                            if(window.rollFail){window.rollFail=false;throw Error('تعذر الحفظ التجريبي؛ أعد المحاولة.');}
                        }
                        return original(op,data);
                    };
                    await liveLoad();render();
                }''')
                await page.locator('nav [data-page="students"]').click()
                await page.locator('#open-student-attendance').click()
                await expect(page.locator('#start-attendance')).to_be_enabled()
                await expect(page.locator('.roll-choice')).to_have_count(0)
                await page.locator('#start-attendance').click()
                assert await page.locator('#roll-dialog').evaluate('(d)=>d.matches(":modal")')
                await expect(page.locator('[data-roll-row]')).to_have_count(30)
                assert await page.evaluate('rollCounts(rollPeople()).unmarked===60 && attendanceState.drafts.size===0 && previewAttendance.students.filter(r=>r.on_date===today).length===0')
                assert await page.locator('#roll-rows').evaluate('(el)=>getComputedStyle(el).gridTemplateColumns.split(" ").length===3')
                assert await page.locator('[data-roll-row]').first.evaluate('(el)=>el.getBoundingClientRect().height<80')
                await expect(page.locator('[data-roll-row="1"] .roll-avatar img')).to_be_visible()
                await page.locator('[data-roll-row="1"] .roll-avatar img').evaluate('(img)=>img.decode()')
                await expect(page.locator('[data-roll-row="2"] .roll-avatar img')).to_have_count(0)
                await expect(page.locator('[data-roll-row="3"] .roll-avatar>span')).to_be_visible()
                assert await page.locator('[data-roll-row="1"] .roll-avatar').evaluate('(el)=>el.getBoundingClientRect().width<=32')
                passed.append('student_portraits_compact_with_missing_and_failed_image_fallbacks')
                passed.append('explicit_modal_start_compact_30_rows_and_no_automatic_status')

                await expect(page.locator('.roll-choice[aria-pressed="true"]')).to_have_count(0)
                await page.locator('#roll-review').click()
                await expect(page.locator('#roll-error')).to_contain_text('اختر حالة')
                await page.locator('[data-roll-filter="all"]').click()
                await mark_visible_present(page)
                await page.locator('[data-roll-person="1000"][data-roll-status="absent"]').click()
                await page.locator('[data-roll-page="1"]').click()
                await mark_visible_present(page)
                await page.locator('[data-roll-person="1031"][data-roll-status="excused"]').click()
                await page.locator('#roll-search').fill('لا توجد نتائج')
                await expect(page.locator('[data-roll-row]')).to_have_count(0)
                await expect(page.locator('#roll-absent-count')).to_have_text('2')
                await page.locator('#roll-review').click()
                await expect(page.locator('#roll-error')).to_contain_text('عذر')
                await expect(page.locator('[data-roll-excuse="1031"]')).to_be_visible()
                await page.locator('[data-roll-excuse="1031"]').fill('موعد طبي')
                assert await page.evaluate('rollCounts(rollPeople()).present===58 && rollCounts(rollPeople()).absent===1 && rollCounts(rollPeople()).excused===1')
                passed.append('drafts_across_pages_search_and_hidden_excuse_validation')

                await page.locator('[data-roll-filter="all"]').click()
                await page.locator('#roll-search').fill('')
                await page.screenshot(path=str(out / 'roll-desktop.png'))
                await page.keyboard.press('Escape')
                await expect(page.locator('#discard-attendance')).to_be_visible()
                await page.locator('#keep-attendance').click()
                await expect(page.locator('#roll-dialog')).to_be_visible()
                await page.locator('#roll-review').click()
                await expect(page.locator('.roll-review-absent')).to_contain_text('موعد طبي')
                await page.screenshot(path=str(out / 'roll-review.png'))
                assert await page.evaluate('window.rollAttempts===0')
                await page.evaluate('window.rollFail=true')
                await page.locator('#roll-save').click()
                await expect(page.locator('#roll-error')).to_contain_text('أعد المحاولة')
                assert await page.evaluate('attendanceState.drafts.size===60 && previewAttendance.students.filter(r=>r.on_date===today).length===0')
                await page.locator('#attendance-form').evaluate('(f)=>{f.requestSubmit();f.requestSubmit();}')
                await expect(page.locator('#roll-dialog')).not_to_be_visible()
                assert await page.evaluate('window.rollAttempts===2 && previewAttendance.students.filter(r=>r.on_date===today).length===60 && previewAttendance.students.filter(r=>r.on_date===today).every(r=>r.revision===1)')
                passed.append('review_then_explicit_approval_retry_without_partial_or_duplicate_save')

                await expect(page.locator('#start-attendance')).to_contain_text('تعديل الحضور')
                await page.locator('#start-attendance').click()
                await expect(page.locator('#roll-title')).to_have_text('تعديل الحضور')
                assert await page.evaluate('attendanceState.drafts.size===0')
                await page.keyboard.press('Escape')
                await expect(page.locator('#discard-attendance')).to_be_visible()
                await page.locator('#keep-attendance').click()
                await page.set_viewport_size({'width':390,'height':844})
                await expect(page.locator('[data-roll-row]')).to_have_count(12)
                await page.locator('[data-roll-person="1000"][data-roll-status="present"]').click()
                await expect(page.locator('#toast.show')).to_have_count(0,timeout=7000)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                assert await page.locator('#roll-dialog').evaluate('(d)=>d.scrollHeight<=d.clientHeight+1')
                await page.screenshot(path=str(out / 'roll-mobile.png'))
                await page.locator('#roll-dialog [data-roll-exit]').click()
                await page.locator('#discard-attendance').click()
                assert await page.evaluate('previewAttendance.students.find(r=>r.person_id==="1000"&&r.on_date===today).status==="absent" && window.rollAttempts===2')
                await expect(page.locator('#roll-dialog')).not_to_be_visible()
                passed.append('mobile_12_rows_fixed_controls_and_explicit_discard_preserves_saved_day')
                await page.set_viewport_size({'width':1440,'height':1000})
                await page.locator('#start-attendance').click()
                await page.locator('[data-roll-clear="1000"]').click()
                await page.locator('#roll-review').click()
                await expect(page.locator('.roll-review-screen')).to_contain_text('إلغاء تسجيل اليوم (1)')
                assert await page.evaluate('!previewAttendance.students.find(r=>r.person_id==="1000"&&r.on_date===today).cancelled_at')
                await page.locator('#roll-save').click()
                await expect(page.locator('#roll-dialog')).not_to_be_visible()
                assert await page.evaluate('!!previewAttendance.students.find(r=>r.person_id==="1000"&&r.on_date===today).cancelled_at')
                passed.append('existing_day_cancellation_is_reviewed_and_only_applied_on_approval')
                assert not errors, errors
            except Exception:
                await page.screenshot(path=str(out / 'failure.png'))
                raise
            finally:
                (out / 'results.json').write_text(json.dumps({'passed':passed,'javascript_errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')
                await browser.close()
                server.shutdown()
    print(json.dumps({'passed':passed,'javascript_errors':errors},ensure_ascii=False))


if __name__ == '__main__':
    asyncio.run(main())
