"""Both language directions, login-only selection, school workflows and user-data isolation."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

from playwright.async_api import async_playwright, expect
from scripts.build_pages_preview import build
from tests.date_entry_helpers import fill_field


async def main():
    out = Path(__file__).resolve().parents[1]/'visual-evidence'/'french'
    out.mkdir(parents=True, exist_ok=True)
    errors, pages = [], {}
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp)/'school')
        server = ThreadingHTTPServer(('127.0.0.1',0), partial(SimpleHTTPRequestHandler,directory=tmp))
        threading.Thread(target=server.serve_forever,daemon=True).start()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
            page = await browser.new_page(viewport={'width':1440,'height':1000})
            page.on('pageerror',lambda e: errors.append(str(e)))
            await page.goto(f'http://127.0.0.1:{server.server_port}/school/',wait_until='networkidle')
            await expect(page.locator('html')).to_have_attribute('dir','rtl')
            await page.locator('[data-language="fr"]').click()
            await page.wait_for_load_state('networkidle')
            await expect(page.locator('html')).to_have_attribute('lang','fr')
            await expect(page.locator('html')).to_have_attribute('dir','ltr')
            await page.screenshot(path=str(out/'login-fr.png'),full_page=True)
            await page.locator('#preview-enter').click()
            await expect(page.locator('#preview-login')).to_be_hidden()
            await expect(page.locator('[data-language="ar"]')).to_be_hidden()
            assert await page.evaluate("document.querySelector('aside').getBoundingClientRect().left===0")
            assert await page.evaluate("I18N.message('لا يمكن حذف ولي الأمر؛ الطفل الطلاب عليه مبلغ 100 أوقية قديمة.').includes('الطلاب')")
            await page.evaluate("document.querySelector('[data-language=ar]').onclick()")
            assert await page.evaluate("I18N.lang==='fr'&&localStorage.getItem('kg.language')==='fr'")
            for name in ['dashboard','students','registration','payments','expenses','records','history','tools','teachers','student-attendance','teacher-attendance','admin']:
                await page.evaluate('(name)=>navigate(name)',name)
                await page.wait_for_timeout(160)
                pages[name] = await page.locator('#content').inner_text()
                await page.screenshot(path=str(out/(name+'-fr.png')),full_page=True)
            # Deliberately hold a lookup response while the user fills the form.
            await page.evaluate('''async()=>{
                teacherOptions=await liveCall('teachers.options');
                const original=previewOperation;
                previewOperation=async(op,data)=>{
                    const value=await original(op,data);
                    if(op==='teachers.options')return new Promise(resolve=>{window.releaseTeacherLookup=()=>resolve(value);});
                    return value;
                };
                toolTab='reports';navigate('tools');window.pendingTeacherLookup=loadWorkspace();
            }''')
            await page.wait_for_function('typeof window.releaseTeacherLookup==="function"')
            await page.locator('#report-form [name="kind"]').select_option('salaries')
            await fill_field(page.locator('#report-form [name="start"]'), '2026-09-01')
            await page.locator('#report-form [name="teacher"]').select_option(index=1)
            selected_teacher=await page.locator('#report-form [name="teacher"]').input_value()
            await page.evaluate('window.releaseTeacherLookup();window.pendingTeacherLookup')
            await expect(page.locator('#report-form [name="kind"]')).to_have_value('salaries')
            await expect(page.locator('#report-form [name="start"]')).to_have_value('2026-09-01')
            await expect(page.locator('#report-form [name="teacher"]')).to_have_value(selected_teacher)
            await page.locator('#report-form [name="kind"]').select_option('students')
            await page.locator('#report-form button').click()
            await expect(page.locator('#report-output th').first).to_have_text('Élève')
            await page.evaluate("navigate('students');studentMode='add';render()")
            await expect(page.locator('#student-form [name="gender"] option').first).to_have_attribute('value','ذكر')
            await expect(page.locator('#student-form [name="gender"] option').first).to_have_text('Garçon')
            pages['student-form'] = await page.locator('#content').inner_text()
            await page.screenshot(path=str(out/'student-form-fr.png'),full_page=True)
            await page.evaluate("profileId='1';studentMode='list';render()")
            await expect(page.locator('.file-identity')).to_contain_text('مريم أحمد')
            await page.screenshot(path=str(out/'student-fr.png'),full_page=True)
            await page.evaluate("profileId='4';render()")
            await expect(page.locator('.file-identity')).to_contain_text('عبد الله سالم')
            await expect(page.locator('#content')).to_contain_text('Frais : Exonéré')
            await page.evaluate("previewState.students.find(s=>s.id==='1').name='الطلاب';liveLoad().then(()=>{profileId='1';render()})")
            await expect(page.locator('.file-identity h2')).to_have_text('الطلاب')
            await page.evaluate('''()=>{
                const original=previewOperation;let hold=true;
                previewOperation=async(op,data)=>{
                    const value=await original(op,data);
                    if(op==='attendance.read'&&hold){hold=false;return new Promise(resolve=>{window.releaseAttendanceLookup=()=>resolve(value);});}
                    return value;
                };
                navigate('student-attendance');
            }''')
            await page.wait_for_function('typeof window.releaseAttendanceLookup==="function"')
            await expect(page.locator('#attendance-department')).to_be_disabled()
            await page.evaluate('window.releaseAttendanceLookup()')
            await expect(page.locator('#attendance-department')).to_be_enabled()
            await page.locator('#start-attendance').click()
            await expect(page.locator('.roll-choice.selected')).to_have_count(0)
            await page.locator('#roll-review').click()
            await expect(page.locator('#roll-error')).to_contain_text('Choisissez')
            await page.locator('[data-roll-filter="all"]').click()
            for ident in await page.locator('[data-roll-status="present"]:enabled').evaluate_all('(es)=>es.map(e=>e.dataset.rollPerson)'):
                await page.locator('[data-roll-person="'+ident+'"][data-roll-status="present"]').click()
            await page.locator('[data-roll-person="1"][data-roll-status="excused"]').click()
            await page.locator('[data-roll-excuse="1"]').fill('Rendez-vous médical — موعد طبي')
            await page.screenshot(path=str(out/'attendance-fr.png'),full_page=True)
            await page.locator('#roll-review').click()
            await page.locator('#roll-save').click()
            await expect(page.locator('#toast')).to_contain_text('validée et enregistrée')
            await expect(page.locator('#roll-dialog')).to_be_hidden()
            await page.set_viewport_size({'width':390,'height':844})
            await page.locator('#start-attendance').click()
            await page.screenshot(path=str(out/'attendance-mobile-fr.png'),full_page=True)
            assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
            await page.locator('#roll-dialog [data-roll-exit]').click()
            await page.locator('#discard-attendance').click()
            await page.locator('#theme').click()
            await page.screenshot(path=str(out/'dark-mobile-fr.png'),full_page=True)
            await page.reload(wait_until='networkidle')
            await expect(page.locator('html')).to_have_attribute('lang','fr')
            assert not errors, errors
            await browser.close()
        server.shutdown()
    (out/'pages.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2),encoding='utf-8')
    print('FRENCH_BROWSER_OK',len(pages),'screens',errors)


if __name__=='__main__':
    asyncio.run(main())
