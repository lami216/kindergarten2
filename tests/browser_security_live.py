"""Benign image security and bilingual print on actual local TLS/PG services."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import uuid

from PIL import Image
from playwright.async_api import async_playwright, expect
from tests.qa_live_pages import guard


def picture(fmt, color='teal'):
    data = io.BytesIO()
    Image.new('RGB', (48, 36), color).save(data, format=fmt)
    return base64.b64encode(data.getvalue()).decode('ascii')


async def main():
    state = json.loads((Path(os.environ['KG_LIVE_QA_DIR']) / 'state.json').read_text())
    guard(state['dsn'])
    assert state['origin'] == 'https://127.0.0.1:8520'
    out = Path('visual-evidence/security-live')
    out.mkdir(parents=True, exist_ok=True)
    results = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        try:
            for language in ('ar', 'fr'):
                for width in (1360, 390):
                    context = await browser.new_context(ignore_https_errors=True,
                        viewport={'width': width, 'height': 1000})
                    page = await context.new_page()
                    try:
                        await page.goto(state['origin'])
                        await page.locator('[data-language="' + language + '"]').click()
                        await page.locator('#live-login [name="username"]').fill(state['username'])
                        await page.locator('#live-login [name="password"]').fill(state['password'])
                        await page.locator('#preview-enter').click()
                        await expect(page.locator('#preview-login')).to_be_hidden()
                        await expect(page.locator('html')).to_have_attribute('dir', 'rtl' if language == 'ar' else 'ltr')
                        async def api(op, data=None):
                            return await page.evaluate('async({op,data})=>liveCall(op,data===null?undefined:data)',
                                                       dict(op=op, data=data))
                        session = await api('session')
                        snapshot = await api('snapshot')
                        name = 'صورة اختبار Élodie ' + uuid.uuid4().hex[:8]
                        student = (await api('students.create', dict(name=name, birth='2022-01-01', gender='ذكر',
                            mother='أم Élodie', motherPhone='22334455', mode='none', amount='0',
                            department_id=snapshot['departments'][0]['id'], request_token=str(uuid.uuid4()),
                            photo=picture('PNG'))))['id']
                        async def post(op, data):
                            return await context.request.post(state['origin'] + '/api/' + op, data=data,
                                headers={'Origin': state['origin'], 'X-CSRF-Token': session['csrf']})
                        for fmt in ('GIF', 'BMP', 'TIFF', 'JPEG2000'):
                            denied = await post('photos.save', dict(student=student, revision=1,
                                reason='benign format rejection', photo=picture(fmt)))
                            assert denied.status == 422, await denied.text()
                        corrupt = await post('photos.save', dict(student=student, revision=1,
                            reason='corrupt rejection', photo=base64.b64encode(b'not an image').decode()))
                        assert corrupt.status == 422
                        for revision, fmt in enumerate(('JPEG', 'WEBP'), start=1):
                            assert (await api('photos.save', dict(student=student, revision=revision,
                                reason='تحديث Élodie', photo=picture(fmt, 'blue' if fmt == 'WEBP' else 'red'))))['revision'] == revision + 1
                        await page.evaluate('async()=>{await liveLoad();navigate("students")}')
                        await page.locator('#student-search').fill(name)
                        avatar = page.locator('[data-student-avatar="' + student + '"] img').first
                        await expect(avatar).to_be_visible()
                        await avatar.evaluate('(img)=>img.decode()')
                        image = await context.request.get(state['origin'] + '/api/photo/' + student)
                        assert image.ok and image.headers['content-type'].startswith('image/jpeg')
                        with Image.open(io.BytesIO(await image.body()), formats=('JPEG',)) as decoded:
                            decoded.load()
                            assert decoded.size == (48, 36) and not decoded.getexif()
                        await page.locator('[data-profile="' + student + '"]').first.click()
                        await page.locator('#open-profile-photo').click()
                        await page.locator('#profile-photo-remove [name="reason"]').fill('حذف Élodie')
                        await page.locator('#profile-photo-remove [name="confirm"]').check()
                        await page.locator('#profile-photo-remove button').click()
                        await expect(page.locator('#profile-photo-dialog')).to_be_hidden()
                        assert (await context.request.get(state['origin'] + '/api/photo/' + student)).status == 404
                        await page.evaluate('navigate("students")')
                        await page.locator('#student-search').fill(name)
                        assert await page.locator('[data-student-avatar="' + student + '"] img').count() == 0
                        await page.evaluate('navigate("reports")')
                        await page.locator('#finance-report-form button.primary').click()
                        await page.wait_for_function('()=>financeData!==null')
                        await page.locator('[data-report-section=money][role=tab]').click()
                        await page.evaluate('window.print=()=>{}')
                        await page.locator('#fin-print').click()
                        await page.emulate_media(media='print')
                        await expect(page.locator('#sidebar')).to_be_hidden()
                        await expect(page.locator('#finance-report-form')).to_be_hidden()
                        assert await page.locator('.fin-print-table tbody tr').count() == len(await page.evaluate('financeData.items'))
                        await page.pdf(path=str(out / f'report-{language}-{width}.pdf'))
                        await page.emulate_media(media='screen')
                        await page.evaluate('window.dispatchEvent(new Event("afterprint"))')
                        await page.screenshot(path=str(out / f'report-{language}-{width}.png'), full_page=True)
                        # A directly requested operation and private image must also enforce grants.
                        worker = 'image_worker_' + uuid.uuid4().hex[:8]
                        await api('users.save', dict(name=worker, username=worker, password='test-image-1234',
                            permissions=['departments.view'], active=True))
                        await api('logout', {})
                        response = await context.request.post(state['origin'] + '/api/login',
                            data={'username': worker, 'password': 'test-image-1234'}, headers={'Origin': state['origin']})
                        assert response.ok
                        session = await (await context.request.get(state['origin'] + '/api/session')).json()
                        assert (await post('photos.save', dict(student=student, revision=4, reason='denied',
                            photo=picture('PNG')))).status == 403
                        assert (await context.request.get(state['origin'] + '/api/photo/' + student)).status == 403
                        results.append(dict(language=language, width=width, passed=True))
                        (out / 'results.json').write_text(json.dumps(results), encoding='utf-8')
                    finally:
                        await context.close()
        finally:
            await browser.close()
    print('SECURITY_LIVE_OK: ' + json.dumps(results))


if __name__ == '__main__':
    asyncio.run(main())
