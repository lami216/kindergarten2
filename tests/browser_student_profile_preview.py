"""Synthetic Pages file/photo journey and responsive screenshots."""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import threading
from PIL import Image
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'visual-evidence/student-profile-preview'


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    photo=OUT/'portrait.png';Image.new('RGB',(800,1000),'#77bba5').save(photo)
    invalid=OUT/'invalid.png';invalid.write_bytes(b'<svg>Not a portrait</svg>')
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT/'docs')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True)
            for width in (390,1280):
                page=await browser.new_page(viewport={'width':width,'height':1000})
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                await page.goto(f'http://127.0.0.1:{server.server_port}')
                await page.locator('#preview-enter').click()
                if width<769: await page.locator('#menu').click()
                await page.locator('nav [data-page="students"]').click()
                await page.get_by_role('button',name='فتح الملف ←',exact=True).first.click()
                await expect(page.locator('.file-hero')).to_be_visible()
                await expect(page.get_by_role('img',name='لم تضف صورة للطالب',exact=True)).to_be_visible()
                await page.locator('#open-profile-photo').click()
                await page.locator('#profile-photo-file').set_input_files(invalid)
                await expect(page.locator('#profile-photo-error')).to_contain_text('صورة سليم')
                await page.locator('#profile-photo-file').set_input_files(photo)
                await expect(page.locator('#profile-photo-preview img')).to_be_visible()
                await page.locator('#profile-photo-form [name="reason"]').fill('إضافة صورة')
                await page.locator('#profile-photo-save').click()
                await expect(page.locator('img.file-portrait')).to_be_visible()
                await page.screenshot(path=str(OUT/f'file-{width}-day.png'),full_page=True)
                await page.locator('#theme').click()
                await page.screenshot(path=str(OUT/f'file-{width}-night.png'),full_page=True)
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                await page.locator('#open-profile-photo').click()
                await page.locator('#profile-photo-remove [name="reason"]').fill('طلب الأسرة')
                await page.locator('#profile-photo-remove [name="confirm"]').check()
                await page.get_by_role('button',name='حذف الصورة',exact=True).click()
                await expect(page.get_by_role('img',name='لم تضف صورة للطالب',exact=True)).to_be_visible()
                await page.get_by_text('✏️ تعديل بيانات الطالب',exact=True).click()
                await expect(page.locator('#profile-edit-dialog')).to_be_visible()
                await page.locator('#profile-edit-child [name="address"]').fill('عنوان مسودة')
                await page.keyboard.press('Escape')
                await expect(page.locator('.discard-box')).to_be_visible()
                await page.get_by_role('button',name='متابعة التعديل',exact=True).click()
                await expect(page.locator('#profile-edit-child [name="address"]')).to_have_value('عنوان مسودة')
                await page.locator('#profile-edit-close').click()
                await page.get_by_role('button',name='تجاهل التغييرات والخروج',exact=True).click()
                await page.locator('#open-profile-edit').click()
                await expect(page.locator('#profile-edit-child [name="address"]')).not_to_have_value('عنوان مسودة')
                await page.locator('#profile-edit-child [name="address"]').fill('العنوان الجديد')
                await page.locator('#profile-edit-child [name="health"]').fill('<b>ملاحظة الأسرة</b>')
                await page.locator('#profile-edit-child button').click()
                await expect(page.get_by_text('العنوان الجديد',exact=True)).to_be_visible()
                await expect(page.locator('.file-details').get_by_text('<b>ملاحظة الأسرة</b>',exact=True)).to_be_visible()
                assert await page.locator('.file-details b').count()==0
                # Intake with an optional image; removal above did not remove child.
                await page.locator('#back-students').click();await page.locator('#add-student').click()
                await page.locator('#student-form [name="name"]').fill('طفل صورة جديد')
                await page.locator('#student-form [name="mother"]').fill('أم الطفل')
                await page.locator('#student-form [name="motherPhone"]').fill('22334455')
                await page.get_by_text('📷 صورة الطالب (اختياري)',exact=True).click()
                await page.locator('#student-form [name="photo"]').set_input_files(photo)
                await expect(page.locator('#intake-photo-preview img')).to_be_visible()
                await page.get_by_role('button',name='حفظ بيانات الطفل والأهل',exact=True).click()
                await page.locator('#student-search').fill('طفل صورة جديد')
                await page.get_by_role('button',name='فتح الملف ←',exact=True).click()
                await expect(page.locator('img.file-portrait')).to_be_visible()
                assert not errors,errors
                await page.close()
            await browser.close()
        print('Synthetic student file and photo add/remove/edit/intake passed at 390/1280 day/night')
    finally: server.shutdown()


if __name__=='__main__': asyncio.run(run())
