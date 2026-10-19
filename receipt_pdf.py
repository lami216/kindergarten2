"""Local, Arabic-shaped PDF export for the exact stored receipt version.

IBM Plex Sans Arabic Regular is bundled under the SIL Open Font License.
Neither HTML printing nor external URLs are involved; the function reads only.
"""
from io import BytesIO
from pathlib import Path
import re
from zoneinfo import ZoneInfo

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from receipt_history import receipt_detail, receipt_line
import localization as L

FONT_PATH=Path(__file__).resolve().parent/"assets"/"IBMPlexSansArabic-Regular.ttf"
FONT_NAME="PlexArabicEmbedded"
INK=colors.HexColor("#18392D")
MUTED=colors.HexColor("#586C62")


def _rtl(text):
    return get_display(arabic_reshaper.reshape(str(text)),base_dir="R")


def _print(c,x,y,text,*,size=11,color=INK):
    c.setFillColor(color)
    c.setFont(FONT_NAME,size)
    if L.language()=='fr':
        visual=get_display(arabic_reshaper.reshape(str(text)),base_dir='L')
        position=45+(A4[0]-45-x)
        # Keep each direction in its own PDF text object. Older PDF readers
        # otherwise discard Latin text when a mixed-script name switches to RTL.
        # Positions use the same shaped visual string; the printed line is unchanged.
        for run in re.split(r'([\u0590-\u08ff\ufb1d-\ufdff\ufe70-\ufeff]+)',visual):
            if run:
                c.drawString(position,y,run)
                position+=pdfmetrics.stringWidth(run,FONT_NAME,size)
    else:
        c.drawRightString(x,y,_rtl(text))


def _wrapped(text, width, size):
    """Keep longer French labels and entered reasons inside the printable area."""
    line = ''
    for char in str(text):
        candidate = line + char
        if char == '\n' or (line and pdfmetrics.stringWidth(candidate,FONT_NAME,size)>width):
            yield line
            line = '' if char == '\n' else char
        else:
            line = candidate
    if line:
        yield line


def render_receipt_pdf(conn, receipt_id, *, student_id=None, locale='ar'):
    with L.using_language(locale):
        return _render_receipt_pdf(conn,receipt_id,student_id=student_id)


def _render_receipt_pdf(conn, receipt_id, *, student_id=None):
    """Return valid PDF bytes; no write, no side-effectful projection."""
    if not FONT_PATH.is_file():
        raise RuntimeError("الخط العربي المحلي المطلوب لتصدير الوصل غير متاح.")
    data=receipt_detail(conn,receipt_id,student_id=student_id)
    r=data["receipt"]
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME,str(FONT_PATH)))
    buf=BytesIO()
    c=Canvas(buf,pagesize=A4,pageCompression=1)
    c.setTitle(L.message(f"وصل روضة #{int(r['receipt_id'])}"))
    c.setAuthor(L.label("إدارة الروضة"))
    w,h=A4
    left,right=45,w-45
    state=("ملغى" if r["state"]!="active" else
           "مصحح لوصل سابق" if r["corrects_id"] else "ساري")
    c.setFillColor(colors.HexColor("#E4F1E9"))
    c.rect(0,h-112,w,112,stroke=0,fill=1)
    _print(c,right,h-55,L.label("روضة أطفال فودي حبيب ساكرا"),size=17 if L.language()=="fr" else 21)
    _print(c,right,h-82,L.message(f"وصل قبض رقم #{int(r['receipt_id'])}"),size=14)
    if r["state"]!="active":
        c.saveState()
        c.translate(w/2,h/2)
        c.rotate(35)
        c.setFillColor(colors.HexColor("#F1D0D0"))
        watermark=get_display(arabic_reshaper.reshape(L.label("ملغى — غير صالح للتحصيل")),base_dir="L" if L.language()=="fr" else "R")
        c.setFont(FONT_NAME,min(54,(w-90)/pdfmetrics.stringWidth(watermark,FONT_NAME,1)))
        c.drawCentredString(0,0,watermark)
        c.restoreState()
    y=h-142
    def line(label,value,*,font_size=11):
        nonlocal y
        for part in _wrapped(f"{L.label(label)}: {value}",right-left,font_size):
            if y<108:
                c.showPage()
                y=h-66
            _print(c,right,y,part,size=font_size)
            y-=20
        y-=6
    line("حالة الوصل",L.label(state))
    line("اسم الطفل",r["student_name"])
    line("الدافع",r["payer"] or L.label("غير مسجل"))
    line("تاريخ القبض الأصلي",str(r["received_on"]))
    line("المبلغ",(f"{L.number(int(r['amount']))} MRO" if L.language()=="fr" else f"{int(r['amount']):,} أوقية قديمة"),font_size=14)
    if r["corrects_id"]:
        line("تصحيح لوصل",f"#{int(r['corrects_id'])}")
    if data["replacements"]:
        line("الوصل البديل",", ".join("#"+str(v["receipt_id"]) for v in data["replacements"]))
    if r["state"]!="active":
        line("سبب إلغاء / تصحيح الوصل",r["cancel_reason"] or L.label("غير متوفر"))
        line("المسؤول",r["cancelled_by"] or L.label("غير مسجل"))
        stamp=r["cancelled_at"]
        if stamp is not None:
            line("تاريخ القرار",stamp.astimezone(ZoneInfo("Africa/Nouakchott")).strftime("%Y-%m-%d %H:%M"))
    if any(item.get('snapshot_source')=='legacy_at_migration' for item in data['items']):
        line('توثيق التفاصيل',L.label('ثُبتت البيانات المتاحة عند تحديث سجل الوصولات'),font_size=8)
    y-=12
    c.setStrokeColor(colors.HexColor("#C3D7CE"))
    c.line(left,y,right,y)
    y-=31
    _print(c,right,y,L.label("تفصيل توزيع الدفعة الأصلية"),size=14)
    y-=29
    for index,item in enumerate(data["items"],1):
        if y<108:
            c.showPage()
            y=h-66
            _print(c,right,y,L.label("تابع تفصيل الوصل"),size=14)
            y-=38
        title=L.message(receipt_line(item))
        amt=f"{L.number(int(item['amount']))} "+("MRO" if L.language()=="fr" else "أوقية قديمة")
        # Split descriptive rows to avoid text clipping with long dates.
        _print(c,right,y,f"{index}. {title}",size=10)
        y-=19
        _print(c,right-9,y,amt,size=10,color=MUTED)
        y-=31
    if y<98:
        c.showPage()
        y=h-75
    c.setStrokeColor(colors.HexColor("#B9CCC2"))
    c.line(left,y+12,right,y+12)
    _print(c,right,y-15,L.message(f"الإجمالي: {L.number(int(r['amount']))} أوقية قديمة"),size=13)
    c.setFont(FONT_NAME,9)
    _print(c,right,52,L.label("نسخة من السجل المالي المحفوظ — لا تغيّر المدفوعات أو مديونية الطفل"),size=7 if L.language()=="fr" else 9,color=MUTED)
    c.save()
    return buf.getvalue()
