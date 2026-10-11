"""QA-only Playwright coverage + same-data before/after visual evidence."""
import asyncio
import json
import os
import re
from pathlib import Path

import psycopg2
from playwright.async_api import async_playwright, expect

OUT = Path("visual-evidence")
BASES = {"before-b99d9ac": "http://127.0.0.1:8502",
         "after-fixes": "http://127.0.0.1:8501"}
SIZES = [360, 390, 430, 768, 1280]


def query_one(sql, params=()):
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"]) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]


def seed():
    with psycopg2.connect(os.environ["TEST_POSTGRES_DSN"]) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO parents(father_id, father_name, father_mobile,
                                    mother_name, mother_mobile)
                VALUES ('QA_REVIEW_FAMILY_01', 'أب عينة واجهة', '0500001111',
                        'أم عينة واجهة', '0599001111')
                ON CONFLICT (father_id) DO NOTHING
            """)
            for sid, name in [("QA_REVIEW_CHILD_01", "طفل واجهة الأول"),
                              ("QA_REVIEW_CHILD_02", "طفل واجهة الثاني")]:
                cur.execute("""
                    INSERT INTO students(student_id, full_name, birth_date, gender,
                                         father_id, has_medical_condition)
                    VALUES (%s, %s, '2022-05-02', 'ذكر', 'QA_REVIEW_FAMILY_01', 1)
                    ON CONFLICT (student_id) DO NOTHING
                """, (sid, name))


async def navigate(page, section):
    nav = page.locator(f".st-key-nav_{section} button")
    # stApp mounts before Streamlit has finished rendering navigation;
    # avoid treating a still-loading 1280px page as a missing opener.
    await nav.wait_for(state="attached", timeout=30000)
    if not await nav.is_visible():
        opener = page.locator('[data-testid="stExpandSidebarButton"]')
        await opener.first.click(timeout=10000)
    await nav.click(timeout=10000)
    heading = "إدارة الطلاب" if section == "students" else "أولياء الأمور"
    await expect(page.locator(".section-title")).to_contain_text(heading, timeout=15000)


async def sidebar_state(page, opened):
    nav = page.locator(".st-key-nav_students button")
    if opened and not await nav.is_visible():
        await page.locator('[data-testid="stExpandSidebarButton"]').first.click(timeout=10000)
    if not opened and await nav.is_visible():
        button = page.locator('[data-testid="stSidebarCollapseButton"] button')
        await button.first.click(timeout=10000)
    await page.wait_for_timeout(220)


async def night_mode(page, desired):
    toggle = page.locator(".st-key-night_mode [role='switch']").first
    await expect(toggle).to_be_visible(timeout=10000)
    current = await toggle.is_checked()
    if current != desired:
        # React Aria renders a visible label over its checkbox input.
        # Click what the user taps; never bypass browser hit-testing.
        await page.locator(".st-key-night_mode label").last.click()
        if desired:
            await expect(toggle).to_be_checked()
        else:
            await expect(toggle).not_to_be_checked()
    await page.wait_for_timeout(250)


async def visualize(browser):
    results = []
    for width in SIZES:
        for version, base in BASES.items():
            context = await browser.new_context(viewport={"width": width, "height": 850},
                                                device_scale_factor=1)
            page = await context.new_page()
            await page.goto(base, wait_until="domcontentloaded")
            await page.locator(".stApp").wait_for(timeout=30000)
            for section in ("students", "parents"):
                await navigate(page, section)
                # Mobile drawer overlays the appearance switch while open.
                await sidebar_state(page, False)
                for dark in (False, True):
                    await night_mode(page, dark)
                    for expanded in (True, False):
                        await sidebar_state(page, expanded)
                        await page.wait_for_timeout(350)
                        slug = (f"{version}_{section}_{width}_" +
                                ("night" if dark else "day") + "_" +
                                ("open" if expanded else "closed"))
                        await page.screenshot(path=str(OUT / (slug + ".png")),
                                              full_page=True, animations="disabled")
                        metrics = await page.evaluate("""() => {
                            const html = document.documentElement;
                            const aside = document.querySelector('[data-testid="stSidebar"]');
                            const descendants = aside ?
                                [...aside.querySelectorAll('*')].filter(e => {
                                    const s = getComputedStyle(e), r = e.getBoundingClientRect();
                                    return s.visibility !== 'hidden' &&
                                      s.display !== 'none' && r.width > 0 && r.height > 0 &&
                                      r.right > 0 && r.left < innerWidth;
                                }).length : -1;
                            return {viewport: innerWidth, scrollWidth: html.scrollWidth,
                                    sidebarVisibleDescendants: descendants,
                                    sidebarVisibility: aside ? getComputedStyle(aside).visibility : null};
                        }""")
                        results.append({"image": slug + ".png", **metrics})
                        # This only checks text widgets; screenshots must be reviewed too.
                        values = await page.locator('input[type="text"],textarea').evaluate_all(
                            "(nodes) => nodes.map(e=>e.value)")
                        assert all(v.strip().lower() not in ("nan", "none", "<na>")
                                   for v in values), slug + " displayed invalid null"
            await context.close()
    (OUT / "measurements.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False))
    print(f"Visual evidence: {len(results)} comparable screenshots")
    overflow = [x["image"] for x in results if x["scrollWidth"] > x["viewport"] + 3]
    if overflow:
        print("Recorded viewport overflow for manual review: " + ", ".join(overflow))
    # Deliberately do not call screenshots visually approved in this script.


async def verify_double_submit_and_sibling(browser):
    context = await browser.new_context(viewport={"width": 390, "height": 850})
    page = await context.new_page()
    await page.goto(BASES["after-fixes"], wait_until="domcontentloaded")
    await navigate(page, "students")
    # On mobile, the deliberately open sidebar is an overlay; close it before
    # interacting with the form, as a user would.
    await sidebar_state(page, False)
    initial_children = query_one("SELECT COUNT(*) FROM students")
    initial_parents = query_one("SELECT COUNT(*) FROM parents")
    await page.locator(".st-key-kid_name input").fill("طفل كروميوم اختبار مكرر")
    await page.locator(".st-key-kid_mother_name input").fill("أم كروميوم اختبار")
    await page.locator(".st-key-kid_mother_phone input").fill("0599444455")
    button = page.get_by_role("button", name=re.compile("حفظ بيانات الطفل والأهل"))
    # The original bug reproduced when the user clicked again after rerender.
    await button.click()
    new_name = page.locator(".st-key-kid_name_v1 input")
    await expect(new_name).to_be_visible(timeout=15000)
    await expect(new_name).to_have_value("")
    await expect(page.get_by_text("تم حفظ الطفل والأهل بنجاح", exact=False)).to_be_visible()
    await expect(page.locator(".st-key-kid_mother_name_v1 input")).to_have_value("")
    assert query_one("SELECT COUNT(*) FROM students") == initial_children + 1
    assert query_one("SELECT COUNT(*) FROM parents") == initial_parents + 1

    # Empty new form must not resubmit old data, even on repeated clicks.
    button = page.get_by_role("button", name=re.compile("حفظ بيانات الطفل والأهل"))
    await button.click()
    await button.click()
    await page.wait_for_timeout(400)
    assert query_one("SELECT COUNT(*) FROM students") == initial_children + 1
    assert query_one("SELECT COUNT(*) FROM parents") == initial_parents + 1
    await expect(new_name).to_have_value("")

    # Starting a genuine new child, toggling existing family, and saving a sibling.
    await new_name.fill("أخ كروميوم جديد")
    checkbox = page.locator(".st-key-kid_use_existing_v1 label").first
    await checkbox.click()
    await expect(new_name).to_have_value("أخ كروميوم جديد")
    await page.get_by_role("button", name=re.compile("حفظ بيانات الطفل والأهل")).click()
    await expect(page.locator(".st-key-kid_name_v2 input")).to_be_visible(timeout=15000)
    assert query_one("SELECT COUNT(*) FROM students") == initial_children + 2
    assert query_one("SELECT COUNT(*) FROM parents") == initial_parents + 1
    assert query_one("""SELECT COUNT(*) FROM students s
        JOIN parents p ON s.father_id=p.father_id
        WHERE s.full_name='أخ كروميوم جديد'""") == 1
    await context.close()
    print("Chromium 390 form reset, duplicate click, validation and sibling checks passed")


async def main():
    OUT.mkdir(exist_ok=True)
    seed()
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        await verify_double_submit_and_sibling(browser)
        await visualize(browser)
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
