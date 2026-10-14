"""Exercise only the synthetic Pages preview; serve only its public docs folder."""
import asyncio
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import threading

from playwright.async_api import async_playwright, expect

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"visual-evidence"/"operator-preview"


async def run():
    OUT.mkdir(parents=True,exist_ok=True)
    server=ThreadingHTTPServer(("127.0.0.1",0),
        partial(SimpleHTTPRequestHandler,directory=str(ROOT/"docs")))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    url=f"http://127.0.0.1:{server.server_port}"
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(headless=True)
            for width in (390,768,1280):
                page=await browser.new_page(viewport={"width":width,"height":900})
                await page.goto(url)
                await expect(page.get_by_role("heading",name="روضة أطفال فودي حبيب ساكرا",exact=True)).to_be_visible()
                await page.screenshot(path=str(OUT/f"login_{width}.png"),full_page=True)
                await page.locator("#preview-enter").click()
                assert await page.locator(".home-shortcut.primary").count() == 0
                await expect(page.get_by_role("heading",name="الرئيسية",exact=True)).to_be_visible()
                await page.screenshot(path=str(OUT/f"dashboard_{width}_day.png"),full_page=True)
                await page.locator("#theme").click()
                await page.screenshot(path=str(OUT/f"dashboard_{width}_night.png"),full_page=True)
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
                await page.locator("#theme").click()
                await page.locator("#home-student").click()
                await page.get_by_label("اسم الطفل *",exact=True).fill("طفل معاينة")
                await page.get_by_label("اسم الأم",exact=True).fill("أم معاينة")
                await page.get_by_label("هاتف الأم",exact=True).fill("00000007")
                await page.get_by_role("button",name="حفظ بيانات الطفل والأهل",exact=True).click()
                await page.locator("#student-search").fill("طفل معاينة")
                await page.get_by_role("button",name="فتح الملف ←",exact=True).click()
                await expect(page.get_by_role("button",name="فتح الوصل")).to_have_count(0)
                await expect(page.get_by_label("المبلغ المدفوع (أوقية قديمة)")).to_have_count(0)
                await page.screenshot(path=str(OUT/f"student_profile_{width}.png"),full_page=True)
                await page.locator("#profile-pay").click()
                await page.locator("#pay-amount").fill("1500")
                await page.locator("#payment-preview-button").click()
                await page.locator("#pay-agree").check()
                await page.locator("#pay-save").click()
                await expect(page.locator("#receipt-dialog")).not_to_be_visible()
                await expect(page.locator("#toast")).to_contain_text("تم تسجيل الدفعة")
                await page.screenshot(path=str(OUT/f"payment_{width}.png"),full_page=True)
                await page.locator('[data-finance="receipts"]').click()
                await page.get_by_role("button",name="فتح الوصل",exact=True).first.click()
                await expect(page.locator("#receipt-dialog")).to_be_visible()
                await page.locator("#receipt-close").click()
                if width<=768:
                    await page.locator("#menu").click()
                await page.locator('nav [data-page="expenses"]').click()
                await page.locator("#exp-amount").fill("5000")
                await expect(page.locator("#partial-field")).not_to_be_visible()
                await page.locator("#expense-status").select_option("partial")
                await expect(page.locator("#partial-field")).to_be_visible()
                await page.locator("#exp-paid").fill("2000")
                await page.get_by_label("المستلم / المورد (اختياري)",exact=True).fill("مورد معاينة")
                await page.get_by_role("button",name="حفظ المصروف",exact=True).click()
                await expect(page.locator("#toast")).to_contain_text("تم تسجيل المصروف")
                await page.screenshot(path=str(OUT/f"expense_{width}.png"),full_page=True)
                assert await page.evaluate("document.documentElement.scrollWidth <= innerWidth+1")
                await page.close()
            await browser.close()
    finally:
        server.shutdown()


if __name__=="__main__":
    asyncio.run(run())
