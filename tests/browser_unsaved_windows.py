"""Real dialog lifecycle regression, without login or business writes.

Run standalone against the actual source helpers, or pass a live origin to
exercise the shipped helpers in an anonymous browser context.
"""
import asyncio
from pathlib import Path
import sys
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


async def main(origin=None):
    cases = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for lang, width in [('ar', 390), ('fr', 1360), ('ar', 1360), ('fr', 390)]:
            context = await browser.new_context(ignore_https_errors=True, viewport=dict(width=width, height=900))
            page = await context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            if origin:
                await page.goto(origin, wait_until='networkidle')
                if lang == 'fr':
                    await page.locator('[data-language=fr]').click()
                    await page.wait_for_load_state('networkidle')
            else:
                await page.set_content('<html><body><dialog id="record-dialog"><div id="record-content"></div></dialog></body></html>')
                await page.evaluate("window.$=s=>document.querySelector(s);window.esc=s=>String(s);window.I18N={tr:s=>s};window.render=()=>{};")
                helpers = (ROOT/'docs/edit-windows.js').read_text().split('const windowProfile=profile;')[0]
                opening = (ROOT/'live/workspace.js').read_text().split('function openProtected(title,body){', 1)[1].split('function confirmation()', 1)[0]
                await page.add_script_tag(content=helpers+'\nfunction openProtected(title,body){'+opening)
            async def open_form():
                await page.evaluate("openProtected('Synthetic edit','<form><input name=probe value=original></form>')")
            async def close_clean():
                await page.locator('#workspace-close').click()
                await expect(page.locator('#record-dialog')).not_to_be_visible()
            def passed(name):
                cases.append(f'{lang}-{width}:{name}')

            await open_form()
            await expect(page.locator('.discard-box')).to_have_count(0)
            await close_clean()
            passed('untouched_form_closes_without_warning')

            await open_form()
            await page.locator('[name=probe]').fill('changed')
            await expect(page.locator('.discard-box')).to_have_count(0)
            await page.locator('#workspace-close').click()
            await expect(page.locator('.discard-box')).to_be_visible()
            await page.locator('[data-discard]').click()
            await expect(page.locator('#record-dialog')).not_to_be_visible()
            await page.evaluate("openProtected('Synthetic read-only summary','<p>No editable fields</p>')")
            await expect(page.locator('#record-dialog input, #record-dialog select, #record-dialog textarea')).to_have_count(0)
            await expect(page.locator('.discard-box')).to_have_count(0)
            await close_clean()
            passed('discard_then_readonly_reopen_has_no_stale_warning')

            await open_form()
            await page.locator('[name=probe]').fill('changed')
            await page.keyboard.press('Escape')
            await expect(page.locator('.discard-box')).to_be_visible()
            await page.locator('[data-keep]').click()
            await expect(page.locator('[name=probe]')).to_have_value('changed')
            await expect(page.locator('.discard-box')).to_have_count(0)
            await page.locator('#workspace-close').click()
            await expect(page.locator('.discard-box')).to_have_count(1)
            await page.locator('[data-keep]').click()
            await page.locator('[name=probe]').fill('original')
            await close_clean()
            passed('keep_editing_and_escape_preserve_real_unsaved_protection')

            await open_form()
            await page.locator('[name=probe]').fill('changed')
            await page.locator('#workspace-close').click()
            await expect(page.locator('.discard-box')).to_be_visible()
            await page.evaluate("document.querySelector('#record-dialog').close()")
            await page.evaluate("openProtected('Synthetic next window','<p>Read only</p>')")
            await expect(page.locator('.discard-box')).to_have_count(0)
            await close_clean()
            passed('external_programmatic_close_does_not_leak_warning')
            await open_form()
            late_close = await page.evaluate("""async () => {
                const d=document.querySelector('#record-dialog');
                const closed=new Promise(resolve=>d.addEventListener('close',resolve,{once:true}));
                d.close();
                openProtected('Synthetic reopened edit','<form><input name=probe value=original></form>');
                d.querySelector('[name=probe]').value='changed';
                d.querySelector('#workspace-close').click();
                await closed;
                return {open:d.open, warning:!!d.querySelector('.discard-box')};
            }""")
            assert late_close == {'open': True, 'warning': True}, late_close
            await page.locator('[data-keep]').click()
            await page.locator('[name=probe]').fill('original')
            await close_clean()
            passed('late_native_close_event_preserves_reopened_dirty_warning')
            assert not errors, errors
            await context.close()
        await browser.close()
    print({'passed': len(cases), 'business_writes': 0, 'cases': cases})


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
