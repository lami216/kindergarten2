"""Current student photos follow identity across lists, replacement and deletion."""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import tempfile
import threading

from PIL import Image
from playwright.async_api import async_playwright, expect
from scripts.build_pages_preview import build


async def main():
    out = Path(__file__).resolve().parents[1] / 'visual-evidence' / 'student-portraits'
    out.mkdir(parents=True, exist_ok=True)
    photo = out / 'first.png'
    replacement = out / 'replacement.png'
    Image.new('RGB', (100, 140), '#3a9880').save(photo)
    Image.new('RGB', (140, 100), '#4d6aac').save(replacement)
    errors, passed = [], []
    with tempfile.TemporaryDirectory() as tmp:
        build(Path(tmp))
        server = ThreadingHTTPServer(('127.0.0.1', 0), partial(SimpleHTTPRequestHandler, directory=tmp))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True, channel='chrome' if sys.platform == 'win32' else None)
            try:
                for language in ('ar', 'fr'):
                    page = await browser.new_page(viewport={'width': 1360, 'height': 960})
                    page.on('pageerror', lambda e: errors.append(str(e)))
                    await page.goto(f'http://127.0.0.1:{server.server_port}/', wait_until='networkidle')
                    if language == 'fr':
                        await page.locator('[data-language="fr"]').click()
                    await page.locator('#preview-enter').click()
                    await expect(page.locator('#preview-login')).to_be_hidden()
                    await page.evaluate("navigate('students')")
                    await page.locator('[data-profile="1"]').first.click()

                    async def upload(file):
                        await page.locator('#open-profile-photo').click()
                        await page.locator('#profile-photo-file').set_input_files(file)
                        await expect(page.locator('#profile-photo-preview img')).to_be_visible()
                        await page.locator('#profile-photo-form [name="reason"]').fill('Photo QA')
                        await page.locator('#profile-photo-save').click()
                        await expect(page.locator('#profile-photo-dialog')).not_to_be_visible()
                        await expect(page.locator('.file-portrait')).to_be_visible()
                        return await page.locator('.file-portrait').get_attribute('src')

                    src = await upload(photo)
                    # Two equal names must not share a photograph: identity is the key.
                    await page.evaluate("async()=>{previewState.students.find(s=>s.id==='2').name=previewState.students.find(s=>s.id==='1').name;await liveLoad();navigate('students');}")
                    avatar = page.locator('#student-rows [data-student-avatar="1"] img')
                    await expect(avatar).to_have_attribute('src', src)
                    await expect(page.locator('#student-rows [data-student-avatar="2"] img')).to_have_count(0)
                    await page.locator('#student-search').fill(await page.evaluate("students.find(s=>s.id==='1').name"))
                    await expect(avatar).to_be_visible()
                    await page.screenshot(path=str(out / (language + '-students.png')), full_page=True)
                    passed.append(language + ': uploaded photo in roster/search; same-name student isolated')

                    # Put this fixture's receipt among the four latest rows shown on home.
                    await page.evaluate("async()=>{previewState.receipts.sort((a,b)=>Number(a.student==='1')-Number(b.student==='1'));await liveLoad();navigate('dashboard')}")
                    await expect(page.locator('#content [data-student-avatar="1"] img').first).to_have_attribute('src', src)
                    await page.evaluate("navigate('payments')")
                    await page.locator('#payment-student').select_option('1')
                    await expect(page.locator('.payment-student-summary [data-student-avatar="1"] img')).to_have_attribute('src', src)
                    await page.evaluate("financeTab='receipts';render()")
                    await expect(page.locator('#receipt-rows [data-student-avatar="1"] img').first).to_have_attribute('src', src)
                    receipt = await page.evaluate("receipts.find(r=>r.student==='1').id")
                    await page.evaluate('(id)=>openReceipt(id)', receipt)
                    await expect(page.locator('#receipt-page [data-student-avatar="1"] img')).to_have_attribute('src', src)
                    await page.evaluate("navigate('registration');document.querySelector('#open-transfer').click()")
                    await expect(page.locator('#transfer-children [data-student-avatar="1"] img')).to_have_attribute('src', src)
                    await page.locator('#transfer-close').click()
                    passed.append(language + ': dashboard, payment, receipt list/document and class transfers')

                    await page.evaluate("navigate('student-attendance')")
                    await expect(page.locator('#attendance-department')).to_be_enabled()
                    await page.locator('#start-attendance').click()
                    await expect(page.locator('[data-roll-row="1"] .roll-avatar img')).to_have_attribute('src', src)
                    await page.locator('[data-roll-exit]').click()
                    await page.locator('#discard-attendance').click()
                    await expect(page.locator('#roll-dialog')).not_to_be_visible()
                    archived = await page.evaluate("async()=>{const s=previewState.students.find(s=>s.cancelled);s.photo=previewClone(previewState.students.find(s=>s.id==='1').photo);await liveLoad();navigate('archives');return s.id}")
                    await expect(page.locator(f'#archive-rows [data-student-avatar="{archived}"] img')).to_have_attribute('src', src)
                    await page.evaluate("navigate('students');profileId='1';render()")
                    updated = await upload(replacement)
                    assert updated != src
                    await page.locator('#back-students').click()
                    await expect(page.locator('#student-rows [data-student-avatar="1"] img')).to_have_attribute('src', updated)
                    passed.append(language + ': attendance uses current photo; replacement reaches list')

                    # An unavailable image returns to the initial without a broken icon.
                    await page.locator('#student-rows [data-student-avatar="1"] img').dispatch_event('error')
                    await expect(page.locator('#student-rows [data-student-avatar="1"] img')).to_have_count(0)
                    await expect(page.locator('#student-rows [data-student-avatar="1"] > span')).not_to_be_empty()
                    await page.locator('[data-profile="1"]').first.click()
                    await page.locator('#open-profile-photo').click()
                    await page.locator('#profile-photo-remove [name="reason"]').fill('Remove QA')
                    await page.locator('#profile-photo-remove [name="confirm"]').check()
                    await page.locator('#profile-photo-remove button').click()
                    await expect(page.locator('.file-initial')).to_be_visible()
                    await page.locator('#back-students').click()
                    await expect(page.locator('#student-rows [data-student-avatar="1"] img')).to_have_count(0)
                    passed.append(language + ': error fallback and deletion remove stale thumbnails')

                    await page.set_viewport_size({'width': 390, 'height': 844})
                    await page.evaluate("document.querySelector('#sidebar').classList.remove('open')")
                    await page.wait_for_function("(()=>{const r=document.querySelector('#sidebar').getBoundingClientRect();return r.right<=0||r.left>=innerWidth})()")
                    assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    await page.screenshot(path=str(out / (language + '-mobile.png')), full_page=True)
                    await page.close()
                assert not errors, errors
            finally:
                await browser.close()
                server.shutdown()
    (out / 'results.json').write_text(json.dumps({'passed': passed, 'errors': errors}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('STUDENT_PORTRAITS_OK', len(passed), 'scenarios', errors)


if __name__ == '__main__':
    asyncio.run(main())
