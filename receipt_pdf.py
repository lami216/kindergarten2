"""Local, Arabic-shaped PDF export for the exact stored receipt version.

IBM Plex Sans Arabic Regular is bundled under the SIL Open Font License.
Neither HTML printing nor external URLs are involved; the function reads only.
"""
from io import BytesIO
from pathlib import Path
from zoneinfo import ZoneInfo

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen.canvas import Canvas

from receipt_history import receipt_detail, receipt_line

FONT_PATH=Path(__file__).resolve().parent/"assets"/"IBMPlexSansArabic-Regular.ttf"
FONT_NAME="PlexArabicEmbedded"
INK=colors.HexColor("#18392D")
MUTED=colors.HexColor("#586C62")


def _rtl(text):
    return get_display(arabic_reshaper.reshape(str(text)),base_dir="R")


def _print(c,x,y,text,*,size=11,color=INK):
    c.setFillColor(color)
    c.setFont(FONT_NAME,size)
    c.drawRightString(x,y,_rtl(text))


def render_receipt_pdf(conn, receipt_id, *, student_id=None):
    """Return valid PDF bytes; no write, no side-effectful projection."""
    if not FONT_PATH.is_file():
        raise RuntimeError("الخط العربي المحلي المطلوب لتصدير الوصل غير متاح.")
    data=receipt_detail(conn,receipt_id,student_id=student_id)
    r=data["receipt"]
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(TTFont(FONT_NAME,str(FONT_PATH)))
    buf=BytesIO()
    c=Canvas(buf,pagesize=A4,pageCompression=1)
    c.setTitle(f"وصل روضة #{int(r['receipt_id'])}")
    c.setAuthor("إدارة الروضة")
    w,h=A4
    left,right=45,w-45
    state=("ملغى" if r["state"]!="active" else
           "مصحح لوصل سابق" if r["corrects_id"] else "ساري")
    c.setFillColor(colors.HexColor("#E4F1E9"))
    c.rect(0,h-112,w,112,stroke=0,fill=1)
    _print(c,right,h-55,"روضة أطفال فودي حبيب ساكرا",size=21)
    _print(c,right,h-82,f"وصل قبض رقم #{int(r['receipt_id'])}",size=14)
    if r["state"]!="active":
        c.saveState()
        c.translate(w/2,h/2)
        c.rotate(35)
        c.setFillColor(colors.HexColor("#F1D0D0"))
        c.setFont(FONT_NAME,54)
        c.drawCentredString(0,0,_rtl("ملغى — غير صالح للتحصيل"))
        c.restoreState()
    y=h-142
    def line(label,value,*,font_size=11):
        nonlocal y
        _print(c,right,y,f"{label}: {value}",size=font_size)
        y-=26
    line("حالة الوصل",state)
    line("اسم الطفل",r["student_name"])
    line("الدافع",r["payer"] or "غير مسجل")
    line("تاريخ القبض الأصلي",str(r["received_on"]))
    line("المبلغ",f"{int(r['amount']):,} أوقية قديمة",font_size=14)
    if r["corrects_id"]:
        line("تصحيح لوصل",f"#{int(r['corrects_id'])}")
    if data["replacements"]:
        line("الوصل البديل",", ".join("#"+str(v["receipt_id"]) for v in data["replacements"]))
    if r["state"]!="active":
        line("سبب إلغاء / تصحيح الوصل",r["cancel_reason"] or "غير متوفر")
        line("المسؤول",r["cancelled_by"] or "غير مسجل")
        stamp=r["cancelled_at"]
        if stamp is not None:
            line("تاريخ القرار",stamp.astimezone(ZoneInfo("Africa/Nouakchott")).strftime("%Y-%m-%d %H:%M"))
    y-=12
    c.setStrokeColor(colors.HexColor("#C3D7CE"))
    c.line(left,y,right,y)
    y-=31
    _print(c,right,y,"تفصيل توزيع الدفعة الأصلية",size=14)
    y-=29
    for index,item in enumerate(data["items"],1):
        if y<108:
            c.showPage()
            y=h-66
            _print(c,right,y,"تابع تفصيل الوصل",size=14)
            y-=38
        title=receipt_line(item)
        amt=f"{int(item['amount']):,} أوقية قديمة"
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
    _print(c,right,y-15,f"الإجمالي: {int(r['amount']):,} أوقية قديمة",size=13)
    c.setFont(FONT_NAME,9)
    _print(c,right,52,"نسخة من السجل المالي المحفوظ — لا تغيّر المدفوعات أو مديونية الطفل",size=9,color=MUTED)
    c.save()
    return buf.getvalue()
