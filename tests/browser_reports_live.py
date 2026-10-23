"""Real TLS service/PostgreSQL: report cards, cash settlement and downloaded XLSX."""
import asyncio
from datetime import date, timedelta
import json
import os
from pathlib import Path
import sys
import uuid

from openpyxl import load_workbook
from playwright.async_api import async_playwright, expect


async def main(origin, username, password):
    out = Path(__file__).resolve().parents[1] / 'visual-evidence' / 'reports-live'
    out.mkdir(parents=True, exist_ok=True)
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True, channel='chrome' if sys.platform == 'win32' else None)
        page = await browser.new_page(ignore_https_errors=True, viewport={'width': 1360, 'height': 1000})
        page.on('pageerror', lambda e: errors.append(str(e)))
        try:
            await page.goto(origin, wait_until='networkidle')
            await page.locator('[data-language="fr"]').click()
            await page.locator('#live-login [name="username"]').fill(username)
            await page.locator('#live-login [name="password"]').fill(password)
            await page.locator('#preview-enter').click()
            await expect(page.locator('#preview-login')).to_be_hidden()
            async def api(op, data=None):
                return await page.evaluate('async({op,data})=>liveCall(op,data===null?undefined:data)', dict(op=op, data=data))
            snapshot = await api('snapshot')
            today = date.fromisoformat(snapshot['today']);start = today.replace(day=1)
            previous = start - timedelta(days=1)
            before = await api('reports.finance', dict(start=str(start), end=str(today)))
            department = await api('departments.create', dict(name='Reports QA ' + uuid.uuid4().hex[:8]))
            prices = snapshot['prices'];cash = sum(prices[k] for k in ('registration', 'gilet', 'tuition'))
            await api('students.create', dict(name='Élève rapports QA', birth='2022-01-01', gender='ذكر',
                mother='Mère QA', motherPhone='22334455', department_id=department['id'], mode='pay',
                registration=True, gilet=True, amount=str(cash), request_token=str(uuid.uuid4())))
            expense = await api('expenses.create', dict(category='=1+1 (live-report-QA)', amount='1200', paid='1000',
                date=str(previous), payee='Fournisseur QA', request_token=str(uuid.uuid4())))
            state = await api('snapshot');entry = next(e for e in state['expenses'] if e['id'] == expense['id'])
            await api('expenses.settle', dict(id=expense['id'], amount='200', date=str(today), reason='Solde payé ce jour',
                revision=entry['revision'], confirmed=True, request_token=str(uuid.uuid4())))
            await page.evaluate('async()=>{await liveLoad();render()}')
            await page.locator('#nav-reports').click()
            await page.locator('#finance-report-form button.primary').click()
            await page.wait_for_function('()=>financeData!==null')
            result = await page.evaluate('financeData')
            assert result['summary']['income'] == before['summary']['income'] + cash
            assert result['summary']['outgoing'] == before['summary']['outgoing'] + 200
            assert sum(r['amount'] for r in result['items'] if r['category'] != 'income') == result['summary']['outgoing']
            await page.locator('#fin-query').fill('live-report-QA')
            await expect(page.locator('.fin-screen-table tbody tr')).to_have_count(1)
            async with page.expect_download() as info:
                await page.locator('#fin-xlsx').click()
            downloaded = await info.value;path = out / 'report-fr.xlsx'
            await downloaded.save_as(path)
            sheet = load_workbook(path).worksheets[1]
            assert sheet['C2'].value == '=1+1 (live-report-QA)' and sheet['C2'].data_type == 's'
            assert sheet['F2'].value == 200
            await page.screenshot(path=str(out / 'report-fr.png'), full_page=True)
            assert not errors, errors
            print('LIVE_REPORTS_OK: saved cash dates, totals, scoped rows and real XLSX')
        finally:
            await browser.close()


if __name__ == '__main__':
    state=json.loads((Path(os.environ['KG_LIVE_QA_DIR'])/'state.json').read_text())
    from tests.qa_live_pages import guard
    guard(state['dsn'])
    asyncio.run(main(state['origin'],state['username'],state['password']))
