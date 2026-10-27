"""Equal-duration comparison shares the report snapshot and export protection."""
from datetime import date, timedelta
from io import BytesIO

from openpyxl import load_workbook
import expense_finance as E
import monthly_finance as F
from tests.test_access_control import access
from tests.test_live_pages_http import browser, post
from tests.test_period_reports import setup_cash, report


def test_previous_equal_length_totals_and_comparison_export(browser):
    client,conn,session,start,previous,*_=setup_cash(browser)
    current=report(client,session)
    old=current['comparison']
    assert old['end']==str(start-timedelta(days=1))
    assert old['start']==str(start-(F.today()-start)-timedelta(days=1))
    assert old['summary']==dict(income=500,outgoing=1000,net=-500)
    assert old['new_count']==0 and old['attendance']['attendance_rate'] is None
    exported=post(client,session,'reports.finance.export',dict(start=str(start),end=str(F.today()),revision=current['revision']))
    assert exported.status_code==200,exported.text
    sheet=load_workbook(BytesIO(exported.content))['مقارنة الفترتين']
    assert list(sheet.values)[3][1:]==(6000,500,5500)
    leap=report(client,session,date(2024,3,1),date(2024,3,1))
    assert leap['comparison']['start']==leap['comparison']['end']=='2024-02-29'


def test_correction_in_previous_period_invalidates_current_export(browser):
    client,conn,session,start,previous,*_=setup_cash(browser)
    current=report(client,session)
    E.create(category='Previous period correction',amount_total=20,amount_paid=20,expense_date=previous)
    updated=report(client,session)
    assert all(updated['summary'][key]==current['summary'][key] for key in ('income','outgoing','net'))
    assert updated['summary']['opening']==current['summary']['opening']-20
    assert updated['summary']['closing']==current['summary']['closing']-20
    assert updated['comparison']['summary']['outgoing']==1020
    assert updated['revision']!=current['revision']
    stale=post(client,session,'reports.finance.export',dict(start=str(start),end=str(F.today()),revision=current['revision']))
    assert stale.status_code==422
