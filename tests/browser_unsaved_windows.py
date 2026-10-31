"""Real dialog lifecycle regression, without login or business writes.

Run standalone against the actual source helpers, or pass a live origin to
exercise the shipped helpers in an anonymous browser context.
"""
import asyncio
from pathlib import Path
import sys
import os
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]


async def main(origin=None):
    cases = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel='chrome' if sys.platform=='win32' else None)
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
                await page.set_content(f'<html lang="{lang}" dir="'+('rtl' if lang=='ar' else 'ltr')+'"><body><dialog id="record-dialog"><div id="record-content"></div></dialog></body></html>')
                await page.evaluate("lang=>{window.$=s=>document.querySelector(s);window.esc=s=>String(s);window.I18N={lang,tr:s=>s,date:s=>s};window.render=()=>{};}",lang)
                helper_path=Path(os.environ.get('KG_UNSAVED_HELPER_OVERRIDE',str(ROOT/'docs/edit-windows.js')))
                helpers = helper_path.read_text(encoding='utf-8').split('const windowProfile=profile;')[0]
                opening = (ROOT/'live/workspace.js').read_text(encoding='utf-8').split('function openProtected(title,body){', 1)[1].split('function confirmation()', 1)[0]
                await page.add_script_tag(content=helpers+'\nfunction openProtected(title,body){'+opening)
                await page.add_script_tag(content=(ROOT/'docs/date-entry.js').read_text(encoding='utf-8'))
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
            assert await page.evaluate("()=>{const e=new Event('beforeunload',{cancelable:true});window.dispatchEvent(e);return e.defaultPrevented;}")
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

            # Real component initialization must not change the protected signature.
            await page.evaluate("openProtected('Synthetic fields','<form><input name=day type=date value=2026-10-15><input name=agree type=checkbox><input name=photo type=file></form>')")
            await expect(page.locator('[data-date-part=day]')).to_have_value('15')
            await expect(page.locator('.discard-box')).to_have_count(0)
            await close_clean()
            passed('date_and_file_initialization_are_not_dirty')

            await page.evaluate("openProtected('Synthetic dates','<form><input name=day type=date value=2026-10-15></form>')")
            await expect(page.locator('[data-date-part=day]')).to_have_value('15')
            await page.locator('[data-date-part=day]').fill('')
            # Finish blur validation before aiming at a close button: revealing
            # the date error can recenter a native dialog between pointer events.
            await page.locator('[data-date-part=day]').evaluate('(input)=>input.blur()')
            await expect(page.locator('.date-entry-error')).to_be_visible()
            dirty_date=await page.evaluate("()=>{const d=$('#record-dialog');return {initial:d._initialSignature,current:formSignature(d),open:d.open,lang:I18N.lang};}")
            assert dirty_date['initial']!=dirty_date['current'],dirty_date
            await page.locator('#workspace-close').click()
            date_exit=await page.evaluate("()=>{const d=$('#record-dialog'),e=d.querySelector('[name=day]');return {open:d.open,warning:!!d.querySelector('.discard-box'),initial:d._initialSignature,current:formSignature(d),draft:e?.dataset.dateDraft,value:e?.value,lang:I18N.lang};}")
            assert date_exit['warning'],date_exit
            await expect(page.locator('.discard-box')).to_have_count(1)
            await page.locator('[data-keep]').click()
            await page.locator('[data-date-part=day]').fill('15')
            await close_clean()
            passed('unfinished_date_is_dirty_and_restored_date_is_clean')

            await page.evaluate("openProtected('Synthetic file','<form><input name=agree type=checkbox><input name=photo type=file></form>')")
            await page.locator('[name=agree]').check()
            await page.locator('#workspace-close').click()
            await expect(page.locator('.discard-box')).to_have_count(1)
            await page.locator('[data-keep]').click()
            await page.locator('[name=agree]').uncheck()
            await page.locator('[name=photo]').set_input_files(dict(name='synthetic.png',mimeType='image/png',buffer=b'synthetic test file'))
            await page.keyboard.press('Escape');await expect(page.locator('.discard-box')).to_have_count(1)
            await page.locator('[data-keep]').click();await page.locator('[name=photo]').set_input_files([])
            await close_clean()
            passed('checkbox_and_file_changes_are_protected_and_reversible')

            # A coordinate click outside the box uses the actual dialog backdrop.
            await open_form();await page.locator('[name=probe]').fill('backdrop change')
            await page.mouse.click(2,2);await expect(page.locator('.discard-box')).to_have_count(1)
            await page.locator('[data-discard]').click();await expect(page.locator('#record-dialog')).not_to_be_visible()
            passed('backdrop_exit_protects_dirty_form')

            preservation=await page.evaluate("""async()=>{
                const d=document.createElement('dialog');d.innerHTML='<button id=synthetic-close>Close</button>';document.body.append(d);
                let ownerCalls=0,added=0;d.onclose=()=>ownerCalls++;
                const add=d.addEventListener.bind(d);d.addEventListener=(type,...args)=>{if(type==='close')added++;return add(type,...args);};
                for(let n=0;n<5;n++)protectEditWindow(d,['synthetic-close']);
                d.showModal();const closed=new Promise(resolve=>add('close',resolve,{once:true}));d.querySelector('button').click();await closed;
                const result={ownerCalls,added};d.remove();return result;
            }""")
            assert preservation['ownerCalls']==1 and preservation['added']<=1,preservation
            passed('owner_close_handler_preserved_without_stacked_listeners')
            assert not errors, errors
            await context.close()
        await browser.close()
    print({'passed': len(cases), 'business_writes': 0, 'cases': cases})


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else None))
