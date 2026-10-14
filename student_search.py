"""Literal child/parent search, including Arabic digits and formatted phones."""
import re
import unicodedata

FIELDS=('full_name','father_name','mother_name','father_mobile','mother_mobile')
TRANSLATION=str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹أإآٱى','01234567890123456789ااااي')


def normalized(value):
    value=str(value or '').translate(TRANSLATION).casefold()
    value=''.join(c for c in unicodedata.normalize('NFKD',value) if not unicodedata.combining(c))
    return ' '.join(value.split())


def matches(row,term):
    term=normalized(term)
    if not term:
        return True
    phone_query=re.sub(r'[\s()+.\-]','',term)
    for field in FIELDS:
        value=row.get(field,'')
        if value is None or isinstance(value,float):
            value=''
        text=normalized(value)
        if term in text:
            return True
        if field.endswith('_mobile') and phone_query.isdecimal() and phone_query in re.sub(r'\D','',text):
            return True
    return False


def filter_children(frame,term):
    if not normalized(term) or frame.empty:
        return frame
    return frame[frame.apply(lambda row:matches(row,term),axis=1)]
