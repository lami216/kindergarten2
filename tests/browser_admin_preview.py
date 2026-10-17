"""Synthetic Pages manager/worker flow, distinct from real backend tests."""
import asyncio
import json
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from playwright.async_api import async_playwright,expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'visual-evidence/admin-preview'


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(('127.0.0.1',0),partial(SimpleHTTPRequestHandler,directory=str(ROOT/'docs')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    results=[]
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True,channel='chrome' if sys.platform=='win32' else None)
            for width in (390,1280):
                page=await browser.new_page(viewport={'width':width,'height':950})
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                await page.goto(f'http://127.0.0.1:{server.server_port}')
                await page.locator('#preview-enter').click()
                async def admin():
                    if width<769: await page.locator('#menu').click()
                    await page.locator('#nav-admin').click()
                async def logout():
                    if width<769: await page.locator('#menu').click()
                    await page.locator('#demo-logout').click()
                await admin()
                await page.locator('#demo-user-create [name="name"]').fill('عامل الروضة')
                await page.locator('#demo-user-create [name="username"]').fill('worker-test')
                await page.locator('#demo-user-create [name="password"]').fill('Strong-demo-password!')
                await page.locator('[value="students.create"]').check()
                await page.locator('[value="expenses.create"]').check()
                await page.locator('#demo-user-create button').click()
                await expect(page.locator('[data-demo-user]')).to_have_count(1)
                await page.screenshot(path=str(OUT/f'accounts-{width}.png'),full_page=True)
                await logout()
                await page.locator('.demo-worker-login summary').click()
                async def worker_login():
                    await page.locator('#demo-worker-login [name="username"]').fill('worker-test')
                    await page.locator('#demo-worker-login [name="password"]').fill('Strong-demo-password!')
                    await page.locator('#demo-worker-login button').click()
                await worker_login()
                await expect(page.locator('#preview-login')).not_to_be_visible()
                await expect(page.locator('#nav-admin')).not_to_be_visible()
                await expect(page.locator('nav [data-page="payments"]')).not_to_be_visible()
                if width<769: await page.locator('#menu').click()
                await page.locator('nav [data-page="students"]').click()
                await expect(page.locator('#student-form')).to_be_visible()
                await expect(page.locator('#student-rows')).to_have_count(0)
                await page.locator('#student-form [name="name"]').fill('طفل عامل الروضة')
                await page.locator('#student-form [name="mother"]').fill('أم الطفل')
                await page.locator('#student-form [name="motherPhone"]').fill('22223333')
                await page.locator('#student-form button').click()
                if width<769: await page.locator('#menu').click()
                await page.locator('nav [data-page="expenses"]').click()
                await page.locator('#expense-form [name="category"]').fill('قرطاسية العامل')
                await page.locator('#expense-form [name="amount"]').fill('1200')
                await expect(page.locator('#content table')).to_have_count(0)
                await page.locator('#expense-form button').click()
                await logout()
                await page.locator('#preview-enter').click();await admin()
                await page.locator('#demo-activity-user').select_option(label='عامل الروضة · worker-test')
                await expect(page.locator('#demo-activity-body')).to_contain_text('1,200')
                await page.screenshot(path=str(OUT/f'activity-{width}.png'),full_page=True)
                await page.locator('[data-demo-user]').click()
                await page.locator('#demo-account-edit [name="active"]').uncheck()
                await page.locator('#demo-account-edit button').click()
                await logout()
                if not await page.locator('#demo-worker-login [name="username"]').is_visible():
                    await page.locator('.demo-worker-login summary').click()
                await worker_login()
                await expect(page.locator('#demo-login-error')).to_contain_text('تعذّر الدخول')
                assert not errors,errors
                assert await page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
                results.append({'width':width,'created_and_measured':True,'scoped_worker':True,'disabled_rejected':True})
                await page.close()
            await browser.close()
    finally: server.shutdown()
    (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Synthetic manager/worker preview creation, grants, activity and disable passed 390/1280')


if __name__=='__main__': asyncio.run(run())
